"""Pydantic models for the Phase15 local API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


Preset = Literal["auto", "generic", "bom", "estimate", "pumsem"]
Engine = Literal["auto", "zai", "gemini", "local", "mistral", "tesseract"]
BomFallback = Literal["auto", "always", "never"]
JobStatus = Literal["queued", "running", "succeeded", "failed", "canceled"]

PRESETS: tuple[str, ...] = ("auto", "generic", "bom", "estimate", "pumsem")
ENGINES: tuple[str, ...] = ("auto", "zai", "gemini", "local", "mistral", "tesseract")
BOM_FALLBACK_MODES: tuple[str, ...] = ("auto", "always", "never")
JOB_STATUSES: tuple[str, ...] = ("queued", "running", "succeeded", "failed", "canceled")


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail


class ConfigDefaults(BaseModel):
    preset: Preset = "auto"
    engine: Engine = "auto"
    output_format: str = "excel"
    bom_fallback: BomFallback = "auto"


class ConfigResponse(BaseModel):
    presets: list[str]
    engines: list[str]
    bom_fallback_modes: list[str]
    defaults: ConfigDefaults


class JobOptions(BaseModel):
    preset: Preset = "auto"
    engine: Engine = "auto"
    pages: str | None = None
    bom_fallback: BomFallback = "auto"
    no_cache: bool = False


class CreateJobResponse(BaseModel):
    job_id: str
    status: JobStatus
    status_url: str
    input_count: int = 1


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    preset: str
    engine: str
    requested_engine: str
    effective_preset: str | None = None
    effective_engine: str | None = None
    engine_note: str | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    exit_code: int | None = None
    cli_exit_code: int | None = None
    analyzer_exit_code: int | None = None
    message: str | None = None
    log_tail: list[str] = Field(default_factory=list)
    stdout_tail: list[str] = Field(default_factory=list)
    stderr_tail: list[str] = Field(default_factory=list)


class JobListItem(BaseModel):
    job_id: str
    status: JobStatus
    preset: str
    engine: str
    created_at: str
    finished_at: str | None = None
    message: str | None = None
    input_count: int = 1


class JobsListResponse(BaseModel):
    jobs: list[JobListItem]


class ArtifactItem(BaseModel):
    artifact_id: str
    name: str
    relative_path: str
    kind: Literal["md", "json", "xlsx", "manifest", "summary", "qa", "other"]
    size_bytes: int
    download_url: str
    role: str = "unknown"
    domain: str = "unknown"
    quality_status: str = "unknown"


class ArtifactsResponse(BaseModel):
    job_id: str
    artifacts: list[ArtifactItem]
    message: str | None = None


class FolderOpenResponse(BaseModel):
    job_id: str
    path: str
    opened: bool
    message: str


class ArtifactPreviewResponse(BaseModel):
    job_id: str
    artifact_id: str
    name: str
    kind: Literal["md", "json", "xlsx", "manifest", "summary", "qa", "other"]
    text: str | None = None
    json_data: Any | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    truncated: bool = False
    message: str | None = None


class QAResponse(BaseModel):
    job_id: str
    status: Literal["ok", "warn", "fail", "unknown"]
    json_files: int = 0
    excel_files: int = 0
    has_manifest: bool = False
    manifest_inputs: int = 0
    manifest_representative: int = 0
    manifest_diagnostic: int = 0
    header_key_mismatch: int = 0
    bad_composite_headers: int = 0
    quality_warnings: dict[str, int] = Field(default_factory=dict)
    manifest_domains: dict[str, int] = Field(default_factory=dict)
    report_path: str | None = None
    summary_markdown: str | None = None


class UsageTotals(BaseModel):
    call_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    unknown_token_calls: int = 0


class UsageByEngine(BaseModel):
    engine: str
    provider: str
    call_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    unknown_token_calls: int = 0


class UsageSummaryResponse(BaseModel):
    range: str
    totals: UsageTotals
    by_engine: list[UsageByEngine] = Field(default_factory=list)


class UsageDailyItem(BaseModel):
    date: str
    call_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


class UsageDailyResponse(BaseModel):
    month: str
    days: list[UsageDailyItem] = Field(default_factory=list)


class UsageEventItem(BaseModel):
    timestamp: str
    job_id: str | None = None
    engine: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    status: str = "ok"
    token_status: str = "known"


class UsageJobResponse(BaseModel):
    job_id: str
    totals: UsageTotals
    events: list[UsageEventItem] = Field(default_factory=list)
