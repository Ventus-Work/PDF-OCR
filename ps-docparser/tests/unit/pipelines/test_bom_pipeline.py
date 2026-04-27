import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from pipelines.base import PipelineContext
from pipelines.bom_pipeline import BomPipeline, _apply_estimate_ocr_corrections
from utils.io import ParserError


def _make_ctx(
    tmp_path,
    engine=None,
    output_format="json",
    pages=None,
    no_bom_fallback=False,
    bom_fallback="auto",
):
    args = MagicMock()
    args.preset = "bom"
    args.engine = engine
    args.output_format = output_format
    args.pages = pages
    args.no_bom_fallback = no_bom_fallback
    args.bom_fallback = bom_fallback
    return PipelineContext(
        input_path=tmp_path / "sample.pdf",
        output_dir=tmp_path / "output",
        args=args,
        tracker=MagicMock(call_count=0),
    )


class TestBomPipeline:
    def test_apply_estimate_ocr_corrections_uses_conservative_dictionary(self):
        text = "HD현대오일백크 건적금액 결적유효기간 신급금 충합계 적절비"

        corrected = _apply_estimate_ocr_corrections(text)

        assert corrected == "HD현대오일뱅크 견적금액 견적유효기간 선급금 총합계 직접비"

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
        mocker.patch("pipelines.bom_pipeline._safe_write_text")

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
        mocker.patch("pipelines.bom_pipeline._safe_write_text")

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
        mocker.patch("pipelines.bom_pipeline._safe_write_text")
        
        mock_logger = mocker.patch("logging.Logger.warning")

        ctx = _make_ctx(tmp_path, engine="zai")
        BomPipeline(ctx).run()
        
        if should_warn:
            assert mock_logger.called
            assert any("혼합 문서" in call.args[0] for call in mock_logger.call_args_list)
        else:
            mock_logger.assert_not_called()

    def test_material_quote_warning_when_bom_empty(self, tmp_path, mocker):
        mock_engine = MagicMock()
        mock_engine.supports_ocr = True
        mocker.patch("pipelines.bom_pipeline.create_engine", return_value=mock_engine)
        mocker.patch("presets.bom.get_bom_keywords", return_value={})
        mocker.patch("presets.bom.get_image_settings", return_value={})

        bom_result = MagicMock()
        bom_result.raw_text = ("견적서 거래처 결정금액 품목 치수 수량 단가 단위 공급가액 메모 " * 30).strip()
        bom_result.drawing_metadata = {"dwg_no": None}
        bom_result.bom_sections = []
        bom_result.line_list_sections = []

        mocker.patch("extractors.bom_extractor.extract_bom_with_retry", return_value=bom_result)
        mocker.patch("extractors.bom_extractor.to_sections", return_value=[])
        mocker.patch("exporters.json_exporter.JsonExporter.export")
        mocker.patch("pipelines.bom_pipeline._safe_write_text")
        mocker.patch("pipelines.bom_pipeline.detect_material_quote", return_value=True)

        mock_logger = mocker.patch("logging.Logger.warning")

        ctx = _make_ctx(tmp_path, engine="zai")
        BomPipeline(ctx).run()

        assert mock_logger.called
        assert any("비-BOM 자재 견적표" in call.args[0] for call in mock_logger.call_args_list)

    def test_material_quote_auto_fallback_exports_estimate_artifacts(self, tmp_path, mocker):
        mock_engine = MagicMock()
        mock_engine.supports_ocr = True
        mocker.patch("pipelines.bom_pipeline.create_engine", return_value=mock_engine)
        mocker.patch("presets.bom.get_bom_keywords", return_value={})
        mocker.patch("presets.bom.get_image_settings", return_value={})

        bom_result = MagicMock()
        bom_result.raw_text = ("quote item qty unit price amount memo " * 40).strip()
        bom_result.drawing_metadata = {"dwg_no": None}
        bom_result.bom_sections = []
        bom_result.line_list_sections = []

        mocker.patch("extractors.bom_extractor.extract_bom_with_retry", return_value=bom_result)
        mocker.patch("extractors.bom_extractor.to_sections", return_value=[])
        mocker.patch("pipelines.bom_pipeline.detect_material_quote", return_value=True)

        json_export = mocker.patch("exporters.json_exporter.JsonExporter.export")
        excel_export = mocker.patch("exporters.excel_exporter.ExcelExporter.export")
        safe_write = mocker.patch("pipelines.bom_pipeline._safe_write_text")
        process_doc = mocker.patch(
            "extractors.ocr_document_extractor.process_pdf_ocr_document",
            return_value="<table><tr><td>estimate</td></tr></table>",
        )
        parse_markdown = mocker.patch(
            "parsers.document_parser.parse_markdown",
            return_value=[{"section_id": "doc", "clean_text": "cover", "tables": []}],
        )
        mocker.patch("presets.estimate.get_table_type_keywords", return_value={"kind": "estimate"})
        mocker.patch("presets.estimate.get_excel_config", return_value={"sheets": []})
        mocker.patch("presets.estimate.extract_cover_metadata", return_value={"serial_no": "S-1"})

        ctx = _make_ctx(tmp_path, engine="zai", output_format="excel")
        BomPipeline(ctx).run()

        assert process_doc.called
        assert parse_markdown.call_count == 1
        assert json_export.call_count == 2
        assert excel_export.call_count == 2
        assert safe_write.call_count == 2

        written_md_paths = [call.args[0].name for call in safe_write.call_args_list]
        written_json_paths = [call.args[1].name for call in json_export.call_args_list]
        written_xlsx_paths = [call.args[1].name for call in excel_export.call_args_list]
        assert any(name.endswith("_bom.md") for name in written_md_paths)
        assert any(name.endswith("_bom_fallback_estimate.md") for name in written_md_paths)
        assert any(name.endswith("_bom.json") for name in written_json_paths)
        assert any(name.endswith("_bom_fallback_estimate.json") for name in written_json_paths)
        assert any(name.endswith("_bom.xlsx") for name in written_xlsx_paths)
        assert any(
            name.endswith("_bom_fallback_estimate.xlsx")
            for name in written_xlsx_paths
        )

    def test_no_bom_fallback_keeps_warning_but_skips_estimate_rerun(
        self,
        tmp_path,
        mocker,
        capsys,
    ):
        mock_engine = MagicMock()
        mock_engine.supports_ocr = True
        mocker.patch("pipelines.bom_pipeline.create_engine", return_value=mock_engine)
        mocker.patch("presets.bom.get_bom_keywords", return_value={})
        mocker.patch("presets.bom.get_image_settings", return_value={})

        bom_result = MagicMock()
        bom_result.raw_text = ("quote item qty unit price amount memo " * 40).strip()
        bom_result.drawing_metadata = {"dwg_no": None}
        bom_result.bom_sections = []
        bom_result.line_list_sections = []

        mocker.patch("extractors.bom_extractor.extract_bom_with_retry", return_value=bom_result)
        mocker.patch("extractors.bom_extractor.to_sections", return_value=[])
        mocker.patch("pipelines.bom_pipeline.detect_material_quote", return_value=True)

        json_export = mocker.patch("exporters.json_exporter.JsonExporter.export")
        excel_export = mocker.patch("exporters.excel_exporter.ExcelExporter.export")
        safe_write = mocker.patch("pipelines.bom_pipeline._safe_write_text")
        process_doc = mocker.patch(
            "extractors.ocr_document_extractor.process_pdf_ocr_document"
        )
        mock_logger = mocker.patch("logging.Logger.warning")

        ctx = _make_ctx(
            tmp_path,
            engine="zai",
            output_format="excel",
            no_bom_fallback=True,
        )
        BomPipeline(ctx).run()

        captured = capsys.readouterr().out
        assert "비-BOM 자재 견적표" in captured
        assert "자동 폴백 비활성화(--bom-fallback never)" in captured
        assert any("비-BOM 자재 견적표" in call.args[0] for call in mock_logger.call_args_list)
        assert process_doc.call_count == 0
        assert json_export.call_count == 1
        assert excel_export.call_count == 1
        assert safe_write.call_count == 1

    def test_auto_fallback_skips_strong_bom_with_line_list(self, tmp_path, mocker):
        mock_engine = MagicMock()
        mock_engine.supports_ocr = True
        mocker.patch("pipelines.bom_pipeline.create_engine", return_value=mock_engine)
        mocker.patch("presets.bom.get_bom_keywords", return_value={})
        mocker.patch("presets.bom.get_image_settings", return_value={})

        bom_section = MagicMock()
        bom_section.headers = ["S/N", "SIZE", "MAT'L", "Q'TY", "WT(kg)"]
        bom_section.rows = [["1", "H200", "SS275", "890", "44.41"]]
        line_section = MagicMock()
        line_section.headers = ["LINE NO.", "SIZE", "ITEM"]
        line_section.rows = [["L-001", "450A", "GUIDE"]]

        bom_result = MagicMock()
        bom_result.raw_text = "BILL OF MATERIALS LINE LIST " * 100
        bom_result.drawing_metadata = {"dwg_no": None}
        bom_result.bom_sections = [bom_section]
        bom_result.line_list_sections = [line_section]

        mocker.patch("extractors.bom_extractor.extract_bom_with_retry", return_value=bom_result)
        mocker.patch("extractors.bom_extractor.to_sections", return_value=[])
        mocker.patch("exporters.json_exporter.JsonExporter.export")
        mocker.patch("exporters.excel_exporter.ExcelExporter.export")
        mocker.patch("pipelines.bom_pipeline._safe_write_text")
        process_doc = mocker.patch("extractors.ocr_document_extractor.process_pdf_ocr_document")

        ctx = _make_ctx(tmp_path, engine="zai", output_format="excel")
        BomPipeline(ctx).run()

        assert process_doc.call_count == 0

    def test_bom_fallback_always_forces_diagnostic_artifact(self, tmp_path, mocker):
        mock_engine = MagicMock()
        mock_engine.supports_ocr = True
        mocker.patch("pipelines.bom_pipeline.create_engine", return_value=mock_engine)
        mocker.patch("presets.bom.get_bom_keywords", return_value={})
        mocker.patch("presets.bom.get_image_settings", return_value={})

        bom_result = MagicMock()
        bom_result.raw_text = "short bom"
        bom_result.drawing_metadata = {"dwg_no": "D-1"}
        bom_result.bom_sections = []
        bom_result.line_list_sections = []

        mocker.patch("extractors.bom_extractor.extract_bom_with_retry", return_value=bom_result)
        mocker.patch("extractors.bom_extractor.to_sections", return_value=[])
        mocker.patch("exporters.json_exporter.JsonExporter.export")
        mocker.patch("exporters.excel_exporter.ExcelExporter.export")
        mocker.patch("pipelines.bom_pipeline._safe_write_text")
        process_doc = mocker.patch(
            "extractors.ocr_document_extractor.process_pdf_ocr_document",
            return_value="<table><tr><td>estimate</td></tr></table>",
        )
        mocker.patch(
            "parsers.document_parser.parse_markdown",
            return_value=[{"section_id": "doc", "clean_text": "cover", "tables": []}],
        )
        mocker.patch("presets.estimate.get_table_type_keywords", return_value={})
        mocker.patch("presets.estimate.get_excel_config", return_value={})
        mocker.patch("presets.estimate.extract_cover_metadata", return_value={})

        ctx = _make_ctx(tmp_path, engine="zai", output_format="excel", bom_fallback="always")
        result = BomPipeline(ctx).run()

        assert process_doc.call_count == 1
        assert result["diagnostics"][0]["role"] == "diagnostic"
        assert (tmp_path / "output" / "RUN_MANIFEST.json").exists()

    def test_mixed_document_fallback_is_reported_as_first_class_artifact(self, tmp_path, mocker):
        mock_engine = MagicMock()
        mock_engine.supports_ocr = True
        mocker.patch("pipelines.bom_pipeline.create_engine", return_value=mock_engine)
        mocker.patch("presets.bom.get_bom_keywords", return_value={})
        mocker.patch("presets.bom.get_image_settings", return_value={})

        bom_result = MagicMock()
        bom_result.raw_text = "견적 직접비 간접비 DESCRIPTION MAT'L " * 80
        bom_result.drawing_metadata = {"dwg_no": None}
        bom_result.bom_sections = [MagicMock()]
        bom_result.line_list_sections = []
        bom_result.bom_sections[0].headers = ["DESCRIPTION", "수량"]
        bom_result.bom_sections[0].rows = [["Scaffolding", "1"]]

        mocker.patch("extractors.bom_extractor.extract_bom_with_retry", return_value=bom_result)
        mocker.patch("extractors.bom_extractor.to_sections", return_value=[])
        mocker.patch("exporters.json_exporter.JsonExporter.export")
        mocker.patch("exporters.excel_exporter.ExcelExporter.export")
        mocker.patch("pipelines.bom_pipeline._safe_write_text")
        mocker.patch(
            "extractors.ocr_document_extractor.process_pdf_ocr_document",
            return_value="<table><tr><td>견적</td></tr></table>",
        )
        mocker.patch(
            "parsers.document_parser.parse_markdown",
            return_value=[
                {
                    "section_id": "doc",
                    "clean_text": "견적",
                    "tables": [
                        {
                            "headers": ["품명", "수량", "금액"],
                            "rows": [{"품명": "설치", "수량": "1", "금액": "1000"}],
                        }
                    ],
                }
            ],
        )
        mocker.patch("presets.estimate.get_table_type_keywords", return_value={})
        mocker.patch("presets.estimate.get_excel_config", return_value={})
        mocker.patch("presets.estimate.extract_cover_metadata", return_value={})

        ctx = _make_ctx(tmp_path, engine="zai", output_format="excel")
        result = BomPipeline(ctx).run()

        assert result["warnings"] == ["mixed_document"]
        assert result["diagnostics"][0]["role"] == "representative"
        assert result["diagnostics"][0]["domain"] == "estimate"
