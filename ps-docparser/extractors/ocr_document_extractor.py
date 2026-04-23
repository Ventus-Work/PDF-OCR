"""OCR-backed document extractor for the generic document pipeline."""

from __future__ import annotations

import html
import logging
import re
from pathlib import Path

from engines.base_engine import BaseEngine, OcrPageResult
from utils.markers import (
    build_context_marker,
    build_page_marker,
    build_section_markers,
    process_toc_context,
)
from utils.text_formatter import format_text_with_linebreaks

logger = logging.getLogger(__name__)

_HTML_TABLE_RE = re.compile(r"<table\b.*?</table>", re.IGNORECASE | re.DOTALL)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*]\([^)]*\)")
_PIPE_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_PIPE_TABLE_SEPARATOR_RE = re.compile(
    r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*$"
)


def _normalize_division_names(division_names):
    if isinstance(division_names, (list, tuple, set)):
        return "|".join(str(item) for item in division_names)
    return division_names


def _flatten_layout_details(layout_details: list) -> list[dict]:
    flat: list[dict] = []
    for item in layout_details or []:
        if isinstance(item, list):
            flat.extend(_flatten_layout_details(item))
        elif isinstance(item, dict):
            flat.append(item)
    return flat


def _layout_sort_key(block: dict) -> tuple[float, float]:
    bbox = block.get("bbox_2d") or block.get("bbox")
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
        try:
            return (float(bbox[1]), float(bbox[0]))
        except (TypeError, ValueError):
            return (0.0, 0.0)
    return (0.0, 0.0)


def _extract_block_text(block: dict) -> str:
    for key in ("html", "content", "markdown", "md", "text", "value"):
        value = block.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _split_markdown_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _render_markdown_table(block_lines: list[str]) -> str:
    header = _split_markdown_row(block_lines[0])
    body_rows = [_split_markdown_row(line) for line in block_lines[2:]]

    parts = ["<table>", "<thead>", "<tr>"]
    for cell in header:
        parts.append(f"<th>{html.escape(cell)}</th>")
    parts.extend(["</tr>", "</thead>"])

    if body_rows:
        parts.append("<tbody>")
        for row in body_rows:
            parts.append("<tr>")
            padded = row + [""] * max(0, len(header) - len(row))
            for cell in padded[: len(header)]:
                parts.append(f"<td>{html.escape(cell)}</td>")
            parts.append("</tr>")
        parts.append("</tbody>")

    parts.append("</table>")
    return "\n".join(parts)


def convert_markdown_tables_to_html(text: str) -> str:
    if not text or "|" not in text:
        return text

    lines = text.splitlines()
    converted: list[str] = []
    idx = 0

    while idx < len(lines):
        if (
            idx + 1 < len(lines)
            and _PIPE_TABLE_ROW_RE.match(lines[idx] or "")
            and _PIPE_TABLE_SEPARATOR_RE.match(lines[idx + 1] or "")
        ):
            block = [lines[idx], lines[idx + 1]]
            idx += 2
            while idx < len(lines) and _PIPE_TABLE_ROW_RE.match(lines[idx] or ""):
                block.append(lines[idx])
                idx += 1
            converted.append(_render_markdown_table(block))
            continue

        converted.append(lines[idx])
        idx += 1

    return "\n".join(converted)


def _strip_markup_for_context(text: str) -> str:
    if not text:
        return ""

    without_tables = _HTML_TABLE_RE.sub("\n", text)
    without_images = _MARKDOWN_IMAGE_RE.sub(" ", without_tables)

    lines = without_images.splitlines()
    filtered: list[str] = []
    idx = 0
    while idx < len(lines):
        if (
            idx + 1 < len(lines)
            and _PIPE_TABLE_ROW_RE.match(lines[idx] or "")
            and _PIPE_TABLE_SEPARATOR_RE.match(lines[idx + 1] or "")
        ):
            idx += 2
            while idx < len(lines) and _PIPE_TABLE_ROW_RE.match(lines[idx] or ""):
                idx += 1
            continue
        filtered.append(lines[idx])
        idx += 1

    plain = _HTML_TAG_RE.sub(" ", "\n".join(filtered))
    plain = plain.replace("|", " ")
    plain = re.sub(r"[ \t]+", " ", plain)
    plain = re.sub(r"\n{3,}", "\n\n", plain)
    return plain.strip()


def _normalize_text_block(text: str, division_names=None) -> str:
    plain = _strip_markup_for_context(text)
    if not plain:
        return ""
    return format_text_with_linebreaks(
        plain,
        division_names=_normalize_division_names(division_names),
    ).strip()


def _normalize_layout_page(
    result: OcrPageResult,
    division_names=None,
) -> tuple[str, str]:
    elements: list[str] = []
    context_parts: list[str] = []

    flat = _flatten_layout_details(result.layout_details)
    for block in sorted(flat, key=_layout_sort_key):
        raw = _extract_block_text(block)
        if not raw:
            continue

        label = str(block.get("label", "")).lower()
        if label == "table":
            table_html = convert_markdown_tables_to_html(raw).strip()
            if table_html:
                elements.append(table_html)
            continue

        normalized = _normalize_text_block(raw, division_names=division_names)
        context_text = _strip_markup_for_context(raw)
        if context_text:
            context_parts.append(context_text)
        if normalized:
            elements.append(normalized)

    return "\n\n".join(elements).strip(), "\n".join(context_parts).strip()


def _normalize_raw_page(
    result: OcrPageResult,
    engine_name: str,
    division_names=None,
) -> tuple[str, str]:
    raw = (result.text or "").strip()
    if not raw:
        return "", ""

    normalized = convert_markdown_tables_to_html(raw)
    context_text = _strip_markup_for_context(raw)

    if engine_name == "tesseract":
        return (
            format_text_with_linebreaks(
                context_text or raw,
                division_names=_normalize_division_names(division_names),
            ).strip(),
            context_text,
        )

    if "<table" in normalized.lower():
        return normalized.strip(), context_text

    return (
        format_text_with_linebreaks(
            context_text or normalized,
            division_names=_normalize_division_names(division_names),
        ).strip(),
        context_text,
    )


def _normalize_page_content(
    result: OcrPageResult,
    engine_name: str,
    division_names=None,
) -> tuple[str, str]:
    if result.layout_details:
        page_content, context_text = _normalize_layout_page(
            result,
            division_names=division_names,
        )
        if page_content:
            return page_content, context_text

    return _normalize_raw_page(
        result,
        engine_name=engine_name,
        division_names=division_names,
    )


def process_pdf_ocr_document(
    pdf_path: str,
    engine: BaseEngine,
    section_map: dict = None,
    page_indices: list[int] | None = None,
    toc_parser_module=None,
    preset: str = None,
    division_names=None,
) -> str:
    """Extract a PDF via OCR engines and emit markdown/HTML for downstream parsing."""
    logger.info("document OCR extraction started: %s (%s)", pdf_path, type(engine).__name__)

    page_map = {}
    if section_map and toc_parser_module:
        page_map = toc_parser_module.build_page_to_sections_map(section_map)

    current_context = {"chapter": "", "section": "", "sections": []}
    markdown_output: list[str] = []

    results = engine.ocr_document(Path(pdf_path), page_indices=page_indices)
    engine_name = type(engine).__name__.replace("Engine", "").lower()

    for index, result in enumerate(results, start=1):
        page_num = result.page_num + 1 if isinstance(result.page_num, int) else index
        page_content, context_text = _normalize_page_content(
            result,
            engine_name=engine_name,
            division_names=division_names,
        )

        if section_map and toc_parser_module:
            current_context, page_sections, pdf_page_num = process_toc_context(
                full_text=context_text,
                page_map=page_map,
                current_context=current_context,
                toc_parser_module=toc_parser_module,
                preset=preset,
                division_names=division_names,
            )
        else:
            page_sections = []
            pdf_page_num = 0

        markdown_output.append(build_page_marker(page_num, current_context))

        if page_sections:
            markdown_output.append(build_section_markers(page_sections))
        elif section_map and toc_parser_module and pdf_page_num > 0:
            active_section = toc_parser_module.get_active_section(pdf_page_num, section_map)
            if active_section:
                markdown_output.append(build_context_marker(active_section))

        if page_content:
            markdown_output.append(page_content.strip())
            markdown_output.append("\n\n")

    return "".join(markdown_output)
