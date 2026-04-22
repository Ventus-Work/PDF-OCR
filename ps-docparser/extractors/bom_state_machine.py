"""
extractors/bom_state_machine.py — BOM/LINE LIST 상태머신 추출 엔진

Why: Phase 12 Step 12-3 분해 결과물.
     bom_extractor.py의 핵심 추출 로직(extract_bom, extract_bom_tables)을
     분리한 상태머신 전담 모듈.

     ⚠️  클로저 분해 금지 원칙 (§7.4):
         extract_bom() 내부의 5개 nested 함수
         (_flush_section, _is_bom_header, _is_ll_header,
          _is_rev_header, _parse_cells)는 nonlocal 상태를 공유하므로
         분해하지 않는다. 모듈 레벨 함수로 치환하면 상태머신 의미가 변한다.

원본: extractors/bom_extractor.py L75~324 (extract_bom + extract_bom_tables)
"""

import logging
import re

from extractors.bom_sanitizer import _sanitize_html
from extractors.bom_types import BomExtractionResult, BomSection

logger = logging.getLogger(__name__)


def extract_bom(text: str, keywords: dict) -> BomExtractionResult:
    """
    OCR 텍스트에서 BOM/LINE LIST 데이터를 상태머신으로 추출한다.

    Args:
        text: OCR 엔진이 반환한 원시 텍스트 (Markdown/HTML 혼재 가능)
        keywords: presets/bom.py의 get_bom_keywords() 반환값

    Returns:
        BomExtractionResult: BOM/LINE LIST 섹션 리스트

    상태머신:
        IDLE     + 앵커 키워드 감지 → BOM_SCAN 또는 LL_SCAN
        *_SCAN   + 헤더 행 감지     → *_DATA
        *_DATA   + 킬 키워드        → IDLE (섹션 종료)
        *_DATA   + 빈 행 2연속      → IDLE (섹션 종료)

    원본: bom_extractor.py L75~264
    """
    from parsers.bom_table_parser import parse_bom_rows, filter_noise_rows  # noqa: F401

    # 키워드 로딩
    anchor_bom  = keywords.get("anchor_bom", [])
    anchor_ll   = keywords.get("anchor_ll", [])
    header_a    = keywords.get("bom_header_a", [])
    header_b    = keywords.get("bom_header_b", [])
    header_c    = keywords.get("bom_header_c", [])
    ll_header_a = keywords.get("ll_header_a", [])
    ll_header_b = keywords.get("ll_header_b", [])
    ll_header_c = keywords.get("ll_header_c", [])
    kill_kw     = keywords.get("kill", [])
    noise_kw    = keywords.get("noise_row", [])
    rev_markers = keywords.get("rev_markers", [])

    # HTML 전처리
    clean_text = _sanitize_html(text)
    lines = clean_text.split('\n')

    # 상태 변수
    state = "IDLE"           # IDLE | BOM_SCAN | BOM_DATA | LL_SCAN | LL_DATA
    blank_count = 0
    header_found = False
    current_rows: list[list[str]] = []
    current_headers: list[str] = []

    # 결과 수집
    bom_sections: list[BomSection] = []
    ll_sections:  list[BomSection] = []

    # ── ⚠️ 클로저 분해 금지: 아래 5개 nested 함수는 nonlocal 상태를 공유한다 ──

    def _flush_section():
        """현재 섹션을 결과에 저장하고 상태를 초기화한다."""
        nonlocal state, blank_count, header_found, current_rows, current_headers

        if current_rows:
            filtered = filter_noise_rows(current_rows, noise_kw)
            section = BomSection(
                section_type="bom" if state.startswith("BOM") else "line_list",
                headers=current_headers,
                rows=filtered,
                raw_row_count=len(current_rows),
            )
            if state.startswith("BOM"):
                bom_sections.append(section)
            else:
                ll_sections.append(section)

        state = "IDLE"
        blank_count = 0
        header_found = False
        current_rows = []
        current_headers = []

    def _is_bom_header(cells_upper: list[str]) -> bool:
        """BOM 헤더 행 판정: A ∧ B ∧ C 그룹 키워드 동시 존재."""
        joined = ' '.join(cells_upper)
        has_a = any(kw in joined for kw in header_a)
        has_b = any(kw in joined for kw in header_b)
        has_c = any(kw in joined for kw in header_c)
        return has_a and has_b and has_c

    def _is_ll_header(cells_upper: list[str]) -> bool:
        """LINE LIST 헤더 행 판정."""
        joined = ' '.join(cells_upper)
        has_a  = any(kw in joined for kw in ll_header_a)
        has_bc = any(kw in joined for kw in ll_header_b + ll_header_c)
        return has_a or has_bc

    def _is_rev_header(cells_upper: list[str]) -> bool:
        """REV 헤더 행 판정 (3개 이상 REV 마커)."""
        joined = ' '.join(cells_upper)
        return sum(1 for m in rev_markers if m in joined) >= 3

    def _parse_cells(line: str) -> list[str]:
        """행에서 셀을 추출한다 (파이프 구분 우선, 공백 2+ 폴백)."""
        stripped = line.strip()
        if '|' in stripped and stripped.count('|') >= 2:
            cells = [c.strip() for c in stripped.split('|')]
            cells = [c for c in cells if c]  # 빈 경계 제거
        else:
            cells = [stripped] if stripped else []
        return cells

    # ── 상태머신 루프 ──
    for line in lines:
        line_stripped = line.strip()
        line_upper    = line_stripped.upper()

        # ── 앵커 감지 (IDLE 상태에서만) ──
        if state == "IDLE":
            if any(kw in line_upper for kw in anchor_bom):
                state = "BOM_SCAN"
                blank_count = 0
                header_found = False
                continue
            if any(kw in line_upper for kw in anchor_ll):
                state = "LL_SCAN"
                blank_count = 0
                header_found = False
                continue

            # 앵커 없이 헤더 키워드만으로도 BOM 감지 (앵커 텍스트 없는 도면 대응)
            cells = _parse_cells(line)
            if cells:
                cells_upper = [c.upper() for c in cells]
                if _is_bom_header(cells_upper):
                    state = "BOM_DATA"
                    header_found = True
                    current_headers = cells
                    blank_count = 0
                    continue

        # ── 킬 키워드 감지 (활성 상태에서) ──
        if state != "IDLE":
            if any(kw in line_upper for kw in kill_kw):
                _flush_section()
                continue

        # ── 빈 행 처리 ──
        cells = _parse_cells(line)

        if not cells or all(c.strip() == '' for c in cells):
            if header_found:
                blank_count += 1
                if blank_count >= 2:
                    _flush_section()
            continue
        else:
            blank_count = 0

        # ── SCAN 상태: 헤더 탐색 ──
        if state in ("BOM_SCAN", "LL_SCAN"):
            cells_upper = [c.upper() for c in cells]

            if state == "BOM_SCAN" and _is_bom_header(cells_upper):
                state = "BOM_DATA"
                header_found = True
                current_headers = cells
                continue
            elif state == "LL_SCAN" and _is_ll_header(cells_upper):
                state = "LL_DATA"
                header_found = True
                current_headers = cells
                continue

        # ── DATA 상태: 데이터 수집 ──
        if state in ("BOM_DATA", "LL_DATA"):
            cells_upper = [c.upper() for c in cells]

            # REV 헤더 감지 → 섹션 종료
            if _is_rev_header(cells_upper):
                _flush_section()
                continue

            # 반복 헤더 건너뛰기 (멀티페이지 BOM에서 헤더 반복)
            if header_found and _is_bom_header(cells_upper):
                continue

            # 구분선 건너뛰기 (---+--- 패턴)
            if all(re.match(r'^[-:= ]+$', c) for c in cells if c):
                continue

            current_rows.append(cells)

    # 루프 종료 후 잔여 섹션 플러시
    if state != "IDLE":
        _flush_section()

    return BomExtractionResult(
        bom_sections=bom_sections,
        line_list_sections=ll_sections,
        raw_text=text,
    )


def extract_bom_tables(
    text: str,
    keywords: dict,
    layout_details: list[dict] | None = None,
) -> BomExtractionResult:
    """
    3단계 폴백으로 BOM 테이블을 추출한다.

    원본 참조: ocr.py L1252~1398 (3단계 폴백 전략)

    단계 1: HTML <table> 기반 추출
        → OCR 엔진이 구조화된 <table>을 반환한 경우
    단계 2: layout_details 기반 추출
        → Z.ai 엔진의 테이블 영역 데이터 활용
    단계 3: 상태머신 기반 추출 (extract_bom)
        → Markdown 파이프 + 공백 구분 텍스트

    원본: bom_extractor.py L267~324
    """
    from parsers.bom_table_parser import parse_html_bom_tables

    # 단계 1: HTML <table> 기반 추출
    html_result = parse_html_bom_tables(text, keywords)

    # 단계 2: layout_details 기반 추출 (HTML에서 못 찾은 경우 보완)
    if not html_result.has_bom and layout_details:
        for item in layout_details:
            if not isinstance(item, dict):
                continue
            if item.get("label") == "table":
                content = item.get("content", "")
                ld_result = parse_html_bom_tables(content, keywords)
                if ld_result.has_bom:
                    html_result.bom_sections = ld_result.bom_sections
                    break

    # 단계 3: 상태머신 기반 추출 (Markdown 파이프 + 공백 정규식)
    # ZAI가 BOM은 HTML로, Line List는 Markdown 평문으로 출력한 경우 등 하이브리드 상황 대응
    sm_result = extract_bom(text, keywords)

    final_result = BomExtractionResult(
        bom_sections=html_result.bom_sections,
        line_list_sections=html_result.line_list_sections,
        raw_text=text,
    )

    # HTML 방식에서 BOM을 못 찾았는데 SM에서 찾았다면 대체
    if not final_result.has_bom and sm_result.has_bom:
        final_result.bom_sections = sm_result.bom_sections

    # HTML 방식에서 LINE LIST를 못 찾았는데 SM에서 찾았다면 대체
    if not final_result.has_line_list and sm_result.has_line_list:
        final_result.line_list_sections = sm_result.line_list_sections

    if final_result.has_bom:
        logger.info("BOM 추출 성공 (%d행)", final_result.total_bom_rows)
    else:
        logger.warning("BOM 추출: 3단계 모두 실패")

    return final_result
