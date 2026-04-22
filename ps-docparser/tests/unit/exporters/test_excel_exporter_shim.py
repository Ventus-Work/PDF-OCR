"""
tests/unit/exporters/test_excel_exporter_shim.py

Phase 12 Step 12-2 — import shim 무결성 검증.

Why: excel_exporter.py가 shim으로 변환된 후에도
     기존 코드베이스가 사용하는 모든 import 경로가 유효한지 보장한다.
"""


def test_public_api_importable():
    """기존 호출자(main.py, _test_phase3.py)가 사용하는 공개 API가 유효해야 한다."""
    from exporters.excel_exporter import export, ExcelExporter, _export_impl
    assert callable(export)
    assert callable(_export_impl)
    assert export is _export_impl  # 별칭 확인


def test_classifier_symbols_via_shim():
    """분류 함수들이 excel_exporter 경로로 접근 가능해야 한다 (테스트 직접 참조 보호)."""
    from exporters.excel_exporter import (
        _classify_table,
        _is_number,
        _try_parse_number,
        _row_style,
    )
    assert callable(_classify_table)
    assert callable(_is_number)
    assert callable(_try_parse_number)
    assert callable(_row_style)


def test_style_symbols_via_shim():
    """스타일 상수/함수가 excel_exporter 경로로 접근 가능해야 한다."""
    from exporters.excel_exporter import (
        _apply_style,
        _FILL_HEADER,
        _FONT_HEADER,
        _ALIGN_CENTER,
        _BORDER_ALL,
    )
    assert callable(_apply_style)
    assert _FILL_HEADER is not None
    assert _FONT_HEADER is not None


def test_builder_symbols_via_shim():
    """빌더 함수들이 excel_exporter 경로로 접근 가능해야 한다."""
    from exporters.excel_exporter import (
        _build_estimate_sheet,
        _build_detail_sheet,
        _build_condition_sheet,
        _build_generic_sheet,
        _DETAIL_HEADER_GROUPS,
    )
    assert callable(_build_estimate_sheet)
    assert callable(_build_detail_sheet)
    assert callable(_build_condition_sheet)
    assert callable(_build_generic_sheet)
    assert isinstance(_DETAIL_HEADER_GROUPS, list)


def test_direct_submodule_imports():
    """하위 모듈 직접 import도 동작해야 한다."""
    from exporters.excel_styles import _apply_style, _FILL_HEADER
    from exporters.excel_classifier import _classify_table, _try_parse_number
    from exporters.excel_builders import _build_estimate_sheet, _DETAIL_HEADER_GROUPS
    assert callable(_apply_style)
    assert callable(_classify_table)
    assert callable(_build_estimate_sheet)
