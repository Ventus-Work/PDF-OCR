"""
tests/unit/parsers/test_section_splitter_shim.py

Phase 12 Step 12-5 — import shim 무결성 검증.

Why: section_splitter.py가 shim으로 변환된 후에도
     기존 코드베이스가 사용하는 모든 import 경로가 유효한지 보장한다.
"""


def test_orchestrator_importable():
    """메인 오케스트레이터가 유효해야 한다."""
    from parsers.section_splitter import split_sections
    assert callable(split_sections)


def test_toc_symbols_via_shim():
    """TOC 함수들이 section_splitter 경로로 접근 가능해야 한다."""
    from parsers.section_splitter import load_toc, build_reverse_map
    assert callable(load_toc)
    assert callable(build_reverse_map)


def test_detector_symbols_via_shim():
    """마커 파싱 함수들이 section_splitter 경로로 접근 가능해야 한다."""
    from parsers.section_splitter import (
        parse_section_markers,
        parse_page_markers,
        get_page_for_position,
        redistribute_text_to_sections,
        _SECTION_MARKER,
        _PAGE_MARKER,
    )
    assert callable(parse_section_markers)
    assert callable(parse_page_markers)
    assert callable(get_page_for_position)
    assert callable(redistribute_text_to_sections)
    assert _SECTION_MARKER is not None
    assert _PAGE_MARKER is not None


def test_direct_submodule_imports():
    """하위 모듈 직접 import도 동작해야 한다."""
    from parsers.section_toc import load_toc, build_reverse_map
    from parsers.section_detector import (
        parse_section_markers, parse_page_markers,
        get_page_for_position, redistribute_text_to_sections,
        _SECTION_MARKER, _PAGE_MARKER,
    )
    assert callable(load_toc)
    assert callable(parse_section_markers)
    assert _SECTION_MARKER is not None


def test_parse_section_markers_via_shim():
    """마커 파싱이 shim을 통해 정상 동작해야 한다."""
    from parsers.section_splitter import parse_section_markers
    sample = "<!-- SECTION: 1-1 | 제목 | 부문:건축 | 장:제1장 -->"
    result = parse_section_markers(sample)
    assert len(result) == 1
    assert result[0]["section_id"] == "1-1"
    assert result[0]["title"] == "제목"
