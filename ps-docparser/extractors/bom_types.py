"""
extractors/bom_types.py — BOM 데이터 클래스 정의

Phase 14: drawing_metadata 필드 추가 (BomExtractionResult)

Why: bom_extractor.py ↔ bom_table_parser.py 간 순환 import 방지.
     양쪽 모두 이 파일에서 데이터 클래스를 import한다.
     제3의 모듈에 정의하므로 import 방향이 항상 단방향:
       bom_types.py ← bom_extractor.py
       bom_types.py ← bom_table_parser.py

Dependencies: 없음 (표준 라이브러리 dataclasses만 사용)
"""
from dataclasses import dataclass, field


@dataclass
class BomSection:
    """추출된 BOM 또는 LINE LIST 섹션 1개."""
    section_type: str                      # "bom" | "line_list"
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    source_page: int | None = None
    raw_row_count: int = 0                 # 필터 전 행 수

    @property
    def parsed_row_count(self) -> int:
        return len(self.rows)


@dataclass
class BomExtractionResult:
    """BOM 추출 전체 결과."""
    bom_sections: list[BomSection] = field(default_factory=list)
    line_list_sections: list[BomSection] = field(default_factory=list)
    raw_text: str = ""
    ocr_engine: str = ""                   # 사용된 엔진명 (로그용)
    # Phase 14: 도면 타이틀 블록 메타데이터 (extract_drawing_meta() 결과)
    # 기본값 빈 dict → positional 호환성 유지, 기존 직접 생성 코드 무수정
    drawing_metadata: dict = field(default_factory=dict)

    @property
    def has_bom(self) -> bool:
        return any(s.rows for s in self.bom_sections)

    @property
    def has_line_list(self) -> bool:
        return any(s.rows for s in self.line_list_sections)

    @property
    def total_bom_rows(self) -> int:
        return sum(s.parsed_row_count for s in self.bom_sections)

    @property
    def total_ll_rows(self) -> int:
        return sum(s.parsed_row_count for s in self.line_list_sections)
