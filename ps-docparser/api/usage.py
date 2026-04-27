"""Usage dashboard readers for the local UI API."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from utils.usage_store import UsageStore, default_usage_db

from .schemas import (
    UsageByEngine,
    UsageDailyItem,
    UsageDailyResponse,
    UsageEventItem,
    UsageJobResponse,
    UsageSummaryResponse,
    UsageTotals,
)


def _store(project_root: Path) -> UsageStore:
    return UsageStore(default_usage_db(project_root))


def usage_summary(project_root: Path, range_name: str = "all") -> UsageSummaryResponse:
    range_value = range_name if range_name in {"today", "month", "all"} else "all"
    summary = _store(project_root).summary(range_value)
    return UsageSummaryResponse(
        range=range_value,
        totals=UsageTotals(**summary["totals"]),
        by_engine=[UsageByEngine(**item) for item in summary["by_engine"]],
    )


def usage_daily(project_root: Path, month: str | None = None) -> UsageDailyResponse:
    month_value = month or datetime.now().astimezone().strftime("%Y-%m")
    days = _store(project_root).daily(month_value)
    return UsageDailyResponse(
        month=month_value,
        days=[UsageDailyItem(**item) for item in days],
    )


def usage_for_job(project_root: Path, job_id: str) -> UsageJobResponse:
    events = _store(project_root).job_events(job_id)
    total_input = sum(int(item["input_tokens"]) for item in events)
    total_output = sum(int(item["output_tokens"]) for item in events)
    total_cost = sum(float(item["estimated_cost_usd"]) for item in events)
    unknown = sum(1 for item in events if item["token_status"] == "unknown")
    return UsageJobResponse(
        job_id=job_id,
        totals=UsageTotals(
            call_count=len(events),
            input_tokens=total_input,
            output_tokens=total_output,
            total_tokens=total_input + total_output,
            estimated_cost_usd=total_cost,
            unknown_token_calls=unknown,
        ),
        events=[UsageEventItem(**item) for item in events],
    )
