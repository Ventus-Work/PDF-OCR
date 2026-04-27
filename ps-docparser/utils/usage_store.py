"""SQLite-backed local usage ledger for UI-triggered parser runs."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    job_id TEXT,
    engine TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    estimated_cost_usd REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'ok',
    token_status TEXT NOT NULL DEFAULT 'known'
);
CREATE INDEX IF NOT EXISTS idx_usage_events_timestamp ON usage_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_usage_events_job_id ON usage_events(job_id);
"""


def default_usage_db(project_root: Path) -> Path:
    return Path(project_root) / "output" / "ui_usage" / "usage.db"


class UsageStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def record_event(
        self,
        *,
        job_id: str | None,
        engine: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        estimated_cost_usd: float,
        status: str = "ok",
        token_status: str = "known",
    ) -> None:
        total_tokens = input_tokens + output_tokens
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO usage_events (
                    timestamp, job_id, engine, provider, model,
                    input_tokens, output_tokens, total_tokens,
                    estimated_cost_usd, status, token_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    job_id,
                    engine,
                    provider,
                    model,
                    input_tokens,
                    output_tokens,
                    total_tokens,
                    estimated_cost_usd,
                    status,
                    token_status,
                ),
            )

    def summary(self, range_name: str = "all") -> dict[str, Any]:
        where, params = self._range_where(range_name)
        with self._connect() as conn:
            totals = self._fetch_one(
                conn,
                f"""
                SELECT
                    COUNT(*) AS call_count,
                    COALESCE(SUM(input_tokens), 0) AS input_tokens,
                    COALESCE(SUM(output_tokens), 0) AS output_tokens,
                    COALESCE(SUM(total_tokens), 0) AS total_tokens,
                    COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd,
                    COALESCE(SUM(CASE WHEN token_status = 'unknown' THEN 1 ELSE 0 END), 0) AS unknown_token_calls
                FROM usage_events
                {where}
                """,
                params,
            )
            by_engine = [
                dict(row)
                for row in conn.execute(
                    f"""
                    SELECT
                        engine,
                        provider,
                        COUNT(*) AS call_count,
                        COALESCE(SUM(input_tokens), 0) AS input_tokens,
                        COALESCE(SUM(output_tokens), 0) AS output_tokens,
                        COALESCE(SUM(total_tokens), 0) AS total_tokens,
                        COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd,
                        COALESCE(SUM(CASE WHEN token_status = 'unknown' THEN 1 ELSE 0 END), 0) AS unknown_token_calls
                    FROM usage_events
                    {where}
                    GROUP BY engine, provider
                    ORDER BY call_count DESC, engine ASC
                    """,
                    params,
                )
            ]
        return {"totals": totals, "by_engine": by_engine}

    def daily(self, month: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT
                        substr(timestamp, 1, 10) AS date,
                        COUNT(*) AS call_count,
                        COALESCE(SUM(input_tokens), 0) AS input_tokens,
                        COALESCE(SUM(output_tokens), 0) AS output_tokens,
                        COALESCE(SUM(total_tokens), 0) AS total_tokens,
                        COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd
                    FROM usage_events
                    WHERE substr(timestamp, 1, 7) = ?
                    GROUP BY substr(timestamp, 1, 10)
                    ORDER BY date ASC
                    """,
                    (month,),
                )
            ]

    def job_events(self, job_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT
                        timestamp, job_id, engine, provider, model,
                        input_tokens, output_tokens, total_tokens,
                        estimated_cost_usd, status, token_status
                    FROM usage_events
                    WHERE job_id = ?
                    ORDER BY timestamp ASC, id ASC
                    """,
                    (job_id,),
                )
            ]

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA)
        return conn

    @staticmethod
    def _fetch_one(conn: sqlite3.Connection, query: str, params: tuple[Any, ...]) -> dict[str, Any]:
        row = conn.execute(query, params).fetchone()
        return dict(row) if row else {}

    @staticmethod
    def _range_where(range_name: str) -> tuple[str, tuple[str, ...]]:
        today = datetime.now().astimezone().strftime("%Y-%m-%d")
        month = datetime.now().astimezone().strftime("%Y-%m")
        if range_name == "today":
            return "WHERE substr(timestamp, 1, 10) = ?", (today,)
        if range_name == "month":
            return "WHERE substr(timestamp, 1, 7) = ?", (month,)
        return "", ()
