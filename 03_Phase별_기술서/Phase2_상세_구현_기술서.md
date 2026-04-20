# Phase 2 상세 구현 기술서 — standalone_parser 이식 + 파이프라인 연결

## 목적

`standalone_parser/` (3개 파일, 642줄)의 마크다운→JSON 정제 파이프라인을 `ps-docparser/parsers/` 패키지로 이식한다.

Phase 2 완료 시점에 **Phase 1이 출력한 마크다운(HTML `<table>` 포함)을 입력하면 기존 `standalone_parser`와 동일한 구조의 JSON이 나와야** 한다.

---

## 원본 소스 함수 분석 (standalone_parser/)

### standalone_parser/config.py (49줄)

| 원본 위치 | 내용 | 이식 대상 |
|---|---|---|
| L3~43 | `PATTERNS` dict (정규식 10개) | 아래 분류표 참조 |
| L45~49 | `TABLE_TYPE_KEYWORDS` dict | `presets/pumsem.py` (도메인 전용) |

**PATTERNS 분류 — 범용 vs 도메인:**

| 패턴 키 | 용도 | 범용/도메인 | 이식 대상 |
|---|---|---|---|
| `section_marker` | `<!-- SECTION: ... -->` 파싱 | **범용** (ps-docparser 자체 포맷) | `parsers/section_splitter.py` 내부 상수 |
| `page_marker` | `<!-- PAGE N \| ... -->` 파싱 | **범용** | `parsers/section_splitter.py` 내부 상수 |
| `context_marker` | `<!-- CONTEXT: ... -->` 파싱 | **범용** | `parsers/section_splitter.py` 내부 상수 |
| `context_section_marker` | `<!-- CONTEXT: ID \| ... -->` 파싱 | **범용** | `parsers/section_splitter.py` 내부 상수 |
| `note_block_start` | `[주]` 블록 감지 | **도메인** (품셈/기술표준) | `presets/pumsem.py` |
| `note_item` | ①②③ 항목 분리 | **도메인** | `presets/pumsem.py` |
| `surcharge` | 할증/가산/감산 조건 | **도메인** | `presets/pumsem.py` |
| `cross_ref` | 교차참조 (제N장 X-Y-Z 참조) | **도메인** | `presets/pumsem.py` |
| `revision` | 보완연도 ('24년 보완) | **도메인** | `presets/pumsem.py` |
| `unit_basis` | 단위 기준 (m³당) | **도메인** | `presets/pumsem.py` |
| `chapter_title` | 장 제목 (제6장 ...) | **도메인** | `presets/pumsem.py` |
| `section_title` | 절 제목 (6-1 콘크리트) | **도메인** | `presets/pumsem.py` |

**핵심 설계 결정:** 마커 패턴 4종은 ps-docparser가 Phase 1에서 직접 생성하는 포맷이므로 `section_splitter.py`에 내장한다. 나머지 8종은 품셈 도메인 전용이므로 `presets/pumsem.py`에 `PARSE_PATTERNS` dict로 이동하고, 파서 함수에 파라미터로 주입한다(Phase 1의 `division_names` 패턴과 동일한 접근).

---

### standalone_parser/html_utils.py (121줄)

| 원본 위치 | 함수명 | 역할 | 이식 대상 |
|---|---|---|---|
| L8~61 | `expand_table(table_tag)` | rowspan/colspan 전개 → 2D 배열 | `parsers/table_parser.py` |
| L64~80 | `extract_cell_text(cell)` | 셀 텍스트 추출 (sup/sub/br 변환) | `parsers/table_parser.py` |
| L83~89 | `clean_cell_text(text)` | 셀 텍스트 정제 (nbsp, 연속 공백) | `parsers/table_parser.py` |
| L92~98 | `parse_html_table(html)` | HTML 문자열 → 2D 배열 (편의 래퍼) | `parsers/table_parser.py` |
| L101~115 | `extract_tables_from_text(text)` | 텍스트에서 `<table>` 태그 위치 추출 | `parsers/table_parser.py` |
| L118~121 | `remove_tables_from_text(text)` | 텍스트에서 `<table>` 태그 제거 | `parsers/table_parser.py` |

---

### standalone_parser/parser.py (472줄)

#### 1단계: Section Splitter (L1~168)

| 원본 위치 | 함수명 | 역할 | 이식 대상 |
|---|---|---|---|
| L14~19 | `load_toc(toc_path)` | 목차 JSON 로드 → section_map | `parsers/section_splitter.py` |
| L21~27 | `build_reverse_map(toc)` | (id, department) → toc_key 역매핑 | `parsers/section_splitter.py` |
| L29~40 | `parse_section_markers(text)` | SECTION 마커 파싱 → list[dict] | `parsers/section_splitter.py` |
| L42~49 | `parse_page_markers(text)` | PAGE 마커 파싱 → list[dict] | `parsers/section_splitter.py` |
| L52~59 | `get_page_for_position(page_markers, pos, start)` | 텍스트 위치 → 페이지 번호 | `parsers/section_splitter.py` |
| L61~107 | `redistribute_text_to_sections(markers, text)` | 인접 섹션 간 텍스트 재배분 | `parsers/section_splitter.py` |
| L109~168 | `split_sections(text, file, toc, reverse)` | **메인 분할 함수** — 마커 기반 섹션 분할 | `parsers/section_splitter.py` |

#### 2단계: Table Parser (L170~318)

| 원본 위치 | 함수명 | 역할 | 이식 대상 |
|---|---|---|---|
| L174~196 | `classify_table(headers, rows)` | 테이블 유형 분류 (A~D) | `parsers/table_parser.py` (**변경**: `type_keywords` 파라미터 추가) |
| L198~202 | `_is_header_like_row(row)` | 헤더 유사 행 감지 | `parsers/table_parser.py` |
| L204~214 | `detect_header_rows(grid)` | 헤더 행 수 결정 (1~3행) | `parsers/table_parser.py` |
| L216~228 | `build_composite_headers(grid, n)` | 다단 헤더 병합 | `parsers/table_parser.py` |
| L230~245 | `is_note_row(row, total_cols)` | 주석 행 감지 ([주], ①② 등) | `parsers/table_parser.py` |
| L247~260 | `try_numeric(val)` | 문자열 → 숫자 변환 | `parsers/table_parser.py` |
| L262~302 | `parse_single_table(html, sid, idx)` | 단일 테이블 파싱 파이프라인 | `parsers/table_parser.py` (**변경**: `type_keywords` 파라미터 추가) |
| L304~318 | `process_section_tables(section)` | 섹션 내 전체 테이블 처리 | `parsers/table_parser.py` (**변경**: `type_keywords` 파라미터 추가) |

#### 3단계: Text Cleaner (L320~417)

| 원본 위치 | 함수명 | 역할 | 이식 대상 |
|---|---|---|---|
| L324~335 | `extract_notes(text)` | `[주]` 블록 → 주석 리스트 추출 | `parsers/text_cleaner.py` (**변경**: `patterns` 파라미터 추가) |
| L337~348 | `extract_conditions(text)` | 할증/가산/감산 조건 추출 | `parsers/text_cleaner.py` (**변경**: `patterns` 파라미터 추가) |
| L350~359 | `extract_cross_references(text)` | 교차참조 추출 | `parsers/text_cleaner.py` (**변경**: `patterns` 파라미터 추가) |
| L361~365 | `clean_text(text)` | HTML 주석 제거 + 정리 | `parsers/text_cleaner.py` (**변경**: `patterns` 파라미터 추가) |
| L367~379 | `remove_duplicate_notes(notes, table_notes)` | 테이블 내 주석과 중복 제거 | `parsers/text_cleaner.py` |
| L381~417 | `process_section_text(section)` | **메인 정제 함수** — 섹션 텍스트 최종 처리 | `parsers/text_cleaner.py` (**변경**: `patterns` 파라미터 추가) |

#### 통합 오케스트레이터 (L423~453)

| 원본 위치 | 함수명 | 역할 | 이식 대상 |
|---|---|---|---|
| L423~453 | `parse_markdown_document(md_path, toc_path)` | 3단계 파이프라인 통합 실행 | `parsers/document_parser.py` (**변경**: `preset`/`type_keywords`/`patterns` 파라미터 추가) |

---

## Phase 2 신규/변경 파일 목록

```
ps-docparser/
├── main.py                          # [변경] --output json/md 옵션 추가, .md 입력 지원
├── config.py                        # [변경 없음]
│
├── engines/                         # [변경 없음]
├── extractors/                      # [변경 없음]
├── utils/                           # [변경 없음]
│
├── parsers/                         # [신규] Phase 2 전체
│   ├── __init__.py                  # 패키지 초기화
│   ├── table_parser.py              # HTML 테이블 → 2D 배열 + 구조 분석
│   ├── section_splitter.py          # 마커 기반 섹션 분할
│   ├── text_cleaner.py              # 본문 정제 + 메타데이터 추출
│   └── document_parser.py           # 3단계 파이프라인 통합 오케스트레이터
│
├── presets/
│   ├── __init__.py
│   └── pumsem.py                    # [변경] PARSE_PATTERNS + TABLE_TYPE_KEYWORDS 추가
│
└── requirements.txt                 # [변경] beautifulsoup4, lxml 추가
```

---

## 파일별 상세 스펙

### 1. `parsers/__init__.py` — 패키지 초기화

```python
"""
parsers/ — 마크다운 → 구조화 JSON 정제 패키지

Why: Phase 1(extractors/)이 PDF에서 추출한 마크다운+HTML을
     구조화된 JSON(섹션별 테이블, 메타데이터 포함)으로 변환하는 2단계 처리기.
     Phase 1 출력물 또는 외부 마크다운 파일을 직접 입력 가능.
"""
```

---

### 2. `parsers/table_parser.py` — HTML 테이블 파서

```python
"""
HTML 테이블 파싱 및 구조 분석.

Why: Phase 1의 AI 엔진이 출력한 HTML <table>에는 rowspan/colspan이 포함되어 있어
     단순 파싱으로는 2D 배열로 복원이 안 된다.
     이 모듈이 셀 병합을 전개하고, 헤더/데이터/주석 행을 분류하여
     JSON-ready 구조체로 변환한다.

원본: standalone_parser/html_utils.py (전체) + standalone_parser/parser.py L170~318
Dependencies: beautifulsoup4, lxml(선택) / html.parser(폴백)
"""
```

**이식 함수 전체 목록 (12개):**

```python
# ── html_utils.py에서 이식 (6개) ──

def expand_table(table_tag: Tag) -> list[list[str]]:
    """HTML 테이블의 rowspan/colspan을 전개하여 2D 배열로 반환.
    원본: html_utils.py L8~61. 변경 없음."""

def extract_cell_text(cell: Tag) -> str:
    """셀에서 텍스트 추출. sup→^, sub→_, br→공백 변환.
    원본: html_utils.py L64~80. 변경 없음."""

def clean_cell_text(text: str) -> str:
    """셀 텍스트 정제 (nbsp, 연속 공백).
    원본: html_utils.py L83~89. 변경 없음."""

def parse_html_table(html: str) -> list[list[str]]:
    """HTML 문자열 → 2D 배열 편의 래퍼.
    원본: html_utils.py L92~98.
    변경점: [리뷰 반영] BeautifulSoup(html, "lxml") → _make_soup(html) 폴백 구조."""

def extract_tables_from_text(text: str) -> list[dict]:
    """텍스트에서 <table>...</table> 위치 추출.
    원본: html_utils.py L101~115. 변경 없음."""

def remove_tables_from_text(text: str) -> str:
    """텍스트에서 <table> 태그 제거.
    원본: html_utils.py L118~121. 변경 없음."""


# ── parser.py Table Parser 섹션에서 이식 (6개) ──

def classify_table(
    headers: list[str],
    rows: list[list[str]],
    type_keywords: dict = None,           # ← 변경점
) -> str:
    """테이블 유형 분류.

    Args:
        headers: 헤더 문자열 리스트
        rows: 데이터 행 리스트
        type_keywords: 유형 판별 키워드 딕셔너리.
                       None이면 "general" 반환 (범용 모드).
                       pumsem 프리셋 시 TABLE_TYPE_KEYWORDS 주입.

    원본: parser.py L174~196.
    변경점: PATTERNS["A_품셈"] 등 전역 참조 → type_keywords 파라미터."""

def _is_header_like_row(row: list[str]) -> bool:
    """헤더 유사 행 감지 (비숫자 셀 비율 > 50%).
    원본: parser.py L198~202. 변경 없음."""

def detect_header_rows(grid: list[list[str]]) -> int:
    """헤더 행 수 결정 (1~3행).
    원본: parser.py L204~214. 변경 없음."""

def build_composite_headers(grid: list[list[str]], n_header_rows: int) -> list[str]:
    """다단 헤더 병합 (2행 이상 → "상위_하위" 형식).
    원본: parser.py L216~228. 변경 없음."""

def is_note_row(row: list[str], total_cols: int = 0) -> bool:
    """주석 행 감지 ([주], ①②, 비고 등).
    원본: parser.py L230~245. 변경 없음.
    참고: 이 함수의 패턴들([주], ①② 등)은 한국 기술문서 범용 표기법이므로
          프리셋 분기 없이 항상 적용한다."""

def try_numeric(val: str):
    """셀 값 정제 — 공백/콤마 정리 후 문자열 유지 (범용 안전 모드).
    원본: parser.py L247~260.
    변경점: [리뷰 반영] 숫자 캐스팅 제거 → 문자열 정제만 수행.
           상세: 위험 7 참조."""

def parse_single_table(
    html: str,
    section_id: str,
    table_idx: int,
    type_keywords: dict = None,           # ← 변경점
) -> dict | None:
    """단일 HTML 테이블을 구조체로 파싱.

    Returns:
        {
            "table_id": "T-{section_id}-{idx:02d}",
            "type": str,              # classify_table 결과
            "headers": list[str],
            "rows": list[dict],       # 헤더 키 기반 dict
            "notes_in_table": list[str],
            "raw_row_count": int,
            "parsed_row_count": int,
        }

    원본: parser.py L262~302.
    변경점: classify_table()에 type_keywords 전달."""

def process_section_tables(
    section: dict,
    type_keywords: dict = None,           # ← 변경점
) -> dict:
    """섹션 내 모든 테이블을 파싱.

    Returns:
        section dict + "tables" 키 추가 + "text_without_tables" 키 추가.

    원본: parser.py L304~318.
    변경점: parse_single_table()에 type_keywords 전달."""
```

**`classify_table()` 범용/프리셋 분기 상세:**

```python
def classify_table(
    headers: list[str],
    rows: list[list[str]],
    type_keywords: dict = None,
) -> str:
    """
    원본: parser.py L174~196

    변경점:
    - type_keywords=None → "general" 반환 (범용 모드)
    - type_keywords 제공 시 → 기존 분류 로직 실행
    - [리뷰 반영] _LABOR_ROW_KEYWORDS 하드코딩 제거 →
      type_keywords["A_품셈_행키워드"]로 외부 주입
    """
    # ── 범용 모드: 키워드 없으면 분류 불가 → 일반 테이블 ──
    if not type_keywords:
        return "general"

    header_text = " ".join(headers).lower()

    # A 유형 판별 (헤더 키워드 매칭)
    a_keywords = type_keywords.get("A_품셈", [])
    if sum(1 for kw in a_keywords if kw in header_text) >= 2:
        return "A_품셈"

    # A 유형 보조 판별 (행 데이터 키워드 매칭)
    # [리뷰 반영] 노동자 직종 키워드도 presets에서 주입받는다.
    #   원본에는 "인부", "용접공" 등이 함수 내부에 하드코딩되어 있었으나,
    #   이는 품셈 도메인 특정 용어이므로 범용 파서에 존재하면 안 된다.
    a_row_keywords = type_keywords.get("A_품셈_행키워드", [])
    if a_row_keywords and rows and len(rows) >= 2:
        labor_row_count = 0
        for row in rows:
            first_val = ""
            if isinstance(row, dict):
                first_val = str(list(row.values())[0]).replace(" ", "") if row else ""
            elif isinstance(row, (list, tuple)):
                first_val = str(row[0]).replace(" ", "") if row else ""
            if any(kw in first_val for kw in a_row_keywords):
                labor_row_count += 1
        if labor_row_count >= 2:
            return "A_품셈"

    # B, C 유형 판별
    if any(kw in header_text for kw in type_keywords.get("B_규모기준", [])):
        return "B_규모기준"
    if len(headers) == 2 and any(kw in header_text for kw in type_keywords.get("C_구분설명", [])):
        return "C_구분설명"

    return "D_기타"
```

---

### 3. `parsers/section_splitter.py` — 섹션 분할기

```python
"""
마크다운 마커 기반 섹션 분할.

Why: Phase 1 추출기가 삽입한 <!-- SECTION -->, <!-- PAGE -->, <!-- CONTEXT --> 마커를
     기준으로 마크다운 텍스트를 섹션 단위로 분할한다.
     이 마커는 ps-docparser 자체 포맷이므로 프리셋과 무관하게 범용으로 적용된다.

원본: standalone_parser/parser.py L10~168 + standalone_parser/config.py (마커 패턴 4종)
Dependencies: 표준 라이브러리만 (re, json, pathlib)
"""
import re
import json
from pathlib import Path
```

**내부 상수 (config.py 마커 패턴 이식):**

```python
# ── ps-docparser 마커 포맷 정규식 (범용 — 프리셋 무관) ──
# Why: 이 패턴들은 utils/markers.py가 생성하는 마커를 역파싱한다.
#      ps-docparser 내부 포맷이므로 변경될 일이 없다.
_SECTION_MARKER = re.compile(
    r'<!-- SECTION: (\S+) \| (.+?) \| 부문:(.+?) \| 장:(.+?) -->'
)
_PAGE_MARKER = re.compile(
    r'<!-- PAGE (\d+) \| (.+?) -->'
)
_CONTEXT_MARKER = re.compile(
    r'<!-- CONTEXT: (.+?) -->'
)
_CONTEXT_SECTION_MARKER = re.compile(
    r'<!-- CONTEXT: (\S+) \| (.+?) \| 부문:(.+?) \| 장:(.+?) -->'
)
```

**이식 함수 (7개):**

```python
def load_toc(toc_path: Path) -> dict:
    """목차 JSON 로드 → section_map 반환.
    원본: parser.py L14~19. 변경 없음."""

def build_reverse_map(toc: dict) -> dict:
    """(section_id, department) → toc_key 역매핑 생성.
    원본: parser.py L21~27. 변경 없음."""

def parse_section_markers(text: str) -> list[dict]:
    """텍스트에서 SECTION 마커를 모두 추출.
    원본: parser.py L29~40.
    변경점: PATTERNS["section_marker"] → _SECTION_MARKER 모듈 상수 참조."""

def parse_page_markers(text: str) -> list[dict]:
    """텍스트에서 PAGE 마커를 모두 추출.
    원본: parser.py L42~49.
    변경점: PATTERNS["page_marker"] → _PAGE_MARKER 모듈 상수 참조."""

def get_page_for_position(page_markers: list[dict], pos: int, file_start_page: int) -> int:
    """텍스트 내 위치 → 해당 페이지 번호 결정.
    원본: parser.py L52~59. 변경 없음."""

def redistribute_text_to_sections(markers: list[dict], combined_text: str) -> dict:
    """연속된 섹션 마커 그룹에 대해 텍스트를 재배분.
    원본: parser.py L61~107. 변경 없음."""

def split_sections(text: str, source_file: str, toc: dict, reverse_map: dict) -> list[dict]:
    """메인 섹션 분할 함수.

    마크다운 텍스트를 SECTION/PAGE/CONTEXT 마커 기준으로 분할하여
    섹션별 raw_text, 메타데이터(페이지, 부문, 장) 딕셔너리 리스트를 반환.

    Returns:
        list[dict]: 각 dict 구조:
        {
            "section_id": str,
            "title": str,
            "department": str,
            "chapter": str,
            "page": int,
            "raw_text": str,          # 마커 제거된 본문 (HTML <table> 포함)
            "source_file": str,
            "toc_title": str,
            "toc_section": str,
            "has_content": bool,       # len(raw_text) > 10
        }

    원본: parser.py L109~168.
    변경점:
    - PATTERNS["section_marker"] → _SECTION_MARKER 모듈 상수
    - PATTERNS["page_marker"] → _PAGE_MARKER 모듈 상수
    - CONTEXT 마커 제거도 모듈 상수 사용"""
```

---

### 4. `parsers/text_cleaner.py` — 본문 정제기

```python
"""
섹션 본문 정제 및 메타데이터 추출.

Why: 섹션의 raw_text에서 테이블을 제거한 뒤 남은 텍스트에서
     주석([주] 블록), 할증 조건, 교차참조, 보완연도, 단위 기준 등
     구조화된 메타데이터를 추출한다.
     도메인 전용 패턴은 파라미터로 주입하여 범용성을 유지한다.

원본: standalone_parser/parser.py L320~417
Dependencies: 표준 라이브러리만 (re)
"""
import re
```

**이식 함수 (6개):**

```python
def extract_notes(text: str, patterns: dict = None) -> tuple[list[str], str]:
    """[주] 블록에서 주석 항목을 추출하고, 해당 블록을 제거한 텍스트를 반환.

    Args:
        text: 원본 텍스트
        patterns: 도메인 패턴 딕셔너리.
                  None이면 주석 추출 스킵 → ([], text) 반환.
                  pumsem 프리셋 시 PARSE_PATTERNS 주입.
                  필요 키: "note_block_start"

    원본: parser.py L324~335.
    변경점: PATTERNS 전역 참조 → patterns 파라미터."""


def extract_conditions(text: str, patterns: dict = None) -> list[dict]:
    """할증/가산/감산 조건 추출.

    Args:
        patterns: 필요 키: "surcharge". None이면 [] 반환.

    Returns:
        [{"type": str, "condition": str, "rate": str}, ...]

    원본: parser.py L337~348.
    변경점: PATTERNS["surcharge"] → patterns["surcharge"]."""


def extract_cross_references(text: str, patterns: dict = None) -> list[dict]:
    """교차참조 추출.

    Args:
        patterns: 필요 키: "cross_ref". None이면 [] 반환.

    Returns:
        [{"target_section_id": str, "target_chapter": str, "context": str}, ...]

    원본: parser.py L350~359.
    변경점: PATTERNS["cross_ref"] → patterns["cross_ref"]."""


def clean_text(text: str, patterns: dict = None) -> str:
    """HTML 주석 제거 + 연속 줄바꿈 정리.

    Args:
        patterns: 필요 키: "chapter_title" (있으면 장 제목 행 제거).
                  None이면 HTML 주석 제거 + 줄바꿈 정리만 수행 (범용).

    원본: parser.py L361~365.
    변경점:
    - HTML 주석 제거, 줄바꿈 정리는 항상 수행 (범용)
    - chapter_title 패턴 삭제는 patterns 제공 시에만 (도메인)"""


def remove_duplicate_notes(notes: list[str], table_notes: list[str]) -> list[str]:
    """텍스트 주석과 테이블 내 주석의 중복 제거.
    원본: parser.py L367~379. 변경 없음."""


def process_section_text(section: dict, patterns: dict = None) -> dict:
    """메인 정제 함수 — 섹션 텍스트 최종 처리.

    3단계 파이프라인의 마지막 처리기로서, 테이블 파싱이 완료된 섹션 dict를
    받아 본문 정제 + 메타데이터 추출을 수행한다.

    Args:
        section: process_section_tables()가 반환한 섹션 dict
        patterns: 도메인 패턴 딕셔너리 (None=범용)

    Returns:
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

    원본: parser.py L381~417.
    변경점: PATTERNS 전역 → patterns 파라미터."""
```

**`extract_notes()` 범용/프리셋 분기 상세:**

```python
def extract_notes(text: str, patterns: dict = None) -> tuple[list[str], str]:
    """
    원본: parser.py L324~335

    변경점:
    - patterns=None → 주석 추출 스킵 (범용 모드)
    - patterns 제공 시 → 기존 로직 실행 (도메인 모드)
    """
    if not patterns or "note_block_start" not in patterns:
        return [], text

    notes, remaining = [], text
    note_block_pattern = re.compile(
        r'\[주\]\s*\n(.*?)(?=\n\n(?!\s*[①②③④⑤⑥⑦⑧⑨⑩])|\n(?=\d+-\d+)|\Z)',
        re.DOTALL,
    )
    for m in note_block_pattern.finditer(text):
        items = re.split(r'(?=[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮])', m.group(1).strip())
        for item in items:
            item = re.sub(r'^[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮]\s*', '', item.strip()).strip()
            if item:
                notes.append(item)
        remaining = note_block_pattern.sub('', remaining)
        remaining = re.sub(r'^\[주\]\s*$', '', remaining, flags=re.MULTILINE)
    return notes, remaining.strip()
```

**`clean_text()` 범용/프리셋 분기 상세:**

```python
def clean_text(text: str, patterns: dict = None) -> str:
    """
    원본: parser.py L361~365

    변경점:
    - HTML 주석 제거 + 줄바꿈 정리 → 항상 수행 (범용)
    - chapter_title 패턴 삭제 → patterns 있을 때만 (도메인)
    """
    # ── 범용: 항상 수행 ──
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)

    # ── 도메인: 장 제목 행 제거 (품셈 프리셋 시) ──
    if patterns and "chapter_title" in patterns:
        text = patterns["chapter_title"].sub('', text)

    # ── 범용: 항상 수행 ──
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()
```

**`process_section_text()` 범용/프리셋 분기 상세:**

```python
def process_section_text(section: dict, patterns: dict = None) -> dict:
    """
    원본: parser.py L381~417

    변경점:
    - patterns=None 시 도메인 메타데이터 추출 스킵
      (revision_year="", unit_basis="", conditions=[], cross_references=[])
    - notes 추출도 patterns 의존
    - clean_text()는 항상 수행 (HTML 주석/줄바꿈 정리는 범용)
    """
    text = section.get("text_without_tables", section.get("raw_text", ""))

    # ── 도메인 전용 메타데이터 (patterns 제공 시에만) ──
    revision_year = ""
    unit_basis = ""
    if patterns:
        m_revision = patterns.get("revision", re.compile(r'$^')).search(text)
        if m_revision:
            year = m_revision.group(1)
            revision_year = (
                f"20{year}" if len(year) == 2 and int(year) < 50
                else (f"19{year}" if len(year) == 2 else year)
            )
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

    # ── 텍스트 정제 (항상 수행, chapter_title만 도메인) ──
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
```

---

### 5. `parsers/document_parser.py` — 통합 오케스트레이터

```python
"""
마크다운 → 구조화 JSON 통합 파이프라인.

Why: section_splitter → table_parser → text_cleaner를 순차 실행하는
     단일 진입점. main.py에서 이 모듈만 import하면 된다.

원본: standalone_parser/parser.py L423~453 (parse_markdown_document)
Dependencies: parsers.section_splitter, parsers.table_parser, parsers.text_cleaner
"""
from pathlib import Path

from parsers.section_splitter import load_toc, build_reverse_map, split_sections
from parsers.table_parser import process_section_tables
from parsers.text_cleaner import process_section_text
```

**핵심 함수:**

```python
def parse_markdown(
    md_input: str,
    toc_path: str = None,
    type_keywords: dict = None,
    patterns: dict = None,
) -> list[dict]:
    """
    마크다운 텍스트를 구조화된 JSON(섹션 리스트)으로 변환한다.

    Why: Phase 1의 추출 결과(마크다운) 또는 외부 마크다운 파일을
         한 번의 호출로 정형 데이터로 변환하는 올인원 함수.
         3단계(분할→테이블→정제) 파이프라인을 내부에서 순차 실행.

    Args:
        md_input: 마크다운 파일 경로 또는 마크다운 텍스트 문자열
        toc_path: 목차 JSON 파일 경로 (없으면 전체를 단일 섹션으로 처리)
        type_keywords: 테이블 유형 분류 키워드 (None=범용)
        patterns: 텍스트 정제 도메인 패턴 (None=범용)

    Returns:
        list[dict]: 섹션별 구조체 리스트 (process_section_text 출력 형식)

    사용 예:
        # 범용 모드 (프리셋 없음)
        result = parse_markdown("output/extracted.md")

        # 품셈 모드
        from presets.pumsem import get_parse_patterns, get_table_type_keywords
        result = parse_markdown(
            "output/pumsem_doc.md",
            toc_path="toc.json",
            type_keywords=get_table_type_keywords(),
            patterns=get_parse_patterns(),
        )
    """
    # ── 입력 판별: 파일 경로 vs 텍스트 문자열 ──
    md_path = Path(md_input)
    if md_path.exists() and md_path.is_file():
        text = md_path.read_text(encoding="utf-8")
        filename = md_path.name
    else:
        text = md_input
        filename = "inline_text"

    # ── TOC 로딩 ──
    toc = {}
    if toc_path and Path(toc_path).exists():
        toc = load_toc(Path(toc_path))
    reverse_map = build_reverse_map(toc)

    # ── Step 1: 섹션 분할 ──
    raw_sections = split_sections(text, filename, toc, reverse_map)

    # ── 마커 없는 경우 (범용 문서, TOC 미제공) → 전체를 단일 섹션으로 처리 ──
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

    # ── Step 2 + 3: 테이블 파싱 → 본문 정제 ──
    parsed_sections = []
    for section in raw_sections:
        if not section.get("has_content", False):
            continue

        section_with_tables = process_section_tables(section, type_keywords)
        final_section = process_section_text(section_with_tables, patterns)
        parsed_sections.append(final_section)

    return parsed_sections
```

---

### 6. `presets/pumsem.py` — 확장 (PARSE_PATTERNS + TABLE_TYPE_KEYWORDS 추가)

```python
"""
presets/pumsem.py — 건설 품셈 전용 프리셋 설정

[기존 Phase 1 코드 유지]
+ Phase 2 추가: PARSE_PATTERNS, TABLE_TYPE_KEYWORDS, 접근 함수
"""
import re

# ── [기존] Phase 1: 부문명 패턴 ──
DIVISION_NAMES = (
    "공통부문|토목부문|건축부문|기계설비부문|"
    "전기부문|통신부문|조경부문|소방부문|"
    "기계부문|설비부문|전기설비부문"
)

def get_division_names() -> str:
    """품셈 프리셋의 부문명 패턴을 반환한다."""
    return DIVISION_NAMES


# ── [신규] Phase 2: 파서 도메인 패턴 ──
# Why: standalone_parser/config.py의 도메인 전용 패턴을 여기로 이동.
#      parsers/text_cleaner.py에 patterns 파라미터로 주입된다.
PARSE_PATTERNS = {
    # 주석 블록
    "note_block_start": re.compile(r'^\[주\]\s*$', re.MULTILINE),
    "note_item": re.compile(
        r'([①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮])\s*(.*?)(?=(?:[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮])|\Z)',
        re.DOTALL,
    ),
    # 할증/가산/감산 조건
    "surcharge": re.compile(
        r'(.+?(?:경우|때|시))\s*(?:본\s*)?(?:품|시공량).*?(\d+)%.*?(가산|감산|감|증|할증)'
    ),
    # 교차참조
    "cross_ref": re.compile(
        r'(?:제(\d+)장\s+)?(\d+-\d+(?:-\d+)?)\s*(?:항?\s*)?(?:참조|준용|적용|따른다)'
    ),
    # 보완연도
    "revision": re.compile(r"\('?(\d{2,4})(?:,\s*'?(\d{2,4}))*년\s*보완\)"),
    # 단위 기준
    "unit_basis": re.compile(r'\(([^)]*당)\)'),
    # 장 제목 (정제 시 제거 대상)
    "chapter_title": re.compile(r'^(제\d+장\s+.+)$', re.MULTILINE),
    # 절/항 제목
    "section_title": re.compile(r'^(\d+-\d+(?:-\d+)?)\s+(.+?)$', re.MULTILINE),
}


# ── [신규] Phase 2: 테이블 유형 분류 키워드 ──
# Why: classify_table()에 주입하여 품셈 테이블 유형을 판별.
#
# [리뷰 반영] A_품셈_행키워드 추가:
#   원본 parser.py에서 _LABOR_ROW_KEYWORDS로 classify_table() 내부에 하드코딩되어 있었다.
#   노동자 직종명은 건설 품셈 도메인 특정 용어이므로 범용 파서에 존재하면 안 된다.
#   → presets/pumsem.py로 완전 분리하여 파라미터 주입 방식으로 전달.
TABLE_TYPE_KEYWORDS = {
    "A_품셈": ["수량", "단위", "인", "대", "수 량", "단 위"],
    "A_품셈_행키워드": [
        "인부", "철공", "용접공", "배관공", "기사", "기능공", "기능사",
        "조공", "내장공", "도장공", "미장공", "목공", "방수공",
        "보통인부", "특별인부", "잡역부",
    ],
    "B_규모기준": ["억", "m²", "규모", "직접노무비"],
    "C_구분설명": ["구분", "내용", "구 분", "내 용"],
}


def get_parse_patterns() -> dict:
    """품셈 프리셋의 파서 도메인 패턴을 반환한다."""
    return PARSE_PATTERNS


def get_table_type_keywords() -> dict:
    """품셈 프리셋의 테이블 유형 분류 키워드를 반환한다."""
    return TABLE_TYPE_KEYWORDS
```

---

### 7. `main.py` — 확장 (파이프라인 연결)

**변경 범위:**

| 변경 항목 | 내용 |
|---|---|
| CLI 인수 추가 | `--output` (md/json, 기본 md) |
| 입력 확장 | `.md` 파일 직접 입력 지원 (PDF가 아닌 마크다운 파싱) |
| 파이프라인 연결 | `--output json` 시 extract → parse 자동 체이닝 |
| 프리셋 로딩 확장 | `presets/pumsem.py`에서 `get_parse_patterns()`, `get_table_type_keywords()` 로딩 |

**CLI 인수 (변경 후):**

```
python main.py <파일> [옵션]

필수:
  <파일>                  PDF 파일 (.pdf) 또는 마크다운 파일 (.md)

옵션:
  --engine <이름>         AI 엔진 (gemini|local, 기본: .env의 DEFAULT_ENGINE)
  --text-only, -t        텍스트 전용 모드 (AI 없음, 무료)
  --toc <파일>            목차 파일 (.json 또는 .txt)
  --pages <지정>          페이지 범위 (PDF 입력 시에만 적용)
  --output <형식>         출력 형식 (md|json, 기본: md)         ← [신규]
  --output-dir <경로>     출력 폴더 (기본: ./output/)
  --preset <이름>         도메인 프리셋 (pumsem, 기본: 없음=범용)
```

**동작 흐름 (변경 후):**

```
[입력이 .pdf인 경우]
  --output md   → PDF 추출 → MD 파일 저장 (기존 동작)
  --output json → PDF 추출 → MD → 파서 실행 → JSON 파일 저장

[입력이 .md인 경우]
  --output md   → 에러 ("이미 마크다운입니다")
  --output json → 파서 실행 → JSON 파일 저장
```

**main.py 변경 코드 핵심 부분:**

```python
# argparse에 추가
parser.add_argument(
    "--output",
    default="md",
    choices=["md", "json"],
    help="출력 형식 (md: 마크다운, json: 구조화 JSON, 기본: md)",
)

# 프리셋 로딩 확장 (기존 division_names에 추가)
parse_patterns = None
type_keywords = None
if preset == "pumsem":
    from presets.pumsem import get_division_names, get_parse_patterns, get_table_type_keywords
    division_names = get_division_names()
    parse_patterns = get_parse_patterns()
    type_keywords = get_table_type_keywords()
    print(f"📋 프리셋 활성화: {preset}")

# 입력 파일 판별
input_path = args.pdf  # 인수 이름은 호환성 유지
is_md_input = input_path.lower().endswith(".md")

if is_md_input:
    # ── .md 입력: 파서만 실행 ──
    if args.output == "md":
        print("❌ 입력이 이미 마크다운 파일입니다. --output json 을 사용하세요.")
        sys.exit(1)

    from parsers.document_parser import parse_markdown
    result = parse_markdown(
        input_path,
        toc_path=args.toc,
        type_keywords=type_keywords,
        patterns=parse_patterns,
    )

else:
    # ── .pdf 입력: 추출 실행 ──
    # ... (기존 Phase 1 추출 로직 그대로) ...
    # md 변수에 추출 결과 저장

    if args.output == "json":
        # ── extract → parse 자동 체이닝 ──
        from parsers.document_parser import parse_markdown
        result = parse_markdown(
            md,                          # 텍스트 문자열 직접 전달
            toc_path=args.toc,
            type_keywords=type_keywords,
            patterns=parse_patterns,
        )
    else:
        # ── MD만 저장 (기존 동작) ──
        result = None

# ── 출력 저장 ──
if args.output == "json" and result is not None:
    json_output_path = output_path.with_suffix(".json")
    with open(json_output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"📄 JSON 출력: {json_output_path}")
    print(f"📊 섹션 수: {len(result)}개")
elif md:
    # 기존 MD 저장 로직
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"📄 MD 출력: {output_path}")
```

**argparse "pdf" 인수 호환성 처리:**

```python
# 기존: parser.add_argument("pdf", help="처리할 PDF 파일 경로")
# 변경: .md도 받을 수 있도록 help 텍스트만 수정 (인수 이름은 유지)
parser.add_argument("pdf", metavar="파일", help="처리할 PDF 또는 마크다운(.md) 파일 경로")
```

> **Why 인수 이름을 "pdf"에서 바꾸지 않는가:** argparse의 위치 인수는 `args.pdf`로 접근된다. 이름을 바꾸면 기존 main.py의 `args.pdf` 참조를 모두 수정해야 한다. Phase 2에서는 `metavar`만 변경하여 사용자에게 보이는 텍스트만 바꾸고, 내부 참조는 유지한다. Phase 4(GUI 리팩터)에서 일괄 정리.

---

### 8. `requirements.txt` — 의존성 추가

```
# ── Phase 1 (기존) ──
pdfplumber
google-generativeai
pdf2image
Pillow
python-dotenv

# ── Phase 2 (신규) ──
beautifulsoup4        # HTML 테이블 파싱 (필수)
lxml                  # 고속 HTML 파서 (선택 — 미설치 시 html.parser 자동 폴백)
```

> **[리뷰 반영]** `lxml`은 선택 의존성으로 격하. `_make_soup()` 폴백 구조에 의해 미설치 시에도 정상 동작한다.

---

## 잠재 위험 요소 검토

### 위험 1: `from config import PATTERNS, TABLE_TYPE_KEYWORDS` 참조 변경

**문제:** 원본 `parser.py`는 `from config import PATTERNS, TABLE_TYPE_KEYWORDS`로 같은 폴더의 `config.py`를 bare import한다. ps-docparser에서는 이 경로가 존재하지 않는다.

**해결:**
| 원본 참조 | 신규 위치 | 전달 방식 |
|---|---|---|
| `PATTERNS["section_marker"]` 등 4종 | `parsers/section_splitter.py` 모듈 상수 | 직접 참조 (내부) |
| `PATTERNS["surcharge"]` 등 8종 | `presets/pumsem.py` → `PARSE_PATTERNS` | 함수 파라미터 주입 |
| `TABLE_TYPE_KEYWORDS` | `presets/pumsem.py` → `TABLE_TYPE_KEYWORDS` | 함수 파라미터 주입 |

**검증:** `from config import` 구문이 새 코드에 단 한 줄도 없어야 한다.

---

### 위험 2: `from html_utils import ...` 참조 변경

**문제:** 원본 `parser.py`는 `from html_utils import expand_table, extract_tables_from_text, remove_tables_from_text`로 같은 폴더의 `html_utils.py`를 import한다. ps-docparser에서는 모든 함수가 `parsers/table_parser.py` 한 파일에 합쳐진다.

**해결:**
- `section_splitter.py`, `text_cleaner.py`에서 table 관련 함수가 필요하면: `from parsers.table_parser import extract_tables_from_text, remove_tables_from_text`
- `document_parser.py`에서: `from parsers.table_parser import process_section_tables`
- 패키지 내부이므로 상대 import 사용: `from .table_parser import ...`

---

### 위험 3: 마커 없는 문서 처리 (범용 모드)

**문제:** `split_sections()`은 SECTION 마커를 기준으로 분할한다. TOC 없이 추출된 범용 문서(예: 견적서)에는 SECTION 마커가 없어 빈 리스트를 반환한다. → 파이프라인 결과 0건.

**해결:** `document_parser.py`의 `parse_markdown()`에서 폴백 처리:

```python
raw_sections = split_sections(text, filename, toc, reverse_map)

if not raw_sections:
    # 마커 없는 문서 → 전체를 단일 섹션으로 처리
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
```

**검증 시나리오:**

| 시나리오 | SECTION 마커 | 동작 | 결과 |
|---|---|---|---|
| 품셈 문서 + TOC | 있음 | `split_sections()` 정상 분할 | 섹션별 JSON |
| 견적서 (마커 없음) | 없음 | 폴백 → 단일 섹션 | 문서 전체가 1개 섹션으로 파싱 |
| 빈 문서 | 없음 | `has_content=False` | 결과 0건 (정상) |

---

### 위험 4: BeautifulSoup 파서 백엔드 "lxml" Windows 호환성 ← [리뷰 반영]

**문제:** 원본 `parse_html_table()`에서 `BeautifulSoup(html, "lxml")` 사용. `lxml`은 C 라이브러리(libxml2/libxslt) 컴파일이 필요하며, Windows에서 빌드 툴(Visual C++) 없이는 설치 실패가 빈번하다.

**해결:** lxml 우선 시도 → 실패 시 내장 html.parser 폴백:

```python
# parsers/table_parser.py 상단
from bs4 import BeautifulSoup, Tag

# [리뷰 반영] lxml → html.parser 폴백 구조
# Why: lxml은 속도와 파싱 관용도(malformed HTML 처리)가 우수하지만,
#      Windows에서 C 컴파일러 없이 설치 실패가 빈번하다.
#      html.parser는 Python 내장이므로 추가 설치 불필요.
#      성능 차이는 우리 사용 규모(수십 테이블)에서 무시 가능.
def _make_soup(html: str) -> BeautifulSoup:
    """lxml 우선, 실패 시 html.parser 폴백으로 BeautifulSoup 생성."""
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")
```

**적용 위치:** `parse_html_table()`, `parse_single_table()` 등 `BeautifulSoup(html, "lxml")` 직접 호출부를 모두 `_make_soup(html)` 호출로 교체.

```python
# 변경 전 (원본)
def parse_html_table(html: str) -> list[list[str]]:
    soup = BeautifulSoup(html, "lxml")       # ← lxml 하드코딩
    ...

# 변경 후
def parse_html_table(html: str) -> list[list[str]]:
    soup = _make_soup(html)                   # ← 폴백 구조
    ...
```

**requirements.txt 변경:**

```
beautifulsoup4        # HTML 테이블 파싱 (필수)
lxml                  # 고속 HTML 파서 (선택 — 미설치 시 html.parser 폴백)
```

**검증 시나리오:**

| 시나리오 | lxml 상태 | 동작 | 결과 |
|---|---|---|---|
| `pip install lxml` 성공 | 설치됨 | lxml 사용 | 고속 파싱 |
| `pip install lxml` 실패 (Windows C 컴파일러 없음) | 미설치 | html.parser 폴백 | 정상 동작 (약간 느림) |
| beautifulsoup4 미설치 | - | ImportError | 명확한 에러 메시지 |

---

### 위험 5: `parse_single_table()` 내부 `expand_table()` 호출 경로

**문제:** 원본에서 `parse_single_table()`은 `html_utils.expand_table()`을 호출하는데, 두 함수가 같은 파일(`parser.py`)에 없다. 이식 후에는 `parsers/table_parser.py`에 합쳐지므로 같은 파일 내 함수 호출이 된다.

**해결:** import 불필요 — 같은 모듈 내부 호출. 오히려 기존보다 단순해진다.

**검증:** `parse_single_table()` 내부에서 `expand_table()` 직접 호출 확인.

---

### 위험 6: `--output json` + `--text-only` 조합

**문제:** `--text-only` 모드는 AI 없이 텍스트만 추출한다. `<table>` HTML이 없어 테이블 파싱 결과가 0건이다. 사용자가 `--text-only --output json`을 조합하면 테이블 없는 JSON이 나온다.

**해결:** 에러가 아닌 정상 동작으로 처리. `<table>`이 없으면 `"tables": []`로 반환된다. 단, 경고 메시지 출력:

```python
if args.text_only and args.output == "json":
    print("⚠️ 텍스트 전용 모드에서는 테이블이 추출되지 않습니다. 테이블 데이터가 필요하면 --text-only를 제거하세요.")
```

---

### 위험 7: `try_numeric()` 숫자 캐스팅에 의한 포맷 파괴 ← [리뷰 반영]

**문제:** 원본 `try_numeric()`은 셀 값을 `int()` 또는 `float()`로 적극 변환한다.

```python
# 원본 (parser.py L247~260)
def try_numeric(val: str):
    val_stripped = val.strip().replace(",", "")
    try:
        if "." in val_stripped:
            return float(val_stripped)
        return int(val_stripped)
    except ValueError:
        return val
```

이 로직은 다음과 같은 파괴적 문제를 야기한다:

| 입력 | 원본 출력 | 문제 |
|---|---|---|
| `"0015"` | `15` (int) | 식별번호/코드의 선행 0이 소실 |
| `"PSQ-0406"` | `"PSQ-0406"` (str) | 안전 (변환 실패 → 원본 유지) |
| `"15,000,000"` | `15000000` (int) | 콤마 제거 후 정수화 — JSON에서 원본 포맷 복원 불가 |
| `"3.140"` | `"3.140"` (str) | 후행 0 보존 시도하나 불일치 가능 |
| `"2026-0406-59"` | `"2026-0406-59"` (str) | 안전 (변환 실패) |

**핵심 위험:** 범용 파서 단계에서 숫자 캐스팅을 하면 원본 포맷이 비가역적으로 파괴된다.
특히 견적서/BOM의 관리번호, 코드, 선행0 포함 식별자가 정수로 변환되면 데이터 무결성이 손상된다.

**해결:** 범용 파서에서는 **문자열 정제만** 수행하고, 숫자 변환은 하지 않는다.

```python
def try_numeric(val: str) -> str:
    """
    셀 값 정제 — 공백 정리만 수행, 숫자 캐스팅은 하지 않는다.

    Why: 범용 파서 단계에서 int/float 변환을 하면 선행 0("0015"→15),
         콤마 포맷("15,000,000"→15000000) 등 원본 데이터가 비가역적으로 파괴된다.
         숫자 변환은 DB 적재(Phase 3) 또는 도메인 프리셋에서 명시적으로 수행해야 한다.

    원본: parser.py L247~260
    변경점: int()/float() 캐스팅 완전 제거 → strip()만 수행
    """
    if not isinstance(val, str):
        return val
    return val.strip()
```

**기존 호환성 영향:**
- `standalone_parser`와의 출력 비교 시 JSON 값 타입이 달라진다 (int → str).
- 이는 **의도된 변경**이다. 범용 파서의 출력은 항상 문자열이 안전하다.
- 품셈 프리셋에서 숫자 변환이 필요하면 `presets/pumsem.py`에 `convert_numeric_cells()` 후처리 함수를 추가하여 `process_section_text()` 이후 단계에서 명시적으로 적용한다 (Phase 3 이후 확장 가능).

---

### 위험 8: `_LABOR_ROW_KEYWORDS` 도메인 침범 ← [리뷰 반영]

**문제:** 원본 `classify_table()` 내부에 노동자 직종 키워드 16종("인부", "용접공", "배관공" 등)이 하드코딩되어 있었다. 이는 건설 품셈 도메인 전용 용어이며, 일반 회사 문서(견적서, 계약서 등)를 파싱할 때 무의미한 키워드 스캔이 실행되어 범용 파서 설계 원칙을 위반한다.

**해결:** `_LABOR_ROW_KEYWORDS` 리스트를 `presets/pumsem.py`의 `TABLE_TYPE_KEYWORDS["A_품셈_행키워드"]`로 완전 이동. `classify_table()`은 `type_keywords.get("A_품셈_행키워드", [])`로 접근하며, `type_keywords=None`(범용 모드)이면 이 분기 자체가 실행되지 않는다.

**검증:**
- `classify_table(headers, rows, type_keywords=None)` → `"general"` 반환, 키워드 스캔 0회
- `classify_table(headers, rows, type_keywords=TABLE_TYPE_KEYWORDS)` → 기존과 동일 분류

---

## 구현 순서 (의존성 기반)

```
1단계: 의존성 없는 파서 모듈 (병렬 작업 가능)
  ├── parsers/__init__.py
  ├── parsers/table_parser.py         (html_utils.py 전체 + parser.py L170~318)
  ├── parsers/section_splitter.py     (parser.py L10~168 + config.py 마커 패턴)
  ├── parsers/text_cleaner.py         (parser.py L320~417)
  └── requirements.txt 업데이트       (beautifulsoup4, lxml 추가)

2단계: 프리셋 확장
  └── presets/pumsem.py               (PARSE_PATTERNS + TABLE_TYPE_KEYWORDS 추가)

3단계: 통합 오케스트레이터 (1+2단계 의존)
  └── parsers/document_parser.py      (parse_markdown 통합 함수)

4단계: CLI 연결 (3단계 의존)
  └── main.py                         (--output json, .md 입력 지원)
```

---

## 검증 계획

### 단위 테스트

| 검증 항목 | 방법 | 기대 결과 |
|---|---|---|
| table_parser 단독 | Phase 1 출력물(견적서 .md)의 `<table>` 추출 → `parse_html_table()` | 2D 배열 정상 반환, rowspan/colspan 전개 |
| table_parser headers | 2단 헤더(재료비/노무비/경비/합계) → `detect_header_rows()` + `build_composite_headers()` | `n_header_rows=2`, 헤더 "재료비_단가" 등 |
| section_splitter | 기존 `standalone_parser`에 입력했던 마크다운(SECTION 마커 포함) → `split_sections()` | 기존과 동일한 섹션 수/ID |
| text_cleaner (범용) | 일반 텍스트 → `process_section_text(section, patterns=None)` | notes=[], conditions=[], clean_text 정상 |
| text_cleaner (품셈) | 품셈 텍스트 + `patterns=PARSE_PATTERNS` | 기존 standalone_parser와 동일 출력 |

### 통합 테스트

| 검증 항목 | 방법 | 기대 결과 |
|---|---|---|
| 기존 호환성 | `standalone_parser`에 기존 마크다운 입력한 결과와 `parsers/document_parser.py`에 동일 입력한 결과를 JSON diff | **구조 동일** |
| PDF→JSON 체이닝 | `python main.py "견적서.pdf" --engine gemini --output json` | MD 추출 → JSON 파싱까지 원스톱 완료 |
| MD→JSON 직접 | `python main.py "output/기존출력.md" --output json` | JSON 정상 출력 |
| 범용 모드 | `python main.py "견적서.pdf" --engine gemini --output json` (프리셋 없음) | 단일 섹션 JSON, 테이블 정상 파싱, 도메인 메타=빈값 |
| 품셈 모드 | `python main.py "품셈.pdf" --preset pumsem --toc "목차.json" --output json` | 섹션별 JSON, 테이블 유형 분류, 주석/조건/교차참조 추출 |
| text-only + json | `python main.py "문서.pdf" --text-only --output json` | 경고 메시지 출력, tables=[] JSON |
| 이식성 | 프로젝트 폴더 다른 경로로 복사 후 동일 테스트 | 정상 동작 |

### 회귀 테스트 (Phase 1 기능 보존)

| 검증 항목 | 방법 | 기대 결과 |
|---|---|---|
| 기존 MD 추출 | `python main.py "견적서.pdf" --engine gemini` (--output 생략) | Phase 1과 동일한 MD 출력 |
| text-only | `python main.py "견적서.pdf" --text-only` | Phase 1과 동일 |
| local 엔진 | `python main.py "견적서.pdf" --engine local` | Phase 1과 동일 |

---

> 작성일: 2026-04-13 | Phase 2 of 4 | 작성: Antigravity AI
