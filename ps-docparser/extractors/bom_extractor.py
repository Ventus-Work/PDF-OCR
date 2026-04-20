"""
extractors/bom_extractor.py — BOM/LINE LIST 추출 상태머신

Why: OCR 텍스트에서 BOM/LINE LIST 데이터를 추출하는 핵심 모듈.
     ocr.py의 도메인 지식(앵커-경계선 패턴, 키워드 그룹)을
     ps-docparser 아키텍처에 맞게 신규 구현한다.

     ocr.py 결함 대응:
     - 문제 C(God Object): 추출 로직만 분리, 단일 책임
     - 문제 D(3중 중복 파싱): bom_table_parser.py 1곳에 통합 위임
     - 문제 E(3중 중복 분기): preset 키워드로 자동 라우팅
     - 문제 F(4중 중복 키워드): presets/bom.py 1곳에서 관리

Dependencies: extractors.bom_types, parsers.bom_table_parser, presets.bom, utils.ocr_utils
"""
import logging
import re
from pathlib import Path

from PIL import Image

# 데이터 클래스를 bom_types.py에서 import (순환 import 방지)
from extractors.bom_types import BomSection, BomExtractionResult
# PDF→이미지 변환을 ocr_utils에서 import (중복 제거)
from utils.ocr_utils import pdf_page_to_image

logger = logging.getLogger(__name__)

# ── Phase 8: 정규식 모듈 레벨 1회 컴파일 캐싱 ──────────────────────────────
# Why: _sanitize_html()은 100페이지 배치에서 수백 회 호출된다.
#      re.sub(r'...') 형태는 매 호출마다 정규식을 재컴파일한다.
#      모듈 로드 시 1회 컴파일 → 이후 N회 호출은 캐시 히트 → CPU 절약.
_RE_TR_CLOSE     = re.compile(r'</tr[^>]*>',          re.IGNORECASE)
_RE_TD_SPLIT     = re.compile(r'</t[dh]>\s*<t[dh][^>]*>', re.IGNORECASE)
_RE_TAG          = re.compile(r'<[^>]+>')
_RE_ENTITY_NAMED = re.compile(r'&[a-zA-Z]+;')
_RE_ENTITY_HEX   = re.compile(r'&#x[0-9a-fA-F]+;')
_RE_WHITESPACE   = re.compile(r'[ \t]+')


def _sanitize_html(text: str) -> str:
    """
    OCR 응답의 HTML 잔여물을 상태머신 입력용 텍스트로 정리한다.

    Why: Z.ai/Mistral OCR 응답에 <table>, <tr>, <td> 태그가
         남아 있을 수 있다. 상태머신은 파이프(|) 구분 텍스트를
         기대하므로 HTML 구조를 파이프로 변환한다.

    원본 참조: ocr.py L1416~1436 (HTML 전처리 5단계)
    Phase 8: 모듈 레벨 _RE_* 상수 사용으로 재컴파일 제거.
    """
    if not text:
        return text

    # Step 1: </tr> → 줄바꿈 (행 구분)
    text = _RE_TR_CLOSE.sub('\n', text)

    # Step 2: </td><td> 또는 </th><th> → 파이프 (열 구분)
    text = _RE_TD_SPLIT.sub(' | ', text)

    # Step 3: 나머지 HTML 태그 제거
    text = _RE_TAG.sub(' ', text)

    # Step 4: HTML 엔티티 치환 (명시적 치환 우선, 나머지는 정규식)
    text = text.replace('&amp;', '&').replace('&#x27;', "'")
    text = _RE_ENTITY_NAMED.sub('', text)
    text = _RE_ENTITY_HEX.sub('', text)

    # Step 5: 연속 공백 압축
    text = _RE_WHITESPACE.sub(' ', text)

    return text


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
    """
    from parsers.bom_table_parser import parse_bom_rows, filter_noise_rows

    # 키워드 로딩
    anchor_bom = keywords.get("anchor_bom", [])
    anchor_ll = keywords.get("anchor_ll", [])
    header_a = keywords.get("bom_header_a", [])
    header_b = keywords.get("bom_header_b", [])
    header_c = keywords.get("bom_header_c", [])
    ll_header_a = keywords.get("ll_header_a", [])
    ll_header_b = keywords.get("ll_header_b", [])
    ll_header_c = keywords.get("ll_header_c", [])
    kill_kw = keywords.get("kill", [])
    noise_kw = keywords.get("noise_row", [])
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
    ll_sections: list[BomSection] = []

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
        has_a = any(kw in joined for kw in ll_header_a)
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
        line_upper = line_stripped.upper()

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


def _get_table_bbox_scaled(
    layout_details: list,
    img_w: int,
    img_h: int,
) -> tuple[int, int, int, int] | None:
    """
    layout_details에서 첫 번째 table 요소의 bbox를 추출하고,
    실제 이미지 크기(img_w × img_h)로 스케일하여 반환한다.

    Why: ZAI OCR의 bbox_2d는 ZAI 내부 좌표계 기준이므로
         pdf_page_to_image()가 생성한 이미지 크기로 변환이 필요하다.
         고정 비율(하단 50%) 대신 실제 감지된 테이블 영역을 사용하면
         도면 레이아웃에 무관하게 정확한 크롭이 가능하다.

    Args:
        layout_details: ZAI OCR 응답의 단일 페이지 요소 목록
                        [{"label": "table", "bbox_2d": [x1,y1,x2,y2],
                          "width": ocr_w, "height": ocr_h}, ...]
        img_w: pdf_page_to_image() 결과 이미지 너비 (픽셀)
        img_h: pdf_page_to_image() 결과 이미지 높이 (픽셀)

    Returns:
        (x1, y1, x2, y2) 정수 튜플, 또는 None (table 미감지 시)
    """
    if not layout_details:
        return None

    # layout_details 구조 정규화:
    # ZAI 응답은 [[{elem}, ...]] (페이지 리스트 × 요소 리스트) 이중 구조.
    # 단일 페이지 요소 리스트 [{elem}, ...] 로 들어올 때도 대응.
    flat: list[dict] = []
    for item in layout_details:
        if isinstance(item, list):
            flat.extend(item)
        elif isinstance(item, dict):
            flat.append(item)

    ocr_w = ocr_h = None
    for elem in flat:
        if ocr_w is None:
            ocr_w = elem.get("width")
            ocr_h = elem.get("height")
        if elem.get("label") == "table":
            bbox = elem.get("bbox_2d")
            if bbox and ocr_w and ocr_h:
                sx = img_w / ocr_w
                sy = img_h / ocr_h
                return (
                    int(bbox[0] * sx),
                    int(bbox[1] * sy),
                    int(bbox[2] * sx),
                    int(bbox[3] * sy),
                )
    return None


def extract_bom_with_retry(
    engine,
    file_path: Path,
    keywords: dict,
    image_settings: dict,
    page_indices: list[int] | None = None,
) -> BomExtractionResult:
    """
    3단계 OCR 재시도로 BOM/LINE LIST를 추출한다.

    원본 참조: ocr.py L2034~2056 (2차 OCR 폴백)

    1차: 전체 페이지 OCR → extract_bom_tables()
    2차: 우측 55% 크롭 OCR → extract_bom() (BOM 복구)
    3차: layout bbox 기반 정밀 크롭 → extract_bom_tables() (LINE LIST 복구)
         - layout_details에 table bbox가 있으면 해당 영역만 크롭 (동적)
         - bbox 없으면 하단 ll_crop_top% 크롭으로 fallback (기존 방식)

    Args:
        engine: OCR 엔진 (supports_ocr=True 필수)
        file_path: PDF/이미지 파일 경로
        keywords: presets/bom.py 키워드
        image_settings: presets/bom.py 이미지 설정
        page_indices: 처리할 페이지 인덱스 (None=전체)

    Returns:
        BomExtractionResult (3차까지 누적)
    """
    default_dpi = image_settings.get("default_dpi", 400)
    retry_dpi = image_settings.get("retry_dpi", 600)
    bom_crop_left = image_settings.get("bom_crop_left_ratio", 0.45)
    ll_crop_top = image_settings.get("ll_crop_top_ratio", 0.50)
    # bbox 내 LINE LIST 예상 구간 (BOM 아래, 개정이력 위)
    # Why: 타이틀 블록의 표준 레이아웃(BOM 상단 35%, LINE LIST 중단, 개정 하단 28%)
    #      기준으로 bbox 내에서 LINE LIST 위치만 잘라낸다.
    #      page 고정 비율이 아니라 감지된 bbox 내 상대 비율이므로 다른 도면에도 적용 가능.
    ll_within_bbox_top    = image_settings.get("ll_within_bbox_top_ratio",    0.25)
    ll_within_bbox_bottom = image_settings.get("ll_within_bbox_bottom_ratio", 0.72)

    # ── 1차: 전체 페이지 OCR ──
    print("   🔍 1차 OCR: 전체 페이지 처리 중...")
    ocr_results = engine.ocr_document(file_path, page_indices)
    full_text = "\n\n".join(r.text for r in ocr_results)
    layout = ocr_results[0].layout_details if ocr_results else []

    result = extract_bom_tables(full_text, keywords, layout_details=layout)
    result.raw_text = full_text
    result.ocr_engine = type(engine).__name__

    # ── 2차: 우측 55% 크롭 (BOM 복구) ──
    if not result.has_bom:
        print("   🔍 2차 OCR: 우측 55% 크롭 (BOM 영역)...")
        try:
            for ocr_r in ocr_results:
                page_img = pdf_page_to_image(file_path, ocr_r.page_num, default_dpi)
                w, h = page_img.size
                cropped = page_img.crop((int(w * bom_crop_left), 0, w, h))
                crop_result = engine.ocr_image(cropped)
                bom2 = extract_bom(crop_result.text, keywords)
                result.bom_sections.extend(bom2.bom_sections)
        except Exception as e:
            logger.warning("2차 OCR 크롭 실패: %s", e)

    # ── 3차: layout bbox 전체 크롭 (LINE LIST 복구 1단계) ──
    # Why: 1차 full-page OCR은 출력이 BOM에서 truncate되어 LINE LIST에 도달하지 못한다.
    #      layout_details의 table bbox(타이틀 블록 전체)만 크롭해서 재OCR하면
    #      전체 도면보다 이미지가 작아져 ZAI 출력 여유가 생긴다.
    #      bbox 미감지 시 기존 하단 비율 크롭으로 fallback.
    if not result.has_line_list:
        print("   🔍 3차 OCR: layout bbox 전체 크롭 (LINE LIST 복구 1단계)...")
        try:
            for ocr_r in ocr_results:
                page_img = pdf_page_to_image(file_path, ocr_r.page_num, retry_dpi)
                img_w, img_h = page_img.size

                page_layout = ocr_r.layout_details or []
                bbox = _get_table_bbox_scaled(page_layout, img_w, img_h)

                if bbox:
                    x1, y1, x2, y2 = bbox
                    cropped = page_img.crop((x1, y1, x2, y2))
                    logger.debug("3차 bbox 크롭: (%d, %d, %d, %d)", x1, y1, x2, y2)
                    print(f"      bbox 크롭: x={x1}~{x2}, y={y1}~{y2}")
                else:
                    cropped = page_img.crop((0, int(img_h * ll_crop_top), img_w, img_h))
                    logger.debug("3차 fallback: 하단 %.0f%% 크롭", ll_crop_top * 100)
                    print(f"      fallback: 하단 {int(ll_crop_top*100)}% 크롭")

                crop_result = engine.ocr_image(cropped)
                ll3 = extract_bom_tables(crop_result.text, keywords)
                result.line_list_sections.extend(ll3.line_list_sections)
        except Exception as e:
            logger.warning("3차 OCR 크롭 실패: %s", e)

    # ── 4차: bbox 내 중간 구간 크롭 (LINE LIST 복구 2단계) ──
    # Why: 3차에서도 ZAI 출력이 BOM 빈 행으로 채워져 LINE LIST까지 도달 못하는 경우,
    #      타이틀 블록(bbox) 내에서 BOM 아래·개정이력 위 구간(35%~72%)만 잘라낸다.
    #      이미지가 더 작아지고 LINE LIST가 맨 위에 오므로 ZAI가 우선 인식한다.
    #      비율은 page 절대값이 아닌 bbox 상대값이므로 다른 레이아웃에도 적용 가능.
    if not result.has_line_list:
        print("   🔍 4차 OCR: bbox 중간 구간 크롭 (LINE LIST 복구 2단계)...")
        try:
            for ocr_r in ocr_results:
                page_img = pdf_page_to_image(file_path, ocr_r.page_num, retry_dpi)
                img_w, img_h = page_img.size

                page_layout = ocr_r.layout_details or []
                bbox = _get_table_bbox_scaled(page_layout, img_w, img_h)

                if bbox:
                    x1, y1, x2, y2 = bbox
                    bh = y2 - y1
                    ll_y1 = y1 + int(bh * ll_within_bbox_top)
                    ll_y2 = y1 + int(bh * ll_within_bbox_bottom)
                    cropped = page_img.crop((x1, ll_y1, x2, ll_y2))
                    logger.debug("4차 bbox 중간 크롭: (%d, %d, %d, %d)", x1, ll_y1, x2, ll_y2)
                    print(f"      bbox 중간 크롭: y={ll_y1}~{ll_y2} ({int(ll_within_bbox_top*100)}%~{int(ll_within_bbox_bottom*100)}%)")

                    crop_result = engine.ocr_image(cropped)
                    ll4 = extract_bom_tables(crop_result.text, keywords)
                    result.line_list_sections.extend(ll4.line_list_sections)
                else:
                    logger.debug("4차 스킵: layout에 table bbox 없음")
        except Exception as e:
            logger.warning("4차 OCR 크롭 실패: %s", e)

    print(f"   ✅ BOM: {result.total_bom_rows}행 / LINE LIST: {result.total_ll_rows}행")
    return result


def to_sections(result: BomExtractionResult) -> list[dict]:
    """
    BomExtractionResult를 Phase 2 출력 호환 JSON 섹션 리스트로 변환한다.

    Why: 기존 ExcelExporter(_build_generic_sheet)를 무수정으로 재사용하기 위해
         Phase 2 parse_markdown() 출력과 동일한 구조를 생성한다.
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
