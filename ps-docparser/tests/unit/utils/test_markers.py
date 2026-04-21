"""
utils/markers.py 단위 테스트 — Phase 10 Step 10-4
목표 커버리지: 17.57% → 80%+
"""
import pytest
from unittest.mock import MagicMock

from utils.markers import (
    build_section_markers,
    build_page_marker,
    build_context_marker,
    process_toc_context,
    _extract_page_footer_metadata,
)


# ══════════════════════════════════════════════════════════
# 픽스처
# ══════════════════════════════════════════════════════════

@pytest.fixture
def sample_sections():
    return [
        {
            "id": "1-1-1",
            "title": "일반사항",
            "chapter": "공통부문",
            "section": "제1장 총칙",
        },
        {
            "id": "1-1-2",
            "title": "용어정의",
            "chapter": "공통부문",
            "section": "제1장 총칙",
        },
    ]


@pytest.fixture
def sample_active_section():
    return {
        "id": "2-1-1",
        "title": "터파기",
        "chapter": "토목부문",
        "section": "제2장 토공사",
    }


# ══════════════════════════════════════════════════════════
# build_section_markers
# ══════════════════════════════════════════════════════════

class TestBuildSectionMarkers:
    def test_empty_sections_returns_empty(self):
        assert build_section_markers([]) == ""

    def test_single_section_marker(self, sample_sections):
        result = build_section_markers([sample_sections[0]])
        assert "<!-- SECTION:" in result
        assert "1-1-1" in result
        assert "일반사항" in result
        assert "공통부문" in result
        assert "제1장 총칙" in result

    def test_multiple_sections(self, sample_sections):
        result = build_section_markers(sample_sections)
        assert result.count("<!-- SECTION:") == 2
        assert "1-1-1" in result
        assert "1-1-2" in result

    def test_ends_with_newline(self, sample_sections):
        result = build_section_markers([sample_sections[0]])
        assert result.endswith("\n")

    def test_format_matches_parser_expectation(self, sample_sections):
        result = build_section_markers([sample_sections[0]])
        # section_splitter.py가 파싱할 수 있는 형식인지 확인
        assert "| 부문:" in result
        assert "| 장:" in result


# ══════════════════════════════════════════════════════════
# build_page_marker
# ══════════════════════════════════════════════════════════

class TestBuildPageMarker:
    def test_basic_page_number(self):
        marker = build_page_marker(10, {})
        assert "PAGE 10" in marker

    def test_with_chapter_context(self):
        ctx = {"chapter": "공통부문", "section": "제1장 총칙"}
        marker = build_page_marker(5, ctx)
        assert "PAGE 5" in marker
        assert "공통부문" in marker
        assert "제1장 총칙" in marker

    def test_empty_context(self):
        marker = build_page_marker(1, {})
        assert "PAGE 1" in marker
        assert " | " not in marker

    def test_only_chapter_no_section(self):
        ctx = {"chapter": "토목부문"}
        marker = build_page_marker(3, ctx)
        assert "토목부문" in marker

    def test_only_section_no_chapter(self):
        ctx = {"section": "제2장 토공사"}
        marker = build_page_marker(7, ctx)
        assert "제2장 토공사" in marker

    def test_high_page_number(self):
        marker = build_page_marker(999, {"chapter": "부문", "section": "장"})
        assert "999" in marker

    def test_separator_format(self):
        ctx = {"chapter": "부문A", "section": "장B"}
        marker = build_page_marker(1, ctx)
        assert "부문A > 장B" in marker

    def test_ends_with_double_newline(self):
        marker = build_page_marker(1, {})
        assert marker.endswith("\n\n")


# ══════════════════════════════════════════════════════════
# build_context_marker
# ══════════════════════════════════════════════════════════

class TestBuildContextMarker:
    def test_none_returns_empty(self):
        assert build_context_marker(None) == ""

    def test_empty_dict_returns_empty(self):
        assert build_context_marker({}) == ""

    def test_basic_context_marker(self, sample_active_section):
        result = build_context_marker(sample_active_section)
        assert "<!-- CONTEXT:" in result
        assert "2-1-1" in result
        assert "터파기" in result
        assert "토목부문" in result

    def test_format(self, sample_active_section):
        result = build_context_marker(sample_active_section)
        assert "| 부문:" in result
        assert "| 장:" in result

    def test_ends_with_double_newline(self, sample_active_section):
        result = build_context_marker(sample_active_section)
        assert result.endswith("\n\n")


# ══════════════════════════════════════════════════════════
# _extract_page_footer_metadata (내부 함수)
# ══════════════════════════════════════════════════════════

class TestExtractPageFooterMetadata:
    def test_empty_text_returns_defaults(self):
        result = _extract_page_footer_metadata("", "토목부문|건축부문")
        assert result["page_num"] == 0
        assert result["chapter"] == ""
        assert result["section"] == ""

    def test_no_division_names_returns_defaults(self):
        result = _extract_page_footer_metadata("제1장 총칙 | 5", "")
        assert result["page_num"] == 0

    def test_chapter_section_extracted(self):
        text = "제3장 배관공사 | 127"
        result = _extract_page_footer_metadata(text, "토목부문|건축부문")
        assert result["section"] == "제3장 배관공사"
        assert result["page_num"] == 127

    def test_division_chapter_extracted(self):
        text = "127 토목부문 제3장 배관공사"
        result = _extract_page_footer_metadata(text, "토목부문")
        assert result["chapter"] == "토목부문"
        assert result["page_num"] > 0


# ══════════════════════════════════════════════════════════
# process_toc_context
# ══════════════════════════════════════════════════════════

class TestProcessTocContext:
    def _make_mock_toc(self):
        mock_toc = MagicMock()
        mock_toc.get_current_context.return_value = {
            "chapter": "토목부문",
            "section": "제2장",
            "sections": [{"id": "2-1-1", "title": "터파기"}],
        }
        return mock_toc

    def test_generic_mode_no_footer_parsing(self):
        # preset=None: 푸터 파싱 없이 빈 page_sections 반환
        ctx, sections, page_num = process_toc_context(
            full_text="127 토목부문",
            page_map={},
            current_context={"chapter": "", "section": "", "sections": []},
            toc_parser_module=MagicMock(),
            preset=None,
        )
        assert page_num == 0
        assert sections == []

    def test_pumsem_mode_extracts_page(self):
        mock_toc = self._make_mock_toc()
        page_map = {127: [{"id": "2-1-1", "title": "터파기", "chapter": "토목부문", "section": "제2장"}]}
        text = "제2장 배관공사 | 127"

        ctx, sections, page_num = process_toc_context(
            full_text=text,
            page_map=page_map,
            current_context={"chapter": "", "section": "", "sections": []},
            toc_parser_module=mock_toc,
            preset="pumsem",
            division_names="토목부문|건축부문",
        )
        assert page_num == 127

    def test_pumsem_without_division_names(self):
        ctx, sections, page_num = process_toc_context(
            full_text="페이지 127",
            page_map={},
            current_context={},
            toc_parser_module=MagicMock(),
            preset="pumsem",
            division_names=None,
        )
        assert page_num == 0

    def test_returns_tuple_of_three(self):
        result = process_toc_context(
            full_text="",
            page_map={},
            current_context={},
            toc_parser_module=MagicMock(),
        )
        assert len(result) == 3
