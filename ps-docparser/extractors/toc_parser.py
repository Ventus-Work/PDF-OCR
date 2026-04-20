"""
extractors/toc_parser.py — 목차 파싱 모듈

Why: 텍스트(.txt) 기반 목차 정보를 파싱하여 
     페이지-섹션 간 매핑 모델(section_map, page_map)을 빌드한다.
     완전히 독립적인 유틸리티로 하이브리드 파이프라인과 결합된다.

이식 원본: pdf_extractor/toc_parser.py
"""

import re
from pathlib import Path


# ── 유틸리티 ─────────────────────────────────────────────

def _get_chapter_num(section_str: str) -> int:
    """섹션 문자열에서 장 번호 추출 (제7장 → 7, 제10장 → 10)"""
    m = re.search(r'제(\d+)장', section_str)
    return int(m.group(1)) if m else 0


def _normalize_section_name(name: str) -> str:
    """섹션명 정규화
    - "공 통" → "공통" (1글자씩 띄어쓰기된 것만 합침)
    - "지붕 및 홈통공사" → 유지 (정상 띄어쓰기)
    """
    m = re.match(r'(제\d+장)\s*(.*)', name)
    if m:
        prefix = m.group(1)
        rest = m.group(2).strip()
        # 모든 토큰이 1글자 한글인 경우만 공백 제거 ("공 통" → "공통")
        if rest and re.match(r'^[가-힣](\s+[가-힣])*$', rest):
            rest = re.sub(r'\s+', '', rest)
        return f"{prefix} {rest}"
    return name.strip()


def _split_line_at_chapter(line: str) -> list:
    """서브섹션 + 장 제목이 한 줄에 합쳐진 경우 분리"""
    if not re.match(r'^\d+-', line):
        return [line]

    m = re.search(r'\s+(제\d+장\s+[가-힣]+(?:\s+[가-힣]+)*\s+\d+)\s*$', line)
    if m:
        before = line[:m.start()].strip()
        chapter_part = m.group(1).strip()
        return [before, chapter_part] if before else [chapter_part]
    return [line]


def _fix_split_chapter_id(section_id: str, chapter_num: int) -> str:
    """2자리 장번호 ID 복원"""
    if chapter_num < 10:
        return section_id

    first_num = int(section_id.split('-')[0])
    expected_remainder = chapter_num % 10

    if first_num == expected_remainder and first_num != chapter_num:
        prefix = str(chapter_num // 10)
        return prefix + section_id

    return section_id


# ── 메인 파서 ────────────────────────────────────────────

def parse_toc(toc_path: str) -> dict:
    """
    목차 파일을 파싱하여 섹션 매핑 사전 생성
    """
    section_map = {}

    with open(toc_path, 'r', encoding='utf-8') as f:
        content = f.read()

    current_chapter = ""
    current_section = ""
    current_chapter_num = 0

    chapter_section_pat = re.compile(
        r'(공통부문|토목부문|건축부문|기계설비부문|유지관리부문)\s+'
        r'(제\d+장\s+[가-힣\s]+)\s+(\d+)'
    )
    section_pat = re.compile(r'(제\d+장\s+[가-힣\s]+?)\s+(\d+)\s*$')
    subsection_pat = re.compile(
        r'^(\d+-\d+(?:-\d+)?)\s+(.+?)[\s\u00b7\u2024\u2027·.]+(\d+)(?:\s+\d+.*)?$'
    )

    lines = content.split('\n')

    for line in lines:
        line = line.strip()
        if not line or line.startswith('<!--'):
            continue

        line = re.sub(r'^목\s*차\s*', '', line)
        line = re.sub(r'\s+\d+\s+목차\s*$', '', line)

        if not line.strip():
            continue

        parts = _split_line_at_chapter(line)

        for part in parts:
            part = part.strip()
            if not part:
                continue

            m = chapter_section_pat.search(part)
            if m:
                current_chapter = m.group(1)
                current_section = _normalize_section_name(m.group(2))
                current_chapter_num = _get_chapter_num(current_section)
                continue

            m = section_pat.search(part)
            if m and not re.match(r'^\d+-', part):
                current_section = _normalize_section_name(m.group(1))
                current_chapter_num = _get_chapter_num(current_section)
                continue

            m = subsection_pat.search(part)
            if m:
                section_id = m.group(1)
                title_raw = m.group(2).strip()
                page_num = int(m.group(3))

                section_id = _fix_split_chapter_id(section_id, current_chapter_num)

                title = re.sub(r'[·\u00b7\u2024\u2027.]+.*$', '', title_raw).strip()
                title = re.sub(r'\s+\d+\s*$', '', title).strip()

                if not section_id or not title:
                    continue

                key = section_id
                counter = 1
                while key in section_map:
                    counter += 1
                    key = f"{section_id}#{counter}"

                section_map[key] = {
                    "id": section_id,
                    "chapter": current_chapter,
                    "section": current_section,
                    "title": title,
                    "page": page_num
                }

    return section_map


# ── 페이지 매핑 ──────────────────────────────────────────

def build_page_to_sections_map(section_map: dict) -> dict:
    """페이지 번호 → 해당 페이지에서 시작하는 섹션들 매핑"""
    page_map = {}

    for key, info in section_map.items():
        page_num = info.get("page", 0)
        if page_num > 0:
            if page_num not in page_map:
                page_map[page_num] = []
            page_map[page_num].append({
                "id": info.get("id", key),
                "chapter": info.get("chapter", ""),
                "section": info.get("section", ""),
                "title": info.get("title", "")
            })

    return page_map


def get_current_context(pdf_page_num: int, page_map: dict, last_context: dict = None) -> dict:
    """현재 PDF 페이지에 해당하는 부문/장/섹션 정보 반환"""
    context = last_context.copy() if last_context else {"chapter": "", "section": "", "sections": []}

    if pdf_page_num in page_map:
        sections = page_map[pdf_page_num]
        context["sections"] = sections
        if sections:
            context["chapter"] = sections[0].get("chapter", context.get("chapter", ""))
            context["section"] = sections[0].get("section", context.get("section", ""))
    else:
        context["sections"] = []

    return context


def get_active_section(pdf_page_num: int, section_map: dict) -> dict | None:
    """주어진 페이지에서 활성화된 섹션 반환 (가장 가까운 이전 섹션)"""
    if not section_map or pdf_page_num <= 0:
        return None

    candidates = []
    for key, info in section_map.items():
        page = info.get("page", 0)
        if 0 < page <= pdf_page_num:
            candidates.append({
                "id": info.get("id", key),
                "chapter": info.get("chapter", ""),
                "section": info.get("section", ""),
                "title": info.get("title", ""),
                "page": page
            })

    if not candidates:
        return None

    candidates.sort(key=lambda x: (x["page"], x["id"]))
    return candidates[-1]


def get_section_info(section_id: str, section_map: dict) -> str:
    """섹션 ID에 대한 구조 정보 문자열 반환"""
    info = section_map.get(section_id)
    if not info:
        for key, val in section_map.items():
            if val.get("id") == section_id:
                info = val
                break
    if not info:
        return ""

    parts = []
    if info.get("chapter"):
        parts.append(info["chapter"])
    if info.get("section"):
        parts.append(info["section"])
    if section_id and info.get("title"):
        parts.append(f"{section_id} {info['title']}")
    return " > ".join(parts)


def parse_toc_file(toc_path: str) -> dict:
    """래퍼 함수"""
    return parse_toc(toc_path)


def inject_section_markers(text: str, section_map: dict) -> str:
    """텍스트에서 섹션 ID를 감지하고 구조 정보 주석 삽입"""
    if not section_map:
        return text

    section_pattern = re.compile(r'^(\d+-\d+-\d+)\s+', re.MULTILINE)

    def replace_with_marker(match):
        sid = match.group(1)
        info_str = get_section_info(sid, section_map)
        if info_str:
            return f"\n<!-- SECTION: {info_str} -->\n{match.group(0)}"
        return match.group(0)

    return section_pattern.sub(replace_with_marker, text)


# ── CLI ──────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    
    # 상위 경로를 임시로 추가하여 독립 실행 가능하도록 조치 (리스크 예방)
    _root = str(Path(__file__).resolve().parent.parent)
    if _root not in sys.path:
        sys.path.insert(0, _root)

    if len(sys.argv) < 2:
        print("사용법: python toc_parser.py <목차파일경로>")
        sys.exit(1)

    toc_path = sys.argv[1]

    print(f"📖 목차 파싱 중: {toc_path}")
    test_map = parse_toc(toc_path)

    print(f"\n✅ {len(test_map)}개 섹션 파싱 완료:\n")
    # 샘플 출력
    for i, (k, v) in enumerate(test_map.items()):
        if i >= 10:
            print(f"... 외 {len(test_map) - 10}개")
            break
        print(f"  [{k}] {v['chapter']} > {v['section']} > {v['id']} {v['title']} (p.{v['page']})")
