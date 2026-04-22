"""
tests/unit/parsers/test_text_cleaner_shim.py

Phase 12 Step 12-4 — import shim 무결성 검증.

Why: text_cleaner.py가 shim으로 변환된 후에도
     기존 코드베이스가 사용하는 모든 import 경로가 유효한지 보장한다.
"""


def test_orchestrator_importable():
    """메인 오케스트레이터가 유효해야 한다."""
    from parsers.text_cleaner import process_section_text
    assert callable(process_section_text)


def test_metadata_symbols_via_shim():
    """메타데이터 추출 함수들이 text_cleaner 경로로 접근 가능해야 한다."""
    from parsers.text_cleaner import (
        extract_notes,
        extract_conditions,
        extract_cross_references,
        remove_duplicate_notes,
    )
    assert callable(extract_notes)
    assert callable(extract_conditions)
    assert callable(extract_cross_references)
    assert callable(remove_duplicate_notes)


def test_normalizer_symbols_via_shim():
    """정규화 함수들이 text_cleaner 경로로 접근 가능해야 한다."""
    from parsers.text_cleaner import (
        clean_text,
        merge_spaced_korean,
        _RE_SINGLE_HANGUL,
    )
    assert callable(clean_text)
    assert callable(merge_spaced_korean)
    assert _RE_SINGLE_HANGUL is not None


def test_direct_submodule_imports():
    """하위 모듈 직접 import도 동작해야 한다."""
    from parsers.text_metadata import (
        extract_notes,
        extract_conditions,
        extract_cross_references,
        remove_duplicate_notes,
    )
    from parsers.text_normalizer import clean_text, merge_spaced_korean, _RE_SINGLE_HANGUL
    assert callable(extract_notes)
    assert callable(clean_text)
    assert callable(merge_spaced_korean)


def test_merge_spaced_korean_via_shim():
    """균등배분 병합 함수가 shim을 통해 정상 동작해야 한다."""
    from parsers.text_cleaner import merge_spaced_korean
    assert merge_spaced_korean("제 출 처") == "제출처"
    assert merge_spaced_korean("SUS 304") == "SUS 304"
