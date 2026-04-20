"""
extractors/text_extractor.py — PDF 텍스트 전용 추출기

Why: 테이블이 없거나 --text-only 모드에서 pdfplumber만으로 텍스트를 추출한다.
     AI 엔진도 pdf2image도 Poppler도 전혀 필요하지 않다.
     비용 0원으로 텍스트 문서를 빠르게 처리할 때 사용한다.

이식 원본: step1_extract_gemini_v33.py L294~367, L658~716
"""

import logging

import pdfplumber

from utils.text_formatter import format_text_with_linebreaks
from utils.markers import (
    build_page_marker,
    build_section_markers,
    build_context_marker,
    process_toc_context,
)

logger = logging.getLogger(__name__)


def extract_text_outside_tables(page, table_bboxes: list) -> str:
    """
    테이블 영역을 제외한 텍스트만 추출한다.

    Why: 하이브리드 모드에서 테이블 영역은 AI가 처리하므로
         pdfplumber 텍스트 추출 시 해당 영역을 건너뛰어야 중복이 없다.

    이식 원본: step1_extract_gemini_v33.py L294~318
    """
    try:
        if table_bboxes:
            filtered_page = page
            failed_bboxes = []
            for bbox in table_bboxes:
                try:
                    filtered_page = filtered_page.outside_bbox(bbox)
                except Exception as e:
                    logger.warning(f"outside_bbox 실패 (bbox={bbox}): {e}")
                    failed_bboxes.append(bbox)

            if len(failed_bboxes) == len(table_bboxes):
                logger.warning("모든 테이블 영역 제외 실패, 전체 텍스트 사용")
                text = page.extract_text()
            else:
                text = filtered_page.extract_text()
        else:
            text = page.extract_text()

        return text.strip() if text else ""
    except Exception as e:
        logger.error(f"텍스트 추출 실패: {e}")
        return ""


def extract_text_regions_with_positions(
    page, table_bboxes: list, division_names: str = None
) -> list[dict]:
    """
    페이지 텍스트를 테이블 bbox 기준으로 분할하여 y좌표와 함께 반환한다.

    Why: 텍스트와 테이블을 y좌표 기준으로 정렬하여 원본 순서대로 재조합하려면
         각 텍스트 영역이 어느 y위치에 있는지 알아야 한다.

    Args:
        page: pdfplumber page 객체
        table_bboxes: 테이블 영역 bbox 리스트
        division_names: 품셈 프리셋 부문명 패턴 (text_formatter에 전달)

    Returns:
        [{"y": float, "type": "text", "content": str}, ...]

    이식 원본: step1_extract_gemini_v33.py L321~367
    """
    if not table_bboxes:
        text = page.extract_text()
        if text and text.strip():
            return [
                {
                    "y": 0,
                    "type": "text",
                    "content": format_text_with_linebreaks(
                        text.strip(), division_names=division_names
                    ),
                }
            ]
        return []

    sorted_bboxes = sorted(table_bboxes, key=lambda b: b[1])
    page_width = page.width
    page_height = page.height

    text_regions = []

    # 텍스트 영역 경계 계산: [0, 테이블상단, 테이블하단, 테이블상단, ...., 페이지하단]
    boundaries = [0]
    for bbox in sorted_bboxes:
        boundaries.append(bbox[1])  # 테이블 상단
        boundaries.append(bbox[3])  # 테이블 하단
    boundaries.append(page_height)

    # 짝수 인덱스 쌍 = 테이블 사이 텍스트 영역
    for i in range(0, len(boundaries) - 1, 2):
        top = boundaries[i]
        bottom = boundaries[i + 1] if i + 1 < len(boundaries) else page_height

        if bottom - top < 5:  # 5pt 미만은 빈 영역으로 간주
            continue

        try:
            crop_bbox = (0, top, page_width, bottom)
            cropped = page.within_bbox(crop_bbox)
            text = cropped.extract_text()
            if text and text.strip():
                formatted = format_text_with_linebreaks(
                    text.strip(), division_names=division_names
                )
                if formatted:
                    text_regions.append({"y": top, "type": "text", "content": formatted})
        except Exception as e:
            logger.debug(f"텍스트 영역 추출 실패 (top={top:.0f}, bottom={bottom:.0f}): {e}")

    return text_regions


def process_pdf_text_only(
    pdf_path: str,
    section_map: dict = None,
    page_indices: list[int] = None,
    toc_parser_module=None,
    preset: str = None,
    division_names: str = None,
) -> str:
    """
    PDF를 텍스트 전용 모드로 처리한다 (AI 엔진 미사용).

    Args:
        pdf_path: 입력 PDF 경로
        section_map: toc_parser.parse_toc_file() 결과 (없으면 None)
        page_indices: 처리할 0-indexed 페이지 인덱스 리스트 (없으면 전체)
        toc_parser_module: extractors.toc_parser 모듈 (목차 연동 시 필요)
        preset: 프리셋 이름 (예: "pumsem")
        division_names: 품셈 부문명 OR 패턴 (text_formatter에 전달)

    Returns:
        마크다운 형식의 추출 결과 문자열

    이식 원본: step1_extract_gemini_v33.py L658~716
    """
    print(f"📄 텍스트 전용 모드로 PDF 처리 중: {pdf_path}")

    page_map = {}
    if section_map and toc_parser_module:
        page_map = toc_parser_module.build_page_to_sections_map(section_map)
        print(f"    📚 페이지 기반 목차 매핑: {len(page_map)}개 페이지")

    current_context = {"chapter": "", "section": "", "sections": []}
    markdown_output = ""

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)

        if page_indices is None:
            indices_to_process = list(range(total_pages))
        else:
            indices_to_process = [i for i in page_indices if i < total_pages]

        print(f"📄 총 {total_pages}페이지 중 {len(indices_to_process)}페이지 처리 예정")

        for idx, i in enumerate(indices_to_process):
            page = pdf.pages[i]
            page_num = i + 1
            print(f"\n🔄 페이지 {page_num} ({idx+1}/{len(indices_to_process)}) 처리 중...")

            text = page.extract_text() or ""

            if section_map and toc_parser_module:
                current_context, page_sections, pdf_page_num = process_toc_context(
                    full_text=text,
                    page_map=page_map,
                    current_context=current_context,
                    toc_parser_module=toc_parser_module,
                    preset=preset,
                    division_names=division_names,
                )
                if page_sections:
                    print(f"    📖 목차 매핑: {len(page_sections)}개 섹션 (PDF 페이지 {pdf_page_num})")
            else:
                page_sections = []
                pdf_page_num = 0

            markdown_output += build_page_marker(page_num, current_context)

            if page_sections:
                markdown_output += build_section_markers(page_sections)
            elif section_map and toc_parser_module and pdf_page_num > 0:
                active_section = toc_parser_module.get_active_section(
                    pdf_page_num, section_map
                )
                if active_section:
                    markdown_output += build_context_marker(active_section)
                    print(f"    📖 컨텍스트 유지: {active_section['id']} (PDF 페이지 {pdf_page_num})")

            if text:
                formatted_text = format_text_with_linebreaks(
                    text, division_names=division_names
                )
                markdown_output += formatted_text + "\n\n"
                print(f"    ✅ 텍스트 추출 완료 ({len(text):,} chars)")
            else:
                print(f"    ⚠️ 텍스트 없음")

    return markdown_output


# ── K4: Bold-fake 글리프 중복 제거 (kordoc 알고리즘 참조, MIT License) ──────
# 알고리즘 참조: kordoc (https://github.com/chrisryugj/kordoc)
# Copyright (c) chrisryugj, MIT License
# 적용 시점: Phase 4 BOM 엔진에서 page.extract_words() 호출 직후 연결 예정


def deduplicate_bold_fake(words: list[dict]) -> list[dict]:
    """
    Bold-fake 글리프 중복을 제거한다.

    Why: 일부 PDF는 볼드를 폰트 가중치 대신 동일 텍스트를
         ±3pt 오프셋으로 중복 렌더링하여 구현한다.
         pdfplumber extract_words() 결과에서 이를 제거하지 않으면
         "품명품명" 같은 중복이 발생한다.

    Args:
        words: pdfplumber page.extract_words() 결과
               각 원소: dict {'x0': float, 'top': float, 'text': str, ...}

    Returns:
        중복 제거된 words 리스트

    판정 기준 (kordoc 참조):
        - 동일 텍스트
        - Y좌표 차이 ≤ 1pt (같은 행)
        - X좌표 차이 ≤ 3pt (오프셋 볼드)
        → 세 조건 모두 충족 시 중복 판정, 첫 번째만 유지

    향후 사용 예시 (Phase 4 hybrid_extractor.py):
        words = plumber_page.extract_words()
        words = deduplicate_bold_fake(words)
        text = " ".join(w['text'] for w in words)
    """
    if not words:
        return words

    result = []
    for word in words:
        text = word['text']
        x0 = word['x0']
        y0 = word['top']

        is_dup = False
        for existing in result:
            if (text == existing['text']
                    and abs(y0 - existing['top']) <= 1.0
                    and abs(x0 - existing['x0']) <= 3.0):
                is_dup = True
                break

        if not is_dup:
            result.append(word)

    return result
