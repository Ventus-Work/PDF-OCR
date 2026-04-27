import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from detector import DetectionResult
from pipelines.base import PipelineContext
from pipelines.document_pipeline import DocumentPipeline, RoutingDecision
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


def _make_ctx(tmp_path, input_name="sample.md", **arg_overrides):
    args = _make_args(**arg_overrides)
    return PipelineContext(
        input_path=tmp_path / input_name,
        output_dir=tmp_path / "output",
        args=args,
        tracker=MagicMock(call_count=0),
    )


def _strong_md() -> str:
    return "<!-- PAGE 1 -->\n\n<table><tr><td>항목</td></tr></table>\n\n" + ("정상내용" * 80)


def _estimate_high_md() -> str:
    return (
        "# 견적서\n\n"
        "견적 견적금액 내역서 납품기일 결제조건 견적유효기간 직접비\n\n"
        "| 항목 | 금액 |\n| --- | --- |\n| 배관 | 1000 |\n"
    )


def _estimate_medium_md() -> str:
    return (
        "# 견적서\n\n"
        "견적 견적금액 내역서 납품기일\n\n"
        "| 항목 | 금액 |\n| --- | --- |\n| 배관 | 1000 |\n"
    )


def _pumsem_high_md() -> str:
    return (
        "# 품셈\n\n"
        "품셈 수량산출 부문 공종 단위 적용기준 노무비 참조\n\n"
        "| 항목 | 수량 |\n| --- | --- |\n| 배관 | 10 |\n"
    )


def _bom_high_md() -> str:
    return (
        "BILL OF MATERIALS\n\n"
        "S/N MARK WT(KG) Q'TY MAT'L LINE LIST\n\n"
        "<table><tr><th>DESCRIPTION</th></tr><tr><td>Plate</td></tr></table>"
    )


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8-sig")


def _patch_exporters(mocker):
    def fake_json_export(sections, path):
        _write_json(Path(path), sections)

    def fake_excel_export(sections, path, **kwargs):
        Path(path).touch()

    json_export = mocker.patch(
        "exporters.json_exporter.JsonExporter.export",
        side_effect=fake_json_export,
    )
    excel_export = mocker.patch(
        "exporters.excel_exporter.ExcelExporter.export",
        side_effect=fake_excel_export,
    )
    return json_export, excel_export


def _patch_parse_markdown(mocker):
    def fake_parse_markdown(md_text, **kwargs):
        type_keywords = kwargs.get("type_keywords")
        if type_keywords == {"kind": "estimate"}:
            return [{"section_id": "estimate", "clean_text": "cover", "tables": []}]
        if type_keywords == {"kind": "pumsem"}:
            return [{"section_id": "pumsem", "clean_text": "body", "tables": []}]
        return [{"section_id": "generic", "clean_text": "generic", "tables": []}]

    return mocker.patch(
        "parsers.document_parser.parse_markdown",
        side_effect=fake_parse_markdown,
    )


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

    def test_resolve_routing_decision_high_estimate_specializes(self, tmp_path):
        pipeline = DocumentPipeline(_make_ctx(tmp_path))
        result = DetectionResult(
            label="estimate",
            confidence="high",
            scores={"estimate": 6, "pumsem": 0, "bom": 0},
            reason_hits=["estimate:견적"],
            material_quote=False,
            suggestion="",
        )

        decision = pipeline._resolve_routing_decision(result)

        assert decision == RoutingDecision(
            mode="specialized",
            target_preset="estimate",
            save_compare=True,
            needs_confirmation=False,
            reason="estimate (high)",
        )

    def test_resolve_routing_decision_material_quote_stays_generic(self, tmp_path):
        pipeline = DocumentPipeline(_make_ctx(tmp_path))
        result = DetectionResult(
            label=None,
            confidence="low",
            scores={"estimate": 0, "pumsem": 0, "bom": 0},
            reason_hits=["material_quote"],
            material_quote=True,
            suggestion="generic",
        )

        decision = pipeline._resolve_routing_decision(result)

        assert decision.mode == "generic"
        assert decision.target_preset is None

    def test_resolve_routing_decision_bom_requires_pdf_input(self, tmp_path):
        pipeline = DocumentPipeline(_make_ctx(tmp_path, input_name="sample.md"))
        result = DetectionResult(
            label="bom",
            confidence="high",
            scores={"estimate": 0, "pumsem": 0, "bom": 6},
            reason_hits=["bom:BILL OF MATERIALS"],
            material_quote=False,
            suggestion="",
        )

        decision = pipeline._resolve_routing_decision(result)

        assert decision.mode == "generic"
        assert "requires original PDF input" in decision.reason

    def test_confirm_route_if_needed_accepts_specialized(self, tmp_path, mocker):
        pipeline = DocumentPipeline(_make_ctx(tmp_path))
        mocker.patch("builtins.input", return_value="")

        decision = pipeline._confirm_route_if_needed(
            RoutingDecision(
                mode="specialized",
                target_preset="estimate",
                save_compare=True,
                needs_confirmation=True,
                reason="estimate (medium)",
            )
        )

        assert decision.mode == "specialized"
        assert decision.target_preset == "estimate"
        assert decision.needs_confirmation is False

    def test_confirm_route_if_needed_cancel_raises(self, tmp_path, mocker):
        pipeline = DocumentPipeline(_make_ctx(tmp_path))
        mocker.patch("builtins.input", return_value="c")

        with pytest.raises(ParserError):
            pipeline._confirm_route_if_needed(
                RoutingDecision(
                    mode="specialized",
                    target_preset="estimate",
                    save_compare=True,
                    needs_confirmation=True,
                    reason="estimate (medium)",
                )
            )

    def test_run_explicit_preset_bypasses_auto_routing(self, tmp_path, mocker):
        md_file = tmp_path / "sample.md"
        md_file.write_text(_estimate_high_md(), encoding="utf-8")

        parse_markdown = _patch_parse_markdown(mocker)
        _patch_exporters(mocker)
        mocker.patch("presets.estimate.get_table_type_keywords", return_value={"kind": "estimate"})
        mocker.patch("presets.estimate.get_excel_config", return_value={"sheets": []})
        analyze = mocker.patch.object(DocumentPipeline, "_analyze_routing")

        ctx = PipelineContext(
            input_path=md_file,
            output_dir=tmp_path / "output",
            args=_make_args(preset="estimate"),
            tracker=MagicMock(call_count=0),
        )

        DocumentPipeline(ctx).run()

        analyze.assert_not_called()
        assert parse_markdown.call_count == 1
        assert parse_markdown.call_args.kwargs["type_keywords"] == {"kind": "estimate"}
        assert not (ctx.output_dir / "_compare").exists()
        output_json = next(ctx.output_dir.glob("*_sample.json"))
        sections = json.loads(output_json.read_text(encoding="utf-8-sig"))
        assert sections[0]["domain"] == "estimate"
        assert sections[0]["quality"] == {"status": "ok", "warnings": []}
        manifest = json.loads((ctx.output_dir / "RUN_MANIFEST.json").read_text(encoding="utf-8-sig"))
        assert manifest["inputs"][0]["primary"]["domain"] == "estimate"
        assert manifest["inputs"][0]["primary"]["role"] == "representative"

    def test_run_generic_preset_forces_generic_without_auto_routing(self, tmp_path, mocker):
        md_file = tmp_path / "sample.md"
        md_file.write_text(_estimate_high_md(), encoding="utf-8")

        parse_markdown = _patch_parse_markdown(mocker)
        _patch_exporters(mocker)
        analyze = mocker.patch.object(DocumentPipeline, "_analyze_routing")

        ctx = PipelineContext(
            input_path=md_file,
            output_dir=tmp_path / "output",
            args=_make_args(preset="generic"),
            tracker=MagicMock(call_count=0),
        )

        DocumentPipeline(ctx).run()

        analyze.assert_not_called()
        assert parse_markdown.call_count == 1
        assert parse_markdown.call_args.kwargs["type_keywords"] is None
        assert not (ctx.output_dir / "_compare").exists()
        manifest = json.loads((ctx.output_dir / "RUN_MANIFEST.json").read_text(encoding="utf-8-sig"))
        assert manifest["inputs"][0]["preset"] == "generic"
        assert manifest["inputs"][0]["primary"]["domain"] == "generic"

    def test_run_high_estimate_creates_compare_and_manifest(self, tmp_path, mocker):
        md_file = tmp_path / "sample.md"
        md_file.write_text(_estimate_high_md(), encoding="utf-8")

        parse_markdown = _patch_parse_markdown(mocker)
        _patch_exporters(mocker)
        mocker.patch("presets.estimate.get_table_type_keywords", return_value={"kind": "estimate"})
        mocker.patch("presets.estimate.get_excel_config", return_value={"sheets": []})
        mocker.patch("presets.estimate.extract_cover_metadata", return_value={"serial_no": "S-1"})

        ctx = PipelineContext(
            input_path=md_file,
            output_dir=tmp_path / "output",
            args=_make_args(output_format="excel"),
            tracker=MagicMock(call_count=0),
        )

        DocumentPipeline(ctx).run()

        assert parse_markdown.call_count == 2
        assert parse_markdown.call_args_list[0].kwargs["type_keywords"] is None
        assert parse_markdown.call_args_list[1].kwargs["type_keywords"] == {"kind": "estimate"}

        compare_dirs = list((ctx.output_dir / "_compare").iterdir())
        assert len(compare_dirs) == 1
        compare_dir = compare_dirs[0]
        manifest = json.loads((compare_dir / "route_manifest.json").read_text(encoding="utf-8"))
        assert manifest["target_preset"] == "estimate"
        assert manifest["chosen_mode"] == "specialized"
        assert manifest["compare_output_paths"]["md"].endswith(".md")
        assert manifest["final_output_paths"]["json"].endswith("_sample.json")
        run_manifest = json.loads((ctx.output_dir / "RUN_MANIFEST.json").read_text(encoding="utf-8-sig"))
        assert run_manifest["inputs"][0]["primary"]["domain"] == "estimate"

        assert len(list(ctx.output_dir.glob("*_sample.json"))) == 1
        assert len(list(ctx.output_dir.glob("*_sample.xlsx"))) == 1
        assert len(list((compare_dir / "generic").glob("*.md"))) == 1
        assert len(list((compare_dir / "generic").glob("*.json"))) == 1
        assert len(list((compare_dir / "generic").glob("*.xlsx"))) == 1

    def test_run_high_pumsem_creates_compare_and_manifest(self, tmp_path, mocker):
        md_file = tmp_path / "sample.md"
        md_file.write_text(_pumsem_high_md(), encoding="utf-8")

        parse_markdown = _patch_parse_markdown(mocker)
        _patch_exporters(mocker)
        mocker.patch("presets.pumsem.get_division_names", return_value=["A"])
        mocker.patch("presets.pumsem.get_parse_patterns", return_value={})
        mocker.patch("presets.pumsem.get_table_type_keywords", return_value={"kind": "pumsem"})

        ctx = PipelineContext(
            input_path=md_file,
            output_dir=tmp_path / "output",
            args=_make_args(output_format="json"),
            tracker=MagicMock(call_count=0),
        )

        DocumentPipeline(ctx).run()

        assert parse_markdown.call_count == 2
        assert parse_markdown.call_args_list[0].kwargs["type_keywords"] is None
        assert parse_markdown.call_args_list[1].kwargs["type_keywords"] == {"kind": "pumsem"}

        compare_dirs = list((ctx.output_dir / "_compare").iterdir())
        assert len(compare_dirs) == 1
        compare_dir = compare_dirs[0]
        manifest = json.loads((compare_dir / "route_manifest.json").read_text(encoding="utf-8"))
        assert manifest["target_preset"] == "pumsem"
        assert manifest["chosen_mode"] == "specialized"
        run_manifest = json.loads((ctx.output_dir / "RUN_MANIFEST.json").read_text(encoding="utf-8-sig"))
        assert run_manifest["inputs"][0]["primary"]["domain"] == "pumsem"

        assert len(list(ctx.output_dir.glob("*_sample.json"))) == 1
        assert len(list((compare_dir / "generic").glob("*.md"))) == 1
        assert len(list((compare_dir / "generic").glob("*.json"))) == 1
        assert not list((compare_dir / "generic").glob("*.xlsx"))

    def test_run_high_bom_delegates_to_bom_pipeline(self, tmp_path, mocker):
        input_pdf = tmp_path / "sample.pdf"
        input_pdf.write_bytes(b"%PDF-1.4")

        _patch_parse_markdown(mocker)
        _patch_exporters(mocker)

        pdf_context = MagicMock()
        pdf_context.__enter__.return_value.pages = [object()]
        pdf_context.__exit__.return_value = False

        mocker.patch("pipelines.document_pipeline.pdfplumber.open", return_value=pdf_context)
        mocker.patch.object(DocumentPipeline, "_build_engine", return_value=MagicMock())
        mocker.patch.object(DocumentPipeline, "_extract_md", return_value=_bom_high_md())

        def fake_bom_run(self):
            output_base = self._get_output_base("_bom")
            Path(str(output_base) + ".md").write_text("bom md", encoding="utf-8")
            Path(str(output_base) + ".json").write_text("[]", encoding="utf-8")

        bom_run = mocker.patch("pipelines.bom_pipeline.BomPipeline.run", autospec=True, side_effect=fake_bom_run)

        ctx = PipelineContext(
            input_path=input_pdf,
            output_dir=tmp_path / "output",
            args=_make_args(output_format="json", engine="local"),
            tracker=MagicMock(call_count=0),
        )

        DocumentPipeline(ctx).run()

        bom_run.assert_called_once()
        assert len(list(ctx.output_dir.glob("*_sample_bom.md"))) == 1
        assert len(list(ctx.output_dir.glob("*_sample_bom.json"))) == 1
        assert not list(ctx.output_dir.glob("*_sample.json"))

        compare_dirs = list((ctx.output_dir / "_compare").iterdir())
        assert len(compare_dirs) == 1
        manifest = json.loads((compare_dirs[0] / "route_manifest.json").read_text(encoding="utf-8"))
        assert manifest["target_preset"] == "bom"
        assert manifest["chosen_mode"] == "specialized"

    def test_run_high_bom_switches_to_bom_default_engine_when_current_engine_is_unsupported(
        self,
        tmp_path,
        mocker,
    ):
        input_pdf = tmp_path / "sample.pdf"
        input_pdf.write_bytes(b"%PDF-1.4")

        pdf_context = MagicMock()
        pdf_context.__enter__.return_value.pages = [object()]
        pdf_context.__exit__.return_value = False

        mocker.patch("pipelines.document_pipeline.pdfplumber.open", return_value=pdf_context)
        mocker.patch.object(DocumentPipeline, "_build_engine", return_value=MagicMock())
        mocker.patch.object(DocumentPipeline, "_extract_md", return_value=_bom_high_md())
        mocker.patch("pipelines.document_pipeline.config.BOM_DEFAULT_ENGINE", "zai")

        captured = {}

        def fake_bom_run(self):
            captured["engine"] = self.ctx.args.engine
            output_base = self._get_output_base("_bom")
            Path(str(output_base) + ".md").write_text("bom md", encoding="utf-8")
            Path(str(output_base) + ".json").write_text("[]", encoding="utf-8")

        mocker.patch("pipelines.bom_pipeline.BomPipeline.run", autospec=True, side_effect=fake_bom_run)

        ctx = PipelineContext(
            input_path=input_pdf,
            output_dir=tmp_path / "output",
            args=_make_args(output_format="json", engine="gemini"),
            tracker=MagicMock(call_count=0),
        )

        DocumentPipeline(ctx).run()

        assert captured["engine"] == "zai"

    def test_run_medium_estimate_in_batch_stays_generic(self, tmp_path, mocker):
        md_file = tmp_path / "sample.md"
        md_file.write_text(_estimate_medium_md(), encoding="utf-8")

        parse_markdown = _patch_parse_markdown(mocker)
        _patch_exporters(mocker)

        ctx = PipelineContext(
            input_path=md_file,
            output_dir=tmp_path / "output",
            args=_make_args(output_format="json", _is_batch_mode=True),
            tracker=MagicMock(call_count=0),
        )

        DocumentPipeline(ctx).run()

        assert parse_markdown.call_count == 1
        assert parse_markdown.call_args.kwargs["type_keywords"] is None
        assert not (ctx.output_dir / "_compare").exists()
        assert len(list(ctx.output_dir.glob("*_sample.json"))) == 1

    def test_run_medium_estimate_prompt_can_choose_generic(self, tmp_path, mocker):
        md_file = tmp_path / "sample.md"
        md_file.write_text(_estimate_medium_md(), encoding="utf-8")

        parse_markdown = _patch_parse_markdown(mocker)
        _patch_exporters(mocker)
        mocker.patch.object(DocumentPipeline, "_should_prompt_for_detected_preset", return_value=True)
        mocker.patch("builtins.input", return_value="g")

        ctx = PipelineContext(
            input_path=md_file,
            output_dir=tmp_path / "output",
            args=_make_args(output_format="json"),
            tracker=MagicMock(call_count=0),
        )

        DocumentPipeline(ctx).run()

        assert parse_markdown.call_count == 1
        assert parse_markdown.call_args.kwargs["type_keywords"] is None
        assert not (ctx.output_dir / "_compare").exists()

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
