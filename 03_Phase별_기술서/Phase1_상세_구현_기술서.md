# Phase 1 상세 구현 기술서 — ps-docparser 뼈대 + 하이브리드 추출기

## 목적

`pdf_extractor/step1_extract_gemini_v33.py` (1,032줄, 단일 파일)를 **모듈 분리**하여 `ps-docparser/` 프로젝트 뼈대를 구축한다.

Phase 1 완료 시점에 **기존 pdf_extractor와 동일한 입출력 결과**가 나와야 한다.

---

## 원본 소스 함수 분석 (step1_extract_gemini_v33.py)

원본에 존재하는 모든 함수/클래스를 분류하고, 이식 대상 모듈을 매핑한다.

### 전역 설정/초기화 (L1~102)

| 원본 위치 | 내용                                 | 이식 대상                               |
| --------- | ------------------------------------ | --------------------------------------- |
| L25~39    | import +`.env` 로딩                | `config.py`                           |
| L55~56    | `GEMINI_API_KEY`, `GEMINI_MODEL` | `config.py`                           |
| L66~85    | `_detect_poppler_path()`           | `config.py`                           |
| L88       | `FREE_TIER_DELAY = 4`              | `config.py`                           |
| L91~95    | `DIVISION_NAMES` (품셈 전용)       | `presets/pumsem.py` (범용에선 미사용) |
| L97~101   | bbox 검증 상수                       | `extractors/table_utils.py`           |

### 클래스 (L106~134)

| 원본 위치 | 클래스/함수      | 이식 대상                  |
| --------- | ---------------- | -------------------------- |
| L106~134  | `UsageTracker` | `utils/usage_tracker.py` |

### 유틸리티 함수 (L137~469)

| 원본 위치 | 함수명                                    | 역할                        | 이식 대상                         |
| --------- | ----------------------------------------- | --------------------------- | --------------------------------- |
| L137~178  | `parse_page_spec()`                     | 페이지 범위 파싱            | `utils/page_spec.py`            |
| L196~203  | `_parse_usage_metadata()`               | API 응답 토큰 파싱          | `utils/usage_tracker.py`        |
| L206~229  | `extract_page_footer_metadata()`        | 푸터 부문명/장 추출         | `presets/pumsem.py` (품셈 전용) |
| L232~239  | `detect_tables()`                       | pdfplumber 테이블 bbox 감지 | `extractors/table_utils.py`     |
| L242~291  | `validate_and_fix_table_bboxes()`       | bbox 검증/보정              | `extractors/table_utils.py`     |
| L294~318  | `extract_text_outside_tables()`         | 테이블 제외 텍스트 추출     | `extractors/text_extractor.py`  |
| L321~367  | `extract_text_regions_with_positions()` | y좌표 기반 텍스트 영역 분할 | `extractors/text_extractor.py`  |
| L370~404  | `_is_sentence_ending()`                 | 한국어 문장 종결 감지       | `utils/text_formatter.py`       |
| L407~469  | `format_text_with_linebreaks()`         | PDF 줄바꿈 병합/정리        | `utils/text_formatter.py`       |
| L472~509  | `crop_table_image()`                    | 테이블 이미지 크롭          | `extractors/table_utils.py`     |

### AI 엔진 함수 (L512~606)

| 원본 위치 | 함수명                              | 역할                            | 이식 대상                    |
| --------- | ----------------------------------- | ------------------------------- | ---------------------------- |
| L512~567  | `extract_table_with_gemini()`     | 테이블 이미지 → HTML (Gemini)  | `engines/gemini_engine.py` |
| L570~606  | `extract_full_page_with_gemini()` | 전체 페이지 → MD+HTML (Gemini) | `engines/gemini_engine.py` |

### TOC 마커 빌더 (L609~655)

| 원본 위치 | 함수명                       | 역할                    | 이식 대상            |
| --------- | ---------------------------- | ----------------------- | -------------------- |
| L609~617  | `_build_section_markers()` | SECTION 마커 생성       | `utils/markers.py` |
| L620~626  | `_build_page_marker()`     | PAGE 마커 생성          | `utils/markers.py` |
| L629~633  | `_build_context_marker()`  | CONTEXT 마커 생성       | `utils/markers.py` |
| L636~655  | `_process_toc_context()`   | 푸터/목차 기반 컨텍스트 | `utils/markers.py` |

### 메인 프로세서 (L658~844)

| 원본 위치 | 함수명                      | 역할                   | 이식 대상                          |
| --------- | --------------------------- | ---------------------- | ---------------------------------- |
| L658~716  | `process_pdf_text_only()` | 텍스트 전용 추출       | `extractors/text_extractor.py`   |
| L719~844  | `process_pdf()`           | 하이브리드 추출 (핵심) | `extractors/hybrid_extractor.py` |

### CLI 진입점 (L847~1032)

| 원본 위치 | 함수명     | 역할                          | 이식 대상   |
| --------- | ---------- | ----------------------------- | ----------- |
| L847~1032 | `main()` | CLI 파싱 + 실행 + 로그 + 출력 | `main.py` |

---

## Phase 1 최종 폴더 구조

```
ps-docparser/
├── main.py                          # CLI 진입점 (조립만)
├── config.py                        # 전역 설정 (.env, API키, Poppler)
│
├── engines/                         # AI 엔진 (Strategy Pattern)
│   ├── __init__.py
│   ├── base_engine.py               # 공통 인터페이스 (ABC)
│   ├── gemini_engine.py             # Gemini Vision 구현
│   └── local_engine.py              # 로컬 전용 (AI 없음, 텍스트만)
│
├── extractors/                      # 추출 로직
│   ├── __init__.py
│   ├── hybrid_extractor.py          # 하이브리드 추출 (메인 파이프라인)
│   ├── text_extractor.py            # 텍스트 전용 추출
│   ├── table_utils.py               # 테이블 감지/bbox 보정/크롭
│   └── toc_parser.py                # 목차 파서 (기존 그대로 복사)
│
├── utils/                           # 유틸리티
│   ├── __init__.py
│   ├── text_formatter.py            # 줄바꿈 병합, 문장 종결 감지
│   ├── markers.py                   # PAGE/SECTION/CONTEXT 마커 생성
│   ├── page_spec.py                 # 페이지 범위 파싱 ("1-15", "20-")
│   └── usage_tracker.py             # API 사용량 추적
│
├── presets/                         # 도메인 프리셋 (선택적)
│   ├── __init__.py
│   └── pumsem.py                    # 품셈 전용 (부문명, 푸터 파싱)
│
├── output/                          # 기본 출력 폴더 (자동 생성)
├── cache/                           # 캐시 폴더 (Phase 4)
│
├── .env                             # API 키 (사용자가 생성)
├── .env.example                     # 템플릿
└── requirements.txt                 # pip 의존성
```

---

## 파일별 상세 스펙

### 1. `config.py` — 전역 설정

```python
"""
전역 설정 모듈.

Why: API 키, Poppler 경로, 엔진 설정을 한 곳에서 관리.
     각 모듈이 직접 .env를 로딩하면 경로 충돌 발생 → 여기서 일원화.

Dependencies: python-dotenv
"""

# 핵심 내보내기:
# - BASE_DIR: Path  (프로젝트 루트)
# - GEMINI_API_KEY: str | None
# - GEMINI_MODEL: str
# - POPPLER_PATH: str | None
# - DEFAULT_ENGINE: str  ("gemini" | "zai" | "local")
# - FREE_TIER_DELAY: int  (초)
# - OUTPUT_DIR: Path  (기본 출력 폴더)
```

**주의점:**

- `.env` 탐색 순서: `BASE_DIR/.env` → `BASE_DIR/../.env` → `cwd/.env`
- `GEMINI_API_KEY`가 없어도 에러 안 남 (`local` 엔진이면 불필요)
- `_detect_poppler_path()` 함수를 여기에 포함

---

### 2. `engines/base_engine.py` — 엔진 공통 인터페이스

```python
"""
AI 엔진 공통 인터페이스 (Abstract Base Class).

Why: 엔진 교체를 플러그인처럼 하려면 공통 계약(인터페이스)이 필요.
     새 엔진 추가 시 이 클래스를 상속하면 파이프라인이 자동으로 인식.
"""
from abc import ABC, abstractmethod
from PIL import Image

class BaseEngine(ABC):
    @abstractmethod
    def extract_table(self, image: Image.Image, table_num: int) -> tuple[str, int, int]:
        """테이블 이미지 → HTML 문자열 변환"""
        ...
  
    @abstractmethod
    def extract_full_page(self, image: Image.Image, page_num: int) -> tuple[str, int, int]:
        """전체 페이지 이미지 → MD+HTML 변환"""
        ...
```

---

### 3. `engines/gemini_engine.py` — Gemini 엔진 구현

```python
"""
Google Gemini Vision 엔진.

Why: 테이블 구조(셀 병합, 테두리 없는 표)를 정확히 파싱하려면 
     Vision AI가 필요. Gemini는 비용 대비 품질이 최적.

원본: step1_extract_gemini_v33.py L512~606
Dependencies: google-generativeai
"""

# 이식할 함수:
# - extract_table_with_gemini() → extract_table()
# - extract_full_page_with_gemini() → extract_full_page()
# - _parse_usage_metadata() → 내부 유틸
# - SAFETY_SETTINGS 상수
# - 프롬프트 문자열 (PROMPT_TABLE, PROMPT_FULL_PAGE)
```

**변경점 (원본 대비):**

- `genai.configure()` 를 `__init__` 에서 호출 (전역 X)
- `tracker` 전역변수 대신 `self.tracker` 인스턴스 변수
- `FREE_TIER_DELAY` → `config.py`에서 import

---

### 4. `engines/local_engine.py` — 로컬 전용 엔진

```python
"""
로컬 전용 엔진 (AI 없음, 무료).

Why: API 키 없이도 텍스트+pdfplumber 테이블은 뽑을 수 있다.
     비용 0원으로 빠르게 대략적 결과를 얻을 때 사용.
"""

# extract_table() → pdfplumber 자체 테이블 파싱 결과를 HTML로 변환
# extract_full_page() → 텍스트만 반환 (이미지 처리 안 함)
```

---

### 5. `extractors/table_utils.py` — 테이블 유틸리티

```python
"""
테이블 감지, bbox 검증/보정, 이미지 크롭 유틸리티.

원본: step1_extract_gemini_v33.py L232~291, L472~509
Dependencies: pdfplumber, Pillow
"""

# 이식할 함수:
# - detect_tables(page) -> list[tuple]
# - validate_and_fix_table_bboxes(bboxes, page_h, page_w) -> tuple[list, bool]
# - crop_table_image(image, bbox, page_h, page_w, extended) -> Image
# - 상수: TABLE_MIN_HEIGHT_RATIO, TABLE_BOTTOM_EXTRA_PADDING
```

---

### 6. `extractors/text_extractor.py` — 텍스트 추출

```python
"""
PDF 텍스트 전용 추출기.

원본: step1_extract_gemini_v33.py L294~367, L658~716
Dependencies: pdfplumber
"""

# 이식할 함수:
# - extract_text_outside_tables(page, table_bboxes) -> str
# - extract_text_regions_with_positions(page, table_bboxes) -> list[dict]
# - process_pdf_text_only(pdf_path, section_map, page_indices) -> str
```

---

### 7. `extractors/hybrid_extractor.py` — 하이브리드 추출 (핵심)

```python
"""
하이브리드 PDF 추출기 — 텍스트(pdfplumber) + 테이블(AI 엔진).

Why: 이 모듈이 ps-docparser의 핵심 파이프라인이다.
     1. pdfplumber로 테이블 bbox 감지
     2. 테이블 없으면 텍스트만 추출 (무료)
     3. 테이블 있으면 해당 영역만 이미지로 크롭 → AI 엔진에 전달
     4. 텍스트+테이블을 y좌표 순으로 정렬하여 마크다운 생성

원본: step1_extract_gemini_v33.py L719~844
Dependencies: pdfplumber, pdf2image, engines/*, table_utils, text_formatter
"""

# 핵심 함수:
# - process_pdf(pdf_path, engine, section_map, page_indices) -> str
#   ※ engine 파라미터 추가 (원본에는 없음 → Gemini 하드코딩이었음)
```

**원본 대비 변경점:**

- `engine: BaseEngine` 파라미터 추가 (엔진 주입)
- `extract_table_with_gemini()` 직접 호출 → `engine.extract_table()` 호출로 변경
- `extract_full_page_with_gemini()` 직접 호출 → `engine.extract_full_page()` 호출로 변경
- `toc_parser` 직접 import → 파라미터로 주입 (선택적)

---

### 8. `utils/text_formatter.py` — 텍스트 포매터

```python
"""
PDF 텍스트 줄바꿈 병합 및 정리.

원본: step1_extract_gemini_v33.py L370~469
"""

# 이식할 함수:
# - _is_sentence_ending(line) -> bool
# - format_text_with_linebreaks(text) -> str

# ⚠️ 주의: DIVISION_NAMES 패턴이 format_text_with_linebreaks()에 하드코딩.
#    범용 모드에서는 이 패턴을 비활성화해야 함.
#    → 해결: preset 파라미터로 분기
```

---

### 9. `utils/markers.py` — 마커 생성기

```python
"""
PAGE/SECTION/CONTEXT 마크다운 주석 마커 생성.

원본: step1_extract_gemini_v33.py L609~655
"""

# 이식할 함수:
# - build_section_markers(page_sections) -> str
# - build_page_marker(page_num, current_context) -> str
# - build_context_marker(active_section) -> str
# - process_toc_context(full_text, page_map, current_context) -> tuple
```

---

### 10. `utils/page_spec.py` — 페이지 범위 파서

```python
"""
페이지 지정 문자열 파싱.

원본: step1_extract_gemini_v33.py L137~178
"""

# 이식할 함수:
# - parse_page_spec(spec, total_pages) -> list[int]
```

---

### 11. `utils/usage_tracker.py` — API 사용량 추적

```python
"""
AI API 사용량(토큰/비용) 추적.

원본: step1_extract_gemini_v33.py L106~134, L196~203
"""

# 이식할 클래스/함수:
# - UsageTracker (클래스)
# - parse_usage_metadata(response) -> tuple[int, int]
```

---

### 12. `extractors/toc_parser.py` — 목차 파서

**기존 `toc_parser.py` (329줄)를 그대로 복사.** 변경 없음.

---

### 13. `main.py` — CLI 진입점

```python
"""
ps-docparser CLI 진입점.

Why: 이 파일은 비즈니스 로직을 포함하지 않는다.
     개별 모듈을 import하여 파이프라인을 조립하는 컨트롤러 역할만 한다.
"""

# 흐름:
# 1. argparse로 CLI 인수 파싱
# 2. config.py 에서 설정 로딩
# 3. --engine 옵션에 따라 엔진 인스턴스 생성
# 4. --text-only면 text_extractor.process_pdf_text_only() 호출
#    아니면 hybrid_extractor.process_pdf() 호출
# 5. 결과를 output/ 폴더에 MD 파일로 저장
# 6. 사용량 summary 출력
```

**CLI 인수:**

```
python main.py <PDF파일> [옵션]

필수:
  <PDF파일>              처리할 PDF 파일 경로

옵션:
  --engine <이름>        AI 엔진 선택 (gemini|local, 기본: .env의 DEFAULT_ENGINE)
  --text-only, -t       텍스트 전용 모드 (AI 엔진 미사용, 무료)
  --toc <파일>           목차 파일 (.json 또는 .txt)
  --pages <지정>         페이지 범위 (예: 1-15, 20-, 1,3,5-10)
  --output-dir <경로>    출력 폴더 (기본: ./output/)
  --preset <이름>        도메인 프리셋 (pumsem|bom, 기본: 없음=범용)
```

---

## 잠재 위험 요소 검토

### ⚠️ 위험 1: `DIVISION_NAMES` 하드코딩 (품셈 종속)

**위치:** `format_text_with_linebreaks()` (L426, L443)

**문제:** 범용 모드에서 품셈 키워드("공통부문", "토목부문" 등)로 줄바꿈을 강제하면 일반 PDF에서 오동작.

**해결:**

```python
def format_text_with_linebreaks(text: str, division_names: str = None) -> str:
    # division_names가 None이면 품셈 패턴 적용 안 함
    if division_names:
        text = re.sub(rf'(?<![-\d])(\d+\s*(?:{division_names}))', r'\n\1', text)
```

---

### ⚠️ 위험 2: `toc_parser` import 방식

**원본:** `import toc_parser` (같은 디렉토리 수준에서 bare import)

**문제:** `ps-docparser/extractors/toc_parser.py`로 옮기면 import 경로가 바뀜.

**해결:** `hybrid_extractor.py`에서 `from extractors import toc_parser` 또는 `from . import toc_parser`. `main.py`에서 경로 주입.

---

### ⚠️ 위험 3: `genai.configure()` 전역 호출

**원본:** L185에서 모듈 로딩 시점에 `genai.configure(api_key=...)` 실행.

**문제:** `local` 엔진 사용 시에도 `google-generativeai` 패키지가 필수 설치되어야 함.

**해결:** `GeminiEngine.__init__()` 에서만 `genai.configure()` 호출. `local` 엔진이면 이 패키지 import 자체를 안 함.

```python
# engines/gemini_engine.py
class GeminiEngine(BaseEngine):
    def __init__(self, api_key: str, model: str):
        import google.generativeai as genai  # 지연 import
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model)
```

---

### ⚠️ 위험 4: `convert_from_path()` Poppler 의존

**원본:** L786~790에서 `pdf2image.convert_from_path()` 호출 시 `POPPLER_PATH` 필요.

**문제:** Poppler 미설치 시 전체 파이프라인 실패.

**해결:** `local` 엔진 + `--text-only` 모드에서는 `pdf2image` 자체를 호출하지 않음. 테이블이 있을 때만 import + 호출.

---

### ⚠️ 위험 5: `tracker` 전역 인스턴스

**원본:** L182에서 `tracker = UsageTracker()` 전역 생성, 모든 함수에서 접근.

**문제:** 모듈 분리 시 전역 변수 공유 불가.

**해결:** `UsageTracker` 인스턴스를 `main.py`에서 생성하여 엔진에 주입.

```python
# main.py
tracker = UsageTracker()
engine = GeminiEngine(api_key=..., model=..., tracker=tracker)
result = process_pdf("input.pdf", engine=engine)
print(tracker.summary())
```

---

## 구현 순서 (의존성 기반)

```
1단계: 의존성 없는 유틸리티 (병렬 작업 가능)
  ├── config.py
  ├── utils/page_spec.py
  ├── utils/usage_tracker.py
  ├── utils/text_formatter.py
  ├── utils/markers.py
  └── requirements.txt, .env.example

2단계: 엔진 계층
  ├── engines/base_engine.py
  ├── engines/gemini_engine.py
  └── engines/local_engine.py

3단계: 추출기 계층
  ├── extractors/toc_parser.py (복사)
  ├── extractors/table_utils.py
  ├── extractors/text_extractor.py
  └── extractors/hybrid_extractor.py

4단계: CLI 진입점
  └── main.py
```

---

## 검증 계획

|  검증 항목  | 방법                                                             | 기대 결과                                         |
| :---------: | ---------------------------------------------------------------- | :------------------------------------------------ |
|  기본 동작  | `python main.py "53-83 OKOK.pdf" --engine gemini --pages 1-15` | 기존 `20260206_53-83 OKOK_p1-15.md`와 동일 출력 |
| 텍스트 전용 | `python main.py "53-83 OKOK.pdf" --text-only`                  | 텍스트만 추출, API 호출 0회                       |
|  로컬 엔진  | `python main.py "53-83 OKOK.pdf" --engine local`               | API 미사용, pdfplumber 테이블만 추출              |
|   이식성   | 프로젝트 폴더를 `D:\temp\`로 복사 후 동일 명령 실행            | 정상 동작                                         |
| API 키 없음 | `.env`에서 `GEMINI_API_KEY` 제거 후 `--engine local`       | 에러 없이 동작                                    |
| API 키 없음 | `.env`에서 `GEMINI_API_KEY` 제거 후 `--engine gemini`      | 명확한 에러 메시지                                |

---

> 작성일: 2026-04-13 | Phase 1 of 4 | 작성: Antigravity AI
