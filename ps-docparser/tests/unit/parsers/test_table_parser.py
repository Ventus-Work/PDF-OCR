"""
parsers/table_parser.py 단위 테스트 — Phase 10 Step 10-1
목표 커버리지: 18.45% → 75%+
"""
import pytest
from bs4 import BeautifulSoup

from parsers.table_parser import (
    _make_soup,
    expand_table,
    extract_cell_text,
    clean_cell_text,
    parse_html_table,
    extract_tables_from_text,
    remove_tables_from_text,
    classify_table,
    detect_header_rows,
    build_composite_headers,
    is_note_row,
    try_numeric,
    parse_single_table,
    process_section_tables,
)


# ══════════════════════════════════════════════════════════
# 유틸 헬퍼
# ══════════════════════════════════════════════════════════

def make_tag(html: str) -> BeautifulSoup:
    """HTML 테이블 태그를 BeautifulSoup Tag로 반환."""
    soup = BeautifulSoup(html, "html.parser")
    return soup.find("table")


# ══════════════════════════════════════════════════════════
# _make_soup
# ══════════════════════════════════════════════════════════

class TestMakeSoup:
    def test_returns_beautifulsoup(self):
        soup = _make_soup("<table><tr><td>셀</td></tr></table>")
        assert soup is not None
        assert soup.find("table") is not None

    def test_malformed_html_no_crash(self):
        # 닫힌 태그 없어도 크래시 없이 파싱
        soup = _make_soup("<table><tr><td>셀")
        assert soup is not None


# ══════════════════════════════════════════════════════════
# expand_table — rowspan/colspan 전개
# ══════════════════════════════════════════════════════════

class TestExpandTable:
    def test_simple_table(self):
        html = "<table><tr><td>A</td><td>B</td></tr><tr><td>1</td><td>2</td></tr></table>"
        tag = make_tag(html)
        grid = expand_table(tag)
        assert grid == [["A", "B"], ["1", "2"]]

    def test_colspan_expands(self):
        html = (
            "<table>"
            "<tr><td colspan='2'>헤더</td></tr>"
            "<tr><td>A</td><td>B</td></tr>"
            "</table>"
        )
        tag = make_tag(html)
        grid = expand_table(tag)
        assert grid[0] == ["헤더", "헤더"]
        assert grid[1] == ["A", "B"]

    def test_rowspan_expands(self):
        html = (
            "<table>"
            "<tr><td rowspan='2'>병합</td><td>R1C2</td></tr>"
            "<tr><td>R2C2</td></tr>"
            "</table>"
        )
        tag = make_tag(html)
        grid = expand_table(tag)
        assert grid[0][0] == "병합"
        assert grid[1][0] == "병합"
        assert grid[0][1] == "R1C2"
        assert grid[1][1] == "R2C2"

    def test_rowspan_and_colspan_combined(self):
        html = (
            "<table>"
            "<tr><td rowspan='2' colspan='2'>대형셀</td><td>R1C3</td></tr>"
            "<tr><td>R2C3</td></tr>"
            "<tr><td>R3C1</td><td>R3C2</td><td>R3C3</td></tr>"
            "</table>"
        )
        tag = make_tag(html)
        grid = expand_table(tag)
        assert grid[0][0] == "대형셀"
        assert grid[0][1] == "대형셀"
        assert grid[1][0] == "대형셀"
        assert grid[1][1] == "대형셀"
        assert grid[2] == ["R3C1", "R3C2", "R3C3"]

    def test_empty_table_returns_empty(self):
        html = "<table></table>"
        tag = make_tag(html)
        assert expand_table(tag) == []

    def test_th_cells_included(self):
        html = "<table><tr><th>이름</th><th>값</th></tr><tr><td>A</td><td>1</td></tr></table>"
        tag = make_tag(html)
        grid = expand_table(tag)
        assert grid[0] == ["이름", "값"]

    def test_none_cells_filled_with_empty_string(self):
        html = (
            "<table>"
            "<tr><td colspan='3'>A</td></tr>"
            "<tr><td>B</td><td>C</td><td>D</td></tr>"
            "</table>"
        )
        tag = make_tag(html)
        grid = expand_table(tag)
        # 모든 셀은 None이 아닌 문자열
        for row in grid:
            for cell in row:
                assert cell is not None
                assert isinstance(cell, str)


# ══════════════════════════════════════════════════════════
# extract_cell_text
# ══════════════════════════════════════════════════════════

class TestExtractCellText:
    def _cell(self, html: str):
        soup = BeautifulSoup(f"<td>{html}</td>", "html.parser")
        return soup.find("td")

    def test_plain_text(self):
        assert extract_cell_text(self._cell("안녕")) == "안녕"

    def test_sup_converted(self):
        result = extract_cell_text(self._cell("10<sup>-7</sup>"))
        assert "^-7" in result

    def test_sub_converted(self):
        result = extract_cell_text(self._cell("H<sub>2</sub>O"))
        assert "_2" in result

    def test_br_becomes_space(self):
        result = extract_cell_text(self._cell("줄1<br/>줄2"))
        assert "줄1" in result and "줄2" in result

    def test_html_entities_unescaped(self):
        result = extract_cell_text(self._cell("&lt;값&gt;"))
        assert "<값>" in result

    def test_nbsp_normalized(self):
        cell = BeautifulSoup("<td>\xa0셀\xa0</td>", "html.parser").find("td")
        result = extract_cell_text(cell)
        assert result == "셀"


# ══════════════════════════════════════════════════════════
# clean_cell_text
# ══════════════════════════════════════════════════════════

class TestCleanCellText:
    def test_strips_whitespace(self):
        assert clean_cell_text("  셀   내용  ") == "셀 내용"

    def test_newline_to_space(self):
        assert clean_cell_text("줄\n바꿈") == "줄 바꿈"

    def test_nbsp_replaced(self):
        assert clean_cell_text("A\xa0B") == "A B"

    def test_empty_string(self):
        assert clean_cell_text("") == ""

    def test_multiple_spaces_collapsed(self):
        assert clean_cell_text("A   B   C") == "A B C"


# ══════════════════════════════════════════════════════════
# parse_html_table
# ══════════════════════════════════════════════════════════

class TestParseHtmlTable:
    def test_basic(self):
        html = "<table><tr><td>A</td><td>B</td></tr></table>"
        grid = parse_html_table(html)
        assert grid == [["A", "B"]]

    def test_no_table_returns_empty(self):
        assert parse_html_table("<div>테이블 없음</div>") == []

    def test_empty_string(self):
        assert parse_html_table("") == []

    def test_with_surrounding_text(self):
        html = "서문 텍스트 <table><tr><td>X</td></tr></table> 후문"
        grid = parse_html_table(html)
        assert grid == [["X"]]


# ══════════════════════════════════════════════════════════
# extract_tables_from_text / remove_tables_from_text
# ══════════════════════════════════════════════════════════

class TestExtractRemoveTables:
    def test_extract_single(self):
        text = "앞 <table><tr><td>A</td></tr></table> 뒤"
        tables = extract_tables_from_text(text)
        assert len(tables) == 1
        assert "html" in tables[0]
        assert tables[0]["start"] < tables[0]["end"]

    def test_extract_multiple(self):
        text = "<table><tr><td>1</td></tr></table> 중간 <table><tr><td>2</td></tr></table>"
        tables = extract_tables_from_text(text)
        assert len(tables) == 2

    def test_extract_no_table(self):
        assert extract_tables_from_text("텍스트만") == []

    def test_remove_single(self):
        text = "앞 <table><tr><td>A</td></tr></table> 뒤"
        result = remove_tables_from_text(text)
        assert "<table>" not in result
        assert "앞" in result and "뒤" in result

    def test_remove_multiple(self):
        text = "<table><tr><td>1</td></tr></table> 중간 <table><tr><td>2</td></tr></table>"
        result = remove_tables_from_text(text)
        assert "<table>" not in result
        assert "중간" in result

    def test_remove_no_table(self):
        text = "테이블 없음"
        assert remove_tables_from_text(text) == text


# ══════════════════════════════════════════════════════════
# classify_table
# ══════════════════════════════════════════════════════════

class TestClassifyTable:
    def test_no_keywords_returns_general(self):
        assert classify_table(["이름", "값"], []) == "general"

    def test_empty_keywords_returns_general(self):
        assert classify_table(["이름", "값"], [], type_keywords={}) == "general"

    def test_a_type_by_header(self):
        kw = {"A_품셈": ["공종명", "단위", "단가"], "A_품셈_행키워드": []}
        headers = ["공종명", "단위", "수량", "단가", "금액"]
        assert classify_table(headers, [], kw) == "A_품셈"

    def test_a_type_by_row_keywords(self):
        kw = {"A_품셈": ["없는키워드"], "A_품셈_행키워드": ["보통인부", "특별인부"]}
        headers = ["종류", "단가"]
        rows = [["보통인부", "100000"], ["특별인부", "150000"], ["기계공", "200000"]]
        result = classify_table(headers, rows, kw)
        assert result == "A_품셈"

    def test_b_type(self):
        kw = {"A_품셈": [], "A_품셈_행키워드": [], "B_규모기준": ["규모", "기준"]}
        headers = ["규모", "기준금액"]
        assert classify_table(headers, [], kw) == "B_규모기준"

    def test_c_type(self):
        kw = {
            "A_품셈": [], "A_품셈_행키워드": [],
            "B_규모기준": [],
            "C_구분설명": ["구분", "내용"],
        }
        headers = ["구분", "내용"]
        assert classify_table(headers, [], kw) == "C_구분설명"

    def test_d_type_fallback(self):
        kw = {"A_품셈": ["없음"], "A_품셈_행키워드": [], "B_규모기준": [], "C_구분설명": []}
        assert classify_table(["기타1", "기타2", "기타3"], [], kw) == "D_기타"


# ══════════════════════════════════════════════════════════
# detect_header_rows
# ══════════════════════════════════════════════════════════

class TestDetectHeaderRows:
    def test_single_header_row(self):
        grid = [["이름", "단가", "수량"], ["배관", "1000", "5"]]
        assert detect_header_rows(grid) == 1

    def test_empty_grid(self):
        assert detect_header_rows([]) == 1

    def test_single_row(self):
        assert detect_header_rows([["A", "B"]]) == 1

    def test_two_header_rows_detected(self):
        # 첫 행에 중복(colspan 흔적), 두 번째 행이 헤더 패턴
        grid = [
            ["재료비", "재료비", "노무비", "노무비"],
            ["단가", "금액", "단가", "금액"],
            ["100", "500", "200", "1000"],
            ["150", "750", "250", "1250"],
        ]
        result = detect_header_rows(grid)
        assert result in (1, 2)  # 구현 재량, 크래시 없이 정수 반환

    def test_three_header_rows(self):
        grid = [
            ["A", "A", "B", "B"],
            ["C", "C", "D", "D"],
            ["E", "E", "F", "F"],
            ["1", "2", "3", "4"],
        ]
        # 크래시 없이 1~3 중 하나 반환
        result = detect_header_rows(grid)
        assert 1 <= result <= 3


# ══════════════════════════════════════════════════════════
# build_composite_headers
# ══════════════════════════════════════════════════════════

class TestBuildCompositeHeaders:
    def test_single_header_row(self):
        grid = [["이름", "단가", "수량"], ["A", "100", "3"]]
        headers = build_composite_headers(grid, 1)
        assert headers == ["이름", "단가", "수량"]

    def test_two_header_rows_merged(self):
        grid = [
            ["재료비", "재료비", "노무비"],
            ["단가", "금액", "단가"],
            ["100", "500", "200"],
        ]
        headers = build_composite_headers(grid, 2)
        assert len(headers) == 3
        # 재료비와 단가가 결합되어야 함
        assert "재료비" in headers[0] and "단가" in headers[0]

    def test_empty_header_cells_handled(self):
        grid = [["A", "", "C"], ["X", "Y", "Z"]]
        headers = build_composite_headers(grid, 1)
        assert headers[1] == ""


# ══════════════════════════════════════════════════════════
# is_note_row
# ══════════════════════════════════════════════════════════

class TestIsNoteRow:
    def test_joo_bracket_pattern(self):
        assert is_note_row(["[주] 참고사항", ""]) is True

    def test_circled_number_pattern(self):
        assert is_note_row(["① 첫 번째 항목"]) is True
        assert is_note_row(["⑩ 열 번째 항목"]) is True

    def test_circle_korean_pattern(self):
        assert is_note_row(["㉮ 항목"]) is True

    def test_dash_start(self):
        assert is_note_row(["- 대시로 시작"]) is True

    def test_bigo_start(self):
        assert is_note_row(["비 고 내용"]) is True

    def test_normal_data_row(self):
        assert is_note_row(["배관공사", "100000", "5"]) is False

    def test_empty_row(self):
        assert is_note_row(["", ""]) is False

    def test_long_single_cell(self):
        long_text = "이 셀에는 아주 긴 설명이 들어있어서 비고 행으로 간주되어야 한다" * 3
        assert is_note_row([long_text]) is True

    def test_em_dash_start(self):
        assert is_note_row(["– 엔 대시로 시작"]) is True


# ══════════════════════════════════════════════════════════
# try_numeric
# ══════════════════════════════════════════════════════════

class TestTryNumeric:
    def test_strips_whitespace(self):
        assert try_numeric("  값  ") == "값"

    def test_leading_zero_preserved(self):
        # 숫자 변환 안 함 — 선행 0 보존
        assert try_numeric("0015") == "0015"

    def test_comma_format_preserved(self):
        assert try_numeric("15,000,000") == "15,000,000"

    def test_non_string_passthrough(self):
        assert try_numeric(123) == 123

    def test_empty_string(self):
        assert try_numeric("") == ""


# ══════════════════════════════════════════════════════════
# parse_single_table
# ══════════════════════════════════════════════════════════

class TestParseSingleTable:
    def test_basic_table(self):
        html = (
            "<table>"
            "<tr><th>이름</th><th>단가</th></tr>"
            "<tr><td>배관</td><td>1000</td></tr>"
            "</table>"
        )
        result = parse_single_table(html, "S-01", 1)
        assert result is not None
        assert result["table_id"] == "T-S-01-01"
        assert result["headers"] == ["이름", "단가"]
        assert len(result["rows"]) == 1
        assert result["rows"][0]["이름"] == "배관"

    def test_no_table_html_returns_none(self):
        assert parse_single_table("<div>없음</div>", "S-01", 1) is None

    def test_empty_table_returns_none(self):
        assert parse_single_table("<table></table>", "S-01", 1) is None

    def test_header_only_table(self):
        html = "<table><tr><th>A</th><th>B</th></tr></table>"
        result = parse_single_table(html, "S-01", 1)
        assert result is not None
        assert result["rows"] == []

    def test_note_rows_extracted(self):
        html = (
            "<table>"
            "<tr><th>항목</th><th>값</th></tr>"
            "<tr><td>배관</td><td>100</td></tr>"
            "<tr><td>[주] 참고사항</td><td></td></tr>"
            "</table>"
        )
        result = parse_single_table(html, "S-01", 1)
        assert result is not None
        assert len(result["notes_in_table"]) >= 1

    def test_all_empty_rows_excluded(self):
        html = (
            "<table>"
            "<tr><th>A</th><th>B</th></tr>"
            "<tr><td></td><td></td></tr>"
            "<tr><td>데이터</td><td>값</td></tr>"
            "</table>"
        )
        result = parse_single_table(html, "S-01", 1)
        # 빈 행 제외
        assert result["parsed_row_count"] == 1

    def test_table_idx_in_id(self):
        html = "<table><tr><th>A</th></tr><tr><td>1</td></tr></table>"
        result = parse_single_table(html, "S-05", 3)
        assert result["table_id"] == "T-S-05-03"

    def test_type_keywords_passed(self):
        kw = {"A_품셈": ["공종명", "단가"], "A_품셈_행키워드": []}
        html = (
            "<table>"
            "<tr><th>공종명</th><th>단위</th><th>단가</th></tr>"
            "<tr><td>배관공사</td><td>m</td><td>5000</td></tr>"
            "</table>"
        )
        result = parse_single_table(html, "S-01", 1, type_keywords=kw)
        assert result["type"] == "A_품셈"


# ══════════════════════════════════════════════════════════
# process_section_tables
# ══════════════════════════════════════════════════════════

class TestProcessSectionTables:
    def _make_section(self, raw_text: str) -> dict:
        return {
            "section_id": "S-01",
            "title": "테스트 섹션",
            "department": "배관",
            "chapter": "제1장",
            "page": 1,
            "raw_text": raw_text,
            "source_file": "test.md",
            "toc_title": "",
            "toc_section": "",
            "has_content": True,
        }

    def test_single_table_extracted(self):
        raw = (
            "본문 텍스트\n"
            "<table><tr><th>항목</th></tr><tr><td>값</td></tr></table>\n"
            "후문"
        )
        section = self._make_section(raw)
        result = process_section_tables(section)
        assert "tables" in result
        assert len(result["tables"]) == 1
        assert "<table>" not in result["text_without_tables"]

    def test_no_table_section(self):
        section = self._make_section("텍스트만 있는 섹션")
        result = process_section_tables(section)
        assert result["tables"] == []
        assert "텍스트만 있는 섹션" in result["text_without_tables"]

    def test_multiple_tables(self):
        raw = (
            "<table><tr><th>A</th></tr><tr><td>1</td></tr></table>"
            " 중간텍스트 "
            "<table><tr><th>B</th></tr><tr><td>2</td></tr></table>"
        )
        section = self._make_section(raw)
        result = process_section_tables(section)
        assert len(result["tables"]) == 2

    def test_original_section_keys_preserved(self):
        section = self._make_section("텍스트")
        result = process_section_tables(section)
        assert result["section_id"] == "S-01"
        assert result["title"] == "테스트 섹션"
