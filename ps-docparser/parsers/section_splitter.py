"""
parsers/section_splitter.py — 마크다운 마커 기반 섹션 분할

Why: Phase 1 추출기가 삽입한 <!-- SECTION -->, <!-- PAGE -->, <!-- CONTEXT --> 마커를
     기준으로 마크다운 텍스트를 섹션 단위로 분할한다.
     이 마커는 ps-docparser 자체 포맷(utils/markers.py가 생성)이므로
     프리셋과 무관하게 범용으로 적용된다.

원본: standalone_parser/parser.py L10~168
      standalone_parser/config.py (마커 패턴 4종)

변경점:
    - PATTERNS["section_marker"] 등 전역 참조 → 모듈 내부 상수로 이동
    - from config import PATTERNS → 제거 (bare import 불필요)

Dependencies: 표준 라이브러리만 (re, json, pathlib)
"""

import json
import re
from pathlib import Path

from .types import ParsedSection


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


# ══════════════════════════════════════════════════════════
# TOC 로딩 유틸리티
# ══════════════════════════════════════════════════════════

def load_toc(toc_path: Path) -> dict:
    """
    목차 JSON 파일을 로드하여 section_map 딕셔너리를 반환한다.

    Args:
        toc_path: 목차 JSON 파일 Path 객체

    Returns:
        dict: section_map {"section_id": {"id":..., "title":..., ...}, ...}
              파일 없으면 빈 dict

    원본: standalone_parser/parser.py L14~19
    """
    if not toc_path.exists():
        return {}
    with open(toc_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("section_map", data)


def build_reverse_map(toc: dict) -> dict:
    """
    (section_id, department) → toc_key 역매핑을 생성한다.

    Why: 마커에서 추출한 section_id + department 조합으로
         원본 toc_key를 역방향으로 찾기 위해 사용.

    Args:
        toc: load_toc()가 반환한 section_map

    Returns:
        dict: {(base_id, department): toc_key, ...}

    원본: standalone_parser/parser.py L21~27
    """
    reverse = {}
    for toc_key, entry in toc.items():
        base_id = entry.get("id", toc_key.split("#")[0])
        department = entry.get("chapter", "")
        reverse[(base_id, department)] = toc_key
    return reverse


# ══════════════════════════════════════════════════════════
# 마커 파싱 함수
# ══════════════════════════════════════════════════════════

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

    원본: standalone_parser/parser.py L29~40
    변경점: PATTERNS["section_marker"] → _SECTION_MARKER 모듈 상수
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

    원본: standalone_parser/parser.py L42~49
    변경점: PATTERNS["page_marker"] → _PAGE_MARKER 모듈 상수
    """
    pages = []
    for m in _PAGE_MARKER.finditer(text):
        pages.append({
            "page": int(m.group(1)),
            "context": m.group(0)[len("<!-- PAGE "):].rstrip(" -->").strip(),
            "pos": m.start(),
        })
    return pages


# ══════════════════════════════════════════════════════════
# 섹션 분할 로직
# ══════════════════════════════════════════════════════════

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

    원본: standalone_parser/parser.py L52~59
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

    원본: standalone_parser/parser.py L61~107
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


def split_sections(
    text: str,
    source_file: str,
    toc: dict,
    reverse_map: dict,
) -> list[ParsedSection]:
    """
    마크다운 텍스트를 SECTION/PAGE/CONTEXT 마커 기준으로 섹션 단위로 분할한다.

    Why: Phase 1이 삽입한 마커를 역파싱하여 섹션별 구조체를 생성.
         각 섹션은 section_id, 제목, 부문, 장, 페이지, 본문 텍스트를 포함한다.

    Args:
        text: 마크다운 + HTML 혼합 텍스트 (Phase 1 출력)
        source_file: 원본 파일명 (추적용)
        toc: load_toc()가 반환한 section_map
        reverse_map: build_reverse_map()이 반환한 역매핑

    Returns:
        list[dict]: 섹션별 딕셔너리 리스트.
            빈 리스트 = SECTION 마커 없음 (범용 문서)
            각 dict:
            {
                "section_id": str,
                "title": str,
                "department": str,
                "chapter": str,
                "page": int,
                "raw_text": str,       # 마커 제거된 본문 (HTML <table> 포함)
                "source_file": str,
                "toc_title": str,
                "toc_section": str,
                "has_content": bool,   # len(raw_text) > 10
            }

    원본: standalone_parser/parser.py L109~168
    변경점:
        - PATTERNS["section_marker"] → _SECTION_MARKER 모듈 상수
        - PATTERNS["page_marker"] → _PAGE_MARKER 모듈 상수
        - CONTEXT 마커 제거도 모듈 상수 사용
    """
    section_markers = parse_section_markers(text)
    page_markers = parse_page_markers(text)

    # SECTION 마커가 없으면 분할 불가 → 빈 리스트 반환
    # (document_parser.py에서 단일 섹션 폴백 처리)
    if not section_markers:
        return []

    file_start_page = page_markers[0]["page"] if page_markers else 0

    # 마커 그룹 구성: 인접한 마커들(사이 내용이 없는)을 하나의 그룹으로 묶기
    groups = []
    current_group = [section_markers[0]]

    for i in range(1, len(section_markers)):
        prev_marker = section_markers[i - 1]
        curr_marker = section_markers[i]
        between_text = text[prev_marker["end"]:curr_marker["pos"]]

        # 마커 사이의 실제 내용만 추출 (다른 마커/공백 제거)
        clean_between = _SECTION_MARKER.sub("", between_text)
        clean_between = _PAGE_MARKER.sub("", clean_between)
        clean_between = re.sub(r'<!-- CONTEXT:.*?-->', '', clean_between).strip()

        # 실제 내용이 10자 이하면 동일 그룹 (인접 마커)
        if len(clean_between) <= 10:
            current_group.append(curr_marker)
        else:
            group_text = text[current_group[-1]["end"]:curr_marker["pos"]].strip()
            groups.append((current_group, group_text))
            current_group = [curr_marker]

    # 마지막 그룹
    last_text = text[current_group[-1]["end"]:].strip()
    groups.append((current_group, last_text))

    # 각 그룹을 섹션별로 변환
    sections = []
    for marker_group, group_text in groups:
        redistributed = redistribute_text_to_sections(marker_group, group_text)

        for marker in marker_group:
            dept = marker["department"]
            toc_key = reverse_map.get(
                (marker["section_id"], dept), marker["section_id"]
            )
            toc_entry = toc.get(toc_key, {})
            if not toc_entry:
                toc_entry = toc.get(marker["section_id"], {})

            page = get_page_for_position(
                page_markers, marker["pos"], file_start_page
            )
            section_text = redistributed.get(marker["section_id"], "")

            # 마커 제거 (본문에서)
            section_text = _SECTION_MARKER.sub("", section_text)
            section_text = _PAGE_MARKER.sub("", section_text)
            section_text = re.sub(r'<!-- CONTEXT:.*?-->', '', section_text).strip()

            sections.append({
                "section_id": toc_key,
                "title": marker["title"],
                "department": dept,
                "chapter": marker["chapter"],
                "page": page,
                "raw_text": section_text,
                "source_file": source_file,
                "toc_title": toc_entry.get("title", ""),
                "toc_section": toc_entry.get("section", ""),
                "has_content": len(section_text) > 10,
            })

    return sections
