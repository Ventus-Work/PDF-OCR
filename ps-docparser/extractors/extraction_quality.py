"""Quality checks for deciding document extraction fallback."""

from __future__ import annotations

from dataclasses import dataclass
import re

import config
from detector import detect_document_type, detect_material_quote

_MARKER_RE = re.compile(r"<!--\s*(?:PAGE|SECTION|CONTEXT).*?-->", re.IGNORECASE | re.DOTALL)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_PIPE_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_PIPE_TABLE_SEPARATOR_RE = re.compile(
    r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*$"
)


@dataclass(slots=True)
class DocumentExtractionMetrics:
    visible_chars: int
    page_count: int
    html_table_count: int
    markdown_table_blocks: int
    material_quote_detected: bool
    document_type_detected: str | None
    score: int
    weak_reason: str
    too_weak: bool = False


def _count_markdown_table_blocks(text: str) -> int:
    lines = text.splitlines()
    count = 0
    idx = 0

    while idx < len(lines):
        if (
            idx + 1 < len(lines)
            and _PIPE_TABLE_ROW_RE.match(lines[idx] or "")
            and _PIPE_TABLE_SEPARATOR_RE.match(lines[idx + 1] or "")
        ):
            count += 1
            idx += 2
            while idx < len(lines) and _PIPE_TABLE_ROW_RE.match(lines[idx] or ""):
                idx += 1
            continue
        idx += 1

    return count


def _plain_text_from_md(md_text: str) -> str:
    text = _MARKER_RE.sub(" ", md_text or "")
    text = re.sub(r"!\[[^\]]*]\([^)]*\)", " ", text)
    text = _HTML_TAG_RE.sub(" ", text)
    text = text.replace("|", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def evaluate_document_extraction(
    md_text: str,
    expected_pages: int | None = None,
) -> DocumentExtractionMetrics:
    plain_text = _plain_text_from_md(md_text)
    visible_chars = len(re.sub(r"\s+", "", plain_text))
    page_markers = len(re.findall(r"<!--\s*PAGE\b", md_text or "", flags=re.IGNORECASE))
    page_count = expected_pages or page_markers or 1
    html_table_count = (md_text or "").lower().count("<table")
    markdown_table_blocks = _count_markdown_table_blocks(md_text or "")
    material_quote_detected = detect_material_quote(plain_text)
    document_type_detected = detect_document_type(plain_text)
    score = visible_chars + (600 * html_table_count) + (250 * markdown_table_blocks)

    reasons: list[str] = []
    if visible_chars < config.DOCUMENT_MIN_VISIBLE_CHARS:
        reasons.append(f"visible_chars<{config.DOCUMENT_MIN_VISIBLE_CHARS}")
    if visible_chars / max(page_count, 1) < config.DOCUMENT_MIN_VISIBLE_CHARS_PER_PAGE:
        reasons.append(
            f"visible_chars_per_page<{config.DOCUMENT_MIN_VISIBLE_CHARS_PER_PAGE}"
        )
    if material_quote_detected and html_table_count == 0 and markdown_table_blocks == 0:
        reasons.append("material_quote_without_table_signal")
    if (
        document_type_detected in {"estimate", "pumsem"}
        and visible_chars < config.DOCUMENT_MIN_STRUCTURED_CHARS
        and html_table_count == 0
        and markdown_table_blocks == 0
    ):
        reasons.append(
            f"{document_type_detected}_document_without_structure"
        )

    return DocumentExtractionMetrics(
        visible_chars=visible_chars,
        page_count=page_count,
        html_table_count=html_table_count,
        markdown_table_blocks=markdown_table_blocks,
        material_quote_detected=material_quote_detected,
        document_type_detected=document_type_detected,
        score=score,
        weak_reason=", ".join(reasons),
        too_weak=bool(reasons),
    )
