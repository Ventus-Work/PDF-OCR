"""
parsers/text_cleaner.py — 섹션 본문 정제 및 메타데이터 추출

Why: 섹션의 raw_text에서 테이블을 제거한 뒤 남은 텍스트에서
     주석([주] 블록), 할증 조건, 교차참조, 보완연도, 단위 기준 등
     구조화된 메타데이터를 추출한다.
     도메인 전용 패턴은 파라미터로 주입하여 범용성을 유지한다.

원본: standalone_parser/parser.py L320~417

변경점 (원본 대비):
    - PATTERNS 전역 상수 참조 → patterns 파라미터로 주입
    - patterns=None 시 도메인 전용 추출 스킵 (범용 모드)
    - clean_text(): HTML 주석 제거 + 줄바꿈 정리는 항상 수행 (범용)
                   chapter_title 제거는 patterns 있을 때만 (도메인)

Dependencies: 표준 라이브러리만 (re)
"""

import re


def extract_notes(
    text: str,
    patterns: dict = None,
) -> tuple[list[str], str]:
    """
    [주] 블록에서 주석 항목을 추출하고, 해당 블록이 제거된 텍스트를 반환한다.

    Why: 품셈 문서의 [주] 블록은 테이블 적용 조건을 설명하는 중요 메타데이터다.
         본문 텍스트와 분리하여 "notes" 키로 별도 저장해야 한다.

    Args:
        text: 원본 텍스트 (테이블 제거 후)
        patterns: 도메인 패턴 딕셔너리.
                  None이면 주석 추출 스킵 → ([], text) 반환 (범용 모드).
                  필요 키: "note_block_start"

    Returns:
        tuple[list[str], str]:
            - list[str]: 추출된 주석 항목 리스트 (원문자 제거)
            - str: [주] 블록이 제거된 나머지 텍스트

    원본: standalone_parser/parser.py L324~335
    변경점: PATTERNS 전역 참조 → patterns 파라미터
    """
    # ── 범용 모드: 패턴 없으면 주석 추출 스킵 ──
    if not patterns or "note_block_start" not in patterns:
        return [], text

    notes = []
    remaining = text

    note_block_pattern = re.compile(
        r'\[주\]\s*\n(.*?)(?=\n\n(?!\s*[①②③④⑤⑥⑦⑧⑨⑩])|\n(?=\d+-\d+)|\Z)',
        re.DOTALL,
    )
    for m in note_block_pattern.finditer(text):
        items = re.split(r'(?=[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮])', m.group(1).strip())
        for item in items:
            item = re.sub(
                r'^[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮]\s*', '', item.strip()
            ).strip()
            if item:
                notes.append(item)
        remaining = note_block_pattern.sub('', remaining)
        remaining = re.sub(r'^\[주\]\s*$', '', remaining, flags=re.MULTILINE)

    return notes, remaining.strip()


def extract_conditions(
    text: str,
    patterns: dict = None,
) -> list[dict]:
    """
    할증/가산/감산 조건을 추출한다.

    Why: 품셈 문서에는 "~경우 본 품의 X% 가산" 형식의 조건이 있어
         데이터베이스 적재 및 검색에 구조화된 형식이 필요하다.

    Args:
        text: 원본 텍스트
        patterns: 필요 키: "surcharge". None이면 [] 반환.

    Returns:
        list[dict]: [{"type": str, "condition": str, "rate": str}, ...]
                    type: "가산" | "감산" | "할증" 등

    원본: standalone_parser/parser.py L337~348
    변경점: PATTERNS["surcharge"] → patterns["surcharge"]
    """
    if not patterns or "surcharge" not in patterns:
        return []

    conditions = []
    for m in patterns["surcharge"].finditer(text):
        cond_type = m.group(3)
        if "감" in cond_type:
            cond_type = "감산"
        elif "증" in cond_type or "가산" in cond_type:
            cond_type = "가산"
        conditions.append({
            "type": cond_type,
            "condition": m.group(1).strip(),
            "rate": f"{m.group(2)}%",
        })

    # 단순 "%할증/가산/감산" 패턴 추가 보완
    for m in re.compile(r'(\d+)%\s*(할증|가산|감산|증감)').finditer(text):
        rate = f"{m.group(1)}%"
        if not any(c["rate"] == rate for c in conditions):
            conditions.append({
                "type": m.group(2),
                "condition": text[max(0, m.start() - 30):m.start()].strip(),
                "rate": rate,
            })

    return conditions


def extract_cross_references(
    text: str,
    patterns: dict = None,
) -> list[dict]:
    """
    텍스트에서 교차참조(다른 섹션/장 참조)를 추출한다.

    Why: 품셈 문서에는 "제N장 X-Y-Z 참조", "X-Y-Z 항 준용" 등의
         교차참조가 빈번하며, 섹션 간 의존 관계를 파악하는 데 필요하다.

    Args:
        text: 원본 텍스트
        patterns: 필요 키: "cross_ref". None이면 [] 반환.

    Returns:
        list[dict]: [
            {
                "target_section_id": str,
                "target_chapter": str,  # "제N장" 형식 (없으면 "")
                "context": str,         # 참조 주변 문맥 (±20자)
            }, ...
        ]

    원본: standalone_parser/parser.py L350~359
    변경점: PATTERNS["cross_ref"] → patterns["cross_ref"]
    """
    if not patterns or "cross_ref" not in patterns:
        return []

    refs = []
    for m in patterns["cross_ref"].finditer(text):
        chapter = m.group(1)
        section_id = m.group(2)
        refs.append({
            "target_section_id": section_id,
            "target_chapter": f"제{chapter}장" if chapter else "",
            "context": text[
                max(0, m.start() - 20):min(len(text), m.end() + 20)
            ].strip(),
        })
    return refs


def clean_text(
    text: str,
    patterns: dict = None,
) -> str:
    """
    텍스트를 정제한다. 범용 정제는 항상, 도메인 정제는 patterns 있을 때만.

    범용 (항상 수행):
        - HTML 주석 (<!-- ... -->) 제거
        - 연속 줄바꿈(3개 이상) → 2개로 정리

    도메인 (patterns["chapter_title"] 있을 때):
        - 장 제목 행 ("제6장 철근콘크리트공사" 등) 제거
          Why: 품셈 문서에서 장 제목은 구조 마커 역할이지 내용이 아님.
               일반 문서에서는 제목을 제거하면 안 되므로 조건부 적용.

    Args:
        text: 정제 대상 텍스트
        patterns: 도메인 패턴 딕셔너리.
                  필요 키: "chapter_title" (있으면 장 제목 행 제거)

    Returns:
        str: 정제된 텍스트

    원본: standalone_parser/parser.py L361~365
    변경점:
        - HTML 주석 제거, 줄바꿈 정리는 항상 수행 (범용)
        - chapter_title 패턴 삭제는 patterns 제공 시에만 (도메인)
    """
    # ── 범용: 항상 수행 ──
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    # K1 보조 호출: MD 파일 직접 입력 시 Phase 1을 거치지 않으므로
    # clean_text() 단계에서 한 번 더 균등배분 병합을 수행하여 커버.
    text = merge_spaced_korean(text)

    # ── 도메인: 장 제목 행 제거 (품셈 프리셋 시) ──
    if patterns and "chapter_title" in patterns:
        text = patterns["chapter_title"].sub('', text)

    # ── 범용: 항상 수행 ──
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def remove_duplicate_notes(
    notes: list[str],
    table_notes: list[str],
) -> list[str]:
    """
    텍스트에서 추출한 주석 중 테이블 내 주석과 중복되는 항목을 제거한다.

    Why: 테이블 하단 주석이 본문 [주] 블록에도 동일하게 나타날 수 있다.
         중복 제거로 notes 리스트를 정제.
         포함 관계(부분 일치)도 중복으로 처리.

    Args:
        notes: 텍스트에서 추출한 주석 리스트
        table_notes: 테이블 내 주석 리스트 (is_note_row로 추출)

    Returns:
        list[str]: 중복 제거된 주석 리스트

    원본: standalone_parser/parser.py L367~379
    """
    if not table_notes:
        return notes

    unique_notes = []
    for note in notes:
        note_clean = re.sub(r'\s+', '', note)
        is_dup = False
        for tn in table_notes:
            tn_clean = re.sub(r'\s+', '', tn)
            shorter, longer = (
                (note_clean, tn_clean)
                if len(note_clean) < len(tn_clean)
                else (tn_clean, note_clean)
            )
            if shorter and shorter in longer:
                is_dup = True
                break
        if not is_dup:
            unique_notes.append(note)
    return unique_notes


def process_section_text(
    section: dict,
    patterns: dict = None,
) -> dict:
    """
    메인 정제 함수 — 섹션 텍스트 최종 처리.

    3단계 파이프라인의 마지막 처리기.
    process_section_tables()가 완료된 섹션 dict를 받아
    본문 정제 + 메타데이터 추출을 수행하여 최종 JSON 구조체를 반환한다.

    Args:
        section: process_section_tables()가 반환한 섹션 dict
                 ("tables", "text_without_tables" 키 포함)
        patterns: 도메인 패턴 딕셔너리 (None=범용).
                  None 시 notes/conditions/cross_references/revision_year/unit_basis
                  모두 빈값으로 반환.

    Returns:
        dict:
        {
            "section_id": str,
            "title": str,
            "department": str,
            "chapter": str,
            "page": int,
            "source_file": str,
            "toc_title": str,
            "clean_text": str,
            "tables": list[dict],
            "notes": list[str],
            "conditions": list[dict],
            "cross_references": list[dict],
            "revision_year": str,    # "" if patterns=None
            "unit_basis": str,       # "" if patterns=None
        }

    원본: standalone_parser/parser.py L381~417
    변경점: PATTERNS 전역 → patterns 파라미터. patterns=None 시 도메인 추출 스킵.
    """
    text = section.get("text_without_tables", section.get("raw_text", ""))

    # ── 도메인 전용 메타데이터 (patterns 제공 시에만) ──
    revision_year = ""
    unit_basis = ""
    if patterns:
        # 보완연도 추출 ('24년 보완 → "2024")
        m_revision = patterns.get("revision", re.compile(r'$^')).search(text)
        if m_revision:
            year = m_revision.group(1)
            if len(year) == 2:
                revision_year = f"20{year}" if int(year) < 50 else f"19{year}"
            else:
                revision_year = year

        # 단위 기준 추출 ((m³당) → "m³당")
        m_unit = patterns.get("unit_basis", re.compile(r'$^')).search(text)
        unit_basis = m_unit.group(1) if m_unit else ""

    # ── 주석 추출 (patterns 의존) ──
    notes, text_after_notes = extract_notes(text, patterns)
    table_notes = []
    for t in section.get("tables", []):
        table_notes.extend(t.get("notes_in_table", []))
    notes = remove_duplicate_notes(notes, table_notes)

    # ── 조건/교차참조 추출 (patterns 의존) ──
    conditions = extract_conditions(text, patterns)
    cross_references = extract_cross_references(text, patterns)

    # ── 텍스트 정제 (HTML 주석/줄바꿈은 항상, chapter_title은 도메인) ──
    clean = clean_text(text_after_notes, patterns)

    return {
        "section_id": section["section_id"],
        "title": section["title"],
        "department": section.get("department", ""),
        "chapter": section.get("chapter", ""),
        "page": section.get("page", 0),
        "source_file": section.get("source_file", ""),
        "toc_title": section.get("toc_title", ""),
        "clean_text": clean,
        "tables": section.get("tables", []),
        "notes": notes,
        "conditions": conditions,
        "cross_references": cross_references,
        "revision_year": revision_year,
        "unit_basis": unit_basis,
    }


# ── K1: 한글 균등배분 병합 (kordoc 알고리즘 참조, MIT License) ──────────────
# 알고리즘 참조: kordoc (https://github.com/chrisryugj/kordoc)
# Copyright (c) chrisryugj, MIT License

# Why: \d 제외 — 숫자 1글자 토큰은 균등배분 판정 대상이 아님 (오탐 방지)
_RE_SINGLE_HANGUL = re.compile(r'^[가-힣]$')


def merge_spaced_korean(text: str) -> str:
    """
    한글 균등배분 텍스트를 병합한다.

    Why: 한국 공문서/견적서에서 "제 출 처", "품   명" 등
         글자 사이에 공백을 넣는 균등배분 배치가 빈번하다.
         PDF 추출 시 공백이 그대로 남아 데이터 품질을 저하시킨다.
         kordoc의 cluster-detector.ts 알고리즘을 참조하여
         한글 1글자 토큰 비율 70%+ 이면 공백을 제거한다.

    예시:
        "제 출 처"   → "제출처"
        "품   명"    → "품명"
        "SUS 304"    → "SUS 304"  (변환 안 함: 한글 토큰 0%)
        "배관 Support" → "배관 Support" (변환 안 함: 비율 미달)

    Args:
        text: 원본 텍스트

    Returns:
        균등배분이 병합된 텍스트
    """
    if not text or len(text) < 3:
        return text

    lines = text.split('\n')
    result_lines = []

    for line in lines:
        tokens = line.split()
        if len(tokens) < 2:
            result_lines.append(line)
            continue

        # 한글 1글자 토큰 비율 계산
        single_hangul_count = sum(1 for t in tokens if _RE_SINGLE_HANGUL.match(t))
        ratio = single_hangul_count / len(tokens)

        if ratio >= 0.7:
            # 균등배분으로 판정 → 공백 제거
            result_lines.append(''.join(tokens))
        else:
            result_lines.append(line)

    return '\n'.join(result_lines)
