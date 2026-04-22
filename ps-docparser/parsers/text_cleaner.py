"""
parsers/text_cleaner.py — 섹션 본문 정제 공개 API shim + 오케스트레이터

Why: Phase 12 Step 12-4 분해 결과물.
     기존 import 경로를 100% 유지하는 shim과
     process_section_text() 오케스트레이터만 포함한다.

     분해 구조:
         text_metadata.py  → 메타데이터 추출 (extract_notes, extract_conditions,
                              extract_cross_references, remove_duplicate_notes)
         text_normalizer.py → 텍스트 정규화 (clean_text, merge_spaced_korean,
                              _RE_SINGLE_HANGUL)

     외부 코드(pipelines/, document_parser.py)는 이 파일을 통해
     모든 심볼에 동일 경로로 접근 가능하다.

원본: parsers/text_cleaner.py L1~395 (Phase 11 완료 기준)

Dependencies: 표준 라이브러리만 (re), 하위 모듈
"""

import re  # process_section_text의 patterns fallback용

# ── Import shim: 하위 모듈에서 전체 공개/반공개 API re-export ──
from parsers.text_metadata import (
    extract_notes,
    extract_conditions,
    extract_cross_references,
    remove_duplicate_notes,
)
from parsers.text_normalizer import (
    _RE_SINGLE_HANGUL,
    merge_spaced_korean,
    clean_text,
)

__all__ = [
    # text_metadata
    "extract_notes",
    "extract_conditions",
    "extract_cross_references",
    "remove_duplicate_notes",
    # text_normalizer
    "_RE_SINGLE_HANGUL",
    "merge_spaced_korean",
    "clean_text",
    # orchestration (this module)
    "process_section_text",
]


# ═══════════════════════════════════════════════════════
# 오케스트레이터 (이 파일에 유지)
# ═══════════════════════════════════════════════════════

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

    원본: text_cleaner.py L251~339
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
