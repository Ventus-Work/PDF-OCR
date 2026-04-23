import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from pipelines.base import PipelineContext
from pipelines.bom_pipeline import BomPipeline
from utils.io import ParserError


def _make_ctx(tmp_path, engine=None, output_format="json", pages=None):
    args = MagicMock()
    args.preset = "bom"
    args.engine = engine
    args.output_format = output_format
    args.pages = pages
    return PipelineContext(
        input_path=tmp_path / "sample.pdf",
        output_dir=tmp_path / "output",
        args=args,
        tracker=MagicMock(call_count=0),
    )


class TestBomPipeline:
    def test_non_ocr_engine_raises(self, tmp_path, mocker):
        mock_engine = MagicMock()
        mock_engine.supports_ocr = False
        mocker.patch("pipelines.bom_pipeline.create_engine", return_value=mock_engine)
        mocker.patch("presets.bom.get_bom_keywords", return_value={})
        mocker.patch("presets.bom.get_image_settings", return_value={})

        ctx = _make_ctx(tmp_path, engine="local")
        with pytest.raises(ParserError, match="OCR 엔진"):
            BomPipeline(ctx).run()

    def test_cache_injected_into_engine(self, tmp_path, mocker):
        mock_engine = MagicMock()
        mock_engine.supports_ocr = True
        mocker.patch("pipelines.bom_pipeline.create_engine", return_value=mock_engine)
        mocker.patch("presets.bom.get_bom_keywords", return_value={})
        mocker.patch("presets.bom.get_image_settings", return_value={})

        bom_result = MagicMock()
        bom_result.raw_text = "raw"
        bom_result.bom_sections = []
        bom_result.line_list_sections = []
        mocker.patch("extractors.bom_extractor.extract_bom_with_retry", return_value=bom_result)
        mocker.patch("extractors.bom_extractor.to_sections", return_value=[])
        mocker.patch("exporters.json_exporter.JsonExporter.export")
        mocker.patch("utils.io._safe_write_text")

        cache_obj = object()
        ctx = _make_ctx(tmp_path, engine="zai")
        ctx.cache = cache_obj
        BomPipeline(ctx).run()
        assert mock_engine.cache is cache_obj

    def test_json_output_created(self, tmp_path, mocker):
        mock_engine = MagicMock()
        mock_engine.supports_ocr = True
        mocker.patch("pipelines.bom_pipeline.create_engine", return_value=mock_engine)
        mocker.patch("presets.bom.get_bom_keywords", return_value={})
        mocker.patch("presets.bom.get_image_settings", return_value={})

        bom_result = MagicMock()
        bom_result.raw_text = "raw"
        bom_result.bom_sections = []
        bom_result.line_list_sections = []
        mocker.patch("extractors.bom_extractor.extract_bom_with_retry", return_value=bom_result)
        mocker.patch("extractors.bom_extractor.to_sections", return_value=[])
        mock_export = mocker.patch("exporters.json_exporter.JsonExporter.export")
        mocker.patch("utils.io._safe_write_text")

        ctx = _make_ctx(tmp_path, engine="zai")
        BomPipeline(ctx).run()
        mock_export.assert_called_once()

    @pytest.mark.parametrize(
        "n_tables, has_meta, text_len, should_warn",
        [
            (1, False, 1200, True),   # warning
            (3, False, 1200, False),  # no warning
            (1, True, 1200, False),   # no warning
            (1, False, 500, False),   # no warning
        ]
    )
    def test_mixed_document_warning_only_when_few_tables_no_meta_and_long_text(
        self, tmp_path, mocker, n_tables, has_meta, text_len, should_warn
    ):
        mock_engine = MagicMock()
        mock_engine.supports_ocr = True
        mocker.patch("pipelines.bom_pipeline.create_engine", return_value=mock_engine)
        mocker.patch("presets.bom.get_bom_keywords", return_value={})
        mocker.patch("presets.bom.get_image_settings", return_value={})

        bom_result = MagicMock()
        bom_result.raw_text = "a" * text_len
        bom_result.drawing_metadata = {"dwg_no": "123" if has_meta else None}
        bom_result.bom_sections = [MagicMock()] * n_tables
        bom_result.line_list_sections = []
        
        mocker.patch("extractors.bom_extractor.extract_bom_with_retry", return_value=bom_result)
        mocker.patch("extractors.bom_extractor.to_sections", return_value=[])
        mocker.patch("exporters.json_exporter.JsonExporter.export")
        mocker.patch("utils.io._safe_write_text")
        
        mock_logger = mocker.patch("logging.Logger.warning")

        ctx = _make_ctx(tmp_path, engine="zai")
        BomPipeline(ctx).run()
        
        if should_warn:
            mock_logger.assert_called_once()
            assert "혼합 문서" in mock_logger.call_args[0][0]
        else:
            mock_logger.assert_not_called()
