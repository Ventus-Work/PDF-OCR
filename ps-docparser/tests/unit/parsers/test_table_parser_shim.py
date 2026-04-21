"""
tests/unit/parsers/test_table_parser_shim.py

Phase 12 Step 12-1 — import shim 무결성 검증.

Why: table_parser.py가 shim으로 변환된 후에도
     기존 코드베이스가 사용하는 모든 import 경로가 유효한지 보장한다.
     향후 shim에서 심볼이 누락되면 CI가 즉시 감지하도록 설계.
"""


def test_html_utils_imports_via_shim():
    """html_utils 함수들이 table_parser 경로로 접근 가능해야 한다."""
    from parsers.table_parser import (
        _make_soup,
        expand_table,
        extract_cell_text,
        clean_cell_text,
        parse_html_table,
        extract_tables_from_text,
        remove_tables_from_text,
    )
    assert callable(_make_soup)
    assert callable(expand_table)
    assert callable(extract_cell_text)
    assert callable(clean_cell_text)
    assert callable(parse_html_table)
    assert callable(extract_tables_from_text)
    assert callable(remove_tables_from_text)


def test_header_utils_imports_via_shim():
    """header_utils 함수들이 table_parser 경로로 접근 가능해야 한다."""
    from parsers.table_parser import (
        classify_table,
        _is_header_like_row,
        detect_header_rows,
        build_composite_headers,
        is_note_row,
        try_numeric,
    )
    assert callable(classify_table)
    assert callable(_is_header_like_row)
    assert callable(detect_header_rows)
    assert callable(build_composite_headers)
    assert callable(is_note_row)
    assert callable(try_numeric)


def test_orchestrator_imports_via_shim():
    """오케스트레이터 함수들이 table_parser 경로로 접근 가능해야 한다."""
    from parsers.table_parser import (
        parse_single_table,
        process_section_tables,
    )
    assert callable(parse_single_table)
    assert callable(process_section_tables)


def test_direct_html_utils_import():
    """html_utils 직접 import도 동작해야 한다 (하위 모듈 공개 API)."""
    from parsers.html_utils import (
        expand_table,
        extract_tables_from_text,
        remove_tables_from_text,
        parse_html_table,
    )
    assert callable(expand_table)
    assert callable(extract_tables_from_text)


def test_direct_header_utils_import():
    """header_utils 직접 import도 동작해야 한다 (하위 모듈 공개 API)."""
    from parsers.header_utils import (
        classify_table,
        detect_header_rows,
        build_composite_headers,
        is_note_row,
        try_numeric,
    )
    assert callable(classify_table)
    assert callable(detect_header_rows)
