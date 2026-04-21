"""
parsers/table_parser.py — HTML 테이블 파싱 오케스트레이터 + import shim

Why: Phase 12 Step 12-1 분해 결과물.
     기존 HTML 파싱 유틸(7개)은 parsers/html_utils.py로,
     헤더/행 분류 유틸(6개)은 parsers/header_utils.py로 이동했다.
     이 파일은 기존 import 경로를 100% 유지하는 shim과
     두 모듈을 조합하는 오케스트레이션 함수(parse_single_table,
     process_section_tables)만 포함한다.

     외부 코드(main.py, pipelines/, 테스트)는 이 파일을 통해
     모든 심볼에 동일 경로로 접근 가능하다.

원본: parsers/table_parser.py L1~614 (Phase 11 완료 기준)
"""

# ── Import shim: 하위 모듈에서 전체 공개 API re-export ──
from parsers.html_utils import (
    _make_soup,
    expand_table,
    extract_cell_text,
    clean_cell_text,
    parse_html_table,
    extract_tables_from_text,
    remove_tables_from_text,
)
from parsers.header_utils import (
    classify_table,
    _is_header_like_row,
    detect_header_rows,
    build_composite_headers,
    is_note_row,
    try_numeric,
)

__all__ = [
    # html_utils
    "_make_soup",
    "expand_table",
    "extract_cell_text",
    "clean_cell_text",
    "parse_html_table",
    "extract_tables_from_text",
    "remove_tables_from_text",
    # header_utils
    "classify_table",
    "_is_header_like_row",
    "detect_header_rows",
    "build_composite_headers",
    "is_note_row",
    "try_numeric",
    # orchestration (this module)
    "parse_single_table",
    "process_section_tables",
]


# ══════════════════════════════════════════════════════════
# 오케스트레이터 함수 (이 파일에 유지)
# ══════════════════════════════════════════════════════════

def parse_single_table(
    html: str,
    section_id: str,
    table_idx: int,
    type_keywords: dict = None,
) -> dict | None:
    """
    단일 HTML 테이블을 구조화된 딕셔너리로 파싱한다.

    Why: html_utils + header_utils 두 모듈을 조합하는 오케스트레이터.
         expand_table()로 2D 배열을 얻은 뒤 헤더/데이터/주석을 분리하고,
         헤더 키 기반 dict 리스트로 변환하여 JSON 직렬화가 용이한 구조를 만든다.

    Args:
        html: <table>...</table> HTML 문자열
        section_id: 섹션 ID (table_id 생성에 사용)
        table_idx: 섹션 내 테이블 순번 (1부터 시작)
        type_keywords: 테이블 유형 분류 키워드 (None=범용, "general" 반환)

    Returns:
        dict | None:
            None이면 파싱 불가 (빈 테이블 등)
            {
                "table_id": "T-{section_id}-{idx:02d}",
                "type": str,               # classify_table() 결과
                "headers": list[str],
                "rows": list[dict],        # 헤더 키 기반 dict (값은 항상 str)
                "notes_in_table": list[str],
                "raw_row_count": int,
                "parsed_row_count": int,
            }

    원본: table_parser.py L483~575
    """
    soup = _make_soup(html)
    table_tag = soup.find("table")
    if not table_tag:
        return None

    grid = expand_table(table_tag)
    if not grid:
        return None

    table_id = f"T-{section_id}-{table_idx:02d}"

    # 헤더만 있고 데이터 없는 경우
    if len(grid) < 2:
        headers = [h.strip() for h in grid[0]]
        return {
            "table_id": table_id,
            "type": classify_table(headers, [], type_keywords),
            "headers": headers,
            "rows": [],
            "notes_in_table": [],
            "raw_row_count": 0,
            "parsed_row_count": 0,
        }

    n_header_rows = detect_header_rows(grid)
    headers = build_composite_headers(grid, n_header_rows)
    n_cols = len(headers)

    data_rows, note_rows = [], []
    for row in grid[n_header_rows:]:
        if is_note_row(row, n_cols):
            note_rows.append(" ".join(c for c in row if c.strip()))
        else:
            data_rows.append(row)

    table_type = classify_table(headers, data_rows, type_keywords)

    rows_as_dicts = []
    for row in data_rows:
        row_dict = {}
        for j, header in enumerate(headers):
            val = row[j] if j < len(row) else ""
            key = header if header else f"col_{j}"
            row_dict[key] = try_numeric(val)  # [리뷰 반영 3] str 유지
        # 모든 값이 빈 행 제외
        if any(v for v in row_dict.values() if v != "" and v is not None):
            rows_as_dicts.append(row_dict)

    return {
        "table_id": table_id,
        "type": table_type,
        "headers": headers,
        "rows": rows_as_dicts,
        "notes_in_table": note_rows,
        "raw_row_count": len(grid) - n_header_rows,
        "parsed_row_count": len(rows_as_dicts),
    }


def process_section_tables(
    section: dict,
    type_keywords: dict = None,
) -> dict:
    """
    섹션 dict 내의 모든 HTML 테이블을 파싱하여 섹션 dict에 추가한다.

    Why: 섹션의 raw_text에 여러 개의 <table>이 있을 수 있다.
         각 테이블을 parse_single_table()로 처리하고, 결과를 "tables" 키에 저장.
         테이블을 제거한 나머지 텍스트는 "text_without_tables" 키에 저장.

    Args:
        section: split_sections()가 반환한 섹션 dict
        type_keywords: 테이블 유형 분류 키워드 (None=범용)

    Returns:
        dict: 입력 section + "tables" 키 + "text_without_tables" 키 추가된 dict

    원본: table_parser.py L578~613
    """
    raw_text = section.get("raw_text", "")
    section_id = section.get("section_id", "unknown")
    table_htmls = extract_tables_from_text(raw_text)

    parsed_tables = []
    for idx, table_info in enumerate(table_htmls, 1):
        result = parse_single_table(table_info["html"], section_id, idx, type_keywords)
        if result:
            parsed_tables.append(result)

    return {
        **section,
        "tables": parsed_tables,
        "text_without_tables": remove_tables_from_text(raw_text),
    }
