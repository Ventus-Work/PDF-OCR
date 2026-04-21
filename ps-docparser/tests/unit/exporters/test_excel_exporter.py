"""tests/unit/exporters/test_excel_exporter.py"""

from __future__ import annotations

from pathlib import Path

import pytest

from exporters.excel_exporter import (
    ExcelExporter,
    _classify_table,
    _try_parse_number,
    _row_style,
)


# ─────────────────────────────────────────────────────────────
# _classify_table
# ─────────────────────────────────────────────────────────────

class TestClassifyTable:
    def test_estimate_by_header(self):
        table = {"headers": ["명 칭", "규 격", "수량", "금 액"], "rows": []}
        assert _classify_table(table) == "estimate"

    def test_estimate_spaceless_header(self):
        table = {"headers": ["명칭", "규격", "수량", "금액"], "rows": []}
        assert _classify_table(table) == "estimate"

    def test_detail_by_header(self):
        table = {"headers": ["품명", "수량", "합계_금액"], "rows": []}
        assert _classify_table(table) == "detail"

    def test_condition_by_keyword(self):
        table = {"headers": ["일반사항"], "rows": []}
        assert _classify_table(table) == "condition"

    def test_condition_by_type_hint(self):
        table = {"headers": ["X", "Y"], "type": "D_기타", "rows": []}
        assert _classify_table(table) == "condition"

    def test_generic_fallback(self):
        table = {"headers": ["X", "Y"], "rows": []}
        assert _classify_table(table) == "generic"

    def test_empty_headers(self):
        table = {"rows": []}
        assert _classify_table(table) == "generic"


# ─────────────────────────────────────────────────────────────
# _try_parse_number
# ─────────────────────────────────────────────────────────────

class TestTryParseNumber:
    @pytest.mark.parametrize("text,expected", [
        ("1,000,000", 1_000_000),
        ("  3.5  ", 3.5),
        ("-500", -500),
        ("0", 0),
        ("0.5", 0.5),
        ("1,234원", None),
        ("(5,000)", None),
        ("0015", None),
        ("-", None),
        ("", None),
        ("N/A", None),
        ("100KW", None),
    ])
    def test_parse_variants(self, text, expected):
        assert _try_parse_number(text) == expected

    def test_non_string_returns_none(self):
        assert _try_parse_number(None) is None
        assert _try_parse_number(123) is None


# ─────────────────────────────────────────────────────────────
# _row_style
# ─────────────────────────────────────────────────────────────

class TestRowStyle:
    def test_subtotal_row(self):
        row = {"명칭": "소 계", "금 액": "1,000,000"}
        assert _row_style(row, "명칭") == "subtotal"

    def test_total_row(self):
        row = {"명칭": "합 계", "금 액": "5,000,000"}
        assert _row_style(row, "명칭") == "subtotal"

    def test_section_row(self):
        row = {"명칭": "1. 배관공사", "금 액": ""}
        assert _row_style(row, "명칭") == "section"

    def test_body_row(self):
        row = {"명칭": "파이프 서포트", "금 액": "1,000,000"}
        assert _row_style(row, "명칭") == "body"

    def test_no_money_key_no_section(self):
        # money_keys 가 빈 리스트면 all([]) == True 함정 → body 반환
        row = {"품명": "앵커볼트"}
        assert _row_style(row, "품명") == "body"


# ─────────────────────────────────────────────────────────────
# ExcelExporter.export() 통합
# ─────────────────────────────────────────────────────────────

class TestExcelExporterExport:
    def _make_section(self, table_type: str = "estimate") -> dict:
        return {
            "title": "테스트",
            "tables": [
                {
                    "headers": ["명 칭", "규 격", "수량", "단위", "금 액"],
                    "rows": [
                        {"명 칭": "파이프 서포트", "규 격": "150A", "수량": 4, "단위": "EA", "금 액": 1_000_000},
                        {"명 칭": "소 계", "규 격": "", "수량": "", "단위": "", "금 액": 1_000_000},
                    ],
                    "type": table_type,
                    "title": "견적",
                }
            ],
        }

    def test_creates_xlsx_file(self, tmp_path: Path):
        out = tmp_path / "test.xlsx"
        ExcelExporter().export([self._make_section()], out)
        assert out.exists()
        assert out.stat().st_size > 0

    def test_returns_output_path(self, tmp_path: Path):
        out = tmp_path / "test.xlsx"
        result = ExcelExporter().export([self._make_section()], out)
        assert result == out

    def test_empty_sections_creates_fallback_sheet(self, tmp_path: Path):
        import openpyxl
        out = tmp_path / "empty.xlsx"
        ExcelExporter().export([], out)
        assert out.exists()
        wb = openpyxl.load_workbook(out)
        assert len(wb.sheetnames) >= 1

    def test_metadata_title_accepted(self, tmp_path: Path):
        out = tmp_path / "titled.xlsx"
        result = ExcelExporter().export(
            [self._make_section()], out, metadata={"description": "견적서 제목"}
        )
        assert result.exists()

    def test_generic_table_creates_table_sheet(self, tmp_path: Path):
        import openpyxl
        section = {
            "title": "BOM",
            "tables": [
                {
                    "headers": ["SIZE", "MAT'L", "Q'TY"],
                    "rows": [{"SIZE": "150A", "MAT'L": "SS400", "Q'TY": 4}],
                    "type": "generic",
                    "title": "",
                }
            ],
        }
        out = tmp_path / "generic.xlsx"
        ExcelExporter().export([section], out)
        wb = openpyxl.load_workbook(out)
        sheet_names = wb.sheetnames
        assert any("Table" in s or "BOM" in s or s for s in sheet_names)

    def test_condition_table_creates_condition_sheet(self, tmp_path: Path):
        import openpyxl
        section = {
            "title": "조건",
            "tables": [
                {
                    "headers": ["일반사항"],
                    "rows": [{"일반사항": "재질: SS400"}, {"일반사항": "도장: 에폭시"}],
                    "type": "condition",
                    "title": "조건",
                }
            ],
        }
        out = tmp_path / "cond.xlsx"
        ExcelExporter().export([section], out)
        wb = openpyxl.load_workbook(out)
        assert "조건" in wb.sheetnames
