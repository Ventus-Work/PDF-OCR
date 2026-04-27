from __future__ import annotations

import json

import pytest

from api.artifacts import encode_artifact_id, list_artifacts, parse_qa, resolve_artifact_path
from api.errors import ApiError
from api.jobs import JobManager
from api.schemas import JobOptions


def make_record_with_outputs(tmp_path):
    manager = JobManager(base_output_dir=tmp_path / "ui_runs", auto_start=False)
    record = manager.create_job(
        filename="sample.pdf",
        content=b"%PDF-1.4\n%%EOF",
        options=JobOptions(preset="bom", engine="zai"),
    )
    result = record.result_dir
    (result / "sample_bom.md").write_text("# md\n", encoding="utf-8")
    (result / "sample_bom.json").write_text("[]\n", encoding="utf-8")
    (result / "sample_bom.xlsx").write_bytes(b"xlsx")
    compare_dir = result / "_compare" / "sample" / "generic"
    compare_dir.mkdir(parents=True)
    (compare_dir / "sample.json").write_text("[]\n", encoding="utf-8")
    (result / "RUN_SUMMARY.md").write_text("# summary\n", encoding="utf-8")
    (result / "OUTPUT_QA_REPORT.md").write_text(
        "\n".join(
            [
                "# Output QA Report",
                "",
                "- Status: `WARN`",
                "- JSON files: `1`",
                "- Excel files: `1`",
                "- RUN_MANIFEST.json: `yes`",
                "- Manifest inputs: `1`",
                "- Manifest representative: `1`",
                "- Manifest diagnostic: `1`",
                "- Header/key mismatch: `0`",
                "- Bad composite headers: `0`",
                "",
                "## Quality Warnings",
                "",
                "- `empty_tail_column`: 1",
                "",
                "## Manifest Domains",
                "",
                "- `bom`: 1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    manifest = {
        "inputs": [
            {
                "source_pdf": "sample.pdf",
                "primary": {
                    "role": "representative",
                    "domain": "bom",
                    "quality_status": "warning",
                    "md": "sample_bom.md",
                    "json": "sample_bom.json",
                    "xlsx": "sample_bom.xlsx",
                },
                "diagnostics": [
                    {
                        "role": "diagnostic",
                        "domain": "estimate",
                        "quality_status": "ok",
                        "json": "sample_estimate.json",
                    }
                ],
            }
        ]
    }
    (result / "RUN_MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    return record


def test_list_artifacts_merges_manifest_metadata(tmp_path):
    record = make_record_with_outputs(tmp_path)

    response = list_artifacts(record)

    assert [item.name for item in response.artifacts[:3]] == [
        "RUN_MANIFEST.json",
        "RUN_SUMMARY.md",
        "OUTPUT_QA_REPORT.md",
    ]
    bom_json = next(item for item in response.artifacts if item.name == "sample_bom.json")
    assert bom_json.role == "representative"
    assert bom_json.domain == "bom"
    assert bom_json.quality_status == "warning"
    compare_json = next(item for item in response.artifacts if item.relative_path == "_compare/sample/generic/sample.json")
    assert compare_json.role == "compare"
    assert compare_json.domain == "generic"


def test_parse_qa_report(tmp_path):
    record = make_record_with_outputs(tmp_path)

    qa = parse_qa(record)

    assert qa.status == "warn"
    assert qa.json_files == 1
    assert qa.excel_files == 1
    assert qa.has_manifest is True
    assert qa.manifest_representative == 1
    assert qa.manifest_diagnostic == 1
    assert qa.header_key_mismatch == 0
    assert qa.bad_composite_headers == 0
    assert qa.quality_warnings == {"empty_tail_column": 1}
    assert qa.manifest_domains == {"bom": 1}


def test_resolve_artifact_blocks_path_traversal(tmp_path):
    record = make_record_with_outputs(tmp_path)

    with pytest.raises(ApiError) as exc_info:
        resolve_artifact_path(record, encode_artifact_id("../secret.json"))

    assert exc_info.value.code == "unsafe_path"


def test_resolve_artifact_allows_known_file(tmp_path):
    record = make_record_with_outputs(tmp_path)

    path = resolve_artifact_path(record, encode_artifact_id("sample_bom.json"))

    assert path.name == "sample_bom.json"
