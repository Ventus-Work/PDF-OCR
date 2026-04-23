"""
Utilities for table detection, bbox repair, and cropping.
"""

from __future__ import annotations

import logging

from PIL import Image

from config import TABLE_BOTTOM_EXTRA_PADDING, TABLE_MIN_HEIGHT_RATIO

logger = logging.getLogger(__name__)

VERTEX_MERGE_FACTOR = 4
MIN_COORD_MERGE_TOL = 8
DEFAULT_SNAP_TOLERANCE = 3


def validate_and_fix_table_bboxes(
    table_bboxes: list[tuple],
    page_height: float,
    page_width: float,
) -> tuple[list[tuple], bool]:
    if not table_bboxes:
        return table_bboxes, False

    fixed_bboxes: list[tuple] = []
    needs_fullpage_fallback = False

    for idx, bbox in enumerate(table_bboxes):
        x0, y0, x1, y1 = bbox
        table_height = y1 - y0
        height_ratio = table_height / page_height

        if height_ratio < TABLE_MIN_HEIGHT_RATIO:
            logger.info(
                "table %s bbox is too short (%.1f%%, %.0fpt / %.0fpt)",
                idx + 1,
                height_ratio * 100,
                table_height,
                page_height,
            )

            if idx + 1 < len(table_bboxes):
                new_y1 = table_bboxes[idx + 1][1] - 5
            else:
                new_y1 = min(page_height * 0.85, page_height - 30)

            new_height = new_y1 - y0
            new_ratio = new_height / page_height
            if new_ratio > 0.5:
                needs_fullpage_fallback = True
                break

            fixed_bboxes.append((x0, y0, x1, new_y1))
        else:
            fixed_bboxes.append(bbox)

    return fixed_bboxes, needs_fullpage_fallback


def crop_table_image(
    page_image: Image.Image,
    bbox: tuple,
    page_height: float,
    page_width: float,
    extended: bool = False,
) -> Image.Image:
    x0, y0, x1, y1 = bbox

    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))

    scale_x = page_image.width / page_width
    scale_y = page_image.height / page_height

    img_x0 = int(x0 * scale_x)
    img_y0 = int(y0 * scale_y)
    img_x1 = int(x1 * scale_x)
    img_y1 = int(y1 * scale_y)

    padding_x = 10
    padding_top = 10
    padding_bottom = int(TABLE_BOTTOM_EXTRA_PADDING * scale_y) if extended else 10

    img_x0 = max(0, img_x0 - padding_x)
    img_y0 = max(0, img_y0 - padding_top)
    img_x1 = min(page_image.width, img_x1 + padding_x)
    img_y1 = min(page_image.height, img_y1 + padding_bottom)

    if img_x1 <= img_x0:
        img_x1 = min(page_image.width, img_x0 + 1)
    if img_y1 <= img_y0:
        img_y1 = min(page_image.height, img_y0 + 1)

    return page_image.crop((img_x0, img_y0, img_x1, img_y1))


def calculate_dynamic_tolerance(page) -> dict[str, float]:
    lines = page.lines or []
    if not lines:
        return {
            "snap_tolerance": DEFAULT_SNAP_TOLERANCE,
            "join_tolerance": DEFAULT_SNAP_TOLERANCE,
            "intersection_tolerance": DEFAULT_SNAP_TOLERANCE,
        }

    h_widths: list[float] = []
    v_widths: list[float] = []
    for line in lines:
        line_width = line.get("lineWidth", line.get("stroke_width", 1))
        if line_width is None:
            line_width = 1
        if abs(line.get("y0", 0) - line.get("y1", 0)) < 2:
            h_widths.append(line_width)
        else:
            v_widths.append(line_width)

    max_h = max(h_widths) if h_widths else 1
    max_v = max(v_widths) if v_widths else 1

    vertex_radius = max(max_h, max_v) * VERTEX_MERGE_FACTOR
    coord_merge_tol = max(MIN_COORD_MERGE_TOL, vertex_radius)
    return {
        "snap_tolerance": coord_merge_tol / 2,
        "join_tolerance": coord_merge_tol,
        "intersection_tolerance": coord_merge_tol,
    }


def _group_words_by_row(words: list[dict], y_tol: float = 3.0) -> list[list[dict]]:
    if not words:
        return []

    sorted_words = sorted(words, key=lambda word: (word["top"], word["x0"]))
    if not sorted_words:
        return []

    rows = []
    current_row = [sorted_words[0]]
    for word in sorted_words[1:]:
        if abs(word["top"] - current_row[0]["top"]) <= y_tol:
            current_row.append(word)
        else:
            rows.append(current_row)
            current_row = [word]
    rows.append(current_row)
    return rows


def _bbox_from_rows(rows: list[list[dict]]) -> tuple | None:
    words = [word for row in rows for word in row]
    if not words:
        return None
    return (
        min(word["x0"] for word in words),
        min(word["top"] for word in words),
        max(word["x1"] for word in words),
        max(word["bottom"] for word in words),
    )


def _find_keyword_condition_tables(rows: list[list[dict]]) -> list[dict]:
    general_kw = "\uc77c\ubc18\uc0ac\ud56d"
    special_kw = "\ud2b9\uae30\uc0ac\ud56d"
    max_row_gap = 26

    tables = []
    for idx, row in enumerate(rows):
        row_text = "".join(word["text"] for word in row).replace(" ", "")
        if general_kw not in row_text or special_kw not in row_text:
            continue

        table_rows = [row]
        for next_idx in range(idx + 1, len(rows)):
            gap = rows[next_idx][0]["top"] - rows[next_idx - 1][0]["top"]
            if gap > max_row_gap and len(table_rows) >= 2:
                break
            table_rows.append(rows[next_idx])
            if len(table_rows) >= 6:
                break

        bbox = _bbox_from_rows(table_rows)
        if bbox is not None:
            tables.append({"bbox": bbox, "rows": []})
    return tables


def _bbox_overlap_ratio(a: tuple, b: tuple) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b

    inter_x0 = max(ax0, bx0)
    inter_y0 = max(ay0, by0)
    inter_x1 = min(ax1, bx1)
    inter_y1 = min(ay1, by1)
    if inter_x1 <= inter_x0 or inter_y1 <= inter_y0:
        return 0.0

    inter_area = (inter_x1 - inter_x0) * (inter_y1 - inter_y0)
    area_a = max((ax1 - ax0) * (ay1 - ay0), 1)
    area_b = max((bx1 - bx0) * (by1 - by0), 1)
    return inter_area / min(area_a, area_b)


def _bbox_area_ratio(a: tuple, b: tuple) -> float:
    area_a = max((a[2] - a[0]) * (a[3] - a[1]), 1)
    area_b = max((b[2] - b[0]) * (b[3] - b[1]), 1)
    return min(area_a, area_b) / max(area_a, area_b)


def _is_duplicate_bbox(a: tuple, b: tuple) -> bool:
    return _bbox_overlap_ratio(a, b) >= 0.75 and _bbox_area_ratio(a, b) >= 0.75


def _merge_table_bboxes(primary: list[tuple], secondary: list[tuple]) -> list[tuple]:
    merged = list(primary)
    for bbox in secondary:
        if any(_is_duplicate_bbox(existing, bbox) for existing in merged):
            continue
        merged.append(bbox)
    return merged


def _merge_detected_tables(primary: list[dict], secondary: list[dict]) -> list[dict]:
    merged = list(primary)
    for table in secondary:
        bbox = table["bbox"]
        if any(_is_duplicate_bbox(existing["bbox"], bbox) for existing in merged):
            continue
        merged.append(table)
    return merged


def detect_tables_by_text_alignment(page) -> list[dict]:
    y_tol = 3.0
    col_cluster_tol = 15.0
    min_header_items = 2
    max_header_items = 8
    min_data_rows = 2

    extract_words = getattr(page, "extract_words", None)
    if not callable(extract_words):
        return []

    try:
        words = extract_words(
            keep_blank_chars=True,
            x_tolerance=3,
            y_tolerance=3,
        )
    except Exception as exc:
        logger.warning("text-alignment table detection failed: %s", exc)
        return []

    rows = _group_words_by_row(words, y_tol=y_tol)
    keyword_tables = _find_keyword_condition_tables(rows)
    if len(words) < 6 or len(rows) < min_data_rows + 1:
        return keyword_tables

    header_idx = None
    for idx, row in enumerate(rows):
        n_items = len(row)
        if min_header_items <= n_items <= max_header_items:
            avg_len = sum(len(word["text"]) for word in row) / n_items
            x_range = max(word["x1"] for word in row) - min(word["x0"] for word in row)
            if avg_len < 15 and x_range > float(page.width) * 0.3:
                header_idx = idx
                break

    if header_idx is None:
        return keyword_tables

    col_centers = sorted((word["x0"] + word["x1"]) / 2 for word in rows[header_idx])
    data_rows = rows[header_idx:]
    if len(data_rows) < min_data_rows + 1:
        return keyword_tables

    table_rows = []
    for row_words in data_rows:
        row_cells = [""] * len(col_centers)
        for word in row_words:
            center = (word["x0"] + word["x1"]) / 2
            min_dist = float("inf")
            min_col = 0
            for col_idx, col_center in enumerate(col_centers):
                dist = abs(center - col_center)
                if dist < min_dist:
                    min_dist = dist
                    min_col = col_idx
            if min_dist < col_cluster_tol:
                row_cells[min_col] = (
                    f"{row_cells[min_col]} {word['text']}".strip()
                    if row_cells[min_col]
                    else word["text"]
                )
        table_rows.append(row_cells)

    if len(table_rows) < min_data_rows:
        return keyword_tables

    generic_table = {
        "bbox": _bbox_from_rows(data_rows),
        "rows": table_rows,
    }
    if generic_table["bbox"] is None:
        return keyword_tables
    return _merge_detected_tables([generic_table], keyword_tables)


def detect_tables(page) -> list[tuple]:
    try:
        tolerance = calculate_dynamic_tolerance(page)
        table_settings = {
            "snap_tolerance": tolerance["snap_tolerance"],
            "join_tolerance": tolerance["join_tolerance"],
            "intersection_tolerance": tolerance["intersection_tolerance"],
        }

        tables = page.find_tables(table_settings=table_settings)
        pdf_bboxes = [table.bbox for table in tables]
        text_bboxes = [table["bbox"] for table in detect_tables_by_text_alignment(page)]

        if pdf_bboxes and text_bboxes:
            return _merge_table_bboxes(pdf_bboxes, text_bboxes)
        if pdf_bboxes:
            return pdf_bboxes
        if text_bboxes:
            return text_bboxes
        return []
    except Exception as exc:
        logger.warning("table detection failed: %s", exc)
        return []
