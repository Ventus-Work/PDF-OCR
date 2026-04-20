"""
utils/markers.py — PAGE/SECTION/CONTEXT 마크다운 주석 마커 생성 모듈

Why: 목차(TOC) 연동 시 각 페이지/섹션의 위치를 HTML 주석으로 삽입한다.
     이 주석은 후처리(step2, step3)에서 구조 정보를 파악하는 기준점으로 사용된다.
     품셈 프리셋에서만 의미 있는 푸터 파싱 로직은 preset 파라미터로 조건부 활성화한다.

이식 원본: step1_extract_gemini_v33.py L609~655
"""

import re


def build_section_markers(page_sections: list) -> str:
    """
    섹션 시작 마커 문자열을 생성한다.

    Args:
        page_sections: toc_parser.get_current_context()가 반환한 섹션 목록

    Returns:
        '<!-- SECTION: ... -->' 형식의 문자열 (섹션이 없으면 빈 문자열)

    이식 원본: step1_extract_gemini_v33.py L609~617
    """
    if not page_sections:
        return ""
    markers = ""
    for sec in page_sections:
        markers += (
            f"<!-- SECTION: {sec['id']} | {sec['title']} "
            f"| 부문:{sec['chapter']} | 장:{sec['section']} -->\n"
        )
    markers += "\n"
    return markers


def build_page_marker(page_num: int, current_context: dict) -> str:
    """
    페이지 시작 마커 문자열을 생성한다.

    Args:
        page_num: 1-indexed 페이지 번호
        current_context: 현재 챕터/섹션 컨텍스트 딕셔너리

    Returns:
        '<!-- PAGE N | 컨텍스트 -->' 형식의 문자열

    이식 원본: step1_extract_gemini_v33.py L620~626
    """
    context_str = ""
    if current_context.get("chapter") or current_context.get("section"):
        parts = [
            p
            for p in [
                current_context.get("chapter", ""),
                current_context.get("section", ""),
            ]
            if p
        ]
        context_str = f" | {' > '.join(parts)}" if parts else ""
    return f"<!-- PAGE {page_num}{context_str} -->\n\n"


def build_context_marker(active_section: dict) -> str:
    """
    섹션이 계속되는 페이지에 삽입하는 CONTEXT 마커를 생성한다.

    Why: 목차의 섹션이 여러 페이지에 걸쳐 있을 때, 각 페이지에 현재 섹션 정보를
         기록해두어 step2 파서가 섹션 경계를 정확히 인식할 수 있게 한다.

    이식 원본: step1_extract_gemini_v33.py L629~633
    """
    if not active_section:
        return ""
    return (
        f"<!-- CONTEXT: {active_section['id']} | {active_section['title']} "
        f"| 부문:{active_section['chapter']} | 장:{active_section['section']} -->\n\n"
    )


def process_toc_context(
    full_text: str,
    page_map: dict,
    current_context: dict,
    toc_parser_module,
    preset: str = None,
    division_names: str = None,
) -> tuple[dict, list, int]:
    """
    페이지 텍스트와 목차 매핑을 바탕으로 현재 컨텍스트를 업데이트한다.

    Args:
        full_text: 현재 페이지 전체 텍스트 (푸터 파싱용)
        page_map: toc_parser.build_page_to_sections_map()이 반환한 딕셔너리
        current_context: 이전 페이지에서 유지된 컨텍스트
        toc_parser_module: extractors.toc_parser 모듈 (의존성 주입)
        preset: 프리셋 이름 (예: "pumsem"). None이면 범용 모드
        division_names: 품셈 부문명 OR 패턴 (푸터 파싱에 사용)

    Returns:
        (updated_context, page_sections, pdf_page_num)

    이식 원본: step1_extract_gemini_v33.py L636~655
    변경점:
        - extract_page_footer_metadata()를 내부 호출하되, preset="pumsem"일 때만 활성화
        - toc_parser를 모듈 파라미터로 주입하여 순환 참조 방지
    """
    pdf_page_num = 0

    # ── 품셈 프리셋: 푸터에서 페이지 번호/부문명/장 정보 추출 ──
    # Why: 범용 모드에서는 이 로직을 실행하면 엉뚱한 숫자를 페이지 번호로
    #      오인할 수 있다. "pumsem" 프리셋일 때만 활성화.
    if preset == "pumsem" and division_names:
        footer_meta = _extract_page_footer_metadata(full_text, division_names)
        pdf_page_num = footer_meta.get("page_num", 0)
        if footer_meta.get("chapter"):
            current_context["chapter"] = footer_meta["chapter"]
        if footer_meta.get("section"):
            current_context["section"] = footer_meta["section"]

    page_sections = []
    if pdf_page_num > 0 and page_map:
        current_context = toc_parser_module.get_current_context(
            pdf_page_num, page_map, current_context
        )
        page_sections = current_context.get("sections", [])

    return current_context, page_sections, pdf_page_num


def _extract_page_footer_metadata(text: str, division_names: str) -> dict:
    """
    품셈 전용: 페이지 하단 푸터에서 부문명과 장 정보를 추출한다.

    Why: 건설 품셈 PDF는 각 페이지 하단에 "000 토목부문 | 제3장 ..." 형식의
         푸터가 있어 목차 없이도 현재 위치를 파악할 수 있다.
         범용 PDF에는 이 패턴이 없으므로 범용 모드에서는 호출하지 않는다.

    이식 원본: step1_extract_gemini_v33.py L206~229
    변경점:
        - DIVISION_NAMES 전역 상수 → division_names 파라미터로 변경
        - process_toc_context()에서만 호출 (private 함수화)
    """
    result = {"chapter": "", "section": "", "page_num": 0}

    if not text or not division_names:
        return result

    # "제N장 제목 | 000" 형식 파싱
    match = re.search(
        r"(제\d+장\s*[가-힣]+(?:\s+[가-힣]+)*)\s+\|?\s*(\d+)(?:\s|$)", text
    )
    if match:
        result["section"] = match.group(1).strip()
        result["page_num"] = int(match.group(2))

    # "000 토목부문" 형식 파싱
    pattern = rf"(\d+)\s+({division_names})"
    match = re.search(pattern, text)
    if match:
        page = int(match.group(1))
        chapter = match.group(2)
        if result["page_num"] == 0:
            result["page_num"] = page
        result["chapter"] = chapter

    return result
