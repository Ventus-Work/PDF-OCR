from __future__ import annotations

import json
from pathlib import Path

import openpyxl

from exporters.excel_exporter import ExcelExporter
from exporters.json_exporter import JsonExporter
from parsers.document_parser import parse_markdown


def test_real_bom_markdown_flows_through_parser_and_exporters(
    sample_md_dir: Path,
    tmp_path: Path,
):
    source_path = sample_md_dir / "bom_real_sample.md"
    sections = parse_markdown(source_path.read_text(encoding="utf-8"))

    assert len(sections) == 1
    assert len(sections[0]["tables"]) == 1

    table = sections[0]["tables"][0]
    assert table["type"] == "BOM_자재"
    assert table["headers"] == [
        "DESCRIPTION",
        "DWG NO.",
        "MAT'L",
        "SIZE",
        "수량",
        "단위",
        "자재중량 [Kg] | UNIT",
        "자재중량 [Kg] | WEIGHT",
        "자재중량 [Kg] | LOSS",
        "자재중량 [Kg] | WEIGHT_2",
        "자재면적 [m2] | UNIT",
        "자재면적 [m2] | m2",
        "자재면적 [m2] | LOSS",
        "자재면적 [m2] | m2_2",
        "비고",
        "Column_16",
    ]
    assert table["rows"][0]["DESCRIPTION"] == "Scaffolding 설치"
    assert table["rows"][0]["수량"] == "1.0"
    assert table["rows"][0]["단위"] == "식"
    assert table["rows"][0]["자재중량 [Kg] | UNIT"] == ""
    assert table["rows"][1]["SIZE"] == "19,800M(6000=3,1800=1)x 2Set"
    assert table["rows"][3]["수량"] == "144.0"
    assert table["rows"][3]["단위"] == "EA"

    json_out = tmp_path / "bom_real_sample.json"
    JsonExporter().export(sections, json_out)
    exported_json = json.loads(json_out.read_text(encoding="utf-8-sig"))
    exported_table = exported_json[0]["tables"][0]

    assert exported_table["headers"] == list(exported_table["rows"][0].keys())

    xlsx_out = tmp_path / "bom_real_sample.xlsx"
    ExcelExporter().export(sections, xlsx_out)
    workbook = openpyxl.load_workbook(xlsx_out)
    worksheet = workbook["BOM_자재표"]

    assert workbook.sheetnames == ["본문", "BOM_자재표"]
    assert [cell.value for cell in worksheet[1]] == table["headers"]
    assert [cell.value for cell in worksheet[2]][:7] == [
        "Scaffolding 설치",
        "KO-D-010-14-16N",
        None,
        None,
        1,
        "식",
        None,
    ]
    assert [cell.value for cell in worksheet[3]][:7] == [
        "Travelling Rail 설치",
        "KO-D-010-14-16N",
        None,
        "19,800M(6000=3,1800=1)x 2Set",
        1,
        "식",
        None,
    ]
