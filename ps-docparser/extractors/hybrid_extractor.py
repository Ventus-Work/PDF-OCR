"""
extractors/hybrid_extractor.py — 하이브리드 PDF 추출기 (핵심 파이프라인)

Why: 이 모듈이 ps-docparser의 가장 핵심적인 파이프라인이다.
     pdfplumber(무료)로 텍스트/테이블 위치를 파악하고,
     AI 엔진(선택적)으로 테이블 이미지를 HTML로 변환하여
     y좌표 순으로 재조합하는 하이브리드 방식을 구현한다.

흐름:
    1. pdfplumber로 테이블 bbox 감지
    2. 테이블 없음 → 텍스트만 추출 (AI 호출 없음, pdf2image 불필요)
    3. 테이블 있음 →
       a. engine.supports_image=True  → pdf2image 크롭 → AI 엔진 전달
       b. engine.supports_image=False → pdfplumber 테이블 → extract_table_from_data()
    4. 텍스트 + 테이블 y좌표 기준 정렬 후 마크다운 조합

이식 원본: step1_extract_gemini_v33.py L719~844
변경점:
    - engine 파라미터 추가 (원본은 Gemini 하드코딩이었음)
    - engine.supports_image 분기로 Poppler 의존성 조건부화
    - toc_parser 직접 import → toc_parser_module 파라미터 주입
    - preset, division_names 파라미터 추가 (범용/품셈 분기)
"""

import logging

import pdfplumber

from engines.base_engine import BaseEngine
from extractors.table_utils import (
    detect_tables,
    validate_and_fix_table_bboxes,
    crop_table_image,
)
from extractors.text_extractor import extract_text_regions_with_positions
from extractors.pdf_image_loader import PdfImageLoader   # Phase 8: LRU 캐시 로더
from parsers.text_cleaner import merge_spaced_korean  # K1: 한글 균등배분 병합
from utils.text_formatter import format_text_with_linebreaks
from utils.markers import (
    build_page_marker,
    build_section_markers,
    build_context_marker,
    process_toc_context,
)
from config import POPPLER_PATH

logger = logging.getLogger(__name__)



def process_pdf(
    pdf_path: str,
    engine: BaseEngine,
    section_map: dict = None,
    page_indices: list[int] = None,
    toc_parser_module=None,
    preset: str = None,
    division_names: str = None,
) -> str:
    """
    PDF를 하이브리드 방식으로 처리한다.

    Args:
        pdf_path: 입력 PDF 파일 경로
        engine: AI 추출 엔진 인스턴스 (GeminiEngine 또는 LocalEngine 등)
        section_map: toc_parser.parse_toc_file() 결과 딕셔너리 (없으면 None)
        page_indices: 처리할 0-indexed 페이지 인덱스 리스트 (없으면 전체)
        toc_parser_module: extractors.toc_parser 모듈 (목차 사용 시 필요)
        preset: 프리셋 이름 (예: "pumsem"). None이면 범용 모드
        division_names: 품셈 부문명 OR 패턴 (text_formatter에 전달)

    Returns:
        마크다운 + HTML 혼합 형식의 추출 결과 문자열

    이식 원본: step1_extract_gemini_v33.py L719~844
    Phase 8: pdf2image 직접 호출 → PdfImageLoader(LRU 캐시) 교체.
             동일 페이지 재접근 시 변환 0회 (캐시 히트).
    """
    print(f"📄 하이브리드 모드 PDF 처리 중: {pdf_path}")
    print(f"   엔진: {engine.__class__.__name__} (이미지 지원: {engine.supports_image})")

    markdown_output = ""

    page_map = {}
    if section_map and toc_parser_module:
        page_map = toc_parser_module.build_page_to_sections_map(section_map)
        print(f"    📚 페이지 기반 목차 매핑: {len(page_map)}개 페이지")

    current_context = {"chapter": "", "section": "", "sections": []}

    # Phase 8: PdfImageLoader — 이미지 지원 엔진일 때만 생성
    # Why: LocalEngine 등 이미지 미지원 시에는 pdf2image/Poppler 불필요.
    loader = (
        PdfImageLoader(pdf_path, poppler_path=POPPLER_PATH)
        if engine.supports_image
        else None
    )

    try:
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)

            if page_indices is None:
                indices_to_process = list(range(total_pages))
            else:
                indices_to_process = [i for i in page_indices if i < total_pages]

            print(f"📄 총 {total_pages}페이지 중 {len(indices_to_process)}페이지 처리 예정")

            for idx, i in enumerate(indices_to_process):
                plumber_page = pdf.pages[i]
                page_num = i + 1
                print(f"\n🔄 페이지 {page_num} ({idx+1}/{len(indices_to_process)}) 처리 중...")

                full_text = plumber_page.extract_text() or ""

                # ── TOC 컨텍스트 업데이트 ──
                if section_map and toc_parser_module:
                    current_context, page_sections, pdf_page_num = process_toc_context(
                        full_text=full_text,
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

                # ── 1. 테이블 감지 ──
                table_bboxes = detect_tables(plumber_page)
                print(f"    📊 테이블 {len(table_bboxes)}개 감지")

                # ── 2. 테이블 없음 → 텍스트만 (모든 엔진 공통, pdf2image 불필요) ──
                if len(table_bboxes) == 0:
                    text = plumber_page.extract_text()
                    if text:
                        text = merge_spaced_korean(text)
                        formatted = format_text_with_linebreaks(
                            text, division_names=division_names
                        )
                        markdown_output += formatted + "\n\n"
                    continue

                # ── 3. 테이블 있음 → 엔진 능력에 따라 분기 ──
                if loader:
                    # ── 3a. 이미지 지원 엔진 — PdfImageLoader에서 캐시 히트/미스 처리 ──
                    try:
                        page_image = loader.get_page(page_num)
                    except Exception as e:
                        logger.error(f"페이지 {page_num} 이미지 변환 실패: {e}")
                        print(f"    ⚠️ 이미지 변환 실패 → 텍스트만 추출")
                        text = plumber_page.extract_text()
                        if text:
                            text = merge_spaced_korean(text)
                            formatted = format_text_with_linebreaks(
                                text, division_names=division_names
                            )
                            markdown_output += formatted + "\n\n"
                        continue

                    # bbox 검증 및 보정
                    fixed_bboxes, needs_fallback = validate_and_fix_table_bboxes(
                        table_bboxes, plumber_page.height, plumber_page.width
                    )

                    if needs_fallback:
                        print(f"    🔄 비정상 테이블 감지 → 전체 페이지 AI 처리로 전환")
                        page_content, _, _ = engine.extract_full_page(page_image, page_num)
                        if page_content:
                            markdown_output += page_content + "\n\n"
                        continue

                    if fixed_bboxes != table_bboxes:
                        print(f"    🔧 테이블 bbox 보정됨: {len(table_bboxes)}개 → {len(fixed_bboxes)}개")

                    elements = extract_text_regions_with_positions(
                        plumber_page, fixed_bboxes, division_names=division_names
                    )

                    for j, bbox in enumerate(fixed_bboxes):
                        table_num = j + 1
                        print(f"    🖼️ 테이블 {table_num} 크롭 및 AI 전송...")
                        table_img = crop_table_image(
                            page_image,
                            bbox,
                            plumber_page.height,
                            plumber_page.width,
                            extended=True,
                        )
                        table_html, _, _ = engine.extract_table(table_img, table_num)
                        if table_html:
                            elements.append({"y": bbox[1], "type": "table", "content": table_html})

                else:
                    # ── 3b. 이미지 미지원 엔진 (LocalEngine 등) ──
                    print(f"    ℹ️ 이미지 미지원 엔진 → pdfplumber 테이블 직접 파싱")
                    pdfplumber_tables = plumber_page.extract_tables()
                    elements = extract_text_regions_with_positions(
                        plumber_page, table_bboxes, division_names=division_names
                    )
                    for t_idx, table_data in enumerate(pdfplumber_tables):
                        html = engine.extract_table_from_data(table_data, t_idx + 1)
                        if html and t_idx < len(table_bboxes):
                            elements.append({
                                "y": table_bboxes[t_idx][1],
                                "type": "table",
                                "content": html,
                            })

                # ── 4. y좌표 기준 정렬 후 마크다운 조합 ──
                elements.sort(key=lambda x: x["y"])
                for elem in elements:
                    markdown_output += elem["content"] + "\n\n"

    finally:
        # Phase 8: try/finally로 loader.close() 확실히 호출
        # Why: 예외 발생 시에도 PIL Image 캐시를 즉시 해제하여 메모리 반환.
        if loader:
            loader.close()

    return markdown_output

