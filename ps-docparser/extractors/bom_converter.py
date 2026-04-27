"""
extractors/bom_converter.py — BomExtractionResult → Phase 2 호환 JSON 변환

Why: Phase 12 Step 12-3 분해 결과물.
     bom_extractor.py의 to_sections() 변환 로직을 분리한 순수 변환 모듈.
     BomExtractionResult → parse_markdown() 출력 호환 JSON 섹션 리스트.
     ExcelExporter(_build_generic_sheet)를 무수정으로 재사용하기 위한 계층.

원본: extractors/bom_extractor.py L513~591 (to_sections)
"""

from extractors.bom_types import BomExtractionResult
from validators.output_quality import prune_empty_tail_columns, validate_bom_table


def _dedupe_headers(headers: list[str]) -> list[str]:
    deduped_headers = []
    seen = {}
    for idx, h in enumerate(headers):
        base = h or f"Column_{idx + 1}"
        if base in seen:
            seen[base] += 1
            deduped_headers.append(f"{base}_{seen[base]}")
        else:
            seen[base] = 1
            deduped_headers.append(base)
    return deduped_headers


def _headers_for_rows(headers: list[str], rows: list[list[str]]) -> list[str]:
    max_row_len = max((len(row) for row in rows), default=0)
    expanded = list(headers)
    for idx in range(len(expanded), max_row_len):
        expanded.append(f"Column_{idx + 1}")
    return expanded


def _rows_to_dicts(headers: list[str], rows: list[list[str]]) -> list[dict]:
    rows_as_dicts = []
    for row in rows:
        row_dict = {}
        for j, key in enumerate(headers):
            row_dict[key] = row[j] if j < len(row) else ""
        rows_as_dicts.append(row_dict)
    return rows_as_dicts


def _normalize_table(headers: list[str], rows: list[list[str]]) -> tuple[list[str], list[dict]]:
    rows_as_dicts = _rows_to_dicts(headers, rows)
    table = {"headers": headers, "rows": rows_as_dicts}
    prune_empty_tail_columns(table)
    return list(table["headers"]), list(table["rows"])


def to_sections(result: BomExtractionResult) -> list[dict]:
    """
    BomExtractionResult를 Phase 2 출력 호환 JSON 섹션 리스트로 변환한다.

    Why: 기존 ExcelExporter(_build_generic_sheet)를 무수정으로 재사용하기 위해
         Phase 2 parse_markdown() 출력과 동일한 구조를 생성한다.

    Args:
        result: BomExtractionResult (extract_bom_tables / extract_bom_with_retry 반환값)

    Returns:
        list[dict]: Phase 2 섹션 JSON 포맷
                    [{"section_id": "BOM-1", "tables": [...], ...}, ...]

    원본: bom_extractor.py L513~591
    """
    sections = []

    # Phase 14: 도면 메타데이터 섹션 추가
    has_meta = any(v is not None for v in result.drawing_metadata.values())
    if has_meta:
        sections.append({
            "section_id": "DRAWING-META-1",
            "title": "도면 메타데이터",
            "type": "drawing_meta",
            "department": None,
            "chapter": None,
            "page": None,
            "clean_text": "",
            "tables": [],
            "notes": [],
            "conditions": [],
            "cross_references": [],
            "revision_year": None,
            "unit_basis": None,
            "drawing_metadata": result.drawing_metadata,
        })

    for i, bom in enumerate(result.bom_sections, 1):
        if not bom.rows:
            continue

        deduped_headers = _dedupe_headers(_headers_for_rows(bom.headers, bom.rows))
        deduped_headers, rows_as_dicts = _normalize_table(deduped_headers, bom.rows)
        quality = validate_bom_table(deduped_headers, rows_as_dicts)

        sections.append({
            "section_id": f"BOM-{i}",
            "title": f"BILL OF MATERIALS #{i}",
            "type": "bom",
            "domain": "bom",
            "role": "primary_material_table",
            "quality": quality,
            "department": None,
            "chapter": None,
            "page": bom.source_page,
            "clean_text": "",
            "tables": [{
                "table_id": f"T-BOM-{i}-01",
                "type": "BOM_자재",
                "domain": "bom",
                "role": "primary_material_table",
                "quality": quality,
                "headers": deduped_headers,
                "rows": rows_as_dicts,
                "notes_in_table": [],
                "raw_row_count": bom.raw_row_count,
                "parsed_row_count": bom.parsed_row_count,
            }],
            "notes": [],
            "conditions": [],
            "cross_references": [],
            "revision_year": None,
            "unit_basis": None,
        })

    for i, ll in enumerate(result.line_list_sections, 1):
        if not ll.rows:
            continue

        deduped_headers = _dedupe_headers(_headers_for_rows(ll.headers, ll.rows))
        deduped_headers, rows_as_dicts = _normalize_table(deduped_headers, ll.rows)
        quality = validate_bom_table(deduped_headers, rows_as_dicts)

        sections.append({
            "section_id": f"LL-{i}",
            "title": f"LINE LIST #{i}",
            "type": "line_list",   # aggregate_boms()의 sec_type 분기 식별용
            "domain": "bom",
            "role": "line_list_table",
            "quality": quality,
            "department": None,
            "chapter": None,
            "page": ll.source_page,
            "clean_text": "",
            "tables": [{
                "table_id": f"T-LL-{i}-01",
                "type": "BOM_LINE_LIST",
                "domain": "bom",
                "role": "line_list_table",
                "quality": quality,
                "headers": deduped_headers,
                "rows": rows_as_dicts,
                "notes_in_table": [],
                "raw_row_count": ll.raw_row_count,
                "parsed_row_count": ll.parsed_row_count,
            }],
            "notes": [],
            "conditions": [],
            "cross_references": [],
            "revision_year": None,
            "unit_basis": None,
        })

    return sections
