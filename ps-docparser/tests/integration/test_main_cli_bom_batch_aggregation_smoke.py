from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import openpyxl

import main as cli_main


def _write_bom_json(out_dir: Path, stem: str) -> None:
    payload = [
        {
            "title": "BOM",
            "type": "bom",
            "tables": [
                {
                    "headers": ["DESCRIPTION", "SIZE", "MAT'L", "Q'TY", "WT(KG)"],
                    "rows": [
                        {
                            "DESCRIPTION": "PIPE",
                            "SIZE": "100A",
                            "MAT'L": "SS400",
                            "Q'TY": 2,
                            "WT(KG)": 10,
                        },
                        {
                            "DESCRIPTION": "PIPE",
                            "SIZE": "100A",
                            "MAT'L": "SS400",
                            "Q'TY": 3,
                            "WT(KG)": 15,
                        },
                    ],
                }
            ],
        }
    ]
    target = out_dir / f"20260424_{stem}_bom.json"
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )
    fallback_target = out_dir / f"20260424_{stem}_bom_fallback_estimate.json"
    fallback_payload = [
        {
            "title": "Fallback BOM",
            "type": "bom",
            "tables": [
                {
                    "headers": ["DESCRIPTION", "SIZE", "MAT'L", "Q'TY", "WT(KG)"],
                    "rows": [
                        {
                            "DESCRIPTION": "PIPE",
                            "SIZE": "100A",
                            "MAT'L": "SS400",
                            "Q'TY": 999,
                            "WT(KG)": 999,
                        }
                    ],
                }
            ],
        }
    ]
    fallback_target.write_text(
        json.dumps(fallback_payload, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )


def test_main_cli_batch_bom_aggregation_smoke(sample_pdf_dir: Path, tmp_path: Path, mocker):
    input_dir = tmp_path / "batch_input"
    input_dir.mkdir()
    shutil.copy2(sample_pdf_dir / "minimal.pdf", input_dir / "alpha.pdf")
    shutil.copy2(sample_pdf_dir / "minimal.pdf", input_dir / "beta.pdf")

    output_dir = tmp_path / "output"

    mocker.patch.object(cli_main, "validate_config", return_value={"errors": []})
    mocker.patch.object(cli_main, "_init_cache", return_value=None)
    mocker.patch.object(cli_main, "_project_root", tmp_path)

    def fake_process_single(args, input_path, out_dir, cache, tracker):
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        out_dir = Path(out_dir)
        stem = Path(input_path).stem
        _write_bom_json(out_dir, stem)
        from utils.run_manifest import make_artifact, record_manifest_entry

        record_manifest_entry(
            out_dir,
            {
                "source_pdf": Path(input_path).name,
                "preset": "bom",
                "engine": "zai",
                "status": "success",
                "primary": make_artifact(
                    output_dir=out_dir,
                    role="representative",
                    domain="bom",
                    json_path=out_dir / f"20260424_{stem}_bom.json",
                    quality_status="ok",
                ),
                "diagnostics": [
                    make_artifact(
                        output_dir=out_dir,
                        role="diagnostic",
                        domain="estimate",
                        json_path=out_dir / f"20260424_{stem}_bom_fallback_estimate.json",
                        quality_status="warning",
                    )
                ],
            },
        )

    mocker.patch.object(cli_main, "_process_single", side_effect=fake_process_single)
    mocker.patch.object(
        sys,
        "argv",
        [
            "main.py",
            str(input_dir),
            "--preset",
            "bom",
            "--engine",
            "zai",
            "--output",
            "excel",
            "--output-dir",
            str(output_dir),
        ],
    )

    cli_main.main()

    agg_files = list(output_dir.glob("*_BOM*.xlsx"))
    assert len(agg_files) == 1
    assert (output_dir / "RUN_MANIFEST.json").exists()

    workbook = openpyxl.load_workbook(agg_files[0])
    worksheet = workbook["BOM \uc9d1\uacc4"]
    assert [cell.value for cell in worksheet[1][:6]] == [
        "ITEM_NO",
        "DESCRIPTION",
        "SIZE",
        "MATERIAL",
        "Q'TY",
        "WT(KG)",
    ]
    assert [cell.value for cell in worksheet[2][:6]] == [
        1,
        "PIPE",
        "100A",
        "SS400",
        10,
        50,
    ]
