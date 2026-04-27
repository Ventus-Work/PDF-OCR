import json

from utils.run_manifest import (
    make_artifact,
    record_manifest_entry,
    representative_bom_jsons_from_manifest,
)


def test_record_manifest_entry_and_select_representative_bom_json(tmp_path):
    out_dir = tmp_path / "output"
    out_dir.mkdir()
    primary_json = out_dir / "sample_bom.json"
    fallback_json = out_dir / "sample_bom_fallback_estimate.json"
    primary_json.write_text("[]", encoding="utf-8-sig")
    fallback_json.write_text("[]", encoding="utf-8-sig")

    entry = {
        "source_pdf": "sample.pdf",
        "preset": "bom",
        "engine": "zai",
        "status": "success",
        "primary": make_artifact(
            output_dir=out_dir,
            role="representative",
            domain="bom",
            json_path=primary_json,
            quality_status="ok",
        ),
        "diagnostics": [
            make_artifact(
                output_dir=out_dir,
                role="representative",
                domain="estimate",
                json_path=fallback_json,
                quality_status="warning",
                kind="fallback_estimate",
            )
        ],
    }

    manifest_path = record_manifest_entry(out_dir, entry)

    assert manifest_path.exists()
    assert (out_dir / "RUN_SUMMARY.md").exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    assert manifest["inputs"][0]["primary"]["role"] == "representative"
    summary = (out_dir / "RUN_SUMMARY.md").read_text(encoding="utf-8-sig")
    assert "## 1급 산출물" in summary
    assert "sample_bom_fallback_estimate.json" in summary
    assert representative_bom_jsons_from_manifest(out_dir) == [primary_json]
