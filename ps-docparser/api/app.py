"""FastAPI application for the local ps-docparser UI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .artifacts import list_artifacts, parse_qa, preview_artifact, resolve_artifact_path
from .errors import ApiError
from .jobs import JobManager, default_job_manager
from .usage import usage_daily, usage_for_job, usage_summary
from .schemas import (
    BOM_FALLBACK_MODES,
    ENGINES,
    PRESETS,
    ConfigDefaults,
    ConfigResponse,
    CreateJobResponse,
    ErrorResponse,
    FolderOpenResponse,
    JobOptions,
)


def create_app(job_manager: JobManager | None = None) -> FastAPI:
    manager = job_manager or default_job_manager
    app = FastAPI(title="ps-docparser Local API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ApiError)
    async def api_error_handler(_, exc: ApiError) -> JSONResponse:
        payload = ErrorResponse(
            error={
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        )
        return JSONResponse(status_code=exc.status_code, content=payload.model_dump())

    @app.get("/api/config", response_model=ConfigResponse)
    def get_config() -> ConfigResponse:
        return ConfigResponse(
            presets=list(PRESETS),
            engines=list(ENGINES),
            bom_fallback_modes=list(BOM_FALLBACK_MODES),
            defaults=ConfigDefaults(),
        )

    @app.post("/api/jobs", response_model=CreateJobResponse, status_code=201)
    async def create_job(
        file: UploadFile = File(...),
        preset: str = Form("auto"),
        engine: str = Form("auto"),
        pages: str | None = Form(None),
        bom_fallback: str = Form("auto"),
        no_cache: bool = Form(False),
    ) -> CreateJobResponse:
        options = _make_options(
            preset=preset,
            engine=engine,
            pages=pages,
            bom_fallback=bom_fallback,
            no_cache=no_cache,
        )
        content = await file.read()
        record = manager.create_job(filename=file.filename, content=content, options=options)
        return CreateJobResponse(
            job_id=record.job_id,
            status=record.status,  # type: ignore[arg-type]
            status_url=f"/api/jobs/{record.job_id}",
            input_count=record.input_count,
        )

    @app.post("/api/jobs/batch", response_model=CreateJobResponse, status_code=201)
    async def create_batch_job(
        files: list[UploadFile] = File(...),
        preset: str = Form("auto"),
        engine: str = Form("auto"),
        pages: str | None = Form(None),
        bom_fallback: str = Form("auto"),
        no_cache: bool = Form(False),
    ) -> CreateJobResponse:
        options = _make_options(
            preset=preset,
            engine=engine,
            pages=pages,
            bom_fallback=bom_fallback,
            no_cache=no_cache,
        )
        uploads = [(file.filename, await file.read()) for file in files]
        record = manager.create_batch_job(files=uploads, options=options)
        return CreateJobResponse(
            job_id=record.job_id,
            status=record.status,  # type: ignore[arg-type]
            status_url=f"/api/jobs/{record.job_id}",
            input_count=record.input_count,
        )

    @app.get("/api/jobs")
    def list_jobs():
        return manager.list_jobs()

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        return manager.to_response(manager.get_job(job_id))

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str):
        return manager.to_response(manager.cancel_job(job_id))

    @app.post("/api/jobs/{job_id}/open-folder", response_model=FolderOpenResponse)
    def open_folder(job_id: str) -> FolderOpenResponse:
        path, opened = manager.open_job_folder(job_id)
        return FolderOpenResponse(
            job_id=job_id,
            path=str(path),
            opened=opened,
            message="작업 폴더를 열었습니다." if opened else "작업 폴더 경로를 확인했습니다.",
        )

    @app.get("/api/jobs/{job_id}/artifacts")
    def get_artifacts(job_id: str):
        return list_artifacts(manager.get_job(job_id))

    @app.get("/api/jobs/{job_id}/artifacts/{artifact_id}/preview")
    def get_artifact_preview(job_id: str, artifact_id: str):
        return preview_artifact(manager.get_job(job_id), artifact_id)

    @app.get("/api/jobs/{job_id}/artifacts/{artifact_id}")
    def download_artifact(job_id: str, artifact_id: str):
        path = resolve_artifact_path(manager.get_job(job_id), artifact_id)
        return FileResponse(path, filename=Path(path).name, media_type=_media_type(path))

    @app.get("/api/jobs/{job_id}/qa")
    def get_qa(job_id: str):
        return parse_qa(manager.get_job(job_id))

    @app.get("/api/usage/summary")
    def get_usage_summary(range: str = "all"):
        return usage_summary(manager.project_root, range_name=range)

    @app.get("/api/usage/daily")
    def get_usage_daily(month: str | None = None):
        return usage_daily(manager.project_root, month=month)

    @app.get("/api/usage/jobs/{job_id}")
    def get_usage_for_job(job_id: str):
        return usage_for_job(manager.project_root, job_id)

    return app


def _make_options(
    *,
    preset: str,
    engine: str,
    pages: str | None,
    bom_fallback: str,
    no_cache: bool,
) -> JobOptions:
    try:
        return JobOptions(
            preset=preset,
            engine=engine,
            pages=pages.strip() if pages and pages.strip() else None,
            bom_fallback=bom_fallback,
            no_cache=no_cache,
        )
    except Exception as exc:
        raise ApiError(
            status_code=400,
            code="invalid_option",
            message="지원하지 않는 옵션입니다.",
            details={"preset": preset, "engine": engine, "bom_fallback": bom_fallback},
        ) from exc


def _media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "application/json"
    if suffix == ".xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return "text/markdown; charset=utf-8"


app = create_app()
