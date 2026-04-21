"""
extractors/toc_parser.py 단위 테스트 — Phase 10 Step 10-2
목표 커버리지: 11.74% → 70%+
"""
import json
import pytest
from pathlib import Path

from extractors.toc_parser import (
    _get_chapter_num,
    _normalize_section_name,
    _split_line_at_chapter,
    _fix_split_chapter_id,
    parse_toc,
    build_page_to_sections_map,
    get_current_context,
    get_active_section,
    get_section_info,
    inject_section_markers,
)


# ══════════════════════════════════════════════════════════
# 픽스처
# ══════════════════════════════════════════════════════════

@pytest.fixture
def simple_section_map():
    return {
        "1-1-1": {
            "id": "1-1-1",
            "chapter": "공통부문",
            "section": "제1장 총칙",
            "title": "일반사항",
            "page": 5,
        },
        "2-1-1": {
            "id": "2-1-1",
            "chapter": "토목부문",
            "section": "제2장 토공사",
            "title": "터파기",
            "page": 10,
        },
        "2-1-2": {
            "id": "2-1-2",
            "chapter": "토목부문",
            "section": "제2장 토공사",
            "title": "되메우기",
            "page": 15,
        },
    }


@pytest.fixture
def sample_toc_file(tmp_path):
    """실제 목차 파일 형식 픽스처."""
    content = (
        "공통부문 제1장 총 칙 1\n"
        "1-1-1 일반사항 ··· 5\n"
        "1-1-2 용어정의 ··· 7\n"
        "토목부문 제2장 토공사 9\n"
        "2-1-1 터파기 ··· 10\n"
        "2-1-2 되메우기 ··· 15\n"
    )
    toc_file = tmp_path / "toc.txt"
    toc_file.write_text(content, encoding="utf-8")
    return str(toc_file)


# ══════════════════════════════════════════════════════════
# _get_chapter_num
# ══════════════════════════════════════════════════════════

class TestGetChapterNum:
    def test_single_digit(self):
        assert _get_chapter_num("제1장") == 1
        assert _get_chapter_num("제7장 공사") == 7

    def test_double_digit(self):
        assert _get_chapter_num("제12장") == 12

    def test_no_chapter(self):
        assert _get_chapter_num("공통부문") == 0

    def test_embedded_in_sentence(self):
        assert _get_chapter_num("제3장 배관공사") == 3


# ══════════════════════════════════════════════════════════
# _normalize_section_name
# ══════════════════════════════════════════════════════════

class TestNormalizeSectionName:
    def test_basic(self):
        assert _normalize_section_name("제1장 공 통") == "제1장 공통"

    def test_two_char_collapse(self):
        result = _normalize_section_name("제5장 배 관")
        assert result == "제5장 배관"

    def test_normal_name_preserved(self):
        result = _normalize_section_name("제2장 지붕 및 홈통공사")
        assert "지붕 및 홈통공사" in result

    def test_preserves_chapter_prefix(self):
        res = _normalize_section_name("제2장 구조물")
        assert "제2장" in res
        assert "구조물" in res

    def test_strips_extra_whitespace(self):
        res = _normalize_section_name("  제3장 공사  ")
        assert res == res.strip()

    def test_empty_input(self):
        assert _normalize_section_name("") == ""

    def test_no_chapter_prefix(self):
        result = _normalize_section_name("공통부문")
        assert result == "공통부문"


# ══════════════════════════════════════════════════════════
# _split_line_at_chapter
# ══════════════════════════════════════════════════════════

class TestSplitLineAtChapter:
    def test_simple_subsection_line_unchanged(self):
        line = "1-1-1 일반사항 ··· 5"
        result = _split_line_at_chapter(line)
        assert result == [line]

    def test_non_subsection_unchanged(self):
        line = "공통부문 제1장 총칙 1"
        result = _split_line_at_chapter(line)
        assert result == [line]

    def test_returns_list(self):
        result = _split_line_at_chapter("1-1-1 항목 5")
        assert isinstance(result, list)
        assert len(result) >= 1


# ══════════════════════════════════════════════════════════
# _fix_split_chapter_id
# ══════════════════════════════════════════════════════════

class TestFixSplitChapterId:
    def test_single_digit_chapter_unchanged(self):
        assert _fix_split_chapter_id("5-1-1", 5) == "5-1-1"

    def test_double_digit_chapter_fixed(self):
        # chapter_num=12, section_id="2-1-1" → "12-1-1"
        result = _fix_split_chapter_id("2-1-1", 12)
        assert result == "12-1-1"

    def test_already_correct(self):
        assert _fix_split_chapter_id("12-1-1", 12) == "12-1-1"


# ══════════════════════════════════════════════════════════
# parse_toc
# ══════════════════════════════════════════════════════════

class TestParseToc:
    def test_parses_sections(self, sample_toc_file):
        result = parse_toc(sample_toc_file)
        assert isinstance(result, dict)
        assert len(result) >= 1

    def test_section_has_required_keys(self, sample_toc_file):
        result = parse_toc(sample_toc_file)
        if result:
            first = next(iter(result.values()))
            assert "id" in first
            assert "title" in first
            assert "page" in first

    def test_page_is_integer(self, sample_toc_file):
        result = parse_toc(sample_toc_file)
        for info in result.values():
            assert isinstance(info["page"], int)

    def test_subsection_id_format(self, sample_toc_file):
        result = parse_toc(sample_toc_file)
        for key in result:
            base_key = key.split("#")[0]
            assert re.match(r'^\d+-\d+(-\d+)?$', base_key), f"Bad key: {key}"

    def test_duplicate_ids_suffixed(self, tmp_path):
        content = (
            "공통부문 제1장 총칙 1\n"
            "1-1-1 항목A ··· 5\n"
            "1-1-1 항목B ··· 6\n"
        )
        toc_file = tmp_path / "dup_toc.txt"
        toc_file.write_text(content, encoding="utf-8")
        result = parse_toc(str(toc_file))
        # 중복 키는 #2로 구분
        assert "1-1-1" in result
        assert "1-1-1#2" in result

    def test_comment_lines_skipped(self, tmp_path):
        content = (
            "<!-- 주석 -->\n"
            "공통부문 제1장 총칙 1\n"
            "1-1-1 항목 ··· 5\n"
        )
        toc_file = tmp_path / "comment_toc.txt"
        toc_file.write_text(content, encoding="utf-8")
        result = parse_toc(str(toc_file))
        assert len(result) == 1

    def test_chapter_section_extracted(self, sample_toc_file):
        result = parse_toc(sample_toc_file)
        for info in result.values():
            assert info.get("chapter") or info.get("section")


import re


# ══════════════════════════════════════════════════════════
# build_page_to_sections_map
# ══════════════════════════════════════════════════════════

class TestBuildPageToSectionsMap:
    def test_basic_mapping(self, simple_section_map):
        page_map = build_page_to_sections_map(simple_section_map)
        assert 5 in page_map
        assert 10 in page_map
        assert 15 in page_map

    def test_multiple_sections_same_page(self):
        section_map = {
            "A-1": {"id": "A-1", "chapter": "부문", "section": "제1장", "title": "A", "page": 5},
            "B-1": {"id": "B-1", "chapter": "부문", "section": "제1장", "title": "B", "page": 5},
        }
        page_map = build_page_to_sections_map(section_map)
        assert len(page_map[5]) == 2

    def test_zero_page_excluded(self):
        section_map = {
            "X-1": {"id": "X-1", "chapter": "", "section": "", "title": "미정", "page": 0},
        }
        page_map = build_page_to_sections_map(section_map)
        assert 0 not in page_map

    def test_empty_section_map(self):
        assert build_page_to_sections_map({}) == {}


# ══════════════════════════════════════════════════════════
# get_current_context
# ══════════════════════════════════════════════════════════

class TestGetCurrentContext:
    def test_page_in_map(self, simple_section_map):
        page_map = build_page_to_sections_map(simple_section_map)
        ctx = get_current_context(5, page_map)
        assert ctx["sections"]
        assert ctx["chapter"] == "공통부문"

    def test_page_not_in_map_returns_empty_sections(self, simple_section_map):
        page_map = build_page_to_sections_map(simple_section_map)
        ctx = get_current_context(999, page_map)
        assert ctx["sections"] == []

    def test_last_context_preserved_for_unknown_page(self, simple_section_map):
        page_map = build_page_to_sections_map(simple_section_map)
        last = {"chapter": "이전부문", "section": "이전장", "sections": []}
        ctx = get_current_context(999, page_map, last_context=last)
        assert ctx["chapter"] == "이전부문"

    def test_no_last_context(self):
        ctx = get_current_context(999, {})
        assert ctx["sections"] == []
        assert ctx["chapter"] == ""


# ══════════════════════════════════════════════════════════
# get_active_section
# ══════════════════════════════════════════════════════════

class TestGetActiveSection:
    def test_returns_latest_before_page(self, simple_section_map):
        # 페이지 12: p5(1-1-1)과 p10(2-1-1) 중 p10이 더 최근
        result = get_active_section(12, simple_section_map)
        assert result is not None
        assert result["page"] == 10

    def test_exact_page_match(self, simple_section_map):
        result = get_active_section(5, simple_section_map)
        assert result["page"] == 5

    def test_page_before_any_section(self, simple_section_map):
        result = get_active_section(2, simple_section_map)
        assert result is None

    def test_empty_section_map(self):
        assert get_active_section(10, {}) is None

    def test_zero_page(self, simple_section_map):
        assert get_active_section(0, simple_section_map) is None


# ══════════════════════════════════════════════════════════
# get_section_info
# ══════════════════════════════════════════════════════════

class TestGetSectionInfo:
    def test_existing_section(self, simple_section_map):
        result = get_section_info("1-1-1", simple_section_map)
        assert "공통부문" in result
        assert "일반사항" in result

    def test_missing_section(self, simple_section_map):
        result = get_section_info("99-99-99", simple_section_map)
        assert result == ""

    def test_lookup_by_id_field(self, simple_section_map):
        # key가 section_id와 다를 때 id 필드로 검색
        section_map = {
            "1-1-1#2": {
                "id": "1-1-1",
                "chapter": "공통부문",
                "section": "제1장",
                "title": "중복항목",
                "page": 6,
            }
        }
        result = get_section_info("1-1-1", section_map)
        assert "중복항목" in result

    def test_separator_format(self, simple_section_map):
        result = get_section_info("1-1-1", simple_section_map)
        assert " > " in result


# ══════════════════════════════════════════════════════════
# inject_section_markers
# ══════════════════════════════════════════════════════════

class TestInjectSectionMarkers:
    def test_empty_section_map_unchanged(self):
        text = "1-1-1 항목"
        assert inject_section_markers(text, {}) == text

    def test_marker_injected(self, simple_section_map):
        text = "1-1-1 일반사항 내용"
        result = inject_section_markers(text, simple_section_map)
        assert "<!-- SECTION:" in result

    def test_unknown_section_unchanged(self, simple_section_map):
        text = "9-9-9 알 수 없는 항목"
        result = inject_section_markers(text, simple_section_map)
        # 알 수 없는 섹션은 마커 없이 그대로
        assert "<!-- SECTION:" not in result

    def test_multiline_text(self, simple_section_map):
        text = "서문\n1-1-1 일반사항\n2-1-1 터파기\n끝"
        result = inject_section_markers(text, simple_section_map)
        assert result.count("<!-- SECTION:") == 2
