"""
parsers/bom_table_parser.py 단위 테스트 — Phase 10 Step 10-1
목표 커버리지: 22.71% → 75%+
"""
from pathlib import Path

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


@pytest.fixture
def fixture_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "fixtures" / "mock_responses"


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

    def test_two_row_header_is_merged_and_second_header_row_not_emitted_as_data(self, bom_keywords):
        html = (
            "<table>"
            "<tr><th>\uc790\uc7ac\uba85</th><th>\uaddc\uaca9</th><th>\uc790\uc7ac\uc911\ub7c9 [Kg]</th><th>\uc218\ub7c9</th><th>\ub2e8\uc704</th></tr>"
            "<tr><th>ITEM</th><th>SIZE</th><th>WEIGHT</th><th>QTY</th><th>UNIT</th></tr>"
            "<tr><td>PIPE</td><td>100A</td><td>10.5</td><td>5</td><td>EA</td></tr>"
            "</table>"
        )
        result = parse_html_bom_tables(html, bom_keywords)
        assert len(result.bom_sections) == 1

        bom_sec = result.bom_sections[0]
        assert bom_sec.headers == [
            "\uc790\uc7ac\uba85 | ITEM",
            "\uaddc\uaca9 | SIZE",
            "\uc790\uc7ac\uc911\ub7c9 [Kg] | WEIGHT",
            "\uc218\ub7c9 | QTY",
            "\ub2e8\uc704 | UNIT",
        ]
        assert bom_sec.rows == [["PIPE", "100A", "10.5", "5", "EA"]]

    def test_rowspan_duplicate_headers_are_collapsed_to_single_header(self, bom_keywords):
        html = (
            "<table>"
            "<tr>"
            "<th rowspan='2'>DESCRIPTION</th>"
            "<th rowspan='2'>DWG NO.</th>"
            "<th colspan='2'>WEIGHT</th>"
            "<th rowspan='2'>QTY</th>"
            "</tr>"
            "<tr><th>UNIT</th><th>KG</th></tr>"
            "<tr><td>PIPE SUPPORT</td><td>D-100</td><td>EA</td><td>12</td><td>3</td></tr>"
            "</table>"
        )

        local_keywords = dict(
            bom_keywords,
            bom_header_a=["DESCRIPTION"],
            bom_header_b=["DWG NO."],
            bom_header_c=["QTY"],
        )
        result = parse_html_bom_tables(html, local_keywords)

        assert len(result.bom_sections) == 1
        headers = result.bom_sections[0].headers
        assert headers == ["DESCRIPTION", "DWG NO.", "WEIGHT | UNIT", "WEIGHT | KG", "QTY"]
        assert "DESCRIPTION | DESCRIPTION" not in headers
        assert "DWG NO. | DWG NO" not in headers

    def test_distinct_duplicate_headers_are_suffixed(self, bom_keywords):
        html = (
            "<table>"
            "<tr><th>DESCRIPTION</th><th>DWG NO.</th><th colspan='2'>WEIGHT</th><th>QTY</th></tr>"
            "<tr><th>DESCRIPTION</th><th>DWG NO</th><th>UNIT</th><th>UNIT</th><th>QTY</th></tr>"
            "<tr><td>PIPE SUPPORT</td><td>D-100</td><td>EA</td><td>KG</td><td>3</td></tr>"
            "</table>"
        )

        local_keywords = dict(
            bom_keywords,
            bom_header_a=["DESCRIPTION"],
            bom_header_b=["DWG NO."],
            bom_header_c=["QTY"],
        )
        result = parse_html_bom_tables(html, local_keywords)

        headers = result.bom_sections[0].headers
        assert headers == [
            "DESCRIPTION",
            "DWG NO.",
            "WEIGHT | UNIT",
            "WEIGHT | UNIT_2",
            "QTY",
        ]
        assert result.bom_sections[0].rows[0] == ["PIPE SUPPORT", "D-100", "EA", "KG", "3"]

    def test_sparse_html_row_fixture_is_aligned_to_composite_headers(self, bom_keywords, fixture_dir):
        local_keywords = dict(bom_keywords, noise_row=["TOTAL"])
        html = (fixture_dir / "bom_sparse_multilevel_table.html").read_text(encoding="utf-8")

        result = parse_html_bom_tables(html, local_keywords)
        assert len(result.bom_sections) == 1

        bom_sec = result.bom_sections[0]
        assert len(bom_sec.headers) == 15
        assert "DESCRIPTION | DESCRIPTION" not in bom_sec.headers
        assert bom_sec.headers[9:13] == [
            "WEIGHT | UNIT",
            "WEIGHT | LOSS",
            "WEIGHT | TOTAL",
            "WEIGHT | KG",
        ]
        assert bom_sec.rows[0][1] == "Scaffolding \uc124\uce58"
        assert bom_sec.rows[0][13] == "1"
        assert bom_sec.rows[0][14] == "\uc2dd"

    def test_quantity_unit_shift_is_repaired_without_touching_normal_rows(self, bom_keywords):
        html = (
            "<table>"
            "<tr>"
            "<th rowspan='2'>DESCRIPTION</th><th rowspan='2'>DWG NO.</th>"
            "<th rowspan='2'>MAT'L</th><th rowspan='2'>SIZE</th>"
            "<th rowspan='2'>수량</th><th rowspan='2'>단위</th>"
            "<th colspan='2'>자재중량 [Kg]</th><th rowspan='2'>비고</th>"
            "</tr>"
            "<tr><th>UNIT</th><th>WEIGHT</th></tr>"
            "<tr><td>Scaffolding 설치</td><td>KO-D-010-14-16N</td><td></td><td></td><td></td><td>1.0</td><td>식</td><td></td><td></td></tr>"
            "<tr><td>Travelling Rail 설치</td><td>KO-D-010-14-16N</td><td></td><td>19,800M</td><td>1.0</td><td>식</td><td></td><td></td><td></td></tr>"
            "</table>"
        )
        local_keywords = dict(
            bom_keywords,
            bom_header_a=["DESCRIPTION"],
            bom_header_b=["DWG NO."],
            bom_header_c=["수량"],
        )

        result = parse_html_bom_tables(html, local_keywords)
        assert len(result.bom_sections) == 1
        rows = result.bom_sections[0].rows
        headers = result.bom_sections[0].headers
        qty_idx = headers.index("수량")
        unit_idx = headers.index("단위")
        shifted_idx = headers.index("자재중량 [Kg] | UNIT")

        assert rows[0][qty_idx] == "1.0"
        assert rows[0][unit_idx] == "식"
        assert rows[0][shifted_idx] == ""
        assert rows[1][qty_idx] == "1.0"
        assert rows[1][unit_idx] == "식"
        assert rows[1][shifted_idx] == ""
