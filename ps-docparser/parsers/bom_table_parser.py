"""
parsers/bom_table_parser.py — BOM 테이블 파싱 (HTML/Markdown/공백 통합)

Why:
    OCR 결과에는 HTML 표, Markdown 파이프 표, 공백 정렬 표가 혼재한다.
    이 모듈은 세 형식을 같은 2D 배열 구조로 맞추고, HTML BOM 표의
    다단 헤더/희소 행을 보정하는 역할을 맡는다.
"""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from extractors.bom_types import BomExtractionResult, BomSection

logger = logging.getLogger(__name__)

_TABLE_PATTERN = re.compile(r"<table[^>]*>.*?</table>", re.DOTALL | re.IGNORECASE)
_OPEN_TABLE_PATTERN = re.compile(r"<table[^>]*>", re.IGNORECASE)
_NUMERIC_CELL_RE = re.compile(r"^-?[\d,.]+$")
_UNIT_VALUE_RE = re.compile(
    r"^(?:EA|SET|LOT|M|M2|M3|KG|TON|식|개|대|본|매|조|개소)$",
    re.IGNORECASE,
)
_SUB_HEADER_KEYWORDS = {
    "NO",
    "ITEM",
    "DESCRIPTION",
    "SPEC",
    "SIZE",
    "DWG",
    "REMARK",
    "MAT'L",
    "MATERIAL",
    "UNIT",
    "WEIGHT",
    "LOSS",
    "M2",
    "KG",
    "QTY",
    "Q'TY",
    "단위",
    "수량",
    "중량",
    "면적",
}
_DUPLICATE_HEADER_SUFFIX_RE = re.compile(r"_\d+$")


def parse_html_bom_tables(
    text: str,
    keywords: dict,
) -> BomExtractionResult:
    """
    텍스트에서 HTML <table> 블록을 추출하고 BOM/LINE LIST 여부를 판정한다.

    Process:
    1. <table> 블록 추출
    2. BOM/LINE LIST 후보 판정
    3. BeautifulSoup + expand_table()로 2D 배열 변환
    4. 타이틀 행 제거
    5. 다단 헤더 병합
    6. 희소 데이터 행 정렬 및 노이즈 행 제거
    """
    from parsers.table_parser import build_composite_headers, expand_table

    header_a = keywords.get("bom_header_a", [])
    header_b = keywords.get("bom_header_b", [])
    header_c = keywords.get("bom_header_c", [])
    ll_hdr_a = [kw.upper() for kw in keywords.get("ll_header_a", [])]
    blacklist = keywords.get("blacklist", [])
    noise_kw = keywords.get("noise_row", [])

    bom_sections: list[BomSection] = []
    ll_sections: list[BomSection] = []

    for html_block in _extract_html_blocks(text):
        block_upper = html_block.upper()

        is_bom = (
            any(kw.upper() in block_upper for kw in header_a)
            and any(kw.upper() in block_upper for kw in header_b)
            and any(kw.upper() in block_upper for kw in header_c)
        )
        # LINE LIST는 OCR 누락이 많아 핵심 키워드만 보여도 후보로 본다.
        is_line_list = any(kw in block_upper for kw in ll_hdr_a)

        if not (is_bom or is_line_list):
            continue

        if any(kw.upper() in block_upper for kw in blacklist):
            continue

        try:
            soup = BeautifulSoup(html_block, "html.parser")
            table_tag = soup.find("table")
            if not table_tag:
                continue
            grid = expand_table(table_tag)
        except Exception as exc:
            logger.warning("HTML 테이블 파싱 실패: %s", exc)
            continue

        effective_grid, section_title = _strip_title_row(grid)
        if len(effective_grid) < 2:
            continue

        headers = [str(cell).strip() for cell in effective_grid[0]]
        rows = effective_grid[1:]

        if rows and _looks_like_sub_header_row(rows[0]):
            headers = _merge_sub_headers(build_composite_headers, headers, rows[0])
            rows = rows[1:]
            logger.info("2행 복합 헤더 병합 완료: %s", headers)

        rows = _normalize_html_bom_rows(rows, headers)
        filtered_rows = filter_noise_rows(rows, noise_kw)

        title_upper = (section_title or "").upper()
        classify_as_line_list = (
            "LINE LIST" in title_upper
            or "LINELIST" in title_upper
            or is_line_list
        )

        target_list = ll_sections if classify_as_line_list else bom_sections
        section_type = "line_list" if classify_as_line_list else "bom"
        target_list.append(
            BomSection(
                section_type=section_type,
                headers=headers,
                rows=filtered_rows,
                raw_row_count=len(rows),
            )
        )
        logger.info("%s 테이블 감지: %d행", section_type.upper(), len(filtered_rows))

    return BomExtractionResult(
        bom_sections=bom_sections,
        line_list_sections=ll_sections,
    )


def _extract_html_blocks(text: str) -> list[str]:
    """완전한 table 블록 또는 잘린 table 시작 구간을 추출한다."""
    html_blocks = _TABLE_PATTERN.findall(text)
    if html_blocks:
        return html_blocks

    open_tag = _OPEN_TABLE_PATTERN.search(text)
    if not open_tag:
        return []

    truncated = text[open_tag.start():]
    logger.debug("잘린 HTML 테이블 감지: %d자 처리", len(truncated))
    return [truncated]


def _strip_title_row(grid: list[list[str]]) -> tuple[list[list[str]], str | None]:
    """
    표 최상단의 colspan 기반 제목 행을 제거한다.

    OCR은 `BILL OF MATERIALS`, `LINE LIST` 같은 제목 행을 한 셀로 주고,
    expand_table()가 이를 행 전체로 복제한다. 이 행은 실제 헤더가 아니므로
    제거한 뒤 다음 행을 컬럼 헤더로 사용한다.
    """
    if len(grid) < 2:
        return grid, None

    header_start = 0
    section_title = None

    for index, row in enumerate(grid[:2]):
        non_empty = [str(cell).strip() for cell in row if str(cell).strip()]
        unique_vals = list(dict.fromkeys(non_empty))
        next_row_len = len(grid[index + 1]) if index + 1 < len(grid) else 0
        single_val = unique_vals[0] if unique_vals else ""

        is_title_row = (
            len(unique_vals) == 1
            and next_row_len > len(unique_vals)
            and not single_val.isdigit()
            and len(single_val) >= 3
        )
        if is_title_row:
            section_title = single_val
            header_start = index + 1
            logger.debug("타이틀 행 감지 및 스킵: '%s' (grid[%d])", section_title, index)
            break

    return grid[header_start:], section_title


def _looks_like_sub_header_row(row: list[str]) -> bool:
    """
    두 번째 행이 실제 데이터가 아니라 보조 헤더인지 판정한다.

    판단 기준:
    - 비어 있지 않은 셀이 2개 이상
    - UNIT/WEIGHT/LOSS 등 보조 헤더 키워드가 2개 이상
    - 숫자 셀 비율이 낮음
    """
    normalized = [str(cell).upper().strip() for cell in row]
    non_empty = [cell for cell in normalized if cell]
    if len(non_empty) < 2:
        return False

    matched_count = sum(
        1
        for cell in non_empty
        if any(keyword in cell for keyword in _SUB_HEADER_KEYWORDS)
    )
    number_count = sum(1 for cell in non_empty if _NUMERIC_CELL_RE.match(cell))
    numeric_ratio = number_count / len(non_empty)
    return matched_count >= 2 and numeric_ratio <= 0.4


def _merge_sub_headers(
    build_composite_headers,
    headers: list[str],
    sub_headers: list[str],
) -> list[str]:
    """
    1행/2행 헤더를 BOM 전용 composite header로 병합한다.

    범용 테이블 파서는 `_` 결합을 유지하지만, BOM 출력은 사용자가 읽는
    자재표이므로 `상위 | 하위` 형태로 의미를 보존한다. rowspan으로 같은
    텍스트가 복제된 경우에는 단일 헤더로 축약한다.
    """
    del build_composite_headers  # 범용 결합 규칙 대신 BOM 전용 규칙을 사용한다.

    max_len = max(len(headers), len(sub_headers))
    merged: list[str] = []

    for idx in range(max_len):
        parent = _normalize_bom_header_text(headers[idx] if idx < len(headers) else "")
        child = _normalize_bom_header_text(sub_headers[idx] if idx < len(sub_headers) else "")

        if parent and child:
            if _header_compare_key(parent) == _header_compare_key(child):
                header = parent
            else:
                header = f"{parent} | {child}"
        else:
            header = parent or child or f"Column_{idx + 1}"

        merged.append(header)

    return _make_unique_bom_headers(merged)


def _normalize_bom_header_text(value: str) -> str:
    """BOM 헤더 표시용 공백만 정리한다."""
    return re.sub(r"\s+", " ", str(value or "").replace("\n", " ")).strip()


def _header_compare_key(value: str) -> str:
    """
    헤더 동일성 비교용 canonical key.

    `DWG NO.`, `DWG NO`, `Dwg No.`처럼 표시만 다른 반복 헤더를 같은
    헤더로 판단하기 위해 공백과 주요 구두점을 제거한다.
    """
    text = _normalize_bom_header_text(value).upper()
    return re.sub(r"[\s._|/\-]+", "", text)


def _make_unique_bom_headers(headers: list[str]) -> list[str]:
    """
    병합 후에도 같은 헤더명이 남으면 `_2`, `_3` suffix로 보존한다.

    dict 변환 단계에서 key 충돌이 나면 값이 덮어써지므로, 파서 단계에서
    header list 자체를 고유화한다.
    """
    seen: dict[str, int] = {}
    unique: list[str] = []

    for idx, header in enumerate(headers):
        base = _normalize_bom_header_text(header) or f"Column_{idx + 1}"
        count = seen.get(base, 0) + 1
        seen[base] = count
        unique.append(base if count == 1 else f"{base}_{count}")

    return unique


def _trim_trailing_duplicate_parent_header(
    headers: list[str],
    sub_headers: list[str],
    merged_headers: list[str],
) -> list[str]:
    """
    1행/2행 길이 불일치로 생긴 꼬리 중복 헤더를 정리한다.

    실측 OCR에서는 마지막 부모 헤더가 한 칸 더 복제되어
    `비고`, `비고` 같은 잔여 컬럼이 생길 수 있다. 하위 헤더가 비어 있고
    마지막 두 헤더가 완전히 동일한 경우에만 trailing duplicate를 제거한다.
    """
    if len(merged_headers) < 2 or len(headers) <= len(sub_headers):
        return merged_headers

    padded_top = list(headers) + [""] * max(0, len(merged_headers) - len(headers))
    padded_bottom = list(sub_headers) + [""] * max(0, len(merged_headers) - len(sub_headers))
    trimmed = list(merged_headers)

    while len(trimmed) >= 2:
        idx = len(trimmed) - 1
        top = str(padded_top[idx]).strip() if idx < len(padded_top) else ""
        prev_top = str(padded_top[idx - 1]).strip() if idx - 1 < len(padded_top) else ""
        bottom = str(padded_bottom[idx]).strip() if idx < len(padded_bottom) else ""

        if bottom or not top:
            break
        if trimmed[idx] != trimmed[idx - 1]:
            break
        if top != prev_top:
            break

        trimmed.pop()

    return trimmed


def _composite_header_bounds(headers: list[str]) -> tuple[int, int] | None:
    composite_indexes = [
        idx
        for idx, header in enumerate(headers)
        if _is_composite_header(header)
    ]
    if not composite_indexes:
        return None
    return composite_indexes[0], composite_indexes[-1] + 1


def _is_composite_header(header: str) -> bool:
    text = str(header or "")
    if " | " in text:
        return True
    return "_" in text and not _DUPLICATE_HEADER_SUFFIX_RE.search(text)


def _header_parts(header: str) -> list[str]:
    return [
        _normalize_bom_header_text(part)
        for part in str(header or "").split("|")
        if _normalize_bom_header_text(part)
    ]


def _semantic_header_key(header: str) -> str:
    text = _normalize_bom_header_text(header).upper()
    text = re.sub(_DUPLICATE_HEADER_SUFFIX_RE, "", text)
    return re.sub(r"[\s._|/\-']+", "", text)


def _is_quantity_header(header: str) -> bool:
    key = _semantic_header_key(header)
    return key in {"QTY", "QTY", "QUANTITY", "수량"} or "수량" in str(header)


def _is_general_unit_header(header: str) -> bool:
    text = str(header or "")
    key = _semantic_header_key(header)
    parts = {_semantic_header_key(part) for part in _header_parts(text)}
    has_unit_token = key in {"UNIT", "단위"} or parts.intersection({"UNIT", "단위"})
    if not has_unit_token:
        return False

    # `자재중량 [Kg] | UNIT` 같은 복합 중량/면적 단위는 일반 수량 단위와 구분한다.
    material_group_tokens = ("WEIGHT", "LOSS", "KG", "M2", "중량", "면적", "자재중량", "자재면적")
    return not any(token.upper() in text.upper() for token in material_group_tokens)


def _is_unit_like_header(header: str) -> bool:
    key = _semantic_header_key(header)
    parts = {_semantic_header_key(part) for part in _header_parts(header)}
    return key in {"UNIT", "단위"} or bool(parts.intersection({"UNIT", "단위"}))


def _is_numeric_quantity_value(value: str) -> bool:
    return bool(_NUMERIC_CELL_RE.match(str(value or "").strip()))


def _is_unit_value(value: str) -> bool:
    text = str(value or "").strip()
    return bool(text and _UNIT_VALUE_RE.match(text))


def _find_qty_unit_shift_columns(headers: list[str]) -> tuple[int, int, int] | None:
    for qty_idx, header in enumerate(headers):
        if not _is_quantity_header(header):
            continue
        unit_idx = qty_idx + 1
        if unit_idx >= len(headers) or not _is_general_unit_header(headers[unit_idx]):
            continue
        for shifted_idx in range(unit_idx + 1, len(headers)):
            if _is_unit_like_header(headers[shifted_idx]):
                return qty_idx, unit_idx, shifted_idx
    return None


def _repair_quantity_unit_shift(row: list[str], headers: list[str]) -> list[str]:
    """
    `수량`이 비고 `단위`에 숫자, 다음 UNIT 계열 컬럼에 단위가 들어간
    한 칸 우측 밀림만 복원한다.
    """
    columns = _find_qty_unit_shift_columns(headers)
    if not columns:
        return row

    qty_idx, unit_idx, shifted_idx = columns
    if shifted_idx >= len(row):
        return row
    if str(row[qty_idx]).strip():
        return row
    if not _is_numeric_quantity_value(row[unit_idx]):
        return row
    if not _is_unit_value(row[shifted_idx]):
        return row
    if not any(str(cell).strip() for cell in row[:qty_idx]):
        return row

    repaired = list(row)
    repaired[qty_idx] = repaired[unit_idx]
    repaired[unit_idx] = repaired[shifted_idx]
    repaired[shifted_idx] = ""
    return repaired


def _realign_sparse_bom_row(row: list[str], headers: list[str]) -> list[str]:
    """
    앞부분은 꽉 차고, 복합 헤더 구간 값만 일부 들어온 희소 행을 재정렬한다.

    실측 BOM에서 첫 행만 `... TAG | 1 | 식`처럼 뒤쪽 값 두 개만 남아
    복합 헤더 블록 앞에 붙는 경우가 있다. 이런 케이스는 뒤쪽 그룹 기준으로
    우측 정렬해 `QTY`, `UNIT` 컬럼으로 이동시킨다.
    """
    target = len(headers)
    padded = row[:target] + [""] * max(target - len(row), 0)
    if len(row) <= 1:
        return padded

    bounds = _composite_header_bounds(headers)
    if not bounds:
        return padded

    group_start, group_end = bounds
    tail_width = target - group_end
    if group_start <= 0:
        return padded

    suffix_values = [cell for cell in padded[group_start:] if str(cell).strip()]
    if (
        len(row) >= target
        and tail_width > 0
        and not any(str(cell).strip() for cell in padded[group_end:])
        and 0 < len(suffix_values) <= tail_width
        and all(str(cell).strip() for cell in padded[:group_start])
    ):
        return (
            padded[:group_start]
            + [""] * (target - group_start - len(suffix_values))
            + suffix_values
        )

    if len(row) <= group_start:
        return padded

    prefix_len = 0
    while prefix_len < min(len(row), group_start) and str(row[prefix_len]).strip():
        prefix_len += 1

    if prefix_len == 0:
        return padded

    suffix = list(row[prefix_len:])
    group_width = target - group_start
    if len(suffix) > group_width:
        return padded

    base = list(row[:prefix_len]) + [""] * (group_start - prefix_len)
    group_values = [""] * (group_width - len(suffix)) + suffix
    return base + group_values


def _normalize_html_bom_rows(rows: list[list[str]], headers: list[str]) -> list[list[str]]:
    target = len(headers)
    normalized_rows = []

    for row in rows:
        if len(row) > target:
            candidates = normalize_columns([row], reference_col_count=target)
        else:
            candidates = [_realign_sparse_bom_row(row, headers)]

        for candidate in candidates:
            normalized_rows.append(_repair_quantity_unit_shift(candidate, headers))

    return normalized_rows


def parse_markdown_pipe_table(text: str) -> list[list[str]]:
    """
    Markdown 파이프(|) 형식 테이블을 2D 배열로 파싱한다.

    입력 예시:
        | S/N | SIZE | MAT'L | Q'TY |
        |-----|------|-------|------|
        | 1   | 100A | SS304 | 2    |
    """
    rows = []
    for line in text.split("\n"):
        line = line.strip()
        if "|" not in line or line.count("|") < 2:
            continue

        cells = [cell.strip() for cell in line.split("|")]
        if cells and cells[0] == "":
            cells = cells[1:]
        if cells and cells[-1] == "":
            cells = cells[:-1]

        if all(re.match(r"^[-:= ]+$", cell) for cell in cells if cell):
            continue

        if cells:
            rows.append(cells)

    return rows


def parse_whitespace_table(text: str) -> list[list[str]]:
    """
    공백 2개 이상으로 구분된 테이블을 2D 배열로 파싱한다.
    """
    rows = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue

        cells = re.split(r"\s{2,}", line)
        if len(cells) >= 3:
            rows.append(cells)

    return rows


def normalize_columns(
    rows: list[list[str]],
    *,
    reference_col_count: int | None = None,
) -> list[list[str]]:
    """
    열 수를 정규화한다.

    - 짧은 행: 빈 셀로 패딩
    - 긴 행: 인접 최소 길이 셀 병합
    """
    if not rows:
        return rows

    target = reference_col_count or max(len(row) for row in rows)
    result = []

    for row in rows:
        if len(row) == target:
            result.append(row)
        elif len(row) < target:
            result.append(row + [""] * (target - len(row)))
        else:
            merged = list(row)
            while len(merged) > target:
                min_len = float("inf")
                min_idx = 0
                for index in range(len(merged) - 1):
                    combined = len(merged[index]) + len(merged[index + 1])
                    if combined < min_len:
                        min_len = combined
                        min_idx = index
                merged[min_idx] = merged[min_idx] + " " + merged[min_idx + 1]
                merged.pop(min_idx + 1)
            result.append(merged)

    return result


def filter_noise_rows(
    rows: list[list[str]],
    noise_keywords: list[str],
) -> list[list[str]]:
    """
    노이즈 행을 필터링한다.

    필터 기준:
    1. 노이즈 키워드 포함 행 제거
    2. 완전 빈 행 제거
    3. 모든 셀이 동일한 행 제거
    """
    result = []

    for row in rows:
        joined_upper = " ".join(str(cell) for cell in row).upper()

        if any(keyword.upper() in joined_upper for keyword in noise_keywords):
            continue
        if all(not str(cell).strip() for cell in row):
            continue

        non_empty = [cell for cell in row if str(cell).strip()]
        if len(non_empty) > 1 and len(set(str(cell).strip() for cell in non_empty)) == 1:
            continue

        result.append(row)

    return result


def parse_bom_rows(text: str) -> list[list[str]]:
    """
    텍스트를 자동 감지하여 BOM 행으로 파싱한다.

    우선순위:
    1. Markdown 파이프 표
    2. 공백 2개 이상 구분 표
    """
    rows = parse_markdown_pipe_table(text)
    if rows:
        return normalize_columns(rows)

    rows = parse_whitespace_table(text)
    if rows:
        return normalize_columns(rows)

    return []
