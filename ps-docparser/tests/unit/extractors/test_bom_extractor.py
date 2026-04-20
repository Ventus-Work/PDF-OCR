"""
bom_extractor.py 단위 테스트 (P1) - Phase 8 안전망
"""
import pytest
from extractors.bom_extractor import _sanitize_html, extract_bom
from extractors.bom_types import BomSection


class TestSanitizeHtml:
    def test_sanitize_html_basic(self):
        html = "<table><tr><td>SIZE</td><td>PIPE</td></tr></table>"
        sanitized = _sanitize_html(html)
        assert "<table>" not in sanitized
        assert "|" in sanitized
        assert "SIZE | PIPE" in sanitized

    def test_sanitize_html_rows_split(self):
        html = "<tr><td>A</td></tr><tr><td>B</td></tr>"
        sanitized = _sanitize_html(html)
        # </tr>이 개행으로 변환되어 2행이 되어야 함
        non_empty_lines = [l for l in sanitized.split("\n") if l.strip()]
        assert len(non_empty_lines) == 2

    def test_sanitize_html_entities(self):
        html = "Size&amp;Type &#x27;PIPE&#x27; &nbsp;END"
        sanitized = _sanitize_html(html)
        assert "&amp;" not in sanitized
        assert "&#x27;" not in sanitized
        assert "&nbsp;" not in sanitized
        assert "&" in sanitized  # &amp; → & 로 복원

    def test_sanitize_html_empty_input(self):
        assert _sanitize_html("") == ""
        assert _sanitize_html("   ").strip() == ""

    def test_sanitize_html_nested_tags(self):
        # 중첩 태그도 모두 제거되어야 함
        html = "<div><span><b>TEXT</b></span></div>"
        sanitized = _sanitize_html(html)
        assert "<" not in sanitized
        assert ">" not in sanitized
        assert "TEXT" in sanitized


class TestBomSection:
    def test_bom_section_fields(self):
        section = BomSection(section_type="BOM", rows=[["1", "PIPE"]], raw_row_count=1)
        assert section.section_type == "BOM"
        assert section.raw_row_count == 1
        assert len(section.rows) == 1

    def test_bom_section_empty(self):
        section = BomSection(section_type="LINE LIST", rows=[], raw_row_count=0)
        assert section.raw_row_count == 0
        assert section.rows == []


class TestExtractBomStateMachine:
    @pytest.fixture
    def minimal_keywords(self):
        return {
            "anchor_bom": ["BILL OF MATERIAL", "BOM"],
            "anchor_ll": ["LINE LIST"],
            "bom_header_a": ["ITEM"],
            "bom_header_b": ["SIZE"],
            "bom_header_c": ["QTY"],
            "ll_header_a": ["LINE"],
            "ll_header_b": ["FROM"],
            "ll_header_c": ["TO"],
            "kill": ["NOTES", "END OF BOM"],
            "noise_row": [],
            "rev_markers": [],
        }

    def test_extract_bom_empty_text(self, minimal_keywords):
        res = extract_bom("", minimal_keywords)
        # 빈 입력 시 섹션 없음
        assert res is not None
        assert len(getattr(res, "sections", [])) == 0

    def test_extract_bom_no_anchor(self, minimal_keywords):
        # 앵커 키워드 없는 텍스트는 IDLE 유지
        text = "그냥 텍스트입니다. 표도 없습니다."
        res = extract_bom(text, minimal_keywords)
        assert len(getattr(res, "sections", [])) == 0
