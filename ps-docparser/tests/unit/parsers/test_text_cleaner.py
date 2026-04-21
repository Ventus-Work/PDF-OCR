"""
parsers/text_cleaner.py 단위 테스트 — Phase 10 Step 10-1
목표 커버리지: 41.29% → 80%+
"""
import re
import pytest

from parsers.text_cleaner import (
    extract_notes,
    extract_conditions,
    extract_cross_references,
    clean_text,
    remove_duplicate_notes,
    process_section_text,
    merge_spaced_korean,
)


# ══════════════════════════════════════════════════════════
# merge_spaced_korean
# ══════════════════════════════════════════════════════════

class TestMergeSpacedKorean:
    def test_spaced_hangul_merged(self):
        assert merge_spaced_korean("제 출 처") == "제출처"
        assert merge_spaced_korean("품   명") == "품명"

    def test_normal_text_unchanged(self):
        assert merge_spaced_korean("배관 Support") == "배관 Support"

    def test_mixed_line(self):
        text = "제 출 처\n배관 Support"
        result = merge_spaced_korean(text)
        lines = result.split('\n')
        assert lines[0] == "제출처"
        assert lines[1] == "배관 Support"

    def test_empty_string(self):
        assert merge_spaced_korean("") == ""

    def test_short_string(self):
        assert merge_spaced_korean("가") == "가"

    def test_numbers_not_merged(self):
        # 숫자 토큰은 한글 단일 글자 아님 → 변환 없음
        result = merge_spaced_korean("1 2 3")
        assert result == "1 2 3"

    def test_single_token_line_unchanged(self):
        assert merge_spaced_korean("배관공사") == "배관공사"

    def test_70_percent_threshold(self):
        # 3개 토큰 중 한글 2개(67%) → 변환 안 함
        result = merge_spaced_korean("가 나 ABC")
        # 비율 < 70% → 그대로 유지
        assert "가 나 ABC" in result

    def test_high_ratio_merged(self):
        # 4개 중 한글 4개(100%) → 변환
        result = merge_spaced_korean("가 나 다 라")
        assert " " not in result


# ══════════════════════════════════════════════════════════
# clean_text
# ══════════════════════════════════════════════════════════

class TestCleanText:
    def test_html_comment_removed(self):
        text = "안녕하세요<!-- 주석 -->\n반갑습니다."
        result = clean_text(text)
        assert "<!--" not in result
        assert "안녕하세요" in result

    def test_triple_newline_collapsed(self):
        text = "A\n\n\n\nB"
        result = clean_text(text)
        assert "\n\n\n" not in result
        assert "A" in result and "B" in result

    def test_chapter_title_removed_with_pattern(self):
        patterns = {"chapter_title": re.compile(r'제\s*\d+\s*장.*?장\s*')}
        text = "제 6 장 배관공사 장\n내용"
        result = clean_text(text, patterns=patterns)
        assert "내용" in result

    def test_chapter_title_preserved_without_pattern(self):
        text = "제1장 제목\n내용"
        result = clean_text(text)
        assert "제1장" in result

    def test_strips_leading_trailing(self):
        result = clean_text("  내용  ")
        assert result == "내용"

    def test_merge_spaced_korean_applied(self):
        # clean_text 내부에서 merge_spaced_korean도 호출
        result = clean_text("제 출 처")
        assert "제출처" in result

    def test_empty_string(self):
        assert clean_text("") == ""

    def test_multiline_html_comment(self):
        text = "시작\n<!-- 여러\n줄\n주석 -->\n끝"
        result = clean_text(text)
        assert "시작" in result and "끝" in result
        assert "<!--" not in result


# ══════════════════════════════════════════════════════════
# extract_notes
# ══════════════════════════════════════════════════════════

class TestExtractNotes:
    def test_no_pattern_returns_empty_and_original(self):
        text = "[주]\n① 첫 항목"
        notes, remaining = extract_notes(text)
        assert notes == []
        assert remaining == text

    def test_no_note_block_key_returns_original(self):
        text = "내용"
        notes, remaining = extract_notes(text, patterns={"other_key": None})
        assert notes == []
        assert remaining == text

    def test_extracts_note_items(self):
        # note_block_start 키가 있어야 추출 활성화
        text = "[주]\n① 첫 번째 항목입니다\n② 두 번째 항목입니다\n\n본문"
        patterns = {"note_block_start": re.compile(r'\[주\]')}
        notes, remaining = extract_notes(text, patterns)
        # 두 항목이 추출되어야 함
        assert len(notes) >= 1
        # 원문자가 제거되어야 함
        for note in notes:
            assert not note.startswith("①") and not note.startswith("②")


# ══════════════════════════════════════════════════════════
# extract_conditions
# ══════════════════════════════════════════════════════════

class TestExtractConditions:
    def test_no_pattern_returns_empty(self):
        text = "30%할증 적용"
        assert extract_conditions(text) == []

    def test_no_surcharge_key_returns_empty(self):
        assert extract_conditions("30%할증", patterns={"other": None}) == []

    def test_simple_percent_pattern_detected(self):
        patterns = {
            "surcharge": re.compile(
                r'(.{0,30}?)(\d+)%\s*(할증|가산|감산|증감)'
            )
        }
        text = "야간작업의 경우 30% 할증"
        conditions = extract_conditions(text, patterns)
        assert len(conditions) >= 1
        assert any("30%" in c["rate"] for c in conditions)

    def test_condition_type_감산(self):
        patterns = {
            "surcharge": re.compile(r'(.{0,30}?)(\d+)%\s*(감산|감가)')
        }
        text = "단순작업 20% 감산"
        conditions = extract_conditions(text, patterns)
        assert any(c["type"] == "감산" for c in conditions)


# ══════════════════════════════════════════════════════════
# extract_cross_references
# ══════════════════════════════════════════════════════════

class TestExtractCrossReferences:
    def test_no_pattern_returns_empty(self):
        assert extract_cross_references("제1장 1-1-1 참조") == []

    def test_no_cross_ref_key_returns_empty(self):
        assert extract_cross_references("내용", patterns={"other": None}) == []

    def test_detects_reference(self):
        patterns = {
            "cross_ref": re.compile(r'(?:제(\d+)장\s+)?(\d+-\d+-\d+)\s*(?:참조|준용)')
        }
        text = "제3장 3-1-2 참조하여 적용한다."
        refs = extract_cross_references(text, patterns)
        assert len(refs) >= 1
        assert refs[0]["target_section_id"] == "3-1-2"

    def test_chapter_format(self):
        patterns = {
            "cross_ref": re.compile(r'(?:제(\d+)장\s+)?(\d+-\d+-\d+)\s*참조')
        }
        text = "제5장 5-2-3 참조"
        refs = extract_cross_references(text, patterns)
        if refs:
            assert "제5장" in refs[0]["target_chapter"]


# ══════════════════════════════════════════════════════════
# remove_duplicate_notes
# ══════════════════════════════════════════════════════════

class TestRemoveDuplicateNotes:
    def test_no_table_notes_returns_all(self):
        notes = ["항목1", "항목2"]
        assert remove_duplicate_notes(notes, []) == notes

    def test_duplicate_removed(self):
        notes = ["공사비 포함", "별도 계상"]
        table_notes = ["공사비 포함"]
        result = remove_duplicate_notes(notes, table_notes)
        assert "공사비 포함" not in result
        assert "별도 계상" in result

    def test_partial_match_removed(self):
        notes = ["재료비 포함 공사"]
        table_notes = ["재료비 포함"]  # 노트가 테이블 노트의 부분 문자열
        result = remove_duplicate_notes(notes, table_notes)
        assert len(result) == 0

    def test_no_match_preserved(self):
        notes = ["고유한 내용"]
        table_notes = ["다른 내용"]
        result = remove_duplicate_notes(notes, table_notes)
        assert "고유한 내용" in result

    def test_empty_notes(self):
        assert remove_duplicate_notes([], ["항목"]) == []

    def test_whitespace_ignored_in_comparison(self):
        notes = ["공 사 비 포함"]
        table_notes = ["공사비포함"]  # 공백 제거 후 동일
        result = remove_duplicate_notes(notes, table_notes)
        assert len(result) == 0


# ══════════════════════════════════════════════════════════
# process_section_text
# ══════════════════════════════════════════════════════════

class TestProcessSectionText:
    def _make_section(self, text_without_tables="내용", **kwargs):
        base = {
            "section_id": "S-01",
            "title": "테스트 섹션",
            "department": "배관",
            "chapter": "제1장",
            "page": 5,
            "source_file": "test.md",
            "toc_title": "TOC 제목",
            "toc_section": "",
            "text_without_tables": text_without_tables,
            "tables": [],
        }
        base.update(kwargs)
        return base

    def test_basic_output_structure(self):
        section = self._make_section()
        result = process_section_text(section)
        required_keys = [
            "section_id", "title", "department", "chapter", "page",
            "source_file", "toc_title", "clean_text", "tables",
            "notes", "conditions", "cross_references",
            "revision_year", "unit_basis",
        ]
        for key in required_keys:
            assert key in result, f"Missing key: {key}"

    def test_section_id_preserved(self):
        section = self._make_section()
        result = process_section_text(section)
        assert result["section_id"] == "S-01"

    def test_clean_text_generated(self):
        section = self._make_section("안녕<!-- 주석 -->하세요")
        result = process_section_text(section)
        assert "<!--" not in result["clean_text"]
        assert "안녕" in result["clean_text"]

    def test_no_patterns_empty_metadata(self):
        section = self._make_section()
        result = process_section_text(section, patterns=None)
        assert result["notes"] == []
        assert result["conditions"] == []
        assert result["cross_references"] == []
        assert result["revision_year"] == ""
        assert result["unit_basis"] == ""

    def test_table_notes_deduped(self):
        section = self._make_section(
            text_without_tables="본문",
            tables=[{"notes_in_table": ["중복 항목"]}],
        )
        patterns = {"note_block_start": re.compile(r'\[주\]')}
        result = process_section_text(section, patterns)
        # 테이블 노트와 중복된 text notes는 제거됨
        assert "중복 항목" not in result["notes"]

    def test_uses_text_without_tables_key(self):
        section = self._make_section("핵심 내용")
        result = process_section_text(section)
        assert "핵심 내용" in result["clean_text"]

    def test_falls_back_to_raw_text(self):
        section = {
            "section_id": "S-01",
            "title": "제목",
            "department": "",
            "chapter": "",
            "page": 0,
            "source_file": "",
            "toc_title": "",
            "raw_text": "원본 내용",
            "tables": [],
        }
        result = process_section_text(section)
        assert "원본 내용" in result["clean_text"]

    def test_revision_year_two_digit(self):
        patterns = {
            "revision": re.compile(r"'(\d{2})년\s*보완"),
            "note_block_start": re.compile(r'\[주\]'),
        }
        section = self._make_section("'24년 보완 적용")
        result = process_section_text(section, patterns)
        assert result["revision_year"] == "2024"

    def test_page_number_preserved(self):
        section = self._make_section()
        result = process_section_text(section)
        assert result["page"] == 5
