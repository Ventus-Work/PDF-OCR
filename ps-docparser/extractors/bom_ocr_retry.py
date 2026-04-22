"""
extractors/bom_ocr_retry.py — OCR 크롭 좌표 계산 및 4차 재시도 추출

Why: Phase 12 Step 12-3 분해 결과물.
     bom_extractor.py의 OCR 재시도 로직(_get_table_bbox_scaled,
     extract_bom_with_retry)을 분리한 OCR 재시도 전담 모듈.
     PDF 이미지 처리와 bbox 스케일링에 집중하며, 상태머신은
     bom_state_machine을 호출한다.

원본: extractors/bom_extractor.py L327~510
"""

import logging
from pathlib import Path

from extractors.bom_types import BomExtractionResult
from utils.ocr_utils import pdf_page_to_image

logger = logging.getLogger(__name__)


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

    원본: bom_extractor.py L327~380
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
    4차 OCR 재시도로 BOM/LINE LIST를 추출한다.

    원본 참조: ocr.py L2034~2056 (2차 OCR 폴백)

    1차: 전체 페이지 OCR → extract_bom_tables()
    2차: 우측 55% 크롭 OCR → extract_bom() (BOM 복구)
    3차: layout bbox 기반 정밀 크롭 → extract_bom_tables() (LINE LIST 복구)
         - layout_details에 table bbox가 있으면 해당 영역만 크롭 (동적)
         - bbox 없으면 하단 ll_crop_top% 크롭으로 fallback (기존 방식)
    4차: bbox 내 중간 구간 크롭 → extract_bom_tables() (LINE LIST 복구 2단계)

    Args:
        engine: OCR 엔진 (supports_ocr=True 필수)
        file_path: PDF/이미지 파일 경로
        keywords: presets/bom.py 키워드
        image_settings: presets/bom.py 이미지 설정
        page_indices: 처리할 페이지 인덱스 (None=전체)

    Returns:
        BomExtractionResult (4차까지 누적)

    원본: bom_extractor.py L383~510
    """
    # 지연 import — 순환 import 방지 (bom_state_machine ↔ bom_ocr_retry)
    from extractors.bom_state_machine import extract_bom, extract_bom_tables

    default_dpi           = image_settings.get("default_dpi", 400)
    retry_dpi             = image_settings.get("retry_dpi", 600)
    bom_crop_left         = image_settings.get("bom_crop_left_ratio", 0.45)
    ll_crop_top           = image_settings.get("ll_crop_top_ratio", 0.50)
    ll_within_bbox_top    = image_settings.get("ll_within_bbox_top_ratio",    0.25)
    ll_within_bbox_bottom = image_settings.get("ll_within_bbox_bottom_ratio", 0.72)

    # ── 1차: 전체 페이지 OCR ──
    print("   🔍 1차 OCR: 전체 페이지 처리 중...")
    ocr_results = engine.ocr_document(file_path, page_indices)
    full_text   = "\n\n".join(r.text for r in ocr_results)
    layout      = ocr_results[0].layout_details if ocr_results else []

    result = extract_bom_tables(full_text, keywords, layout_details=layout)
    result.raw_text   = full_text
    result.ocr_engine = type(engine).__name__

    # ── 2차: 우측 55% 크롭 (BOM 복구) ──
    if not result.has_bom:
        print("   🔍 2차 OCR: 우측 55% 크롭 (BOM 영역)...")
        try:
            for ocr_r in ocr_results:
                page_img = pdf_page_to_image(file_path, ocr_r.page_num, default_dpi)
                w, h = page_img.size
                cropped    = page_img.crop((int(w * bom_crop_left), 0, w, h))
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
                    bh    = y2 - y1
                    ll_y1 = y1 + int(bh * ll_within_bbox_top)
                    ll_y2 = y1 + int(bh * ll_within_bbox_bottom)
                    cropped = page_img.crop((x1, ll_y1, x2, ll_y2))
                    logger.debug("4차 bbox 중간 크롭: (%d, %d, %d, %d)", x1, ll_y1, x2, ll_y2)
                    print(
                        f"      bbox 중간 크롭: y={ll_y1}~{ll_y2} "
                        f"({int(ll_within_bbox_top*100)}%~{int(ll_within_bbox_bottom*100)}%)"
                    )

                    crop_result = engine.ocr_image(cropped)
                    ll4 = extract_bom_tables(crop_result.text, keywords)
                    result.line_list_sections.extend(ll4.line_list_sections)
                else:
                    logger.debug("4차 스킵: layout에 table bbox 없음")
        except Exception as e:
            logger.warning("4차 OCR 크롭 실패: %s", e)

    print(f"   ✅ BOM: {result.total_bom_rows}행 / LINE LIST: {result.total_ll_rows}행")
    return result
