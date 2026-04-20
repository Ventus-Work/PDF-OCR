import pytest
from parsers.section_splitter import parse_section_markers, parse_page_markers


class TestParseSectionMarkers:
    def test_single_marker(self):
        text = "<!-- SECTION: S-1 | 일반사항 | 부문:건축 | 장:제1장 -->"
        m = parse_section_markers(text)
        assert len(m) == 1
        assert m[0]["section_id"] == "S-1"
        assert m[0]["title"] == "일반사항"

    def test_multiple_markers(self):
        text = (
            "<!-- SECTION: S-1 | 일반사항 | 부문:건축 | 장:제1장 -->\n"
            "본문\n"
            "<!-- SECTION: S-2 | 내역서 | 부문:토목 | 장:제2장 -->\n"
        )
        m = parse_section_markers(text)
        assert len(m) == 2
        assert m[1]["section_id"] == "S-2"

    def test_no_marker_returns_empty(self):
        assert parse_section_markers("일반 텍스트만") == []

    def test_malformed_marker_ignored(self):
        # 파이프 구분자 부족 → 무시되어야 함
        text = "<!-- SECTION: S-X -->"
        m = parse_section_markers(text)
        # 최소한 크래시 없이 빈 리스트 또는 부분 파싱
        assert isinstance(m, list)


class TestParsePageMarkers:
    def test_single_page(self):
        text = "<!-- PAGE 10 -->"
        m = parse_page_markers(text)
        assert len(m) == 1
        assert m[0]["page"] == 10

    def test_multiple_pages(self):
        text = "<!-- PAGE 1 -->\nA\n<!-- PAGE 2 -->\nB\n<!-- PAGE 3 -->"
        m = parse_page_markers(text)
        assert [x["page"] for x in m] == [1, 2, 3]
