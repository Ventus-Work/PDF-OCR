import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from pipelines.base import PipelineContext
from pipelines.document_pipeline import DocumentPipeline
from utils.io import ParserError


def _make_ctx(tmp_path, preset=None, engine=None, output_format="md",
              text_only=False, pages=None, toc=None):
    args = MagicMock()
    args.preset = preset
    args.engine = engine
    args.output_format = output_format
    args.text_only = text_only
    args.pages = pages
    args.toc = toc
    return PipelineContext(
        input_path=tmp_path / "sample.md",  # .md 직접 입력으로 Phase 1 스킵
        output_dir=tmp_path / "output",
        args=args,
        tracker=MagicMock(call_count=0),
    )


class TestDocumentPipeline:
    def test_validate_engine_rejects_zai_mistral_tesseract(self, tmp_path):
        for bad_engine in ("zai", "mistral", "tesseract"):
            ctx = _make_ctx(tmp_path, engine=bad_engine)
            ctx.args.text_only = False
            pipeline = DocumentPipeline(ctx)
            with pytest.raises(ParserError, match="표준 파이프라인"):
                pipeline._validate_engine(bad_engine)

    def test_pumsem_preset_loads_resources(self, tmp_path, mocker):
        mocker.patch("presets.pumsem.get_division_names", return_value=["A", "B"])
        mocker.patch("presets.pumsem.get_parse_patterns", return_value={})
        mocker.patch("presets.pumsem.get_table_type_keywords", return_value={})

        ctx = _make_ctx(tmp_path, preset="pumsem")
        pipeline = DocumentPipeline(ctx)
        data = pipeline._load_preset("pumsem")
        assert "division_names" in data
        assert data["division_names"] == ["A", "B"]

    def test_estimate_preset_loads_resources(self, tmp_path, mocker):
        mocker.patch("presets.estimate.get_table_type_keywords", return_value={"k": "v"})
        mocker.patch("presets.estimate.get_excel_config", return_value={"sheets": []})

        ctx = _make_ctx(tmp_path, preset="estimate")
        pipeline = DocumentPipeline(ctx)
        data = pipeline._load_preset("estimate")
        assert "type_keywords" in data
        assert "excel_config" in data

    def test_md_input_skips_phase1_and_produces_json(self, tmp_path, mocker):
        """직접 .md 입력 시 Phase 1 스킵, JSON 출력까지 동작 확인."""
        md_file = tmp_path / "sample.md"
        md_file.write_text("# 테스트\n내용", encoding="utf-8")

        mocker.patch(
            "parsers.document_parser.parse_markdown",
            return_value=[{"section_id": "1", "title": "테스트", "tables": []}],
        )
        mock_export = mocker.patch("exporters.json_exporter.JsonExporter.export")

        args = MagicMock()
        args.preset = None
        args.engine = None
        args.output_format = "json"
        args.text_only = False
        args.pages = None
        args.toc = None
        ctx = PipelineContext(
            input_path=md_file,
            output_dir=tmp_path / "output",
            args=args,
            tracker=MagicMock(call_count=0),
        )
        (tmp_path / "output").mkdir()
        DocumentPipeline(ctx).run()
        mock_export.assert_called_once()
