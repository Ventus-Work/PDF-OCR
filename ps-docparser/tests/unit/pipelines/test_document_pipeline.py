from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from pipelines.base import PipelineContext
from pipelines.document_pipeline import DocumentPipeline
from utils.io import ParserError


def _make_args(**overrides):
    base = {
        "preset": None,
        "engine": None,
        "output_format": "json",
        "text_only": False,
        "pages": None,
        "toc": None,
        "_is_batch_mode": False,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_ctx(tmp_path, **arg_overrides):
    args = _make_args(**arg_overrides)
    return PipelineContext(
        input_path=tmp_path / "sample.md",
        output_dir=tmp_path / "output",
        args=args,
        tracker=MagicMock(call_count=0),
    )


def _strong_md() -> str:
    return "<!-- PAGE 1 -->\n\n<table><tr><td>품목</td></tr></table>\n\n" + ("정상내용" * 80)


class TestDocumentPipeline:
    def test_validate_engine_accepts_ocr_engines(self, tmp_path):
        for engine_name in ("zai", "mistral", "tesseract"):
            pipeline = DocumentPipeline(_make_ctx(tmp_path, engine=engine_name))
            pipeline._validate_engine(engine_name)

    def test_validate_engine_rejects_unknown_engine(self, tmp_path):
        pipeline = DocumentPipeline(_make_ctx(tmp_path, engine="unknown"))
        with pytest.raises(ParserError, match="지원하지 않는 엔진"):
            pipeline._validate_engine("unknown")

    def test_pumsem_preset_loads_resources(self, tmp_path, mocker):
        mocker.patch("presets.pumsem.get_division_names", return_value=["A", "B"])
        mocker.patch("presets.pumsem.get_parse_patterns", return_value={})
        mocker.patch("presets.pumsem.get_table_type_keywords", return_value={})

        pipeline = DocumentPipeline(_make_ctx(tmp_path, preset="pumsem"))
        data = pipeline._load_preset("pumsem")

        assert data["division_names"] == ["A", "B"]

    def test_estimate_preset_loads_resources(self, tmp_path, mocker):
        mocker.patch("presets.estimate.get_table_type_keywords", return_value={"k": "v"})
        mocker.patch("presets.estimate.get_excel_config", return_value={"sheets": []})

        pipeline = DocumentPipeline(_make_ctx(tmp_path, preset="estimate"))
        data = pipeline._load_preset("estimate")

        assert data["type_keywords"] == {"k": "v"}
        assert data["excel_config"] == {"sheets": []}

    def test_md_input_skips_phase1_and_produces_json(self, tmp_path, mocker):
        md_file = tmp_path / "sample.md"
        md_file.write_text("# 테스트\n내용", encoding="utf-8")

        mocker.patch(
            "parsers.document_parser.parse_markdown",
            return_value=[{"section_id": "1", "title": "테스트", "tables": []}],
        )
        export_json = mocker.patch("exporters.json_exporter.JsonExporter.export")

        ctx = PipelineContext(
            input_path=md_file,
            output_dir=tmp_path / "output",
            args=_make_args(),
            tracker=MagicMock(call_count=0),
        )
        ctx.output_dir.mkdir()

        DocumentPipeline(ctx).run()

        export_json.assert_called_once()

    def test_maybe_confirm_detected_preset_accepts_estimate(self, tmp_path, mocker):
        pipeline = DocumentPipeline(_make_ctx(tmp_path))
        mocker.patch.object(pipeline, "_should_prompt_for_detected_preset", return_value=True)
        mocker.patch("detector.detect_document_type", return_value="estimate")
        mocker.patch("builtins.input", return_value="")

        assert pipeline._maybe_confirm_detected_preset("estimate-like text") == "estimate"

    def test_should_prompt_for_detected_preset_returns_false_in_batch_mode(self, tmp_path, mocker):
        pipeline = DocumentPipeline(_make_ctx(tmp_path, _is_batch_mode=True))

        stdin = mocker.Mock()
        stdout = mocker.Mock()
        stdin.isatty.return_value = True
        stdout.isatty.return_value = True
        mocker.patch("pipelines.document_pipeline.sys.stdin", stdin)
        mocker.patch("pipelines.document_pipeline.sys.stdout", stdout)

        assert pipeline._should_prompt_for_detected_preset() is False

    def test_should_prompt_for_detected_preset_returns_false_without_isatty(self, tmp_path, mocker):
        pipeline = DocumentPipeline(_make_ctx(tmp_path))

        stdin = mocker.Mock()
        stdin.isatty.return_value = True
        mocker.patch("pipelines.document_pipeline.sys.stdin", stdin)
        mocker.patch("pipelines.document_pipeline.sys.stdout", object())

        assert pipeline._should_prompt_for_detected_preset() is False

    def test_maybe_confirm_detected_preset_cancel_raises(self, tmp_path, mocker):
        pipeline = DocumentPipeline(_make_ctx(tmp_path))
        mocker.patch.object(pipeline, "_should_prompt_for_detected_preset", return_value=True)
        mocker.patch("detector.detect_document_type", return_value="estimate")
        mocker.patch("builtins.input", return_value="c")

        with pytest.raises(ParserError):
            pipeline._maybe_confirm_detected_preset("estimate-like text")

    def test_run_uses_confirmed_estimate_preset_without_reextracting_md(self, tmp_path, mocker):
        md_file = tmp_path / "sample.md"
        md_file.write_text("estimate-like text", encoding="utf-8")

        parse_markdown = mocker.patch(
            "parsers.document_parser.parse_markdown",
            return_value=[{"section_id": "1", "title": "t", "tables": []}],
        )
        mocker.patch("exporters.json_exporter.JsonExporter.export")
        mocker.patch.object(DocumentPipeline, "_should_prompt_for_detected_preset", return_value=True)
        mocker.patch("detector.detect_document_type", return_value="estimate")
        mocker.patch("builtins.input", return_value="")
        mocker.patch("presets.estimate.get_table_type_keywords", return_value={"kind": "estimate"})
        mocker.patch("presets.estimate.get_excel_config", return_value={"sheets": []})

        ctx = PipelineContext(
            input_path=md_file,
            output_dir=tmp_path / "output",
            args=_make_args(),
            tracker=MagicMock(call_count=0),
        )
        ctx.output_dir.mkdir()

        DocumentPipeline(ctx).run()

        assert ctx.args.preset == "estimate"
        assert parse_markdown.call_args.kwargs["type_keywords"] == {"kind": "estimate"}

    def test_extract_md_local_weak_output_triggers_zai_fallback(self, tmp_path, mocker):
        pipeline = DocumentPipeline(_make_ctx(tmp_path, engine="local"))
        weak_md = "<!-- PAGE 1 -->\n\n없음"
        strong_md = _strong_md()

        mocker.patch.object(pipeline, "_expected_pages", return_value=1)
        build_engine = mocker.patch.object(pipeline, "_build_engine", return_value=MagicMock())

        def fake_run(*, engine_name, **kwargs):
            return weak_md if engine_name == "local" else strong_md

        run_extract = mocker.patch.object(
            pipeline,
            "_run_extraction_with_engine",
            side_effect=fake_run,
        )

        result = pipeline._extract_md(
            args=pipeline.ctx.args,
            input_path=tmp_path / "scan.pdf",
            engine_name="local",
            engine=MagicMock(),
            section_map=None,
            page_indices=None,
            preset=None,
            preset_data={},
        )

        assert result == strong_md
        build_engine.assert_called_once_with("zai")
        assert [call.kwargs["engine_name"] for call in run_extract.call_args_list] == ["local", "zai"]

    def test_extract_md_gemini_strong_output_skips_fallback(self, tmp_path, mocker):
        pipeline = DocumentPipeline(_make_ctx(tmp_path, engine="gemini"))
        strong_md = _strong_md()

        mocker.patch.object(pipeline, "_expected_pages", return_value=1)
        mocker.patch.object(
            pipeline,
            "_run_extraction_with_engine",
            return_value=strong_md,
        )
        build_engine = mocker.patch.object(pipeline, "_build_engine")

        result = pipeline._extract_md(
            args=pipeline.ctx.args,
            input_path=tmp_path / "strong.pdf",
            engine_name="gemini",
            engine=MagicMock(),
            section_map=None,
            page_indices=None,
            preset=None,
            preset_data={},
        )

        assert result == strong_md
        build_engine.assert_not_called()

    def test_extract_md_explicit_zai_uses_direct_ocr_without_chain(self, tmp_path, mocker):
        pipeline = DocumentPipeline(_make_ctx(tmp_path, engine="zai"))
        run_extract = mocker.patch.object(
            pipeline,
            "_run_extraction_with_engine",
            return_value="<table><tr><td>x</td></tr></table>",
        )
        build_engine = mocker.patch.object(pipeline, "_build_engine")

        result = pipeline._extract_md(
            args=pipeline.ctx.args,
            input_path=tmp_path / "scan.pdf",
            engine_name="zai",
            engine=MagicMock(),
            section_map=None,
            page_indices=None,
            preset=None,
            preset_data={},
        )

        assert "<table>" in result
        build_engine.assert_not_called()
        assert len(run_extract.call_args_list) == 1
        assert run_extract.call_args.kwargs["engine_name"] == "zai"

    def test_extract_md_text_only_never_uses_fallback(self, tmp_path, mocker):
        args = _make_args(text_only=True)
        ctx = PipelineContext(
            input_path=tmp_path / "sample.pdf",
            output_dir=tmp_path / "output",
            args=args,
            tracker=MagicMock(call_count=0),
        )
        pipeline = DocumentPipeline(ctx)

        text_only = mocker.patch(
            "extractors.text_extractor.process_pdf_text_only",
            return_value="plain text",
        )
        run_extract = mocker.patch.object(pipeline, "_run_extraction_with_engine")

        result = pipeline._extract_md(
            args=args,
            input_path=ctx.input_path,
            engine_name="local",
            engine=None,
            section_map=None,
            page_indices=None,
            preset=None,
            preset_data={},
        )

        assert result == "plain text"
        text_only.assert_called_once()
        run_extract.assert_not_called()
