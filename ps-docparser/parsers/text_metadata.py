"""
parsers/text_metadata.py — 섹션 본문 메타데이터 추출 함수 모음

Why: Phase 12 Step 12-4 분해 결과물.
     text_cleaner.py의 메타데이터 추출 로직(주석/할증/교차참조/중복제거)을
     분리한 순수 추출 모듈.
     외부 의존성 없음 (re만 사용). 단독 테스트 가능.

원본: parsers/text_cleaner.py L23~248 (4개 함수)
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

    원본: text_cleaner.py L23~69
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

    원본: text_cleaner.py L72~119
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

    원본: text_cleaner.py L122~162
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

    원본: text_cleaner.py L209~248
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
