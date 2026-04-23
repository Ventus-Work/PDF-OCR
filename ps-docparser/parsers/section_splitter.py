"""
parsers/section_splitter.py — 섹션 분할 공개 API shim + 오케스트레이터

Why: Phase 12 Step 12-5 분해 결과물.
     기존 import 경로를 100% 유지하는 shim과
     split_sections() 오케스트레이터만 포함한다.

     분해 구조:
         section_toc.py     → TOC 로딩/역매핑 (load_toc, build_reverse_map)
         section_detector.py → 마커 정규식 상수 + 파싱/재배분 4함수
                               (_SECTION_MARKER, _PAGE_MARKER, _CONTEXT_MARKER,
                                _CONTEXT_SECTION_MARKER,
                                parse_section_markers, parse_page_markers,
                                get_page_for_position, redistribute_text_to_sections)

     외부 코드(document_parser.py, pipelines/)는 이 파일을 통해
     모든 심볼에 동일 경로로 접근 가능하다.

원본: parsers/section_splitter.py L1~381 (Phase 11 완료 기준)

Dependencies: 표준 라이브러리 (re), .types, 하위 모듈
"""

import re

from .types import ParsedSection

# ── Import shim: 하위 모듈에서 전체 공개/반공개 API re-export ──
from parsers.section_toc import load_toc, build_reverse_map
from parsers.section_detector import (
    _SECTION_MARKER,
    _PAGE_MARKER,
    _CONTEXT_MARKER,
    _CONTEXT_SECTION_MARKER,
    parse_section_markers,
    parse_page_markers,
    get_page_for_position,
    redistribute_text_to_sections,
)

__all__ = [
    # section_toc
    "load_toc",
    "build_reverse_map",
    # section_detector
    "_SECTION_MARKER", "_PAGE_MARKER", "_CONTEXT_MARKER", "_CONTEXT_SECTION_MARKER",
    "parse_section_markers",
    "parse_page_markers",
    "get_page_for_position",
    "redistribute_text_to_sections",
    # orchestration (this module)
    "split_sections_by_title_patterns",
    "split_sections",
]


# ═══════════════════════════════════════════════════════
# 오케스트레이터 (이 파일에 유지)
# ═══════════════════════════════════════════════════════

def _strip_parser_markers(text: str) -> str:
    """페이지/컨텍스트 마커를 제거한 뒤 앞뒤 공백을 정리한다."""
    text = _PAGE_MARKER.sub("", text)
    text = _SECTION_MARKER.sub("", text)
    text = _CONTEXT_MARKER.sub("", text)
    text = _CONTEXT_SECTION_MARKER.sub("", text)
    return text.strip()


def _current_chapter_title(chapter_matches: list[re.Match], pos: int) -> str:
    """현재 위치에 가장 가까운 직전 장 제목을 찾는다."""
    current = ""
    for match in chapter_matches:
        if match.start() > pos:
            break
        current = match.group(0).strip()
    return current


def split_sections_by_title_patterns(
    text: str,
    source_file: str,
    patterns: dict | None,
) -> list[ParsedSection]:
    """
    SECTION 마커가 없는 품셈 문서를 제목 패턴으로 분리한다.

    Why:
        TOC/SECTION 마커가 없는 품셈 문서는 `1-2`, `1-2-1`류 제목만 남아 있는 경우가
        많다. 이 fallback이 없으면 문서 전체가 `doc` 한 섹션으로 묶여 섹션별 표 맥락을
        잃는다.
    """
    if not patterns:
        return []

    section_pattern = patterns.get("section_title")
    if section_pattern is None:
        return []

    section_matches = list(section_pattern.finditer(text))
    if not section_matches:
        return []

    chapter_pattern = patterns.get("chapter_title")
    chapter_matches = list(chapter_pattern.finditer(text)) if chapter_pattern else []
    page_markers = parse_page_markers(text)
    file_start_page = page_markers[0]["page"] if page_markers else 0

    sections: list[ParsedSection] = []
    seen_ids: dict[str, int] = {}

    def _append_section(
        section_id: str,
        title: str,
        chapter: str,
        start: int,
        end: int,
    ) -> None:
        raw_text = _strip_parser_markers(text[start:end])
        if len(raw_text) <= 10:
            return

        base_id = section_id or f"section_{len(sections) + 1}"
        count = seen_ids.get(base_id, 0) + 1
        seen_ids[base_id] = count
        unique_id = base_id if count == 1 else f"{base_id}_{count}"

        sections.append({
            "section_id": unique_id,
            "title": title.strip() or unique_id,
            "department": "",
            "chapter": chapter.strip(),
            "page": get_page_for_position(page_markers, start, file_start_page),
            "raw_text": raw_text,
            "source_file": source_file,
            "toc_title": "",
            "toc_section": "",
            "has_content": True,
        })

    first_start = section_matches[0].start()
    intro_text = _strip_parser_markers(text[:first_start])
    if len(intro_text) > 10:
        intro_chapter = _current_chapter_title(chapter_matches, first_start)
        _append_section("intro", intro_chapter or "서문", intro_chapter, 0, first_start)

    for idx, match in enumerate(section_matches):
        start = match.start()
        end = section_matches[idx + 1].start() if idx + 1 < len(section_matches) else len(text)
        section_id = match.group(1).strip() if match.lastindex and match.lastindex >= 1 else ""
        title = match.group(2).strip() if match.lastindex and match.lastindex >= 2 else match.group(0).strip()
        chapter = _current_chapter_title(chapter_matches, start)
        _append_section(section_id, title, chapter, start, end)

    return sections

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

    원본: section_splitter.py L266~380
    """
    section_markers = parse_section_markers(text)
    page_markers    = parse_page_markers(text)

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
            dept    = marker["department"]
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
