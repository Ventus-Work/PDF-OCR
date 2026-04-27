from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import openpyxl

from exporters.excel_exporter import ExcelExporter
from exporters.json_exporter import JsonExporter
from pipelines.base import PipelineContext
from pipelines.document_pipeline import DocumentPipeline
from utils.io import _safe_write_text


def _make_args(**overrides):
    base = {
        "preset": None,
        "engine": "local",
        "output_format": "excel",
        "text_only": False,
        "pages": None,
        "toc": None,
        "_is_batch_mode": False,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _load_real_bom_sections(fixtures_dir: Path) -> list[dict]:
    fixture_path = fixtures_dir / "mock_responses" / "bom_real_sample_sections.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def test_document_pipeline_real_pdf_bom_fixture_auto_routes_to_bom_pipeline(
    sample_pdf_dir: Path,
    sample_md_dir: Path,
    fixtures_dir: Path,
    tmp_path: Path,
    mocker,
):
    input_pdf = sample_pdf_dir / "minimal.pdf"
    bom_md = (sample_md_dir / "bom_real_sample.md").read_text(encoding="utf-8")
    sections = _load_real_bom_sections(fixtures_dir)

    mocker.patch.object(DocumentPipeline, "_build_engine", return_value=MagicMock())
    mocker.patch.object(DocumentPipeline, "_extract_md", return_value=bom_md)

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

    ctx = PipelineContext(
        input_path=input_pdf,
        output_dir=tmp_path / "output",
        args=_make_args(),
        tracker=MagicMock(call_count=0),
    )

    DocumentPipeline(ctx).run()

    bom_run.assert_called_once()

    final_md_files = list(ctx.output_dir.glob("*_minimal_bom.md"))
    final_json_files = list(ctx.output_dir.glob("*_minimal_bom.json"))
    final_xlsx_files = list(ctx.output_dir.glob("*_minimal_bom.xlsx"))
    generic_root_md_files = list(ctx.output_dir.glob("*_minimal.md"))
    generic_root_json_files = list(ctx.output_dir.glob("*_minimal.json"))
    generic_root_xlsx_files = list(ctx.output_dir.glob("*_minimal.xlsx"))

    assert len(final_md_files) == 1
    assert len(final_json_files) == 1
    assert len(final_xlsx_files) == 1
    assert not generic_root_md_files
    assert not generic_root_json_files
    assert not generic_root_xlsx_files

    compare_dirs = list((ctx.output_dir / "_compare").iterdir())
    assert len(compare_dirs) == 1
    compare_dir = compare_dirs[0]
    compare_md_files = list((compare_dir / "generic").glob("*.md"))
    compare_json_files = list((compare_dir / "generic").glob("*.json"))
    compare_xlsx_files = list((compare_dir / "generic").glob("*.xlsx"))
    assert len(compare_md_files) == 1
    assert len(compare_json_files) == 1
    assert len(compare_xlsx_files) == 1

    compare_sections = json.loads(compare_json_files[0].read_text(encoding="utf-8-sig"))
    compare_table = compare_sections[0]["tables"][0]
    assert compare_table["type"] == "BOM_자재"
    assert compare_table["rows"][0]["DESCRIPTION"] == "Scaffolding 설치"

    manifest = json.loads((compare_dir / "route_manifest.json").read_text(encoding="utf-8"))
    assert manifest["target_preset"] == "bom"
    assert manifest["chosen_mode"] == "specialized"

    workbook = openpyxl.load_workbook(final_xlsx_files[0])
    assert workbook.sheetnames == ["BOM_자재표"]
