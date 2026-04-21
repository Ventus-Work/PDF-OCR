"""tests/unit/exporters/test_bom_aggregator.py"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from exporters.bom_aggregator import aggregate_boms, export_aggregated_excel


def _write_json(path: Path, data: list) -> Path:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8-sig")
    return path


def _bom_section(rows: list[dict]) -> dict:
    return {
        "type": "bom",
        "tables": [
            {
                "headers": ["S/N", "SIZE", "MATERIAL", "Q'TY", "WT(KG)"],
                "rows": rows,
            }
        ],
    }


class TestAggregateBoms:
    def test_empty_input_returns_one_section(self):
        result = aggregate_boms([])
        assert len(result) == 1
        assert result[0]["title"] == "Aggregated BOM"
        assert result[0]["tables"][0]["rows"] == []

    def test_single_file_rows_preserved(self, tmp_path: Path):
        rows = [
            {"SIZE": "150A", "MATERIAL": "SS400", "Q'TY": 4, "WT(KG)": 12.5},
            {"SIZE": "100A", "MATERIAL": "SS400", "Q'TY": 8, "WT(KG)": 6.2},
        ]
        jf = _write_json(tmp_path / "a_bom.json", [_bom_section(rows)])
        result = aggregate_boms([jf])
        agg_rows = result[0]["tables"][0]["rows"]
        assert len(agg_rows) == 2
        sizes = {r["SIZE"] for r in agg_rows}
        assert "150A" in sizes and "100A" in sizes

    def test_duplicate_size_material_summed(self, tmp_path: Path):
        rows_a = [{"SIZE": "150A", "MATERIAL": "SS400", "Q'TY": 4, "WT(KG)": 10.0}]
        rows_b = [{"SIZE": "150A", "MATERIAL": "SS400", "Q'TY": 2, "WT(KG)": 5.0}]
        jf_a = _write_json(tmp_path / "a_bom.json", [_bom_section(rows_a)])
        jf_b = _write_json(tmp_path / "b_bom.json", [_bom_section(rows_b)])
        result = aggregate_boms([jf_a, jf_b])
        agg_rows = result[0]["tables"][0]["rows"]
        assert len(agg_rows) == 1
        r = agg_rows[0]
        assert r["Q'TY"] == 6.0
        assert abs(r["WT(KG)"] - 15.0) < 0.001

    def test_returns_headers_in_result(self, tmp_path: Path):
        rows = [{"SIZE": "80A", "MATERIAL": "SS304", "Q'TY": 2, "WT(KG)": 1.5}]
        jf = _write_json(tmp_path / "a_bom.json", [_bom_section(rows)])
        result = aggregate_boms([jf])
        headers = result[0]["tables"][0]["headers"]
        assert "SIZE" in headers
        assert "Q'TY" in headers

    def test_invalid_json_file_skipped(self, tmp_path: Path):
        bad = tmp_path / "bad.json"
        bad.write_text("NOT JSON", encoding="utf-8")
        result = aggregate_boms([bad])
        assert result[0]["tables"][0]["rows"] == []


class TestExportAggregatedExcel:
    def test_creates_xlsx(self, tmp_path: Path):
        rows = [{"SIZE": "150A", "MATERIAL": "SS400", "Q'TY": 4, "WT(KG)": 12.5}]
        jf = _write_json(tmp_path / "a_bom.json", [_bom_section(rows)])
        out = tmp_path / "aggregated.xlsx"
        export_aggregated_excel([jf], out)
        assert out.exists()
        assert out.stat().st_size > 0

    def test_empty_input_raises_value_error(self, tmp_path: Path):
        out = tmp_path / "empty.xlsx"
        with pytest.raises(ValueError, match="JSON"):
            export_aggregated_excel([], out)
