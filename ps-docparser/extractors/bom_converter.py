"""
extractors/bom_converter.py — BomExtractionResult → Phase 2 호환 JSON 변환

Why: Phase 12 Step 12-3 분해 결과물.
     bom_extractor.py의 to_sections() 변환 로직을 분리한 순수 변환 모듈.
     BomExtractionResult → parse_markdown() 출력 호환 JSON 섹션 리스트.
     ExcelExporter(_build_generic_sheet)를 무수정으로 재사용하기 위한 계층.

원본: extractors/bom_extractor.py L513~591 (to_sections)
"""

from extractors.bom_types import BomExtractionResult


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

    for i, bom in enumerate(result.bom_sections, 1):
        if not bom.rows:
            continue
        rows_as_dicts = []
        for row in bom.rows:
            row_dict = {}
            for j, cell in enumerate(row):
                key = bom.headers[j] if j < len(bom.headers) else f"열{j+1}"
                row_dict[key] = cell
            rows_as_dicts.append(row_dict)

        sections.append({
            "section_id": f"BOM-{i}",
            "title": f"BILL OF MATERIALS #{i}",
            "department": None,
            "chapter": None,
            "page": bom.source_page,
            "clean_text": "",
            "tables": [{
                "table_id": f"T-BOM-{i}-01",
                "type": "BOM_자재",
                "headers": bom.headers,
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
        rows_as_dicts = []
        for row in ll.rows:
            row_dict = {}
            for j, cell in enumerate(row):
                key = ll.headers[j] if j < len(ll.headers) else f"열{j+1}"
                row_dict[key] = cell
            rows_as_dicts.append(row_dict)

        sections.append({
            "section_id": f"LL-{i}",
            "title": f"LINE LIST #{i}",
            "type": "line_list",   # aggregate_boms()의 sec_type 분기 식별용
            "department": None,
            "chapter": None,
            "page": ll.source_page,
            "clean_text": "",
            "tables": [{
                "table_id": f"T-LL-{i}-01",
                "type": "BOM_LINE_LIST",
                "headers": ll.headers,
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
