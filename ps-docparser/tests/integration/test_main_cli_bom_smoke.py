from __future__ import annotations

import json
import sys
from pathlib import Path

import openpyxl

import main as cli_main
from exporters.excel_exporter import ExcelExporter
from exporters.json_exporter import JsonExporter
from utils.io import _safe_write_text


def _load_real_bom_sections(fixtures_dir: Path) -> list[dict]:
    fixture_path = fixtures_dir / "mock_responses" / "bom_real_sample_sections.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def test_main_cli_real_pdf_bom_fixture_auto_routes_to_bom_pipeline(
    sample_pdf_dir: Path,
    sample_md_dir: Path,
    fixtures_dir: Path,
    tmp_path: Path,
    mocker,
):
    input_pdf = sample_pdf_dir / "minimal.pdf"
    output_dir = tmp_path / "output"
    bom_md = (sample_md_dir / "bom_real_sample.md").read_text(encoding="utf-8")
    sections = _load_real_bom_sections(fixtures_dir)

    mocker.patch.object(cli_main, "validate_config", return_value={"errors": []})
    mocker.patch.object(cli_main, "_init_cache", return_value=None)
    mocker.patch.object(cli_main, "_project_root", tmp_path)
    mocker.patch("pipelines.document_pipeline.DocumentPipeline._build_engine")
    mocker.patch(
        "pipelines.document_pipeline.DocumentPipeline._extract_md",
        return_value=bom_md,
    )

    def fake_bom_run(self):
        output_base = self._get_output_base("_bom")
        _safe_write_text(Path(str(output_base) + ".md"), bom_md)
        JsonExporter().export(sections, Path(str(output_base) + ".json"))
        ExcelExporter().export(sections, Path(str(output_base) + ".xlsx"))

    bom_run = mocker.patch(
        "pipelines.bom_pipeline.BomPipeline.run",
        autospec=True,
        side_effect=fake_bom_run,
    )
    mocker.patch.object(
        sys,
        "argv",
        [
            "main.py",
            str(input_pdf),
            "--engine",
            "local",
            "--output",
            "excel",
            "--output-dir",
            str(output_dir),
        ],
    )

    cli_main.main()

    bom_run.assert_called_once()
    log_path = tmp_path / "ps-docparser.log"
    assert log_path.exists()

    final_md_files = list(output_dir.glob("*_minimal_bom.md"))
    final_json_files = list(output_dir.glob("*_minimal_bom.json"))
    final_xlsx_files = list(output_dir.glob("*_minimal_bom.xlsx"))
    generic_root_json_files = list(output_dir.glob("*_minimal.json"))

    assert len(final_md_files) == 1
    assert len(final_json_files) == 1
    assert len(final_xlsx_files) == 1
    assert not generic_root_json_files

    compare_dirs = list((output_dir / "_compare").iterdir())
    assert len(compare_dirs) == 1
    manifest = json.loads((compare_dirs[0] / "route_manifest.json").read_text(encoding="utf-8"))
    assert manifest["target_preset"] == "bom"
    assert manifest["chosen_mode"] == "specialized"

    compare_sections = json.loads(
        next((compare_dirs[0] / "generic").glob("*.json")).read_text(encoding="utf-8-sig")
    )
    assert compare_sections[0]["tables"][0]["type"] == "BOM_자재"

    workbook = openpyxl.load_workbook(final_xlsx_files[0])
    assert workbook.sheetnames == ["BOM_자재표"]
