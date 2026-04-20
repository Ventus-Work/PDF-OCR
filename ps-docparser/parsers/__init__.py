"""
parsers/ — 마크다운 → 구조화 JSON 정제 패키지 (Phase 2)

Why: Phase 1(extractors/)이 PDF에서 추출한 마크다운+HTML을
     구조화된 JSON(섹션별 테이블, 메타데이터 포함)으로 변환하는 2단계 처리기.
     Phase 1 출력물 또는 외부 마크다운 파일을 직접 입력 가능.

공개 API:
    from parsers.document_parser import parse_markdown
    from parsers.table_parser import parse_html_table, process_section_tables
    from parsers.section_splitter import split_sections
    from parsers.text_cleaner import process_section_text
"""
