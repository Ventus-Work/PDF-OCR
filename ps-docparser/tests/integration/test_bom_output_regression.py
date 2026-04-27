from __future__ import annotations

import json
from pathlib import Path

import openpyxl

from exporters.excel_exporter import ExcelExporter
from exporters.json_exporter import JsonExporter


def _load_real_bom_sections(fixtures_dir: Path) -> list[dict]:
    fixture_path = fixtures_dir / "mock_responses" / "bom_real_sample_sections.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def test_real_bom_sample_json_export_preserves_headers_and_row_keys(
    fixtures_dir: Path,
    tmp_path: Path,
):
    sections = _load_real_bom_sections(fixtures_dir)
    table = sections[0]["tables"][0]

    assert table["headers"] == list(table["rows"][0].keys())

    out = tmp_path / "bom_sample.json"
    JsonExporter().export(sections, out)

    exported = json.loads(out.read_text(encoding="utf-8-sig"))
    exported_table = exported[0]["tables"][0]

    assert exported == sections
    assert exported_table["headers"] == list(exported_table["rows"][0].keys())
    assert exported_table["rows"][0]["수량"] == "1.0"
    assert exported_table["rows"][0]["단위"] == "식"
    assert exported_table["rows"][0]["자재중량 [Kg] | UNIT"] == ""


def test_real_bom_sample_excel_export_keeps_bom_sheet_and_row_alignment(
    fixtures_dir: Path,
    tmp_path: Path,
):
    sections = _load_real_bom_sections(fixtures_dir)
    table = sections[0]["tables"][0]

    out = tmp_path / "bom_sample.xlsx"
    ExcelExporter().export(sections, out)

    workbook = openpyxl.load_workbook(out)
    assert workbook.sheetnames == ["BOM_자재표"]

    worksheet = workbook["BOM_자재표"]
    assert [cell.value for cell in worksheet[1]] == table["headers"]

    first_row = [cell.value for cell in worksheet[2]]
    assert first_row[:7] == [
        "Scaffolding 설치",
        "KO-D-010-14-16N",
        None,
        None,
        1,
        "식",
        None,
    ]

    second_row = [cell.value for cell in worksheet[3]]
    assert second_row[:7] == [
        "Travelling Rail 설치",
        "KO-D-010-14-16N",
        None,
        "19,800M(6000=3,1800=1)x 2Set",
        1,
        "식",
        None,
    ]

    third_row = [cell.value for cell in worksheet[4]]
    assert third_row[:7] == [
        "Stud Bolt/Nut Weld",
        "KO-D-010-14-16N",
        None,
        None,
        144,
        "EA",
        None,
    ]
