from __future__ import annotations

import json
import sys
from pathlib import Path

import main as cli_main


def _estimate_high_md() -> str:
    return (
        "# 견적서\n\n"
        "견적 견적금액 내역서 납품기일 결제조건 견적유효기간 직접비\n\n"
        "| 항목 | 금액 |\n| --- | --- |\n| 배관 | 1000 |\n"
    )


def _pumsem_high_md() -> str:
    return (
        "# 품셈\n\n"
        "품셈 수량산출 부문 공종 단위 적용기준 노무비 참조\n\n"
        "| 항목 | 수량 |\n| --- | --- |\n| 배관 | 10 |\n"
    )


def _patch_parse_markdown(mocker):
    def fake_parse_markdown(md_text, **kwargs):
        type_keywords = kwargs.get("type_keywords")
        if type_keywords == {"kind": "estimate"}:
            return [{"section_id": "estimate", "clean_text": "estimate", "tables": []}]
        if type_keywords == {"kind": "pumsem"}:
            return [{"section_id": "pumsem", "clean_text": "pumsem", "tables": []}]
        return [{"section_id": "generic", "clean_text": "generic", "tables": []}]

    mocker.patch(
        "parsers.document_parser.parse_markdown",
        side_effect=fake_parse_markdown,
    )


def test_main_cli_estimate_auto_route_creates_root_final_and_compare_generic(
    sample_pdf_dir: Path,
    tmp_path: Path,
    mocker,
):
    input_pdf = sample_pdf_dir / "minimal.pdf"
    output_dir = tmp_path / "output"

    mocker.patch.object(cli_main, "validate_config", return_value={"errors": []})
    mocker.patch.object(cli_main, "_init_cache", return_value=None)
    mocker.patch.object(cli_main, "_project_root", tmp_path)
    mocker.patch("pipelines.document_pipeline.DocumentPipeline._build_engine")
    mocker.patch(
        "pipelines.document_pipeline.DocumentPipeline._extract_md",
        return_value=_estimate_high_md(),
    )
    _patch_parse_markdown(mocker)
    mocker.patch("presets.estimate.get_table_type_keywords", return_value={"kind": "estimate"})
    mocker.patch("presets.estimate.get_excel_config", return_value={"sheets": []})
    mocker.patch.object(
        sys,
        "argv",
        [
            "main.py",
            str(input_pdf),
            "--engine",
            "local",
            "--output",
            "json",
            "--output-dir",
            str(output_dir),
        ],
    )

    cli_main.main()

    root_md = next(output_dir.glob("*_minimal.md"))
    root_json = next(output_dir.glob("*_minimal.json"))
    compare_dir = next((output_dir / "_compare").iterdir())
    compare_md = next((compare_dir / "generic").glob("*.md"))
    compare_json = next((compare_dir / "generic").glob("*.json"))

    assert root_md.exists()
    assert root_json.exists()
    assert compare_md.exists()
    assert compare_json.exists()

    root_sections = json.loads(root_json.read_text(encoding="utf-8-sig"))
    compare_sections = json.loads(compare_json.read_text(encoding="utf-8-sig"))
    assert root_sections[0]["section_id"] == "estimate"
    assert compare_sections[0]["section_id"] == "generic"

    manifest = json.loads((compare_dir / "route_manifest.json").read_text(encoding="utf-8"))
    assert manifest["target_preset"] == "estimate"
    assert manifest["chosen_mode"] == "specialized"


def test_main_cli_pumsem_auto_route_creates_root_final_and_compare_generic(
    sample_pdf_dir: Path,
    tmp_path: Path,
    mocker,
):
    input_pdf = sample_pdf_dir / "minimal.pdf"
    output_dir = tmp_path / "output"

    mocker.patch.object(cli_main, "validate_config", return_value={"errors": []})
    mocker.patch.object(cli_main, "_init_cache", return_value=None)
    mocker.patch.object(cli_main, "_project_root", tmp_path)
    mocker.patch("pipelines.document_pipeline.DocumentPipeline._build_engine")
    mocker.patch(
        "pipelines.document_pipeline.DocumentPipeline._extract_md",
        return_value=_pumsem_high_md(),
    )
    _patch_parse_markdown(mocker)
    mocker.patch("presets.pumsem.get_division_names", return_value=["A"])
    mocker.patch("presets.pumsem.get_parse_patterns", return_value={})
    mocker.patch("presets.pumsem.get_table_type_keywords", return_value={"kind": "pumsem"})
    mocker.patch.object(
        sys,
        "argv",
        [
            "main.py",
            str(input_pdf),
            "--engine",
            "local",
            "--output",
            "json",
            "--output-dir",
            str(output_dir),
        ],
    )

    cli_main.main()

    root_json = next(output_dir.glob("*_minimal.json"))
    compare_dir = next((output_dir / "_compare").iterdir())
    compare_json = next((compare_dir / "generic").glob("*.json"))

    root_sections = json.loads(root_json.read_text(encoding="utf-8-sig"))
    compare_sections = json.loads(compare_json.read_text(encoding="utf-8-sig"))
    assert root_sections[0]["section_id"] == "pumsem"
    assert compare_sections[0]["section_id"] == "generic"

    manifest = json.loads((compare_dir / "route_manifest.json").read_text(encoding="utf-8"))
    assert manifest["target_preset"] == "pumsem"
    assert manifest["chosen_mode"] == "specialized"
