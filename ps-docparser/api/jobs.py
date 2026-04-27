"""In-memory job manager that wraps the existing CLI subprocess."""

from __future__ import annotations

import re
import json
import os
import shutil
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import config

from .errors import ApiError
from .schemas import (
    BOM_FALLBACK_MODES,
    ENGINES,
    JOB_STATUSES,
    PRESETS,
    JobListItem,
    JobOptions,
    JobStatusResponse,
    JobsListResponse,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UI_RUNS_DIR = PROJECT_ROOT / "output" / "ui_runs"

PDF_SUFFIX = ".pdf"
LOG_TAIL_LINES = 100
JOB_STATUS_FILE = "JOB_STATUS.json"


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


DEFAULT_MAX_UPLOAD_MB = _int_env("UI_MAX_UPLOAD_MB", 200)
DEFAULT_MAX_CONCURRENT_JOBS = _int_env("UI_MAX_CONCURRENT_JOBS", 1)
DEFAULT_MAX_QUEUED_JOBS = _int_env("UI_MAX_QUEUED_JOBS", 10)
PAGE_TOKEN_RE = re.compile(r"^(?P<start>[1-9]\d*)(?:-(?P<end>\d*))?$")


def _now() -> datetime:
    return datetime.now().astimezone()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") if value else None


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def sanitize_filename(filename: str | None) -> str:
    """Return a filesystem-safe PDF filename."""

    raw_name = Path(filename or "uploaded.pdf").name
    stem = Path(raw_name).stem or "uploaded"
    suffix = Path(raw_name).suffix.lower() or PDF_SUFFIX
    safe_stem = re.sub(r"[^0-9A-Za-z가-힣._ -]+", "_", stem).strip(" ._")
    if not safe_stem:
        safe_stem = "uploaded"
    return f"{safe_stem}{suffix}"


def read_log_tail(paths: list[Path], limit: int = LOG_TAIL_LINES) -> list[str]:
    lines: list[str] = []
    for path in paths:
        if not path.exists():
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in content.splitlines():
            lines.append(line)
    return lines[-limit:]


def read_single_log_tail(path: Path, limit: int = LOG_TAIL_LINES) -> list[str]:
    return read_log_tail([path], limit=limit)


def normalize_pages(pages: str | None) -> str | None:
    value = (pages or "").strip()
    if not value:
        return None
    normalized: list[str] = []
    for token in value.split(","):
        part = token.strip()
        match = PAGE_TOKEN_RE.match(part)
        if not match:
            raise ApiError(
                status_code=400,
                code="invalid_pages",
                message="페이지 범위 형식이 올바르지 않습니다.",
                details={"pages": value},
            )
        start = int(match.group("start"))
        end = match.group("end")
        if end and int(end) < start:
            raise ApiError(
                status_code=400,
                code="invalid_pages",
                message="페이지 범위의 끝 페이지는 시작 페이지보다 작을 수 없습니다.",
                details={"pages": value},
            )
        normalized.append(part)
    return ",".join(normalized)


@dataclass
class JobRecord:
    job_id: str
    input_path: Path
    result_dir: Path
    stdout_log: Path
    stderr_log: Path
    preset: str
    engine: str
    pages: str | None
    bom_fallback: str
    no_cache: bool
    status: str
    created_at: datetime
    input_count: int = 1
    started_at: datetime | None = None
    finished_at: datetime | None = None
    exit_code: int | None = None
    cli_exit_code: int | None = None
    analyzer_exit_code: int | None = None
    command: list[str] | None = None
    effective_preset: str | None = None
    effective_engine: str | None = None
    engine_note: str | None = None
    process: subprocess.Popen | None = None
    message: str | None = None

    @property
    def logs(self) -> list[Path]:
        return [self.stdout_log, self.stderr_log]

    @property
    def job_dir(self) -> Path:
        return self.result_dir.parent

    @property
    def status_path(self) -> Path:
        return self.job_dir / JOB_STATUS_FILE


class JobManager:
    """Small local registry for UI-triggered parser jobs."""

    def __init__(
        self,
        *,
        base_output_dir: Path | None = None,
        project_root: Path = PROJECT_ROOT,
        auto_start: bool = True,
        max_upload_mb: int = DEFAULT_MAX_UPLOAD_MB,
        max_concurrent_jobs: int = DEFAULT_MAX_CONCURRENT_JOBS,
        max_queued_jobs: int = DEFAULT_MAX_QUEUED_JOBS,
        enable_open_folder: bool = True,
    ) -> None:
        self.project_root = Path(project_root)
        self.base_output_dir = Path(base_output_dir or DEFAULT_UI_RUNS_DIR)
        self.auto_start = auto_start
        self.max_upload_bytes = max_upload_mb * 1024 * 1024
        self.max_concurrent_jobs = max_concurrent_jobs
        self.max_queued_jobs = max_queued_jobs
        self.enable_open_folder = enable_open_folder
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.RLock()

    def create_job(self, *, filename: str | None, content: bytes, options: JobOptions) -> JobRecord:
        return self._create_job_from_files(files=[(filename, content)], options=options)

    def create_batch_job(self, *, files: list[tuple[str | None, bytes]], options: JobOptions) -> JobRecord:
        if not files:
            raise ApiError(
                status_code=400,
                code="invalid_upload",
                message="업로드할 PDF 파일이 없습니다.",
            )
        return self._create_job_from_files(files=files, options=options)

    def _create_job_from_files(self, *, files: list[tuple[str | None, bytes]], options: JobOptions) -> JobRecord:
        self._validate_options(options)
        safe_files: list[tuple[str, bytes]] = []
        used_names: set[str] = set()
        for filename, content in files:
            if not content:
                raise ApiError(
                    status_code=400,
                    code="invalid_upload",
                    message="빈 PDF 파일은 업로드할 수 없습니다.",
                    details={"filename": filename or ""},
                )
            if len(content) > self.max_upload_bytes:
                raise ApiError(
                    status_code=413,
                    code="upload_too_large",
                    message=f"업로드 파일은 {self.max_upload_bytes // (1024 * 1024)}MB를 초과할 수 없습니다.",
                    details={"filename": filename or "", "size_bytes": len(content)},
                )

            safe_name = sanitize_filename(filename)
            if Path(safe_name).suffix.lower() != PDF_SUFFIX:
                raise ApiError(
                    status_code=400,
                    code="invalid_upload",
                    message="PDF 파일만 업로드할 수 있습니다.",
                    details={"filename": filename or ""},
                )
            safe_name = self._dedupe_filename(safe_name, used_names)
            used_names.add(safe_name)
            safe_files.append((safe_name, content))

        pages = normalize_pages(options.pages)
        self._validate_capacity()

        job_id = self._new_job_id()
        job_dir = self.base_output_dir / job_id
        input_dir = job_dir / "input"
        result_dir = job_dir / "result"
        log_dir = job_dir / "logs"
        input_dir.mkdir(parents=True, exist_ok=True)
        result_dir.mkdir(parents=True, exist_ok=True)
        log_dir.mkdir(parents=True, exist_ok=True)

        for safe_name, content in safe_files:
            (input_dir / safe_name).write_bytes(content)

        input_path = input_dir / safe_files[0][0] if len(safe_files) == 1 else input_dir

        record = JobRecord(
            job_id=job_id,
            input_path=input_path,
            result_dir=result_dir,
            stdout_log=log_dir / "stdout.log",
            stderr_log=log_dir / "stderr.log",
            preset=options.preset,
            engine=options.engine,
            pages=pages,
            bom_fallback=options.bom_fallback,
            no_cache=options.no_cache,
            status="queued",
            created_at=_now(),
            input_count=len(safe_files),
        )

        with self._lock:
            self._jobs[job_id] = record
            self._save_status(record)

        if self.auto_start:
            thread = threading.Thread(target=self._run_job, args=(record,), daemon=True)
            thread.start()
        return record

    def get_job(self, job_id: str) -> JobRecord:
        with self._lock:
            record = self._jobs.get(job_id)
        if record is None:
            record = self._load_job(job_id)
        if record is None:
            raise ApiError(status_code=404, code="job_not_found", message="작업을 찾을 수 없습니다.")
        return record

    def list_jobs(self, *, limit: int = 50) -> JobsListResponse:
        self._load_jobs_from_disk()
        with self._lock:
            records = sorted(
                self._jobs.values(),
                key=lambda item: item.created_at,
                reverse=True,
            )[:limit]
        return JobsListResponse(
            jobs=[
                JobListItem(
                    job_id=record.job_id,
                    status=record.status,  # type: ignore[arg-type]
                    preset=record.preset,
                    engine=record.engine,
                    created_at=_iso(record.created_at) or "",
                    finished_at=_iso(record.finished_at),
                    message=record.message,
                    input_count=record.input_count,
                )
                for record in records
            ]
        )

    def open_job_folder(self, job_id: str) -> tuple[Path, bool]:
        record = self.get_job(job_id)
        folder = record.job_dir.resolve()
        base = self.base_output_dir.resolve()
        try:
            folder.relative_to(base)
        except ValueError as exc:
            raise ApiError(status_code=400, code="unsafe_path", message="허용되지 않는 작업 폴더입니다.") from exc
        if not folder.exists():
            raise ApiError(status_code=404, code="job_folder_not_found", message="작업 폴더를 찾을 수 없습니다.")
        if not self.enable_open_folder:
            return folder, False
        if os.name == "nt" and hasattr(os, "startfile"):
            os.startfile(str(folder))  # type: ignore[attr-defined]
            return folder, True
        return folder, False

    def cancel_job(self, job_id: str) -> JobRecord:
        record = self.get_job(job_id)
        with self._lock:
            if record.status == "queued":
                record.status = "canceled"
                record.finished_at = _now()
                record.message = "사용자 요청으로 작업이 취소되었습니다."
                self._save_status(record)
                return record
            if record.status != "running":
                return record
            process = record.process

        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

        with self._lock:
            record.status = "canceled"
            record.finished_at = _now()
            record.message = "사용자 요청으로 작업이 취소되었습니다."
            self._save_status(record)
        return record

    def to_response(self, record: JobRecord) -> JobStatusResponse:
        self._refresh_effective_fields(record)
        stdout_tail = read_single_log_tail(record.stdout_log)
        stderr_tail = read_single_log_tail(record.stderr_log)
        return JobStatusResponse(
            job_id=record.job_id,
            status=record.status,  # type: ignore[arg-type]
            preset=record.preset,
            engine=record.engine,
            requested_engine=record.engine,
            effective_preset=record.effective_preset,
            effective_engine=record.effective_engine,
            engine_note=record.engine_note,
            created_at=_iso(record.created_at) or "",
            started_at=_iso(record.started_at),
            finished_at=_iso(record.finished_at),
            exit_code=record.exit_code,
            cli_exit_code=record.cli_exit_code,
            analyzer_exit_code=record.analyzer_exit_code,
            message=record.message,
            log_tail=(stdout_tail + stderr_tail)[-LOG_TAIL_LINES:],
            stdout_tail=stdout_tail,
            stderr_tail=stderr_tail,
        )

    def build_cli_command(self, record: JobRecord) -> list[str]:
        command = [
            sys.executable,
            str(self.project_root / "main.py"),
            str(record.input_path),
            "--output-dir",
            str(record.result_dir),
            "--output",
            "excel",
        ]
        if record.engine != "auto":
            command.extend(["--engine", record.engine])
        if record.preset != "auto":
            command.extend(["--preset", record.preset])
        if record.pages:
            command.extend(["--pages", record.pages])
        if record.preset == "bom" or (record.preset == "auto" and record.bom_fallback != "auto"):
            command.extend(["--bom-fallback", record.bom_fallback])
        if record.no_cache:
            command.append("--no-cache")
        return command

    def _run_job(self, record: JobRecord) -> None:
        with self._lock:
            if record.status == "canceled":
                return
            record.status = "running"
            record.started_at = _now()
            record.message = "작업 실행 중"
            self._save_status(record)

        try:
            command = self.build_cli_command(record)
            with self._lock:
                record.command = command
                self._save_status(record)
            with record.stdout_log.open("w", encoding="utf-8") as stdout, record.stderr_log.open("w", encoding="utf-8") as stderr:
                stdout.write("Command: " + " ".join(command) + "\n")
                stdout.flush()
                env = os.environ.copy()
                env["PS_DOCPARSER_JOB_ID"] = record.job_id
                env["PS_DOCPARSER_USAGE_DB"] = str(self.project_root / "output" / "ui_usage" / "usage.db")
                env.setdefault("PYTHONUTF8", "1")
                env.setdefault("PYTHONIOENCODING", "utf-8")
                process = subprocess.Popen(
                    command,
                    cwd=self.project_root,
                    stdout=stdout,
                    stderr=stderr,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=env,
                )
                with self._lock:
                    record.process = process
                exit_code = process.wait()

            with self._lock:
                record.cli_exit_code = exit_code
                record.exit_code = exit_code
                record.process = None
                self._save_status(record)

            if exit_code == 0 and record.status != "canceled":
                analyzer_code = self._run_analyzer(record)
                with self._lock:
                    record.analyzer_exit_code = analyzer_code
                    record.exit_code = analyzer_code
                    self._save_status(record)
                if analyzer_code == 0:
                    self._finish(record, "succeeded", "작업이 완료되었습니다.")
                else:
                    self._finish(record, "failed", f"QA 분석 단계에서 실패했습니다. analyzer_exit_code={analyzer_code}")
            elif record.status != "canceled":
                self._finish(record, "failed", f"CLI 실행이 실패했습니다. cli_exit_code={exit_code}")
        except Exception as exc:
            with self._lock:
                record.exit_code = record.exit_code if record.exit_code is not None else 1
                self._save_status(record)
            self._finish(record, "failed", f"{type(exc).__name__}: {exc}")

    def _run_analyzer(self, record: JobRecord) -> int:
        analyzer = self.project_root / "tools" / "analyze_outputs.py"
        if not analyzer.exists():
            with record.stderr_log.open("a", encoding="utf-8") as stderr:
                stderr.write("\nanalyze_outputs.py를 찾을 수 없습니다.\n")
            return 1
        command = [sys.executable, str(analyzer), str(record.result_dir)]
        with record.stdout_log.open("a", encoding="utf-8") as stdout, record.stderr_log.open("a", encoding="utf-8") as stderr:
            stdout.write("\nAnalyzer: " + " ".join(command) + "\n")
            stdout.flush()
            completed = subprocess.run(
                command,
                cwd=self.project_root,
                stdout=stdout,
                stderr=stderr,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        return completed.returncode

    def _finish(self, record: JobRecord, status: str, message: str) -> None:
        with self._lock:
            if record.status == "canceled":
                return
            record.status = status
            record.finished_at = _now()
            record.message = message
            self._refresh_effective_fields(record)
            self._save_status(record)

    def _validate_capacity(self) -> None:
        with self._lock:
            running = sum(1 for record in self._jobs.values() if record.status == "running")
            queued = sum(1 for record in self._jobs.values() if record.status == "queued")
        if running >= self.max_concurrent_jobs:
            raise ApiError(
                status_code=409,
                code="too_many_running_jobs",
                message="동시에 실행할 수 있는 작업 수를 초과했습니다.",
                details={"max_concurrent_jobs": self.max_concurrent_jobs},
            )
        if queued >= self.max_queued_jobs:
            raise ApiError(
                status_code=409,
                code="queue_full",
                message="대기 중인 작업 수를 초과했습니다.",
                details={"max_queued_jobs": self.max_queued_jobs},
            )

    def _record_to_payload(self, record: JobRecord) -> dict:
        job_dir = record.job_dir

        def rel(path: Path) -> str:
            try:
                return str(path.resolve().relative_to(job_dir.resolve())).replace("\\", "/")
            except ValueError:
                return str(path)

        return {
            "job_id": record.job_id,
            "status": record.status,
            "preset": record.preset,
            "engine": record.engine,
            "requested_engine": record.engine,
            "effective_preset": record.effective_preset,
            "effective_engine": record.effective_engine,
            "engine_note": record.engine_note,
            "pages": record.pages,
            "bom_fallback": record.bom_fallback,
            "no_cache": record.no_cache,
            "input_path": rel(record.input_path),
            "result_dir": rel(record.result_dir),
            "stdout_log": rel(record.stdout_log),
            "stderr_log": rel(record.stderr_log),
            "command": record.command,
            "created_at": _iso(record.created_at),
            "started_at": _iso(record.started_at),
            "finished_at": _iso(record.finished_at),
            "cli_exit_code": record.cli_exit_code,
            "analyzer_exit_code": record.analyzer_exit_code,
            "exit_code": record.exit_code,
            "message": record.message,
            "input_count": record.input_count,
        }

    def _save_status(self, record: JobRecord) -> None:
        record.job_dir.mkdir(parents=True, exist_ok=True)
        record.status_path.write_text(
            json.dumps(self._record_to_payload(record), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _record_from_payload(self, job_dir: Path, payload: dict) -> JobRecord:
        def path_from(key: str, default: str) -> Path:
            value = payload.get(key) or default
            path = Path(value)
            return path if path.is_absolute() else job_dir / path

        status = str(payload.get("status") or "failed")
        message = payload.get("message")
        finished_at = _parse_iso(payload.get("finished_at"))
        if status in {"queued", "running"}:
            status = "failed"
            finished_at = finished_at or _now()
            message = message or "API 재시작으로 실행 상태를 확인할 수 없습니다."

        return JobRecord(
            job_id=str(payload.get("job_id") or job_dir.name),
            input_path=path_from("input_path", "input/uploaded.pdf"),
            result_dir=path_from("result_dir", "result"),
            stdout_log=path_from("stdout_log", "logs/stdout.log"),
            stderr_log=path_from("stderr_log", "logs/stderr.log"),
            preset=str(payload.get("preset") or "auto"),
            engine=str(payload.get("engine") or payload.get("requested_engine") or "auto"),
            pages=payload.get("pages"),
            bom_fallback=str(payload.get("bom_fallback") or "auto"),
            no_cache=bool(payload.get("no_cache")),
            status=status,
            created_at=_parse_iso(payload.get("created_at")) or _now(),
            input_count=int(payload.get("input_count") or 1),
            started_at=_parse_iso(payload.get("started_at")),
            finished_at=finished_at,
            exit_code=payload.get("exit_code"),
            cli_exit_code=payload.get("cli_exit_code"),
            analyzer_exit_code=payload.get("analyzer_exit_code"),
            command=payload.get("command"),
            effective_preset=payload.get("effective_preset"),
            effective_engine=payload.get("effective_engine"),
            engine_note=payload.get("engine_note"),
            message=message,
        )

    def _load_job(self, job_id: str) -> JobRecord | None:
        status_path = self.base_output_dir / job_id / JOB_STATUS_FILE
        if not status_path.exists():
            return None
        try:
            payload = json.loads(status_path.read_text(encoding="utf-8-sig"))
        except Exception:
            return None
        record = self._record_from_payload(status_path.parent, payload)
        with self._lock:
            self._jobs[record.job_id] = record
            self._save_status(record)
        return record

    def _load_jobs_from_disk(self) -> None:
        if not self.base_output_dir.exists():
            return
        for status_path in self.base_output_dir.glob(f"*/{JOB_STATUS_FILE}"):
            with self._lock:
                if status_path.parent.name in self._jobs:
                    continue
            try:
                payload = json.loads(status_path.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
            record = self._record_from_payload(status_path.parent, payload)
            with self._lock:
                self._jobs[record.job_id] = record

    def _refresh_effective_fields(self, record: JobRecord) -> None:
        manifest_path = record.result_dir / "RUN_MANIFEST.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
                first_input = (manifest.get("inputs") or [{}])[0]
                primary = first_input.get("primary") or {}
                domain = primary.get("domain")
                if domain:
                    record.effective_preset = str(domain)
            except Exception:
                pass

        if record.engine == "auto":
            if record.effective_preset == "bom":
                record.effective_engine = config.BOM_DEFAULT_ENGINE
            else:
                record.effective_engine = config.DEFAULT_ENGINE
            record.engine_note = (
                f"engine=auto는 DEFAULT_ENGINE={config.DEFAULT_ENGINE} 기준으로 실행됩니다. "
                f"BOM 특화 경로는 BOM_DEFAULT_ENGINE={config.BOM_DEFAULT_ENGINE}을 사용할 수 있습니다."
            )
        else:
            record.effective_engine = record.engine
            record.engine_note = None

    def _new_job_id(self) -> str:
        self.base_output_dir.mkdir(parents=True, exist_ok=True)
        while True:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            suffix = uuid.uuid4().hex[:8]
            job_id = f"ui_{timestamp}_{suffix}"
            if not (self.base_output_dir / job_id).exists():
                return job_id

    def _validate_options(self, options: JobOptions) -> None:
        errors: dict[str, str] = {}
        if options.preset not in PRESETS:
            errors["preset"] = options.preset
        if options.engine not in ENGINES:
            errors["engine"] = options.engine
        if options.bom_fallback not in BOM_FALLBACK_MODES:
            errors["bom_fallback"] = options.bom_fallback
        if errors:
            raise ApiError(
                status_code=400,
                code="invalid_option",
                message="지원하지 않는 옵션입니다.",
                details=errors,
            )

    @staticmethod
    def _dedupe_filename(filename: str, used_names: set[str]) -> str:
        if filename not in used_names:
            return filename
        path = Path(filename)
        counter = 2
        while True:
            candidate = f"{path.stem}_{counter}{path.suffix}"
            if candidate not in used_names:
                return candidate
            counter += 1

    def clear_job_files(self, job_id: str) -> None:
        record = self.get_job(job_id)
        if record.status == "running":
            raise ApiError(status_code=409, code="job_running", message="실행 중인 작업 파일은 정리할 수 없습니다.")
        shutil.rmtree(record.result_dir.parent, ignore_errors=True)
        with self._lock:
            self._jobs.pop(job_id, None)


default_job_manager = JobManager()
