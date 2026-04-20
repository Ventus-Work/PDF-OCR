# Phase 2 구현 결과 보고서 (마크다운 → 구조화 JSON 파이프라인)

## 📌 개요
본 문서는 `Phase2_상세_구현_기술서.md`에 명세된 계획을 바탕으로 완료된 범용 문서 파서(`ps-docparser`)의 2단계 구현 결과를 요약·정리한 보고서입니다.

Phase 1이 **PDF → Markdown** 변환 파이프라인이었다면, Phase 2는 그 출력물인 Markdown을 입력으로 받아 **섹션 분할 → HTML 테이블 파싱 → 본문 정제 → 구조화 JSON 출력**까지 수행하는 두 번째 파이프라인입니다.

`standalone_parser/parser.py` 472줄 및 `standalone_parser/html_utils.py` 121줄에 흩어져 있던 파싱 로직이 SRP(단일 책임 원칙)에 따라 4개의 독립 모듈로 재설계되었으며, 도메인 전용 패턴(건설 품셈 키워드 8종)은 `presets/pumsem.py`로 완전 분리되어 범용성을 유지합니다.

---

## 🛠 아키텍처 구현 결과 요약

### 1. 신규 패키지 및 모듈 (5개 신규 생성, 2개 확장)

#### `parsers/` 패키지 (신규 생성)

*   **`parsers/__init__.py`**: 패키지 선언. Phase 2 파이프라인 역할 명세 주석 포함.

*   **`parsers/section_splitter.py`** (원본: `standalone_parser/parser.py` L10~168):
    *   `<!-- SECTION -->`, `<!-- PAGE -->`, `<!-- CONTEXT -->` 마커 역파싱.
    *   마커 패턴 4종을 모듈 내부 상수(`_SECTION_MARKER`, `_PAGE_MARKER` 등)로 이동. Phase 1의 `config.py` 전역 참조 제거.
    *   인접 마커 그룹핑 로직 및 `redistribute_text_to_sections()` 보존.
    *   SECTION 마커 없는 문서(견적서 등) → 빈 리스트 반환(폴백은 `document_parser.py`가 처리).

*   **`parsers/table_parser.py`** (원본: `html_utils.py` 전체 + `parser.py` L170~318):
    *   `expand_table()`: rowspan/colspan 셀 확장.
    *   `extract_cell_text()` / `clean_cell_text()`: 셀 텍스트 추출 및 HTML 태그 제거.
    *   `parse_html_table()` / `extract_tables_from_text()` / `remove_tables_from_text()`: HTML 테이블 파싱 및 본문 분리.
    *   `classify_table()`: 헤더·행 키워드 기반 테이블 유형 분류. `type_keywords=None` 시 `"general"` 반환(범용 모드).
    *   `detect_header_rows()` / `build_composite_headers()`: 다단 헤더(재료비_단가 등 복합 헤더) 자동 구성.
    *   `parse_single_table()` / `process_section_tables()`: 섹션 단위 테이블 일괄 처리.
    *   **[리뷰 반영 1]** `_make_soup()`: lxml 우선, 실패 시 `html.parser` 폴백.

*   **`parsers/text_cleaner.py`** (원본: `parser.py` L320~417):
    *   `extract_notes()` / `extract_conditions()` / `extract_cross_references()`: 도메인 메타데이터 추출. 모두 `patterns=None` 시 빈값 반환(범용 모드 단락).
    *   `clean_text()`: HTML 주석 제거 + 연속 줄바꿈 정리(항상 실행). 장 제목 행 제거는 `patterns` 제공 시에만(도메인).
    *   `remove_duplicate_notes()`: 테이블 내 주석과 본문 주석의 포함 관계 기반 중복 제거.
    *   `process_section_text()`: 위 함수들을 통합하는 최종 정제기.

*   **`parsers/document_parser.py`** (통합 진입점, 신규):
    *   `parse_markdown(md_input, toc_path, type_keywords, patterns)` 단일 함수로 3단계 파이프라인 조립.
    *   입력: 파일 경로(str) 또는 텍스트 문자열 모두 수용 (`Path.exists()` 분기).
    *   SECTION 마커 없는 문서 → 전체를 단일 `"doc"` 섹션으로 래핑하는 폴백 내장.

#### 기존 모듈 확장

*   **`presets/pumsem.py`** (Phase 2 항목 추가):
    *   `PARSE_PATTERNS`: 파서 도메인 패턴 8종 (`note_block_start`, `note_item`, `surcharge`, `cross_ref`, `revision`, `unit_basis`, `chapter_title`, `section_title`). `get_parse_patterns()` 함수로 접근.
    *   `TABLE_TYPE_KEYWORDS`: 테이블 유형 분류 키워드. **[리뷰 반영 1]** `"A_품셈_행키워드"` 키 추가(노동자 직종명 16종 — `classify_table()` 내부 하드코딩에서 완전 분리). `get_table_type_keywords()` 함수로 접근.

*   **`main.py`** (Phase 2 파이프라인 연결):
    *   위치 인수 `pdf` → `input` (`.pdf` 및 `.md` 모두 수용).
    *   `--output md|json` 인수 추가(기본값: `md`). Phase 1 동작 완전 하위 호환.
    *   `.md` 직접 입력 시 Phase 1(추출) 스킵, Phase 2만 실행.
    *   `--preset pumsem` 로딩 확장: `get_parse_patterns()`, `get_table_type_keywords()` 자동 로드 후 파서에 주입.
    *   PDF → MD 추출 완료 후 `--output json` 시 `parse_markdown()` 자동 체이닝. 중간 MD 파일도 함께 저장.
    *   JSON 출력 시 섹션 수 / 테이블 수 요약 콘솔 출력.

*   **`requirements.txt`**:
    *   `beautifulsoup4` 추가 (필수).
    *   `lxml` 추가 (선택적 — `_make_soup()` 폴백으로 미설치 환경 지원).

---

## 🚨 식별된 리스크 및 해결 결과 (설계서 검증)

| # | 위험 요소 (Risk) | 해결 방식 | 결과 |
| :- | :--- | :--- | :--- |
| 1 | **SRP 위반 — `_LABOR_ROW_KEYWORDS` 하드코딩** | 노동자 직종명 16종을 `classify_table()` 내부에서 제거. `presets/pumsem.py`의 `TABLE_TYPE_KEYWORDS["A_품셈_행키워드"]`로 이동. `type_keywords=None` 시 빈 리스트로 자동 무력화. | 범용 모드에서 건설 도메인 키워드 완전 차단 |
| 2 | **lxml Windows C-컴파일러 의존성** | `_make_soup()` 헬퍼 함수 도입. `try: BeautifulSoup(html, "lxml")` → `except: BeautifulSoup(html, "html.parser")` 폴백 패턴. | lxml 미설치 Windows 환경에서 ImportError 없이 정상 동작 |
| 3 | **`try_numeric()` 포맷 파괴** | `int()` / `float()` 캐스팅 완전 제거. `val.strip()` 만 수행. "15,000,000" → 그대로 보존. "0015" → 그대로 보존. | 선행 0 및 쉼표 포맷 비가역적 손실 방지. 타입 변환은 Phase 3(DB 적재) 또는 호출자 책임으로 위임 |
| 4 | **UTF-8 BOM 미삽입 → VS Code 인코딩 오판** | MD / JSON 파일 저장 시 `encoding="utf-8"` → `encoding="utf-8-sig"` 변경. BOM 삽입으로 Windows 계열 편집기가 인코딩을 EUC-KR로 오추론하는 현상 차단. | VS Code `json(516)` 파싱 오류 완전 해소 |

---

## 🧪 테스트 및 기능 검증 결과

실제 견적서(`고려아연 배관 Support 제작_추가_2차분 견적서.pdf` 1-2페이지 추출 MD)를 대상으로 Phase 2 파이프라인 전 구간 검증 시행.

### Test 1. `.md` 직접 입력 → JSON 변환 (`--output json --preset pumsem`)

```
python main.py "output/20260413_고려아연 배관 Support 제작_추가_2차분 견적서_p1-2_1.md" \
    --output json --preset pumsem
```

**결과: Pass**

| 검증 항목 | 내용 | 결과 |
| :--- | :--- | :--- |
| 섹션 분할 폴백 | SECTION 마커 없는 견적서 → 단일 `"doc"` 섹션으로 정상 래핑 | ✅ |
| 테이블 추출 수 | 내역서 요약(T-01), 일반사항(T-02), 상세내역(T-03) | ✅ 3개 |
| 복합 헤더 구성 | `재료비_단가`, `재료비_금액`, `노무비_단가` 등 2단 헤더 자동 조합 | ✅ 13개 열 |
| 금액 정합성 | T-01 합계 ↔ T-03 각 소계 합산 교차검증 | ✅ 완전 일치 |
| 반올림 조정액 캡처 | `-7,521` → `notes_in_table`에 정상 수록 | ✅ |
| 인코딩 | VS Code에서 한글 깨짐 없이 JSON 오류 0 | ✅ |

**금액 교차검증 (파서 출력값 기준):**

```
FILTER PRESS AREA        658,050
PIPERACK AREA          2,934,659
BLACK MASS             6,592,006
도장비                 5,003,940
────────────────────────────────
직접비 소계           15,188,655  ✅ (T-03 합 계 행 일치)
일반관리비             1,518,866  ✅ (직접비의 10%)
────────────────────────────────
소계                  16,707,521
반올림 조정액             - 7,521  ✅ (notes_in_table 캡처)
────────────────────────────────
총 합 계              16,700,000  ✅ (견적 표지 금액 일치)
```

### Test 2. 범용 모드 (프리셋 없음, `patterns=None`)

`--preset` 미지정 상태로 동일 문서 파싱.

**결과: Pass**

- `notes`, `conditions`, `cross_references`, `revision_year`, `unit_basis` 모두 빈값으로 정상 처리.
- 도메인 키워드 없이도 테이블 3개 추출 성공 (type: `"general"` 반환).
- 범용 정제(`clean_text` — HTML 주석 제거, 줄바꿈 정리)는 정상 실행.
- 건설 품셈 도메인 패턴이 일반 문서에 오작동하지 않음을 확인.

---

## 📐 설계 원칙 준수 현황

| 원칙 | 적용 위치 | 상태 |
| :--- | :--- | :--- |
| **SRP** (단일 책임 원칙) | 섹션 분할 / 테이블 파싱 / 텍스트 정제 / 파이프라인 조립을 4개 모듈로 분리 | ✅ |
| **의존성 주입 (DI)** | `type_keywords`, `patterns`를 함수 파라미터로 주입. 전역 상수 참조 제거 | ✅ |
| **범용성 보장** | `type_keywords=None`, `patterns=None` 시 도메인 로직 완전 우회 | ✅ |
| **하위 호환성** | `--output md`(기본값) 시 Phase 1과 동일 동작 보장 | ✅ |
| **이식성** | 모든 경로 `__file__` 기준 절대 경로 사용 | ✅ |

---

## 🚀 결론 및 Next Steps

Phase 2 목표였던 **"Phase 1 추출 마크다운을 단일 호출로 구조화 JSON으로 변환하는 범용 파이프라인 구축"** 이 100% 달성되었습니다.

`ps-docparser`는 현재 **PDF → MD (Phase 1) → JSON (Phase 2)** 전 구간 자동화 파이프라인을 단일 CLI로 실행할 수 있는 완성된 도구입니다.

**추후 진행 가능 항목 (Phase 3 제안):**
1. JSON 출력을 Excel / DB(SQLite, PostgreSQL 등)에 적재하는 로더 개발
2. 추출된 섹션·테이블 데이터를 기반으로 견적 비교·분석 자동화 기능 추가
3. `presets/` 에 견적서 전용 프리셋(`preset: estimate`) 추가 — 견적 특화 테이블 유형 분류 및 금액 집계 로직 탑재
4. 기존 GUI(`step1_gui.py`)와 Phase 2 파이프라인 연동 래퍼 빌드
