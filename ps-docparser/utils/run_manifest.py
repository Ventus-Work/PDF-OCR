"""Run manifest helpers for representative/diagnostic output tracking."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _rel(path: str | Path | None, base: Path) -> str | None:
    if path is None:
        return None
    p = Path(path)
    try:
        return str(p.resolve().relative_to(base.resolve()))
    except Exception:
        return str(p)


def _load_manifest(path: Path, output_dir: Path) -> dict[str, Any]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            pass
    return {
        "run_id": output_dir.name,
        "created_at": _now_iso(),
        "inputs": [],
    }


def quality_status_from_sections(sections: list[dict[str, Any]]) -> str:
    statuses: list[str] = []
    for section in sections:
        quality = section.get("quality")
        if isinstance(quality, dict) and quality.get("status"):
            statuses.append(str(quality["status"]))
        for table in section.get("tables", []):
            table_quality = table.get("quality")
            if isinstance(table_quality, dict) and table_quality.get("status"):
                statuses.append(str(table_quality["status"]))
    if "fail" in statuses:
        return "fail"
    if "warning" in statuses:
        return "warning"
    return "ok"


def make_artifact(
    *,
    output_dir: Path,
    role: str,
    domain: str,
    json_path: str | Path | None = None,
    xlsx_path: str | Path | None = None,
    md_path: str | Path | None = None,
    quality_status: str = "ok",
    kind: str = "output",
) -> dict[str, Any]:
    return {
        "kind": kind,
        "role": role,
        "domain": domain,
        "md": _rel(md_path, output_dir),
        "json": _rel(json_path, output_dir),
        "xlsx": _rel(xlsx_path, output_dir),
        "quality_status": quality_status,
    }


def record_manifest_entry(output_dir: Path, entry: dict[str, Any]) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "RUN_MANIFEST.json"
    manifest = _load_manifest(manifest_path, output_dir)
    manifest["updated_at"] = _now_iso()
    manifest.setdefault("inputs", []).append(entry)

    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )
    write_run_summary(output_dir, manifest)
    return manifest_path


def write_run_summary(output_dir: Path, manifest: dict[str, Any] | None = None) -> Path:
    output_dir = Path(output_dir)
    if manifest is None:
        manifest = _load_manifest(output_dir / "RUN_MANIFEST.json", output_dir)

    lines = [
        "# 실행 결과 요약",
        "",
        f"- Run ID: `{manifest.get('run_id', output_dir.name)}`",
        f"- Created: `{manifest.get('created_at', '')}`",
        f"- Updated: `{manifest.get('updated_at', '')}`",
        "",
        "## 1급 산출물",
        "",
        "| source | domain | quality | json | excel |",
        "|---|---|---|---|---|",
    ]

    diagnostics: list[tuple[str, dict[str, Any]]] = []
    for entry in manifest.get("inputs", []):
        source = entry.get("source_pdf", "")
        primary = entry.get("primary") or {}
        lines.append(
            "| {source} | {domain} | {quality} | {json} | {xlsx} |".format(
                source=source,
                domain=primary.get("domain", ""),
                quality=primary.get("quality_status", ""),
                json=primary.get("json", ""),
                xlsx=primary.get("xlsx", ""),
            )
        )
        for diagnostic in entry.get("diagnostics", []) or []:
            if diagnostic.get("role") == "representative":
                lines.append(
                    "| {source} | {domain} | {quality} | {json} | {xlsx} |".format(
                        source=source,
                        domain=diagnostic.get("domain", ""),
                        quality=diagnostic.get("quality_status", ""),
                        json=diagnostic.get("json", ""),
                        xlsx=diagnostic.get("xlsx", ""),
                    )
                )
            else:
                diagnostics.append((source, diagnostic))

    lines.extend(["", "## 보조/진단 산출물", "", "| source | role | domain | quality | json | excel |", "|---|---|---|---|---|---|"])
    for source, diagnostic in diagnostics:
        lines.append(
            "| {source} | {role} | {domain} | {quality} | {json} | {xlsx} |".format(
                source=source,
                role=diagnostic.get("role", ""),
                domain=diagnostic.get("domain", ""),
                quality=diagnostic.get("quality_status", ""),
                json=diagnostic.get("json", ""),
                xlsx=diagnostic.get("xlsx", ""),
            )
        )

    summary_path = output_dir / "RUN_SUMMARY.md"
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    return summary_path


def representative_bom_jsons_from_manifest(output_dir: Path) -> list[Path]:
    output_dir = Path(output_dir)
    manifest_path = output_dir / "RUN_MANIFEST.json"
    if not manifest_path.exists():
        return []
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    json_paths: list[Path] = []
    for entry in manifest.get("inputs", []):
        primary = entry.get("primary") or {}
        if primary.get("role") != "representative":
            continue
        if primary.get("domain") != "bom":
            continue
        if primary.get("quality_status") not in {"ok", "warning"}:
            continue
        rel_json = primary.get("json")
        if rel_json:
            json_path = output_dir / rel_json
            if json_path.exists():
                json_paths.append(json_path)
    return json_paths
