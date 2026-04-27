from __future__ import annotations

import json

from openpyxl import Workbook

from tools.analyze_outputs import analyze_output_dir, write_report


def test_analyze_output_dir_reports_manifest_counts(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "RUN_MANIFEST.json").write_text(
        json.dumps(
            {
                "inputs": [
                    {
                        "primary": {
                            "role": "representative",
                            "domain": "bom",
                            "json": "sample_bom.json",
                        },
                        "diagnostics": [
                            {
                                "role": "representative",
                                "domain": "estimate",
                                "json": "sample_bom_fallback_estimate.json",
                            }
                        ],
                    },
                    {
                        "primary": {
                            "role": "representative",
                            "domain": "pumsem",
                            "json": "sample_pumsem.json",
                        },
                        "diagnostics": [],
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8-sig",
    )
    (output_dir / "sample_bom.json").write_text(
        json.dumps(
            [
                {
                    "tables": [
                        {
                            "domain": "bom",
                            "role": "primary_material_table",
                            "headers": ["DESCRIPTION", "수량"],
                            "rows": [{"DESCRIPTION": "PIPE", "수량": "1"}],
                        }
                    ]
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8-sig",
    )

    summary = analyze_output_dir(output_dir)
    report = write_report(output_dir, summary)

    assert summary["manifest"]["inputs"] == 2
    assert summary["manifest"]["representative"] == 3
    assert summary["manifest"]["diagnostic"] == 1
    assert summary["manifest"]["domains"] == {"bom": 1, "estimate": 1, "pumsem": 1}
    assert "Manifest diagnostic: `1`" in report.read_text(encoding="utf-8-sig")


def test_analyze_output_dir_warns_when_detail_json_values_are_missing_from_excel(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "detail.json").write_text(
        json.dumps(
            [
                {
                    "tables": [
                        {
                            "domain": "estimate",
                            "role": "detail_table",
                            "headers": [
                                "품명_1. TT03",
                                "재료비_금액_1. TT03",
                                "노무비_금액_1. TT03",
                                "합계_금액_1. TT03",
                            ],
                            "rows": [
                                {
                                    "품명_1. TT03": "1) 하지철골 제작 및 설치",
                                    "재료비_금액_1. TT03": "67,725,000",
                                    "노무비_금액_1. TT03": "59,850,000",
                                    "합계_금액_1. TT03": "129,874,500",
                                },
                                {
                                    "품명_1. TT03": "2) LTP 판넬 제작",
                                    "재료비_금액_1. TT03": "130,384,000",
                                    "노무비_금액_1. TT03": "110,152,000",
                                    "합계_금액_1. TT03": "286,932,022",
                                },
                                {
                                    "품명_1. TT03": "3) LTP 판넬 설치",
                                    "재료비_금액_1. TT03": "",
                                    "노무비_금액_1. TT03": "166,950,000",
                                    "합계_금액_1. TT03": "166,950,000",
                                },
                            ],
                        }
                    ]
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8-sig",
    )

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "내역서"
    worksheet.append(["품명", "재료비", "노무비", "합계"])
    worksheet.append(["", "", "", ""])
    worksheet.append(["", "", "", ""])
    workbook.save(output_dir / "detail.xlsx")

    summary = analyze_output_dir(output_dir)

    assert summary["quality_warnings"]["excel_value_loss_suspected"] == 1


def test_analyze_output_dir_recomputes_readability_warnings(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    repeated_note = "동일하게 반복되는 아주 긴 조건 메모 문장입니다. 화면에서 중복으로 보이면 안 됩니다."
    (output_dir / "generic_quote.json").write_text(
        json.dumps(
            [
                {
                    "tables": [
                        {
                            "domain": "generic",
                            "role": "generic_table",
                            "quality": {"status": "ok", "warnings": []},
                            "headers": ["No", "품목", "치수", "수량", "단가", "공급가액"],
                            "rows": [
                                {"No": "1", "품목": "GI", "치수": "A", "수량": "1", "단가": "10", "공급가액": "10"},
                                {"No": "납기", "품목": repeated_note, "치수": "", "수량": repeated_note, "단가": "", "공급가액": ""},
                                {"No": "운송조건", "품목": repeated_note, "치수": "", "수량": "", "단가": "", "공급가액": ""},
                            ],
                        }
                    ]
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8-sig",
    )

    summary = analyze_output_dir(output_dir)

    assert summary["quality_warnings"]["generic_estimate_misroute_suspected"] == 1
    assert summary["quality_warnings"]["repeated_long_cell_value"] == 1
