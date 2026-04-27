from validators.output_quality import (
    annotate_output_contract,
    infer_table_contract,
    validate_bom_table,
    validate_table_contract,
)


def test_validate_bom_table_ok_for_aligned_quantity_unit():
    headers = ["DESCRIPTION", "수량", "단위", "자재중량 [Kg] | UNIT"]
    rows = [
        {
            "DESCRIPTION": "Scaffolding 설치",
            "수량": "1.0",
            "단위": "식",
            "자재중량 [Kg] | UNIT": "",
        }
    ]

    quality = validate_bom_table(headers, rows)

    assert quality == {"status": "ok", "warnings": []}


def test_validate_bom_table_warns_on_quantity_unit_shift():
    headers = ["DESCRIPTION", "수량", "단위", "자재중량 [Kg] | UNIT"]
    rows = [
        {
            "DESCRIPTION": "Scaffolding 설치",
            "수량": "",
            "단위": "1.0",
            "자재중량 [Kg] | UNIT": "식",
        }
    ]

    quality = validate_bom_table(headers, rows)

    assert quality["status"] == "warning"
    assert "qty_unit_shift_suspected" in quality["warnings"]


def test_validate_bom_table_fails_on_header_key_mismatch():
    headers = ["DESCRIPTION", "QTY"]
    rows = [{"DESCRIPTION": "PIPE", "WRONG": "1"}]

    quality = validate_bom_table(headers, rows)

    assert quality["status"] == "fail"
    assert "header_row_key_mismatch" in quality["warnings"]


def test_validate_bom_table_warns_on_self_repeating_header_and_empty_tail():
    headers = ["DESCRIPTION | DESCRIPTION", "Column_2"]
    rows = [{"DESCRIPTION | DESCRIPTION": "PIPE", "Column_2": ""}]

    quality = validate_bom_table(headers, rows)

    assert quality["status"] == "warning"
    assert "self_repeating_composite_header" in quality["warnings"]
    assert "empty_tail_column" in quality["warnings"]


def test_infer_table_contract_for_estimate_preset():
    table = {
        "headers": ["명칭", "규격", "수량", "단위", "금액"],
        "rows": [],
        "type": "estimate",
    }

    assert infer_table_contract(table, preset="estimate") == ("estimate", "estimate_table")


def test_infer_table_contract_for_pumsem_type():
    table = {
        "headers": ["규격", "단위수량"],
        "rows": [],
        "type": "A_품셈",
    }

    assert infer_table_contract(table, preset=None) == ("pumsem", "pumsem_quantity_table")


def test_infer_table_contract_for_trade_statement_keywords():
    table = {
        "headers": ["거래명세표(공급자보관용)_일련번호", "공급자", "공급받는자"],
        "rows": [],
        "type": "D_기타",
    }

    assert infer_table_contract(table, preset=None) == ("trade_statement", "trade_statement_table")


def test_validate_table_contract_warns_on_estimate_amount_missing():
    quality = validate_table_contract(
        ["품명", "수량", "단위"],
        [{"품명": "배관", "수량": "1", "단위": "EA"}],
        domain="estimate",
        role="estimate_table",
    )

    assert quality["status"] == "warning"
    assert "estimate_amount_column_missing" in quality["warnings"]


def test_infer_table_contract_keeps_material_quantity_table_out_of_estimate_summary():
    table = {
        "headers": [
            "설치구분",
            "제품",
            "철판종류",
            "치수",
            "재질",
            "단위",
            "수량",
            "개별제품중량 (kg)",
            "전체중량 (kg)",
            "전체단면적 (M2)",
            "도장면적 (M2)",
            "비고",
        ],
        "rows": [{"제품": "ROOF PANEL", "수량": "860"}],
        "type": "D_기타",
    }

    assert infer_table_contract(table, preset="estimate") == (
        "generic",
        "material_quantity_table",
    )


def test_infer_table_contract_classifies_bom_like_table_inside_estimate_fallback():
    table = {
        "headers": [
            "DESCRIPTION",
            "DWG NO.",
            "MAT'L",
            "SIZE",
            "수량",
            "단위",
            "자재중량 [Kg]_UNIT",
            "자재면적 [m2]_m2",
        ],
        "rows": [{"DESCRIPTION": "Scaffolding 설치", "수량": "1"}],
        "type": "D_기타",
    }

    assert infer_table_contract(table, preset="estimate") == (
        "bom",
        "primary_material_table",
    )


def test_annotate_output_contract_adds_domain_role_and_quality():
    sections = [
        {
            "section_id": "estimate",
            "tables": [
                {
                    "headers": ["명칭", "규격", "수량", "단위", "금액"],
                    "rows": [{"명칭": "배관", "규격": "", "수량": "1", "단위": "EA", "금액": "1000"}],
                }
            ],
        }
    ]

    annotated = annotate_output_contract(sections, preset="estimate")
    table = annotated[0]["tables"][0]

    assert annotated[0]["domain"] == "estimate"
    assert annotated[0]["quality"] == {"status": "ok", "warnings": []}
    assert table["domain"] == "estimate"
    assert table["role"] == "estimate_table"
    assert table["quality"] == {"status": "ok", "warnings": []}


def test_annotate_output_contract_prunes_empty_generated_tail_column():
    sections = [
        {
            "section_id": "bom",
            "tables": [
                {
                    "type": "BOM_자재",
                    "headers": ["DESCRIPTION", "수량", "Column_3"],
                    "rows": [
                        {"DESCRIPTION": "Scaffolding", "수량": "1", "Column_3": ""},
                        {"DESCRIPTION": "Rail", "수량": "2", "Column_3": ""},
                    ],
                }
            ],
        }
    ]

    annotated = annotate_output_contract(sections, preset="bom")
    table = annotated[0]["tables"][0]

    assert table["headers"] == ["DESCRIPTION", "수량"]
    assert list(table["rows"][0].keys()) == ["DESCRIPTION", "수량"]
    assert table["quality"] == {"status": "ok", "warnings": []}


def test_annotate_estimate_splits_embedded_condition_rows_and_prunes_tail():
    headers = [
        "No",
        "품목",
        "재질",
        "치수",
        "수량",
        "중량",
        "단가",
        "단위",
        "공급가액",
        "메모",
        "col_10",
        "col_11",
    ]
    repeated_note = '*도금많:227 기준 *두께별 최소 수량:20분~25분 기준 *전략 인도 조건 *두께별4"×8"기준 가공'
    sections = [
        {
            "section_id": "estimate",
            "tables": [
                {
                    "table_id": "T-doc-02",
                    "headers": headers,
                    "rows": [
                        {
                            "No": "1",
                            "품목": "GI SHEET",
                            "재질": "",
                            "치수": "0.8x1219x2438",
                            "수량": "1,200",
                            "중량": "23,520",
                            "단가": "1,285",
                            "단위": "KG",
                            "공급가액": "30,223,200",
                            "메모": "",
                            "col_10": "",
                            "col_11": "",
                        },
                        {
                            "No": "",
                            "품목": "-이하 여백-",
                            "재질": "",
                            "치수": "",
                            "수량": "",
                            "중량": "",
                            "단가": "",
                            "단위": "",
                            "공급가액": "",
                            "메모": "",
                            "col_10": "",
                            "col_11": "",
                        },
                        {
                            "No": "남기",
                            "품목": "발주후2~3주",
                            "재질": repeated_note,
                            "치수": "",
                            "수량": repeated_note,
                            "중량": "",
                            "단가": "",
                            "단위": "",
                            "공급가액": "",
                            "메모": "",
                            "col_10": "",
                            "col_11": "",
                        },
                        {
                            "No": "운습조건",
                            "품목": "도착도",
                            "재질": repeated_note,
                            "치수": "",
                            "수량": repeated_note,
                            "중량": "",
                            "단가": "",
                            "단위": "",
                            "공급가액": "",
                            "메모": "",
                            "col_10": "",
                            "col_11": "",
                        },
                    ],
                }
            ],
        }
    ]

    annotated = annotate_output_contract(sections, preset="estimate")

    item_table, condition_table = annotated[0]["tables"]
    assert item_table["headers"] == [
        "No",
        "품목",
        "재질",
        "치수",
        "수량",
        "중량",
        "단가",
        "단위",
        "공급가액",
        "메모",
    ]
    assert len(item_table["rows"]) == 1
    assert item_table["role"] == "estimate_table"
    assert condition_table["headers"] == ["조건", "값", "비고"]
    assert condition_table["role"] == "condition_table"
    assert condition_table["rows"][0]["조건"] == "납기"
    assert condition_table["rows"][0]["값"] == "발주후2~3주"
    assert condition_table["rows"][1]["조건"] == "운송조건"
    assert condition_table["rows"][1]["비고"] == ""


def test_annotate_estimate_normalizes_source_info_table():
    sections = [
        {
            "section_id": "estimate",
            "tables": [
                {
                    "table_id": "T-doc-01",
                    "headers": [
                        "상호_등록번호",
                        "고려철강(주)_610-86-22576",
                        "고려철강(주)_성명",
                        "고려철강(주)_김태현",
                    ],
                    "rows": [
                        {
                            "상호_등록번호": "주소",
                            "고려철강(주)_610-86-22576": "울산시 울주군 청량면 고려철강(주)",
                            "고려철강(주)_성명": "울산시 울주군 청량면 고려철강(주)",
                            "고려철강(주)_김태현": "울산시 울주군 청량면 고려철강(주)",
                        },
                        {
                            "상호_등록번호": "전화번호",
                            "고려철강(주)_610-86-22576": "052-268-6096",
                            "고려철강(주)_성명": "FAX",
                            "고려철강(주)_김태현": "052-269-6096",
                        },
                    ],
                }
            ],
        }
    ]

    annotated = annotate_output_contract(sections, preset="estimate")
    table = annotated[0]["tables"][0]

    assert table["role"] == "source_info_table"
    assert table["headers"] == ["항목", "값", "보조항목", "보조값"]
    assert table["rows"][0] == {"항목": "상호", "값": "고려철강(주)", "보조항목": "", "보조값": ""}
    assert table["rows"][1] == {"항목": "등록번호", "값": "610-86-22576", "보조항목": "", "보조값": ""}
    assert table["rows"][2] == {"항목": "성명", "값": "김태현", "보조항목": "", "보조값": ""}


def test_validate_table_contract_warns_on_generic_estimate_and_repeated_long_text():
    repeated_note = "동일하게 반복되는 아주 긴 조건 메모 문장입니다. 화면에서 중복으로 보이면 안 됩니다."
    quality = validate_table_contract(
        ["No", "품목", "치수", "수량", "단가", "공급가액"],
        [
            {"No": "1", "품목": "GI", "치수": "A", "수량": "1", "단가": "10", "공급가액": "10"},
            {"No": "납기", "품목": repeated_note, "치수": "", "수량": repeated_note, "단가": "", "공급가액": ""},
            {"No": "운송조건", "품목": repeated_note, "치수": "", "수량": "", "단가": "", "공급가액": ""},
        ],
        domain="generic",
        role="generic_table",
    )

    assert quality["status"] == "warning"
    assert "generic_estimate_misroute_suspected" in quality["warnings"]
    assert "repeated_long_cell_value" in quality["warnings"]
