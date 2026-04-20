import pytest
from pathlib import Path
from unittest.mock import MagicMock
from pipelines.base import PipelineContext
from pipelines.factory import create_pipeline
from pipelines.bom_pipeline import BomPipeline
from pipelines.document_pipeline import DocumentPipeline
from utils.io import ParserError


def _make_ctx(tmp_path, preset=None, engine=None):
    args = MagicMock()
    args.preset = preset
    args.engine = engine
    args.pages = None
    args.text_only = False
    return PipelineContext(
        input_path=tmp_path / "test.pdf",
        output_dir=tmp_path / "output",
        args=args,
    )


class TestCreatePipeline:
    def test_bom_preset_returns_bom_pipeline(self, tmp_path):
        ctx = _make_ctx(tmp_path, preset="bom")
        pipeline = create_pipeline(ctx)
        assert isinstance(pipeline, BomPipeline)

    def test_estimate_preset_returns_document_pipeline(self, tmp_path):
        ctx = _make_ctx(tmp_path, preset="estimate")
        pipeline = create_pipeline(ctx)
        assert isinstance(pipeline, DocumentPipeline)

    def test_none_preset_returns_document_pipeline(self, tmp_path):
        ctx = _make_ctx(tmp_path, preset=None)
        pipeline = create_pipeline(ctx)
        assert isinstance(pipeline, DocumentPipeline)

    def test_bom_pipeline_rejects_gemini_engine(self, tmp_path, mocker):
        """BOM 파이프라인은 gemini 엔진을 거부한다 (OCR 미지원)."""
        mock_engine = MagicMock()
        mock_engine.supports_ocr = False
        mocker.patch("pipelines.bom_pipeline.create_engine", return_value=mock_engine)
        mocker.patch("presets.bom.get_bom_keywords", return_value={})
        mocker.patch("presets.bom.get_image_settings", return_value={})

        ctx = _make_ctx(tmp_path, preset="bom", engine="gemini")
        pipeline = BomPipeline(ctx)
        with pytest.raises(ParserError, match="OCR 엔진"):
            pipeline.run()
