"""
tests/unit/extractors/test_bom_extractor_shim.py

Phase 12 Step 12-3 — import shim 무결성 검증.

Why: bom_extractor.py가 shim으로 변환된 후에도
     기존 코드베이스가 사용하는 모든 import 경로가 유효한지 보장한다.
     특히 pipelines/bom_pipeline.py의 3개 심볼이 핵심.
"""


def test_pipeline_critical_imports():
    """pipelines/bom_pipeline.py가 사용하는 핵심 3개 심볼이 유효해야 한다."""
    from extractors.bom_extractor import (
        extract_bom_tables,
        extract_bom_with_retry,
        to_sections,
    )
    assert callable(extract_bom_tables)
    assert callable(extract_bom_with_retry)
    assert callable(to_sections)


def test_state_machine_imports_via_shim():
    """상태머신 함수가 bom_extractor 경로로 접근 가능해야 한다."""
    from extractors.bom_extractor import extract_bom, extract_bom_tables
    assert callable(extract_bom)
    assert callable(extract_bom_tables)


def test_sanitizer_imports_via_shim():
    """HTML 전처리 함수/상수가 bom_extractor 경로로 접근 가능해야 한다."""
    from extractors.bom_extractor import (
        _sanitize_html,
        _RE_TR_CLOSE,
        _RE_TD_SPLIT,
        _RE_TAG,
    )
    assert callable(_sanitize_html)
    assert _RE_TR_CLOSE is not None
    assert _RE_TD_SPLIT is not None


def test_ocr_retry_imports_via_shim():
    """OCR 재시도 함수가 bom_extractor 경로로 접근 가능해야 한다."""
    from extractors.bom_extractor import (
        _get_table_bbox_scaled,
        extract_bom_with_retry,
    )
    assert callable(_get_table_bbox_scaled)
    assert callable(extract_bom_with_retry)


def test_direct_submodule_imports():
    """하위 모듈 직접 import도 동작해야 한다."""
    from extractors.bom_sanitizer import _sanitize_html
    from extractors.bom_state_machine import extract_bom, extract_bom_tables
    from extractors.bom_ocr_retry import extract_bom_with_retry, _get_table_bbox_scaled
    from extractors.bom_converter import to_sections
    assert callable(_sanitize_html)
    assert callable(extract_bom)
    assert callable(extract_bom_tables)
    assert callable(extract_bom_with_retry)
    assert callable(to_sections)
