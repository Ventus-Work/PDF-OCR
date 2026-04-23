"""
parsers/section_splitter.py 단위 테스트 — Phase 10 Step 10-1
목표 커버리지: 21.95% → 75%+
"""
import json
import re
import pytest
from pathlib import Path

from parsers.section_splitter import (
    load_toc,
    build_reverse_map,
    parse_section_markers,
    parse_page_markers,
    get_page_for_position,
    redistribute_text_to_sections,
    split_sections_by_title_patterns,
    split_sections,
)


# ══════════════════════════════════════════════════════════
# 픽스처
# ══════════════════════════════════════════════════════════

@pytest.fixture
def simple_toc():
    return {
        "S-1": {"id": "S-1", "title": "일반사항", "chapter": "건축"},
        "S-2": {"id": "S-2", "title": "배관공사", "chapter": "토목"},
    }


@pytest.fixture
def section_text_single():
    return (
        "<!-- SECTION: S-1 | 일반사항 | 부문:건축 | 장:제1장 -->\n"
        "<!-- PAGE 5 -->\n"
        "섹션 1의 내용입니다.\n"
        "두 번째 줄입니다.\n"
    )


@pytest.fixture
def section_text_multi():
    return (
        "<!-- PAGE 1 -->\n"
        "<!-- SECTION: S-1 | 일반사항 | 부문:건축 | 장:제1장 -->\n"
        "섹션 1 내용\n"
        "<!-- PAGE 3 -->\n"
        "<!-- SECTION: S-2 | 배관공사 | 부문:토목 | 장:제2장 -->\n"
        "섹션 2 내용\n"
    )


# ══════════════════════════════════════════════════════════
# load_toc
# ══════════════════════════════════════════════════════════

class TestLoadToc:
    def test_loads_section_map(self, tmp_path):
        toc_data = {"section_map": {"S-1": {"id": "S-1", "title": "테스트"}}}
        toc_file = tmp_path / "toc.json"
        toc_file.write_text(json.dumps(toc_data, ensure_ascii=False), encoding="utf-8")

        result = load_toc(toc_file)
        assert "S-1" in result
        assert result["S-1"]["title"] == "테스트"

    def test_loads_flat_dict(self, tmp_path):
        # section_map 키 없이 바로 dict인 경우
        toc_data = {"S-1": {"id": "S-1", "title": "직접"}}
        toc_file = tmp_path / "toc.json"
        toc_file.write_text(json.dumps(toc_data, ensure_ascii=False), encoding="utf-8")

        result = load_toc(toc_file)
        assert "S-1" in result

    def test_missing_file_returns_empty(self, tmp_path):
        result = load_toc(tmp_path / "nonexistent.json")
        assert result == {}

    def test_empty_section_map(self, tmp_path):
        toc_data = {"section_map": {}}
        toc_file = tmp_path / "toc.json"
        toc_file.write_text(json.dumps(toc_data), encoding="utf-8")
        assert load_toc(toc_file) == {}


# ══════════════════════════════════════════════════════════
# build_reverse_map
# ══════════════════════════════════════════════════════════

class TestBuildReverseMap:
    def test_basic_reverse_map(self, simple_toc):
        rm = build_reverse_map(simple_toc)
        assert ("S-1", "건축") in rm
        assert rm[("S-1", "건축")] == "S-1"

    def test_empty_toc(self):
        assert build_reverse_map({}) == {}

    def test_chapter_used_as_department(self):
        toc = {"K-1": {"id": "K-1", "title": "항목", "chapter": "배관"}}
        rm = build_reverse_map(toc)
        assert ("K-1", "배관") in rm

    def test_entry_without_chapter(self):
        toc = {"K-1": {"id": "K-1", "title": "항목"}}
        rm = build_reverse_map(toc)
        # chapter 없으면 빈 문자열 키
        assert ("K-1", "") in rm


# ══════════════════════════════════════════════════════════
# parse_section_markers
# ══════════════════════════════════════════════════════════

class TestParseSectionMarkers:
    def test_single_marker(self):
        text = "<!-- SECTION: S-1 | 일반사항 | 부문:건축 | 장:제1장 -->"
        m = parse_section_markers(text)
        assert len(m) == 1
        assert m[0]["section_id"] == "S-1"
        assert m[0]["title"] == "일반사항"
        assert m[0]["department"] == "건축"
        assert m[0]["chapter"] == "제1장"

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
        text = "<!-- SECTION: S-X -->"
        m = parse_section_markers(text)
        assert isinstance(m, list)

    def test_pos_and_end_populated(self):
        text = "prefix <!-- SECTION: S-1 | 제목 | 부문:부문 | 장:장 --> suffix"
        m = parse_section_markers(text)
        assert len(m) == 1
        assert m[0]["pos"] > 0
        assert m[0]["end"] > m[0]["pos"]


# ══════════════════════════════════════════════════════════
# parse_page_markers
# ══════════════════════════════════════════════════════════

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

    def test_no_page_marker(self):
        assert parse_page_markers("텍스트만") == []

    def test_pos_is_populated(self):
        text = "앞 <!-- PAGE 5 --> 뒤"
        m = parse_page_markers(text)
        assert m[0]["pos"] > 0


# ══════════════════════════════════════════════════════════
# get_page_for_position
# ══════════════════════════════════════════════════════════

class TestGetPageForPosition:
    def _markers(self, pages_and_positions):
        return [{"page": p, "pos": pos} for p, pos in pages_and_positions]

    def test_before_any_marker_uses_start_page(self):
        markers = self._markers([(5, 100)])
        assert get_page_for_position(markers, 50, 1) == 1

    def test_at_marker_uses_that_page(self):
        markers = self._markers([(5, 100)])
        assert get_page_for_position(markers, 100, 1) == 5

    def test_after_marker_uses_that_page(self):
        markers = self._markers([(5, 100)])
        assert get_page_for_position(markers, 200, 1) == 5

    def test_between_two_markers(self):
        markers = self._markers([(3, 100), (7, 300)])
        assert get_page_for_position(markers, 200, 1) == 3

    def test_empty_markers(self):
        assert get_page_for_position([], 100, 0) == 0


# ══════════════════════════════════════════════════════════
# redistribute_text_to_sections
# ══════════════════════════════════════════════════════════

class TestRedistributeTextToSections:
    def _marker(self, sid, title):
        return {"section_id": sid, "title": title}

    def test_single_marker_gets_all_text(self):
        markers = [self._marker("S-1", "일반사항")]
        result = redistribute_text_to_sections(markers, "전체 내용")
        assert result["S-1"] == "전체 내용"

    def test_empty_text(self):
        markers = [self._marker("S-1", "A"), self._marker("S-2", "B")]
        result = redistribute_text_to_sections(markers, "")
        assert result == {"S-1": "", "S-2": ""}

    def test_empty_markers(self):
        result = redistribute_text_to_sections([], "내용")
        assert result == {}

    def test_two_markers_text_split(self):
        markers = [self._marker("S-1", "첫번째"), self._marker("S-2", "두번째")]
        text = "첫번째 섹션 내용\n두번째 섹션 내용"
        result = redistribute_text_to_sections(markers, text)
        # 두 섹션 모두 키가 존재해야 함
        assert "S-1" in result
        assert "S-2" in result

    def test_no_split_point_last_section_gets_text(self):
        markers = [self._marker("S-1", "없는제목"), self._marker("S-2", "없는제목2")]
        text = "분할점 없는 텍스트"
        result = redistribute_text_to_sections(markers, text)
        # 마지막 섹션이 전체 텍스트를 가져야 함
        assert result["S-2"] == text


# ══════════════════════════════════════════════════════════
# split_sections (통합)
# ══════════════════════════════════════════════════════════

class TestSplitSections:
    def test_no_section_marker_returns_empty(self):
        result = split_sections("섹션 마커 없음", "test.md", {}, {})
        assert result == []

    def test_single_section(self, simple_toc):
        text = (
            "<!-- PAGE 1 -->\n"
            "<!-- SECTION: S-1 | 일반사항 | 부문:건축 | 장:제1장 -->\n"
            "섹션 내용입니다.\n"
        )
        rm = build_reverse_map(simple_toc)
        sections = split_sections(text, "test.md", simple_toc, rm)
        assert len(sections) >= 1
        s = sections[0]
        assert s["title"] == "일반사항"
        assert s["source_file"] == "test.md"

    def test_multiple_sections(self, simple_toc):
        text = (
            "<!-- PAGE 1 -->\n"
            "<!-- SECTION: S-1 | 일반사항 | 부문:건축 | 장:제1장 -->\n"
            "섹션 1 내용\n"
            "<!-- PAGE 3 -->\n"
            "<!-- SECTION: S-2 | 배관공사 | 부문:토목 | 장:제2장 -->\n"
            "섹션 2 내용\n"
        )
        rm = build_reverse_map(simple_toc)
        sections = split_sections(text, "test.md", simple_toc, rm)
        assert len(sections) == 2

    def test_page_assigned_correctly(self, simple_toc):
        text = (
            "<!-- PAGE 5 -->\n"
            "<!-- SECTION: S-1 | 일반사항 | 부문:건축 | 장:제1장 -->\n"
            "내용\n"
        )
        rm = build_reverse_map(simple_toc)
        sections = split_sections(text, "test.md", simple_toc, rm)
        assert sections[0]["page"] == 5

    def test_section_marker_removed_from_raw_text(self, simple_toc):
        text = (
            "<!-- SECTION: S-1 | 일반사항 | 부문:건축 | 장:제1장 -->\n"
            "실제 내용만 남아야 함\n"
        )
        rm = build_reverse_map(simple_toc)
        sections = split_sections(text, "test.md", simple_toc, rm)
        if sections:
            assert "<!-- SECTION:" not in sections[0]["raw_text"]

    def test_has_content_flag(self, simple_toc):
        text = (
            "<!-- SECTION: S-1 | 일반사항 | 부문:건축 | 장:제1장 -->\n"
            "충분히 긴 내용 텍스트가 여기 있습니다.\n"
        )
        rm = build_reverse_map(simple_toc)
        sections = split_sections(text, "test.md", simple_toc, rm)
        assert sections[0]["has_content"] is True

    def test_empty_toc_still_parses(self):
        text = (
            "<!-- SECTION: S-1 | 제목 | 부문:부문 | 장:장 -->\n"
            "내용\n"
        )
        sections = split_sections(text, "test.md", {}, {})
        assert len(sections) >= 1


class TestSplitSectionsByTitlePatterns:
    def test_splits_pumsem_like_titles_without_section_markers(self):
        patterns = {
            "chapter_title": re.compile(r"^(제\d+장\s+.+)$", re.MULTILINE),
            "section_title": re.compile(r"^(\d+-\d+(?:-\d+)?)\s+(.+?)$", re.MULTILINE),
        }
        text = (
            "제1장 적용기준\n"
            "머리말입니다.\n"
            "1-1 일반사항\n"
            "일반사항 본문\n"
            "1-2 단위표준\n"
            "단위표준 본문\n"
        )
        sections = split_sections_by_title_patterns(text, "pumsem.md", patterns)
        assert [section["section_id"] for section in sections] == ["intro", "1-1", "1-2"]
        assert sections[1]["title"] == "일반사항"
        assert sections[1]["chapter"] == "제1장 적용기준"
        assert "1-1 일반사항" in sections[1]["raw_text"]

    def test_returns_empty_when_no_section_title_pattern_matches(self):
        patterns = {
            "chapter_title": re.compile(r"^(제\d+장\s+.+)$", re.MULTILINE),
            "section_title": re.compile(r"^(\d+-\d+(?:-\d+)?)\s+(.+?)$", re.MULTILINE),
        }
        assert split_sections_by_title_patterns("제1장 적용기준\n본문만", "pumsem.md", patterns) == []
