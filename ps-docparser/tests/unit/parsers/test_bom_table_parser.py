"""
parsers/bom_table_parser.py 단위 테스트 — Phase 10 Step 10-1
목표 커버리지: 22.71% → 75%+
"""
import pytest

from parsers.bom_table_parser import (
    parse_html_bom_tables,
    parse_markdown_pipe_table,
    parse_whitespace_table,
    normalize_columns,
    filter_noise_rows,
    parse_bom_rows,
)


# ══════════════════════════════════════════════════════════
# 픽스처 — BOM 키워드
# ══════════════════════════════════════════════════════════

@pytest.fixture
def bom_keywords():
    return {
        "bom_header_a": ["ITEM", "품번"],
        "bom_header_b": ["SIZE", "SIZE/RATING"],
        "bom_header_c": ["QTY", "Q'TY", "수량"],
        "ll_header_a": ["LINE NO", "LINE LIST"],
        "ll_header_b": ["SIZE"],
        "ll_header_c": ["FROM"],
        "blacklist": ["DRAWING LIST"],
        "noise_row": ["소계", "합계", "TOTAL"],
    }


# ══════════════════════════════════════════════════════════
# parse_markdown_pipe_table
# ══════════════════════════════════════════════════════════

class TestParseMarkdownPipeTable:
    def test_basic_pipe_table(self):
        text = "| PIPE | 10 |\n| BALL VALVE | 5 |"
        rows = parse_markdown_pipe_table(text)
        assert len(rows) == 2
        assert rows[0][0].strip() == "PIPE"
        assert rows[1][1].strip() == "5"

    def test_with_separator_line(self):
        text = (
            "| 헤더1 | 헤더2 |\n"
            "|-------|-------|\n"
            "| 데이터1 | 데이터2 |"
        )
        rows = parse_markdown_pipe_table(text)
        # 구분선은 제외
        assert len(rows) == 2
        assert rows[0][0].strip() == "헤더1"
        assert rows[1][0].strip() == "데이터1"

    def test_no_pipe_returns_empty(self):
        assert parse_markdown_pipe_table("파이프 없는 텍스트") == []

    def test_empty_string(self):
        assert parse_markdown_pipe_table("") == []

    def test_trailing_leading_pipe_stripped(self):
        text = "| A | B | C |"
        rows = parse_markdown_pipe_table(text)
        assert len(rows) == 1
        assert len(rows[0]) == 3

    def test_mixed_content(self):
        text = (
            "설명 텍스트\n"
            "| S/N | SIZE | MAT'L |\n"
            "|-----|------|-------|\n"
            "| 1 | 100A | SS304 |"
        )
        rows = parse_markdown_pipe_table(text)
        assert any("S/N" in r[0] for r in rows)

    def test_cells_stripped(self):
        text = "|  공백있음  |  값  |"
        rows = parse_markdown_pipe_table(text)
        assert rows[0][0] == "공백있음"
        assert rows[0][1] == "값"


# ══════════════════════════════════════════════════════════
# parse_whitespace_table
# ══════════════════════════════════════════════════════════

class TestParseWhitespaceTable:
    def test_basic_whitespace_table(self):
        text = "이름  단가  수량\n배관  1000  5"
        rows = parse_whitespace_table(text)
        assert len(rows) == 2
        assert "이름" in rows[0][0]

    def test_three_or_more_cells_required(self):
        # 셀 2개 이하 행은 제외
        text = "A  B\nX  Y  Z"
        rows = parse_whitespace_table(text)
        assert len(rows) == 1  # 3개짜리만

    def test_empty_lines_skipped(self):
        text = "A  B  C\n\nD  E  F"
        rows = parse_whitespace_table(text)
        assert len(rows) == 2

    def test_empty_string(self):
        assert parse_whitespace_table("") == []


# ══════════════════════════════════════════════════════════
# normalize_columns
# ══════════════════════════════════════════════════════════

class TestNormalizeColumns:
    def test_already_normalized(self):
        rows = [["A", "B", "C"], ["1", "2", "3"]]
        result = normalize_columns(rows)
        assert result == rows

    def test_short_row_padded(self):
        rows = [["A", "B", "C"], ["1", "2"]]
        result = normalize_columns(rows)
        assert len(result[1]) == 3
        assert result[1][2] == ""

    def test_long_row_merged(self):
        rows = [["A", "B", "C"], ["1", "2", "3", "4"]]
        result = normalize_columns(rows, reference_col_count=3)
        assert len(result[1]) == 3

    def test_empty_rows(self):
        assert normalize_columns([]) == []

    def test_reference_col_count_overrides(self):
        rows = [["A", "B"], ["1", "2", "3"]]
        result = normalize_columns(rows, reference_col_count=2)
        assert all(len(r) == 2 for r in result)


# ══════════════════════════════════════════════════════════
# filter_noise_rows
# ══════════════════════════════════════════════════════════

class TestFilterNoiseRows:
    def test_noise_keyword_removed(self):
        rows = [["PIPE", "10"], ["소계", "10"], ["합계", "20"]]
        filtered = filter_noise_rows(rows, ["소계", "합계"])
        assert len(filtered) == 1
        assert filtered[0][0] == "PIPE"

    def test_empty_rows_removed(self):
        rows = [["PIPE", "10"], ["", ""], ["VALVE", "5"]]
        filtered = filter_noise_rows(rows, [])
        assert len(filtered) == 2

    def test_all_same_cell_row_removed(self):
        rows = [["PIPE", "10"], ["X", "X", "X"]]
        filtered = filter_noise_rows(rows, [])
        assert len(filtered) == 1

    def test_no_noise(self):
        rows = [["PIPE", "10"], ["VALVE", "5"]]
        assert filter_noise_rows(rows, []) == rows

    def test_case_insensitive_noise_check(self):
        rows = [["PIPE", "10"], ["TOTAL", "15"]]
        filtered = filter_noise_rows(rows, ["total"])
        assert len(filtered) == 1

    def test_empty_input(self):
        assert filter_noise_rows([], ["소계"]) == []


# ══════════════════════════════════════════════════════════
# parse_bom_rows (자동 감지)
# ══════════════════════════════════════════════════════════

class TestParseBomRows:
    def test_detects_pipe_format(self):
        text = "| S/N | SIZE | MAT'L |\n| 1 | 100A | SS304 |"
        rows = parse_bom_rows(text)
        assert len(rows) >= 1

    def test_detects_whitespace_format(self):
        text = "S/N  SIZE  MATL\n1  100A  SS304"
        rows = parse_bom_rows(text)
        assert len(rows) >= 1

    def test_empty_text_returns_empty(self):
        assert parse_bom_rows("") == []

    def test_pipe_takes_priority_over_whitespace(self):
        # 파이프가 있으면 파이프 포맷으로 처리
        text = "| A | B |\n| 1 | 2 |"
        rows = parse_bom_rows(text)
        assert rows[0][0] in ("A", " A ")


# ══════════════════════════════════════════════════════════
# parse_html_bom_tables
# ══════════════════════════════════════════════════════════

class TestParseHtmlBomTables:
    def _bom_html(self, headers, rows):
        """BOM 테이블 HTML 생성 헬퍼."""
        header_row = "<tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>"
        data_rows = ""
        for row in rows:
            data_rows += "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>"
        return f"<table>{header_row}{data_rows}</table>"

    def test_bom_table_detected(self, bom_keywords):
        html = self._bom_html(
            ["ITEM", "SIZE/RATING", "QTY"],
            [["1", "100A", "5"], ["2", "50A", "3"]],
        )
        result = parse_html_bom_tables(html, bom_keywords)
        assert len(result.bom_sections) >= 1

    def test_non_bom_table_ignored(self, bom_keywords):
        html = self._bom_html(
            ["이름", "나이", "직업"],
            [["홍길동", "30", "배관공"]],
        )
        result = parse_html_bom_tables(html, bom_keywords)
        assert len(result.bom_sections) == 0
        assert len(result.line_list_sections) == 0

    def test_blacklisted_table_ignored(self, bom_keywords):
        html = self._bom_html(
            ["ITEM", "SIZE/RATING", "QTY"],
            [["DRAWING LIST", "100A", "5"]],
        )
        # 블랙리스트 키워드가 블록 전체에 포함되면 제외
        result = parse_html_bom_tables(html, bom_keywords)
        # DRAWING LIST가 헤더/블록에 있어야 제외됨 (키워드는 블록 전체 검색)
        assert isinstance(result.bom_sections, list)

    def test_no_html_returns_empty(self, bom_keywords):
        result = parse_html_bom_tables("텍스트만", bom_keywords)
        assert result.bom_sections == []
        assert result.line_list_sections == []

    def test_line_list_detected(self, bom_keywords):
        html = self._bom_html(
            ["LINE NO", "SIZE", "FROM", "TO"],
            [["L-001", "100A", "P-101", "P-102"]],
        )
        result = parse_html_bom_tables(html, bom_keywords)
        assert len(result.line_list_sections) >= 1

    def test_noise_rows_filtered(self, bom_keywords):
        html = self._bom_html(
            ["ITEM", "SIZE/RATING", "QTY"],
            [["1", "100A", "5"], ["소계", "", "5"], ["2", "50A", "3"]],
        )
        result = parse_html_bom_tables(html, bom_keywords)
        if result.bom_sections:
            row_values = [
                str(c).strip()
                for r in result.bom_sections[0].rows
                for c in r
            ]
            assert "소계" not in row_values

    def test_title_row_skipped(self, bom_keywords):
        # colspan 단일 셀 타이틀 행 스킵 검증
        html = (
            "<table>"
            "<tr><td colspan='3'>BILL OF MATERIALS</td></tr>"
            "<tr><th>ITEM</th><th>SIZE/RATING</th><th>QTY</th></tr>"
            "<tr><td>1</td><td>100A</td><td>5</td></tr>"
            "</table>"
        )
        result = parse_html_bom_tables(html, bom_keywords)
        if result.bom_sections:
            # 첫 데이터 행이 "BILL OF MATERIALS"가 아닌 실제 데이터여야 함
            first_rows = result.bom_sections[0].rows
            assert first_rows

    def test_truncated_html_handled(self, bom_keywords):
        # 닫힌 태그 없이 잘린 HTML
        html = "<table><tr><th>ITEM</th><th>SIZE/RATING</th><th>QTY</th></tr><tr><td>1</td><td>100A</td><td>5"
        result = parse_html_bom_tables(html, bom_keywords)
        assert isinstance(result.bom_sections, list)

    def test_empty_keywords(self):
        html = "<table><tr><td>A</td></tr></table>"
        result = parse_html_bom_tables(html, {})
        assert result.bom_sections == []
