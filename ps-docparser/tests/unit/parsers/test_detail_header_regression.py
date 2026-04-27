from parsers.header_utils import build_composite_headers, normalize_header_text
from parsers.table_parser import parse_single_table


DETAIL_HTML = """
<table>
  <thead>
    <tr>
      <th>품명</th>
      <th>규격</th>
      <th>단위</th>
      <th>수량</th>
      <th>재료비</th>
      <th></th>
      <th>노무비</th>
      <th></th>
      <th>경비</th>
      <th></th>
      <th>합계</th>
      <th></th>
      <th>비고</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td></td>
      <td></td>
      <td></td>
      <td></td>
      <td>단 가</td>
      <td>금 액</td>
      <td>단 가</td>
      <td>금 액</td>
      <td>단 가</td>
      <td>금 액</td>
      <td>단 가</td>
      <td>금 액</td>
      <td></td>
    </tr>
    <tr>
      <td>1) SUPPORT 제작</td>
      <td>SS275</td>
      <td>KG</td>
      <td>-</td>
      <td></td>
      <td></td>
      <td>1,720</td>
      <td>-</td>
      <td>146</td>
      <td>-</td>
      <td>1,866</td>
      <td>-</td>
      <td></td>
    </tr>
    <tr>
      <td>2) SUPPORT 제작</td>
      <td>SUS304</td>
      <td>KG</td>
      <td>117</td>
      <td></td>
      <td></td>
      <td>5,160</td>
      <td>603,720</td>
      <td>146</td>
      <td>17,082</td>
      <td>5,306</td>
      <td>620,802</td>
      <td></td>
    </tr>
  </tbody>
</table>
"""

DETAIL_HTML_WITH_SECTION_MARKER = """
<table>
  <thead>
    <tr>
      <th>품명</th>
      <th>규격</th>
      <th>단위</th>
      <th>수량</th>
      <th colspan="2">재료비</th>
      <th colspan="2">노무비</th>
      <th colspan="2">경비</th>
      <th colspan="2">합계</th>
      <th>비고</th>
    </tr>
    <tr>
      <th></th>
      <th></th>
      <th></th>
      <th></th>
      <th>단가</th>
      <th>금액</th>
      <th>단가</th>
      <th>금액</th>
      <th>단가</th>
      <th>금액</th>
      <th>단가</th>
      <th>금액</th>
      <th></th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td colspan="13">1. TT03</td>
    </tr>
    <tr>
      <td>1) 하지철골 제작 및 설치</td>
      <td></td>
      <td>TON</td>
      <td>15.75</td>
      <td>4,300,000</td>
      <td>67,725,000</td>
      <td>3,800,000</td>
      <td>59,850,000</td>
      <td>146,000</td>
      <td>2,299,500</td>
      <td>8,246,000</td>
      <td>129,874,500</td>
      <td>아연도금</td>
    </tr>
  </tbody>
</table>
"""


def test_normalize_header_text_compacts_spaced_non_latin_tokens():
    assert normalize_header_text("단 가") == "단가"
    assert normalize_header_text("금 액") == "금액"
    assert normalize_header_text("單 價") == "單價"
    assert normalize_header_text("재료비_금 액") == "재료비_금액"


def test_build_composite_headers_fills_blank_parent_slots_for_cost_breakdown():
    grid = [
        ["품명", "규격", "단위", "수량", "재료비", "", "노무비", "", "경비", "", "합계", "", "비고"],
        ["", "", "", "", "단 가", "금 액", "단 가", "금 액", "단 가", "금 액", "단 가", "금 액", ""],
    ]

    headers = build_composite_headers(grid, 2)

    assert headers == [
        "품명",
        "규격",
        "단위",
        "수량",
        "재료비_단가",
        "재료비_금액",
        "노무비_단가",
        "노무비_금액",
        "경비_단가",
        "경비_금액",
        "합계_단가",
        "합계_금액",
        "비고",
    ]


def test_parse_single_table_preserves_distinct_cost_amount_keys():
    result = parse_single_table(DETAIL_HTML, "S-01", 3)

    assert result is not None
    assert result["headers"] == [
        "품명",
        "규격",
        "단위",
        "수량",
        "재료비_단가",
        "재료비_금액",
        "노무비_단가",
        "노무비_금액",
        "경비_단가",
        "경비_금액",
        "합계_단가",
        "합계_금액",
        "비고",
    ]
    assert len(set(result["headers"])) == len(result["headers"])

    first_row = result["rows"][0]
    second_row = result["rows"][1]

    assert first_row["노무비_단가"] == "1,720"
    assert first_row["노무비_금액"] == "-"
    assert first_row["경비_금액"] == "-"
    assert first_row["합계_금액"] == "-"

    assert second_row["노무비_금액"] == "603,720"
    assert second_row["경비_금액"] == "17,082"
    assert second_row["합계_금액"] == "620,802"


def test_parse_single_table_does_not_merge_repeated_section_marker_into_headers():
    result = parse_single_table(DETAIL_HTML_WITH_SECTION_MARKER, "S-01", 4)

    assert result is not None
    assert result["headers"] == [
        "품명",
        "규격",
        "단위",
        "수량",
        "재료비_단가",
        "재료비_금액",
        "노무비_단가",
        "노무비_금액",
        "경비_단가",
        "경비_금액",
        "합계_단가",
        "합계_금액",
        "비고",
    ]
    assert result["rows"][0]["품명"] == "1. TT03"
    assert result["rows"][0]["재료비_금액"] == ""
    assert result["rows"][1]["품명"] == "1) 하지철골 제작 및 설치"
    assert result["rows"][1]["재료비_금액"] == "67,725,000"
    assert result["rows"][1]["합계_금액"] == "129,874,500"
