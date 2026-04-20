"""
parsers/document_parser.py — 마크다운 → 구조화 JSON 통합 파이프라인

Why: section_splitter → table_parser → text_cleaner를 순차 실행하는
     단일 진입점. main.py에서 이 모듈만 import하면 Phase 2 파이프라인이 완성된다.

흐름:
    1. 입력 판별: 파일 경로 → 텍스트 로딩 / 텍스트 문자열 → 직접 사용
    2. TOC 로딩 (선택적)
    3. split_sections()   → SECTION 마커 기반 섹션 분할
       마커 없으면       → 전체를 단일 섹션으로 폴백 (범용 문서 대응)
    4. process_section_tables() → HTML 테이블 파싱
    5. process_section_text()   → 본문 정제 + 메타데이터 추출

원본: standalone_parser/parser.py L423~453 (parse_markdown_document)
변경점:
    - 파일 경로 / 텍스트 문자열 모두 입력 가능
    - type_keywords, patterns 파라미터 추가 (프리셋 주입)
    - 마커 없는 문서 → 단일 섹션 폴백 (범용 대응)

Dependencies: parsers.section_splitter, parsers.table_parser, parsers.text_cleaner
"""

from pathlib import Path

from .section_splitter import load_toc, build_reverse_map, split_sections
from .table_parser import process_section_tables
from .text_cleaner import process_section_text
from .types import ParsedSection


def parse_markdown(
    md_input: str,
    toc_path: str = None,
    type_keywords: dict = None,
    patterns: dict = None,
) -> list[ParsedSection]:
    """
    마크다운 텍스트를 구조화된 JSON(섹션 리스트)으로 변환한다.

    Why: Phase 1의 추출 결과(마크다운) 또는 외부 마크다운 파일을
         한 번의 호출로 정형 데이터로 변환하는 올인원 함수.
         3단계(분할→테이블→정제) 파이프라인을 내부에서 순차 실행.

    Args:
        md_input: 마크다운 파일 경로 (str) 또는 마크다운 텍스트 문자열
        toc_path: 목차 JSON 파일 경로 (없으면 전체를 단일 섹션으로 처리)
        type_keywords: 테이블 유형 분류 키워드 (None=범용 → "general" 반환)
                       presets.pumsem.get_table_type_keywords() 로 얻음
        patterns: 텍스트 정제 도메인 패턴 (None=범용 → 도메인 추출 스킵)
                  presets.pumsem.get_parse_patterns() 로 얻음

    Returns:
        list[dict]: 섹션별 구조체 리스트.
            각 dict는 process_section_text() 출력 형식:
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
                "revision_year": str,
                "unit_basis": str,
            }

    사용 예:
        # 범용 모드 (프리셋 없음)
        result = parse_markdown("output/extracted.md")

        # 범용 모드 (텍스트 직접 전달)
        result = parse_markdown(md_text_string)

        # 품셈 모드
        from presets.pumsem import get_parse_patterns, get_table_type_keywords
        result = parse_markdown(
            "output/pumsem_doc.md",
            toc_path="toc.json",
            type_keywords=get_table_type_keywords(),
            patterns=get_parse_patterns(),
        )

    원본: standalone_parser/parser.py L423~453 (parse_markdown_document)
    변경점:
        - 입력: 파일 경로 OR 텍스트 문자열 모두 지원
        - type_keywords, patterns 파라미터 추가
        - 마커 없는 문서 → 단일 섹션 폴백 (범용 문서 대응)
    """
    # ── 1. 입력 판별: 파일 경로 vs 텍스트 문자열 ──
    # Why: main.py에서 추출된 MD 텍스트를 직접 넘기거나,
    #      기존 MD 파일 경로를 넘기는 두 가지 사용 패턴을 모두 지원.
    md_path = Path(md_input)
    if md_path.exists() and md_path.is_file():
        text = md_path.read_text(encoding="utf-8")
        filename = md_path.name
    else:
        text = md_input
        filename = "inline_text"

    # ── 2. TOC 로딩 ──
    toc = {}
    if toc_path and Path(toc_path).exists():
        toc = load_toc(Path(toc_path))
    reverse_map = build_reverse_map(toc)

    # ── 3. Step 1: 섹션 분할 ──
    raw_sections = split_sections(text, filename, toc, reverse_map)

    # ── 마커 없는 문서 폴백 (범용 모드) ──
    # Why: TOC 없이 추출된 범용 문서(견적서, 계약서 등)에는 SECTION 마커가 없다.
    #      빈 리스트를 그대로 반환하면 파이프라인 결과가 0건이 되므로,
    #      전체 문서를 하나의 섹션으로 처리하여 테이블이라도 파싱한다.
    if not raw_sections:
        raw_sections = [{
            "section_id": "doc",
            "title": filename,
            "department": "",
            "chapter": "",
            "page": 0,
            "raw_text": text,
            "source_file": filename,
            "toc_title": "",
            "toc_section": "",
            "has_content": len(text.strip()) > 10,
        }]

    # ── 4+5. Step 2+3: 테이블 파싱 → 본문 정제 ──
    parsed_sections = []
    for section in raw_sections:
        if not section.get("has_content", False):
            continue

        # Step 2: HTML 테이블 파싱
        section_with_tables = process_section_tables(section, type_keywords)

        # Step 3: 본문 정제 + 메타데이터 추출
        final_section = process_section_text(section_with_tables, patterns)
        parsed_sections.append(final_section)

    return parsed_sections
