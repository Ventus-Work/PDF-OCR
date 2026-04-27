"""
exporters/bom_aggregator.py — 다수의 BOM JSON 데이터를 단일 명세로 집계한다.

Why:
    도면(PDF)이 61개일 때, 개별 도면에 있는 파이프 서포트 부품들의
    규격(SIZE)과 재질(MATERIAL)이 동일한 경우 전체 수량과 중량을 합산하여
    최종 하나의 집계 내역서(BOM)를 생성해야 한다.

주요 기능:
    - _HEADER_ALIASES: 도면마다 다른 헤더명(MAT'L, WT(kg) 등) 정규화
    - Group By 연산: SIZE, MATERIAL 기준 그룹핑
    - 수량(Q'TY) 및 중량(WT) 합산
    - 결측치/파싱 불가 값을 0.0으로 안전 처리
    - export_aggregated_excel(): 배치 종료 후 집계 xlsx 자동 생성 공개 API

Phase 5 단위 4 변경사항:
    - aggregate_boms() 반환 테이블에 headers/rows 포맷 병용 추가 (ExcelExporter 호환)
    - export_aggregated_excel(): JSON 파일 목록 → 집계 → xlsx까지 원스텝 공개 함수
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)

# ── 헤더 정규화 매핑 테이블 ──
# 실제 도면 OCR마다 다르게 잡힐 수 있는 컬럼명을 정규화된 대표명으로 매핑한다.
# 예: data["WT(KG)"] 와 data["WT(kg)"] 모두 "WEIGHT"로 취급하여 값을 찾는다.
_HEADER_ALIASES: dict[str, list[str]] = {
    "SIZE": ["SIZE"],
    "MATERIAL": ["MATERIAL", "MAT'L", "MATL", "재질"],
    "QUANTITY": ["Q'TY", "QTY", "Q'ty", "Qty", "수량"],
    "WEIGHT": ["WT(KG)", "WT(kg)", "WT", "WEIGHT", "중량"],
    "DESCRIPTION": ["DESCRIPTION", "DESC", "품명"],
    "ITEM_NO": ["ITEM NO.", "ITEM", "NO", "ITEM NO"],
}

# 역방향 조회 딕셔너리: alias(대문자) -> canonical
# Why: _table_to_dicts에서 OCR 원본 헤더 -> 정규화 헤더 변환이 필요한데,
#      _HEADER_ALIASES는 canonical->aliases 구조이므로 역방향 딕셔너리를 미리 생성한다.
_ALIAS_TO_CANONICAL: dict[str, str] = {
    alias.upper(): canonical
    for canonical, aliases in _HEADER_ALIASES.items()
    for alias in aliases
}


def _get_row_value(row: dict[str, Any], canonical_key: str, default: Any = "") -> Any:
    """
    row 딕셔너리에서 정규화된 헤더(canonical_key)에 해당하는 값을 추출한다.

    Why:
        _table_to_dicts()를 거친 row는 이미 키가 canonical_key로 정규화되어 있으므로
        우선적으로 canonical_key를 직접 조회한다.
        혹시 정규화되지 않은 원본 row가 들어올 경우를 대비해 alias 목록도 확인한다.
    """
    if canonical_key in row:
        return row[canonical_key]

    aliases = _HEADER_ALIASES.get(canonical_key, [canonical_key])
    for alias in aliases:
        if alias in row:
            return row[alias]
    return default


def _parse_float(value: Any) -> float:
    """
    숫자 형태의 문자열을 안전하게 float로 변환한다.
    문자 혼합("2.5 kg"), 쉼표("1,000") 등은 정제 후 변환 시도하며,
    실패 시 0.0을 반환하여 집계 중단(Crash)을 방지한다.
    """
    if isinstance(value, (int, float)):
        return float(value)
    
    if not isinstance(value, str):
        return 0.0

    val_str = value.replace(",", "").strip()
    if not val_str:
        return 0.0

    try:
        return float(val_str)
    except ValueError:
        # "2.5 EA" 와 같은 경우 숫자 부분만 추출 시도 (간이 정제)
        parts = []
        for char in val_str:
            if char.isdigit() or char in ".-":
                parts.append(char)
            else:
                break
        
        if parts:
            try:
                return float("".join(parts))
            except ValueError:
                pass
        
        return 0.0


def aggregate_boms(json_files: list[Path]) -> list[dict[str, Any]]:
    """
    여러 JSON 파일의 BOM 섹션 데이터를 수집하여,
    (SIZE, MATERIAL)을 기준으로 수량과 중량을 집계한다.

    Args:
        json_files: 파싱된 결과물 JSON 파일 경로 리스트

    Returns:
        통합된(Aggregated) 섹션 리스트.
        기존 Line List 등은 제거되고 단 1개의 결합된 "BOM" 테이블만 포함된다.
    """
    # 구조: (size, material) -> { merged_row }
    grouped_data: defaultdict[tuple[str, str], dict[str, Any]] = defaultdict(dict)
    
    # [단위 6] LINE LIST 보존용 데이터 수집
    line_list_data: list[dict[str, Any]] = []

    total_parsed_rows = 0

    for jpath in json_files:
        try:
            with open(jpath, "r", encoding="utf-8-sig") as f:
                sections = json.load(f)
        except Exception as e:
            logger.error("JSON 파싱 실패 (%s): %s", jpath.name, e)
            continue

        for sec in sections:
            sec_type = sec.get("type")
            
            # LINE LIST 처리: 모든 행 데이터를 수집 (출처 포함)
            if sec_type == "line_list":
                for table in sec.get("tables", []):
                    rows = _table_to_dicts(table)
                    for r in rows:
                        r["■ SOURCE DOC"] = jpath.name.replace("_bom.json", "")
                        line_list_data.append(r)
                continue

            # BOM 처리
            if sec_type not in ("estimate", "bom", None):
                continue

            for table in sec.get("tables", []):
                rows = _table_to_dicts(table)

                for row in rows:
                    size = str(_get_row_value(row, "SIZE", "")).strip()
                    material = str(_get_row_value(row, "MATERIAL", "")).strip()

                    if not size and not material:
                        continue

                    quantity = _parse_float(_get_row_value(row, "QUANTITY", 0))
                    weight = _parse_float(_get_row_value(row, "WEIGHT", 0))

                    if quantity == 0 and weight == 0:
                        continue

                    group_key = (size, material)
                    total_parsed_rows += 1

                    if group_key not in grouped_data:
                        grouped_data[group_key] = {
                            "ITEM_NO": "",
                            "DESCRIPTION": str(_get_row_value(row, "DESCRIPTION", "")).strip(),
                            "SIZE": size,
                            "MATERIAL": material,
                            "Q'TY": quantity,
                            "WT(KG)": weight,
                        }
                    else:
                        grouped_data[group_key]["Q'TY"] += quantity
                        grouped_data[group_key]["WT(KG)"] += weight

    logger.info("BOM 집계 완료: 원본 %d행 -> 그룹화 %d행", total_parsed_rows, len(grouped_data))

    # 1개의 테이블로 압축하여 반환
    aggregated_rows = []
    headers = ["ITEM_NO", "DESCRIPTION", "SIZE", "MATERIAL", "Q'TY", "WT(KG)"]
    
    sorted_items = sorted(
        grouped_data.values(),
        key=lambda x: (x.get("SIZE", ""), x.get("MATERIAL", ""))
    )

    for item in sorted_items:
        row_list = [item.get(h, "") for h in headers]
        aggregated_rows.append(row_list)

    for idx, row_list in enumerate(aggregated_rows, start=1):
        row_list[0] = idx

    rows_as_dicts = [
        {h: row_list[i] for i, h in enumerate(headers)}
        for row_list in aggregated_rows
    ]

    aggregated_section = {
        "title": "Aggregated BOM",
        "type": "estimate",
        "text": "BATCH AGGREGATION RESULT",
        "clean_text": "",
        "tables": [
            {
                "html": "",
                "markdown": "",
                "headers": headers,
                "rows": rows_as_dicts,
                "array": [headers] + [r for r in aggregated_rows],
                "row_count": len(aggregated_rows) + 1,
                "col_count": len(headers),
                "title": "BOM 집계",
            }
        ],
        "key_value": {}
    }

    results = [aggregated_section]

    source_rows = [{"JSON": str(jpath.name)} for jpath in json_files]
    if source_rows:
        source_headers = ["JSON"]
        results.append({
            "title": "집계 대상 파일",
            "type": "generic",
            "text": "BOM AGGREGATION SOURCES",
            "clean_text": "",
            "tables": [
                {
                    "html": "",
                    "markdown": "",
                    "headers": source_headers,
                    "rows": source_rows,
                    "array": [source_headers] + [[row["JSON"]] for row in source_rows],
                    "row_count": len(source_rows) + 1,
                    "col_count": len(source_headers),
                    "title": "집계 대상 파일",
                }
            ],
            "key_value": {},
        })

    # [단위 6] 수집된 LINE LIST가 있다면, 별도 섹션(generic)으로 추가
    if line_list_data:
        # 모든 헤더 추출 (순서 보존, SOURCE DOC을 맨 첫열로 배치)
        ll_headers = ["■ SOURCE DOC"]
        for r in line_list_data:
            for k in r.keys():
                if k not in ll_headers:
                    ll_headers.append(k)

        ll_rows_as_dicts = []
        for r in line_list_data:
            normalized_row = {h: r.get(h, "") for h in ll_headers}
            ll_rows_as_dicts.append(normalized_row)

        ll_array = [ll_headers] + [[r.get(h, "") for h in ll_headers] for r in line_list_data]

        ll_section = {
            "title": "LINE LIST",
            "type": "generic",
            "text": "AGGREGATED LINE LIST",
            "clean_text": "",
            "tables": [
                {
                    "html": "",
                    "markdown": "",
                    "headers": ll_headers,
                    "rows": ll_rows_as_dicts,
                    "array": ll_array,
                    "row_count": len(line_list_data) + 1,
                    "col_count": len(ll_headers),
                    "title": "LINE LIST",
                }
            ],
            "key_value": {}
        }
        results.append(ll_section)

    return results


def export_aggregated_excel(
    json_files: list[Path],
    output_path: Path,
    *,
    title: str | None = None,
) -> Path:
    """
    배치 완료 후 단일 집계 xlsx를 생성하는 공개 API.

    Why:
        main.py의 배치 루프 종료 시점에 이 함수 하나만 호출하면
        aggregate_boms() → ExcelExporter.export() 의 전체 흐름이 처리된다.
        main.py를 오염시키지 않는 단일 책임 원칙을 따른다.

    Args:
        json_files:   배치에서 생성된 JSON 파일 경로 리스트
        output_path:  저장할 .xlsx 경로 (부모 디렉토리가 없으면 자동 생성)
        title:        문서 제목 (기본값: "BOM 집계 - YYYYMMDD")

    Returns:
        저장된 파일 경로 (Path)
    """
    from exporters.excel_exporter import ExcelExporter  # 지연 임포트 (순환 방지)

    if not json_files:
        raise ValueError("집계할 JSON 파일이 없습니다.")

    aggregated_sections = aggregate_boms(json_files)

    doc_title = title or f"BOM 집계 - {datetime.now().strftime('%Y%m%d')}"

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ExcelExporter().export(
        aggregated_sections,
        output_path,
        metadata={"description": doc_title},
    )

    row_count = len(
        aggregated_sections[0]["tables"][0]["rows"]
        if aggregated_sections else []
    )
    logger.info(
        "집계 xlsx 생성 완료: %s (%d개 항목)", output_path.name, row_count
    )
    return output_path


def _table_to_dicts(table: dict[str, Any]) -> list[dict[str, Any]]:
    """
    테이블 데이터를 정규화된 헤더 키의 딕셔너리 리스트로 변환한다.

    Why:
        JSON은 두 가지 포맷으로 저장된다:
        1. array 포맷: [["header1", ...], ["val1", ...], ...]
        2. headers/rows 포맷: {"headers": [...], "rows": [{"header1": "val1", ...}]}
        두 포맷을 모두 처리하고, _HEADER_ALIASES로 헤더를 정규화하여
        집계 시 동일 컬럼이 서로 다른 이름으로 저장된 경우를 통합한다.
    """
    raw_rows: list[dict[str, Any]] = []

    arr = table.get("array", [])
    if arr and len(arr) >= 2:
        # array 포맷: 첫 행이 헤더
        raw_headers = [str(h).strip() for h in arr[0]]
        for row in arr[1:]:
            row_dict: dict[str, Any] = {}
            for col_idx, cell_value in enumerate(row):
                if col_idx < len(raw_headers):
                    row_dict[raw_headers[col_idx]] = cell_value
            raw_rows.append(row_dict)
    else:
        # headers/rows 포맷 (array 없거나 데이터 행 없을 때 폴백)
        hdrs = table.get("headers", [])
        rows = table.get("rows", [])
        if hdrs and rows:
            raw_rows = list(rows)
        elif rows:
            # headers 없이 rows만 있는 경우 그대로 사용
            raw_rows = list(rows)

    if not raw_rows:
        return []

    # 역방향 ALIAS → CANONICAL 정규화: MAT'L -> MATERIAL, WT(kg) -> WEIGHT 등
    result = []
    for raw_row in raw_rows:
        if not isinstance(raw_row, dict):
            continue
        normalized: dict[str, Any] = {}
        for raw_key, value in raw_row.items():
            # Why: ZAI OCR는 MAT'L, Q'TY 등의 헤더에 U+2019(RIGHT SINGLE QUOTATION MARK)를
            #      사용하지만 _ALIAS_TO_CANONICAL은 U+0027(ASCII apostrophe)로 정의되어 있다.
            #      upper() 전에 스마트 따옴표를 ASCII 따옴표로 정규화하여 매칭 누락을 방지한다.
            key_upper = (
                str(raw_key).strip()
                .replace('\u2019', "'")  # RIGHT SINGLE QUOTATION MARK → ASCII apostrophe
                .replace('\u2018', "'")  # LEFT SINGLE QUOTATION MARK → ASCII apostrophe
                .upper()
            )
            # _ALIAS_TO_CANONICAL은 str을 반환하므로 TypeError 없음
            canonical = _ALIAS_TO_CANONICAL.get(key_upper, str(raw_key).strip())
            normalized[canonical] = value
        result.append(normalized)

    return result
