from pathlib import Path

from extractors.bom_types import BomExtractionResult, BomSection
from scripts.manual_ocr_smoke import run_smoke


def test_run_smoke_uses_current_factory_and_retry_signature(tmp_path, mocker):
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    tracker = mocker.Mock(call_count=0)
    engine = mocker.Mock()
    create_engine = mocker.patch("engines.factory.create_engine", return_value=engine)
    mocker.patch("utils.usage_tracker.UsageTracker", return_value=tracker)
    mocker.patch("presets.bom.get_bom_keywords", return_value={"k": "v"})
    mocker.patch("presets.bom.get_image_settings", return_value={"dpi": 300})

    result = BomExtractionResult(
        bom_sections=[BomSection(section_type="bom", headers=["ITEM"], rows=[["1"]])],
        line_list_sections=[BomSection(section_type="line_list", headers=["LINE"], rows=[["L-1"]])],
    )
    retry = mocker.patch("extractors.bom_ocr_retry.extract_bom_with_retry", return_value=result)
    sections = [{"section_id": "BOM-1", "tables": []}]
    to_sections = mocker.patch("extractors.bom_converter.to_sections", return_value=sections)

    returned = run_smoke(pdf_path, "zai")

    create_engine.assert_called_once_with("zai", tracker)
    retry.assert_called_once_with(engine, pdf_path, {"k": "v"}, {"dpi": 300})
    to_sections.assert_called_once_with(result)
    assert returned == sections
