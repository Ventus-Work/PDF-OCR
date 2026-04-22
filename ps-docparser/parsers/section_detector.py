"""
parsers/section_detector.py — 마커 파싱 및 텍스트 재배분 유틸리티

Why: Phase 12 Step 12-5 분해 결과물.
     section_splitter.py의 마커 파싱 로직과 정규식 상수를 분리한 모듈.
     ps-docparser 내부 마커 포맷(SECTION/PAGE/CONTEXT)을 역파싱하는
     저수준 탐지 함수를 담당한다.
     외부 의존성: re만 사용.

원본: parsers/section_splitter.py L34~263
     (정규식 상수 4개 + 파싱/재배분 4개 함수)
"""

import re


# ══════════════════════════════════════════════════════════
# ps-docparser 마커 포맷 정규식 (범용 — 프리셋 무관)
#
# Why: 이 패턴들은 utils/markers.py가 생성하는 마커를 역파싱한다.
#      ps-docparser 내부 포맷이므로 변경될 일이 없다.
#      presets/에 넣지 않는 이유: 마커 포맷은 도메인과 무관한 인프라 포맷.
# ══════════════════════════════════════════════════════════

_SECTION_MARKER = re.compile(
    r'<!-- SECTION: (\S+) \| (.+?) \| 부문:(.+?) \| 장:(.+?) -->'
)
_PAGE_MARKER = re.compile(
    r'<!-- PAGE (\d+)(?:\s*\|[^-]*)? -->'
)
_CONTEXT_MARKER = re.compile(
    r'<!-- CONTEXT: (.+?) -->'
)
_CONTEXT_SECTION_MARKER = re.compile(
    r'<!-- CONTEXT: (\S+) \| (.+?) \| 부문:(.+?) \| 장:(.+?) -->'
)


def parse_section_markers(text: str) -> list[dict]:
    """
    텍스트에서 SECTION 마커를 모두 추출한다.

    Args:
        text: 마크다운 텍스트

    Returns:
        list[dict]: [
            {
                "section_id": str,
                "title": str,
                "department": str,
                "chapter": str,
                "pos": int,   # 마커 시작 위치
                "end": int,   # 마커 끝 위치
            }, ...
        ]

    원본: section_splitter.py L99~131
    """
    markers = []
    for m in _SECTION_MARKER.finditer(text):
        markers.append({
            "section_id": m.group(1),
            "title": m.group(2).strip(),
            "department": m.group(3).strip(),
            "chapter": m.group(4).strip(),
            "pos": m.start(),
            "end": m.end(),
        })
    return markers


def parse_page_markers(text: str) -> list[dict]:
    """
    텍스트에서 PAGE 마커를 모두 추출한다.

    Args:
        text: 마크다운 텍스트

    Returns:
        list[dict]: [{"page": int, "context": str, "pos": int}, ...]

    원본: section_splitter.py L134~154
    """
    pages = []
    for m in _PAGE_MARKER.finditer(text):
        pages.append({
            "page": int(m.group(1)),
            "context": m.group(0)[len("<!-- PAGE "):].rstrip(" -->").strip(),
            "pos": m.start(),
        })
    return pages


def get_page_for_position(
    page_markers: list[dict],
    pos: int,
    file_start_page: int,
) -> int:
    """
    텍스트 내 위치(pos)에 해당하는 페이지 번호를 반환한다.

    Why: SECTION 마커의 텍스트 위치를 PAGE 마커와 대조하여
         해당 섹션이 몇 페이지에서 시작하는지 파악.

    Args:
        page_markers: parse_page_markers() 결과
        pos: 대상 위치 (문자 인덱스)
        file_start_page: 파일 첫 페이지 번호 (PAGE 마커 없을 때 기본값)

    Returns:
        int: 페이지 번호

    원본: section_splitter.py L161~188
    """
    current_page = file_start_page
    for pm in page_markers:
        if pm["pos"] <= pos:
            current_page = pm["page"]
        else:
            break
    return current_page


def redistribute_text_to_sections(
    markers: list[dict],
    combined_text: str,
) -> dict:
    """
    연속된 섹션 마커 그룹(내용이 비어있는 마커들)에 텍스트를 재배분한다.

    Why: 일부 페이지에서 여러 섹션 마커가 연속으로 등장하고
         그 뒤에 텍스트가 한 블록으로 나올 때,
         섹션 ID 기반으로 텍스트를 각 섹션에 할당한다.

    Args:
        markers: 연속 마커 그룹 (같은 페이지에 이어진 섹션들)
        combined_text: 마커 이후 텍스트 전체

    Returns:
        dict: {section_id: text, ...}

    원본: section_splitter.py L191~263
    """
    if not markers or not combined_text.strip():
        return {m["section_id"]: "" for m in markers}
    if len(markers) == 1:
        return {markers[0]["section_id"]: combined_text}

    split_points = []
    for marker in markers:
        sid = marker["section_id"]
        title = marker["title"]

        # section_id로 텍스트 내 위치 탐색
        escaped_sid = re.escape(sid)
        pattern = re.compile(rf'^{escaped_sid}\s+', re.MULTILINE)
        m = pattern.search(combined_text)
        if m:
            split_points.append((m.start(), sid))
            continue

        # section_id 탐색 실패 시 제목 앞글자로 탐색
        if title and len(title) >= 2:
            title_prefix = re.escape(title[:min(len(title), 8)])
            m = re.search(title_prefix, combined_text)
            if m:
                line_start = combined_text.rfind('\n', 0, m.start())
                line_start = line_start + 1 if line_start >= 0 else 0
                split_points.append((line_start, sid))

    split_points.sort(key=lambda x: x[0])

    if not split_points:
        result = {m["section_id"]: "" for m in markers}
        result[markers[-1]["section_id"]] = combined_text
        return result

    result = {m["section_id"]: "" for m in markers}

    # 첫 번째 split_point 이전 텍스트는 첫 섹션에 붙임
    if split_points[0][0] > 0:
        pre_text = combined_text[:split_points[0][0]].strip()
        if pre_text:
            result[split_points[0][1]] = pre_text + "\n"

    for i, (pos, sid) in enumerate(split_points):
        if i + 1 < len(split_points):
            text = combined_text[pos:split_points[i + 1][0]].strip()
        else:
            text = combined_text[pos:].strip()
        if result[sid]:
            result[sid] = result[sid] + "\n" + text
        else:
            result[sid] = text

    return result
