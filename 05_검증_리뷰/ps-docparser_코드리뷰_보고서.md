# ps-docparser 종합 코드 리뷰 보고서

**리뷰 일자:** 2026-04-17
**리뷰 범위:** ps-docparser 전체 (3,160줄)
**리뷰 모델:** Claude Opus 4

---

## 1. 프로젝트 개요

- **프로젝트명:** ps-docparser (범용 문서 파서 통합 플랫폼)
- **현재 상태:** Phase 5 (배치 처리 + 캐싱 완료)
- **총 코드량:** 3,160줄 (테스트, 디버그 제외)
- **주요 기능:** PDF → 마크다운 → JSON → Excel 변환 (BOM 특화)
- **개발 언어:** Python 3.10+

---

## 2. 코드 구조 및 아키텍처

### 2.1 프로젝트 구조

```
ps-docparser/ (3,160줄)
├── main.py (786줄)              # CLI 진입점 - Phase 5까지 통합
├── config.py (157줄)             # 전역 설정 (.env 로딩, 경로 감지)
├── detector.py (78줄)            # 문서 유형 자동 감지
├── audit_main.py (148줄)         # 모듈 연결 감사 스크립트
│
├── engines/ (OCR/AI 엔진, 전략 패턴)
│   ├── base_engine.py (170줄)    # ABC 인터페이스
│   ├── gemini_engine.py          # Google Gemini Vision
│   ├── local_engine.py           # pdfplumber만 (무료)
│   ├── zai_engine.py             # Z.ai GLM-OCR (BOM 전용)
│   ├── mistral_engine.py         # Mistral Pixtral OCR (폴백)
│   └── tesseract_engine.py       # Tesseract 로컬 OCR
│
├── extractors/ (단계1: PDF → 마크다운)
│   ├── hybrid_extractor.py       # 핵심 파이프라인
│   ├── text_extractor.py         # 텍스트 전용 (무료)
│   ├── bom_extractor.py          # BOM/LINE LIST 상태머신
│   ├── table_utils.py            # bbox 감지, 검증, 크롭
│   ├── toc_parser.py             # 목차 파일 파싱
│   └── bom_types.py              # BOM 데이터클래스
│
├── parsers/ (단계2: 마크다운 → JSON)
│   ├── document_parser.py        # 통합 진입점
│   ├── section_splitter.py       # 목차 기반 섹션 분할
│   ├── table_parser.py           # rowspan/colspan 전개
│   ├── text_cleaner.py           # 본문 정제
│   └── bom_table_parser.py       # BOM 행 파싱
│
├── exporters/ (단계3: JSON → 출력 형식)
│   ├── base_exporter.py          # 공통 인터페이스
│   ├── excel_exporter.py         # JSON → Excel
│   ├── json_exporter.py          # JSON 파일 저장
│   └── bom_aggregator.py         # BOM 배치 집계
│
├── presets/ (도메인별 설정)
│   ├── pumsem.py                 # 건설 품셈 전용
│   ├── estimate.py               # 견적서 전용
│   └── bom.py                    # BOM 전용
│
├── utils/ (공통 유틸리티)
│   ├── usage_tracker.py          # API 비용 추적
│   ├── page_spec.py              # 페이지 범위 파싱
│   ├── text_formatter.py         # 줄바꿈 병합
│   ├── markers.py                # PAGE/SECTION/CONTEXT 마커
│   └── ocr_utils.py              # file_to_data_uri
│
├── cache/ (Phase 5: API 응답 캐싱)
│   └── table_cache.py            # SQLite 캐시
│
├── requirements.txt              # pip 의존성 (9개)
├── .env / .env.example           # API 키 설정
└── output/                        # 기본 출력 폴더
```

### 2.2 핵심 처리 흐름

```
입력 파일 (PDF/MD 또는 디렉토리)
    ↓
[config.py] 전역 설정 로딩 (.env, Poppler, Tesseract 경로 감지)
    ↓
[main.py] CLI 인수 파싱 → _process_single() 함수로 위임
    ↓
┌─────────────────────────────────────────────────┐
│ Phase 1: PDF → 마크다운                         │
├─────────────────────────────────────────────────┤
│ ├─ PDF 입력인가?                                │
│ ├─ 프리셋 로딩 (pumsem/estimate/bom)           │
│ ├─ 엔진 선택 (gemini/zai/mistral/tesseract)    │
│ ├─ --preset bom인가?                           │
│ │  └─ YES → bom_extractor (상태머신)           │
│ │  └─ NO  → hybrid/text_extractor              │
│ └─ 출력: {date}_{filename}.md                  │
└─────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────┐
│ Phase 2: 마크다운 → JSON 파싱                  │
├─────────────────────────────────────────────────┤
│ ├─ document_parser.parse_markdown()            │
│ │  ├─ split_sections()       (목차 기반)      │
│ │  ├─ process_section_tables() (HTML 파싱)    │
│ │  └─ process_section_text()  (텍스트 정제)   │
│ └─ 출력: [{section_id, title, tables, ...}]   │
└─────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────┐
│ Phase 3: JSON → Excel 변환                      │
├─────────────────────────────────────────────────┤
│ ├─ excel_exporter.export()                     │
│ │  ├─ 테이블 자동 분류:                        │
│ │  │  - 견적서 (명칭+금액)                     │
│ │  │  - 내역서 (품명+합계금액)                │
│ │  │  - 조건   (일반사항/특기사항)            │
│ │  │  - 범용   (Table_N)                      │
│ │  └─ 스타일 (색상, 폰트, 테두리)             │
│ └─ 출력: {date}_{filename}.xlsx               │
└─────────────────────────────────────────────────┘
    ↓
[main.py] 배치 처리 요약 + BOM 배치 집계 + 캐시 통계
```

---

## 3. 문제점 파악 (Code Smells & Bugs)

### 3.1 에러 처리 부족

#### 문제 1: main.py - 파일 쓰기 권한 오류 미처리
**파일:** `main.py:507`
```python
with open(md_path, "w", encoding="utf-8-sig") as f:
    f.write(md)
```
**문제:**
- Windows에서 Excel이 .xlsx를 열고 있으면 `PermissionError` 발생 → 배치 전체 중단

**개선:**
```python
try:
    with open(md_path, "w", encoding="utf-8-sig") as f:
        f.write(md)
except PermissionError as e:
    raise ParserError(f"파일 쓰기 권한 오류: {md_path} — {e}")
except IOError as e:
    raise ParserError(f"파일 I/O 오류: {md_path} — {e}")
```

#### 문제 2: config.py - 환경변수 없음 시 조용히 None 반환
**파일:** `config.py:41-48`
```python
GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")
DEFAULT_ENGINE: str = os.getenv("DEFAULT_ENGINE", "gemini")
```
**문제:** 실행은 되지만 API 호출 시점에 403 오류 발생

**개선:**
```python
def _validate_api_keys():
    engine = os.getenv("DEFAULT_ENGINE", "gemini")
    if engine == "gemini" and not GEMINI_API_KEY:
        logger.warning("⚠️ GEMINI_API_KEY가 없습니다. .env 확인 또는 --engine local 사용")
```

#### 문제 3: bom_extractor.py - 정규식 컴파일 캐싱 없음
**파일:** `extractors/bom_extractor.py:30-60`
```python
def _sanitize_html(text: str) -> str:
    text = re.sub(r'</tr[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</t[dh]>\s*<t[dh][^>]*>', ' | ', text, flags=re.IGNORECASE)
```
**문제:** 배치 처리 시 매번 정규식 컴파일 → 61개 PDF 처리 시 수천 회 반복

**개선:**
```python
_RE_TABLE_END = re.compile(r'</tr[^>]*>', re.IGNORECASE)
_RE_CELL_SEP = re.compile(r'</t[dh]>\s*<t[dh][^>]*>', re.IGNORECASE)

def _sanitize_html(text: str) -> str:
    text = _RE_TABLE_END.sub('\n', text)
    text = _RE_CELL_SEP.sub(' | ', text)
```

### 3.2 성능 문제

#### 문제 4: hybrid_extractor.py - 페이지별 pdf2image 반복 호출
**파일:** `extractors/hybrid_extractor.py:150-200`
```python
if engine.supports_image:
    from pdf2image import convert_from_path
    images = convert_from_path(str(pdf_path), dpi=400, ...)
```
**문제:** 페이지당 1회 전체 PDF를 이미지로 변환 → 300+페이지 대용량 PDF에서 답답함

**개선:** LRU 캐시 도입, lazy loading으로 `images[i]` 접근 시만 변환

### 3.3 타입 힌팅 부족

#### 문제 5: parsers/document_parser.py - 반환값 검증 없음
**파일:** `parsers/document_parser.py:31-50`
```python
def parse_markdown(md_input: str, ...) -> list[dict]:
    return sections  # 구조 검증 없음
```
**개선:**
```python
from typing import TypedDict

class SectionDict(TypedDict):
    section_id: str
    title: str
    clean_text: str
    tables: list[dict]

def parse_markdown(...) -> list[SectionDict]:
    ...
```

### 3.4 하드코딩 및 매직넘버

#### 문제 6: config.py - Poppler 경로 하드코딩
**파일:** `config.py:72-76`
```python
candidates = [
    r"C:\poppler\poppler-24.08.0\Library\bin",
    r"C:\Program Files\poppler\Library\bin",
    r"C:\poppler\bin",
]
```
**문제:** Poppler 버전(24.08.0) 고정 → 새 버전 설치하면 작동 안 함

**개선:**
```python
import glob
def _detect_poppler_path() -> str | None:
    candidates = glob.glob(r"C:\poppler\poppler-*\Library\bin")
    if candidates:
        return sorted(candidates)[-1]  # 최신 버전 선택
```

#### 문제 7: utils/usage_tracker.py - Gemini 가격 하드코딩 (outdated)
**파일:** `utils/usage_tracker.py:43-48`
```python
est_cost = (
    (self.total_input_tokens / 1_000_000 * 0.10)
    + (self.total_output_tokens / 1_000_000 * 0.40)
)
# 주석: "2025Q1 기준" ← 이미 2026년 4월!
```
**문제:** Gemini 가격 변동 시 예상 비용 부정확

**개선:**
```python
# config.py
GEMINI_PRICING = {
    "input": 0.10,
    "output": 0.40,
    "updated": "2026-04-17",
}
```

### 3.5 테스트 부족

#### 문제 8: 단위 테스트 미흡
**파일:** `test_phase5_unit*.py` (총 5개)
**문제:** 통합 테스트 위주, 각 함수별 단위 테스트 거의 없음
- `detector.detect_document_type()` → 테스트 없음
- `page_spec.parse_page_spec()` → 테스트 없음
- `table_cache.TableCache` → 테스트 없음

**개선:**
```python
# tests/test_detector.py
def test_detect_estimate():
    text = "견적금액: 1,000,000원"
    assert detector.detect_document_type(text) == "estimate"

def test_detect_bom():
    text = "BILL OF MATERIALS\nS/N | SPEC | Q'TY"
    assert detector.detect_document_type(text) == "bom"
```

### 3.6 의존성 & 호환성 문제

#### 문제 9: requirements.txt - 버전 고정 없음
**파일:** `requirements.txt`
```
pdfplumber
google-generativeai
pdf2image
Pillow
python-dotenv
beautifulsoup4
lxml
openpyxl
```
**문제:** 최신 버전 자동 설치 → breaking change 위험

**개선:**
```
pdfplumber>=0.11.0,<1.0.0
google-generativeai>=0.8.0,<1.0.0
pdf2image>=1.17.0,<2.0.0
Pillow>=11.0.0,<12.0.0
python-dotenv>=1.0.0,<2.0.0
beautifulsoup4>=4.12.0,<5.0.0
lxml>=5.0.0,<6.0.0
openpyxl>=3.10.0,<4.0.0
```

#### 문제 10: Windows 경로 감지만 구현
**파일:** `config.py:71-94`
**문제:** Linux/macOS는 `shutil.which()` 시도 안 함

**개선:**
```python
def _detect_poppler_path() -> str | None:
    # 1순위: 환경변수
    if env_path := os.environ.get("POPPLER_PATH"):
        if os.path.exists(env_path):
            return env_path

    # 2순위: 시스템 PATH
    if which := shutil.which("pdftotext"):
        return os.path.dirname(which)

    # 3순위: OS별 기본 경로
    if platform.system() == "Windows":
        candidates = glob.glob(r"C:\poppler\poppler-*\Library\bin")
    elif platform.system() == "Darwin":
        candidates = ["/usr/local/bin", "/opt/homebrew/bin"]
    else:
        candidates = ["/usr/bin"]
```

---

## 4. 범용화를 위한 개선 포인트

### 4.1 현재 범용성 한계

| 항목 | 현재 상태 | 평가 |
|------|---------|-----|
| **입력 형식** | PDF만 (MD 간접 지원) | ⚠️ 중간 — HWPX, DOCX 미지원 |
| **출력 형식** | MD, JSON, Excel | ✅ 양호 |
| **문서 유형** | 견적서, 품셈, BOM | ⚠️ 중간 |
| **엔진 확장성** | 전략 패턴 (ABC) | ✅ 양호 |
| **프리셋 확장** | 3개 프리셋 | ⚠️ 제한적 |
| **OS 호환성** | Windows/Linux | ⚠️ 중간 — macOS 미흡 |
| **설치 난이도** | .env 수동 작성 | ⚠️ 높음 |
| **배치 처리** | 지원 | ✅ 양호 |
| **캐싱** | SQLite (Phase 5) | ✅ 양호 |

### 4.2 문서 타입 확장 전략

**현재:** 하드코딩된 3개 도메인 (견적서, 품셈, BOM)

**개선: 프리셋 레지스트리 패턴**
```python
# presets/registry.py (신규)
PRESETS_REGISTRY = {
    "estimate": {
        "module": "presets.estimate",
        "description": "견적서 양식 최적화",
        "supported_formats": ["md", "json", "excel"],
    },
    "invoice": {"module": "presets.invoice", ...},
    "contract": {"module": "presets.contract", ...},
}

# main.py에서 동적 로딩
preset_config = PRESETS_REGISTRY.get(args.preset)
if preset_config:
    preset_module = importlib.import_module(preset_config["module"])
```

### 4.3 입력 형식 확장

#### HWPX (한컴 오피스) 지원
```python
# extractors/hwpx_extractor.py (신규)
from zipfile import ZipFile
import xml.etree.ElementTree as ET

def extract_hwpx_text(hwpx_path: str) -> str:
    with ZipFile(hwpx_path) as z:
        content = z.read('content.xml').decode('utf-8')
        root = ET.fromstring(content)
        # XML 파싱 → 마크다운 변환
```

#### DOCX 지원
```python
# extractors/docx_extractor.py
from docx import Document

def extract_docx(docx_path: str) -> str:
    doc = Document(docx_path)
    markdown = ""
    for element in doc.element.body:
        if isinstance(element, Table):
            markdown += _table_to_markdown(element)
        else:
            markdown += element.text + "\n"
    return markdown
```

#### 통합 진입점
```python
def _get_extractor(input_path: Path):
    suffix = input_path.suffix.lower()
    extractors = {
        ".pdf": "hybrid_extractor",
        ".hwpx": "hwpx_extractor",
        ".docx": "docx_extractor",
        ".md": None,  # Phase 1 스킵
    }
    if suffix not in extractors:
        raise ParserError(f"지원하지 않는 형식: {suffix}")
    return extractors[suffix]
```

### 4.4 설정 자동화

**현재:** `.env` 수동 작성 → 진입 장벽

**개선: 대화형 설정 마법사**
```python
# cli setup 커맨드
def setup_wizard():
    print("=== ps-docparser 초기 설정 ===\n")

    api_key = input("Gemini API 키 입력 (선택): ").strip()
    poppler_path = input("Poppler 경로 (엔터=자동감지): ").strip()
    tesseract_path = input("Tesseract 경로 (엔터=자동감지): ").strip()

    env_content = f"""GEMINI_API_KEY={api_key}
POPPLER_PATH={poppler_path}
TESSERACT_PATH={tesseract_path}
DEFAULT_ENGINE=gemini
FREE_TIER_DELAY=4
CACHE_ENABLED=true
"""
    with open(".env", "w") as f:
        f.write(env_content)
    print("✅ .env 파일 생성 완료")
```

---

## 5. 코드 품질 개선 사항

### 5.1 엔진 팩토리 패턴

```python
# engines/factory.py (신규)
class EngineFactory:
    @staticmethod
    def create(engine_name: str, **kwargs) -> BaseEngine:
        factories = {
            "gemini": GeminiEngineFactory,
            "zai": ZaiEngineFactory,
            "local": LocalEngineFactory,
            "mistral": MistralEngineFactory,
            "tesseract": TesseractEngineFactory,
        }
        factory_class = factories.get(engine_name)
        if not factory_class:
            raise ValueError(f"Unknown engine: {engine_name}")
        return factory_class.build(**kwargs)
```

### 5.2 파이프라인 클래스 캡슐화

```python
# pipelines/full_pipeline.py (신규)
class FullPipeline:
    """Phase 1→2→3 전체 파이프라인."""

    def __init__(self, config: Config, cache: TableCache = None):
        self.config = config
        self.cache = cache

    def process(self, input_path: Path, preset: str = None) -> dict:
        """
        Returns:
            {
                "status": "success" | "error",
                "outputs": {"md": Path, "json": Path, "xlsx": Path},
                "error": str | None,
                "metrics": {
                    "api_calls": int,
                    "tokens_used": int,
                    "processing_time_s": float,
                    "cache_hit_rate": float,
                }
            }
        """
```

### 5.3 파일별 문제점 정리표

| 모듈 | 문제 | 우선순위 | 영향도 |
|------|------|--------|-------|
| main.py (786줄) | 함수 너무 김 | 중 | 높음 |
| hybrid_extractor.py | 페이지별 이미지 변환 비효율 | 중 | 중 |
| bom_extractor.py | 정규식 캐싱 없음 | 낮음 | 낮음 |
| config.py | 버전 하드코딩, 경로 감지 미흡 | 높음 | 높음 |
| parsers/* | 반환값 타입 검증 없음 | 낮음 | 중 |
| test_*.py | 단위 테스트 부족 | 높음 | 높음 |
| requirements.txt | 버전 미지정 | 높음 | 높음 |

---

## 6. 보안 관련 사항

### 6.1 API 키 관리
- `.env` 파일 평문 저장 ✅ 표준 관행
- `.gitignore`에 `.env` 등재 확인 필요
- **개선:** 로그 마스킹 추가

```python
def _safe_log_config():
    api_key = GEMINI_API_KEY or "NOT_SET"
    masked = api_key[:4] + "*" * (len(api_key) - 8) + api_key[-4:] if api_key != "NOT_SET" else "NOT_SET"
    logger.info(f"Gemini API: {masked}")
```

### 6.2 입력 검증

```python
def parse_markdown(md_input: str, ...) -> list[dict]:
    if isinstance(md_input, str) and Path(md_input).is_file():
        size_mb = Path(md_input).stat().st_size / 1024 / 1024
        if size_mb > 100:
            raise ParserError(f"파일 크기 초과: {size_mb:.1f}MB > 100MB")
```

---

## 7. 성능 최적화 제안

### 7.1 메모리 최적화

| 개선안 | 현재 | 개선 후 | 절감 |
|------|------|------|------|
| pdf2image 페이지 캐싱 | 페이지마다 전체 변환 | LRU(5) 캐시 | 80% |
| 정규식 컴파일 캐싱 | 매번 컴파일 | 모듈 로드 1회 | 70% |
| 크롭 이미지 재사용 | 매번 할당 | numpy stack 재사용 | 30% |

### 7.2 병렬 처리 (선택적)

```python
import concurrent.futures

if args.parallel and is_batch:
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(_process_single, ..., pdf): pdf.name
            for pdf in pdf_files
        }
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except ParserError as e:
                failed.append((futures[future], str(e)))
```

> **주의:** GIL 때문에 CPU 바운드 작업은 이득 없음. API I/O 대기 시에만 유리.

---

## 8. 최종 평가 및 등급

### 8.1 종합 평가

| 항목 | 등급 | 의견 |
|------|------|------|
| **아키텍처** | A- | 전략 패턴, 3단계 파이프라인 잘 설계 |
| **에러 처리** | C+ | ParserError 도입했으나 I/O, API 오류 미흡 |
| **테스트** | D | 통합 테스트만 있고 단위 테스트 거의 없음 |
| **성능** | B- | 배치 처리 좋음, pdf2image 비효율 |
| **보안** | B | API 키 환경변수 관리 좋음, 입력 검증 부족 |
| **문서화** | B | 모듈 docstring 충실, API 문서 없음 |
| **호환성** | C+ | Linux/Windows 지원, macOS 미흡 |
| **범용성** | B | 3개 문서 타입만 지원, 확장 구조는 존재 |

### 8.2 액션 플랜

#### 🔴 즉시 해결 (P0 - 1주)
1. ✅ requirements.txt 버전 고정
2. ✅ config.py Poppler/Tesseract 경로 감지 개선
3. ✅ main.py 파일 쓰기 권한 오류 처리
4. ⚠️ 단위 테스트 최소 50% 커버리지 확보

#### 🟡 중기 개선 (P1 - 1개월)
5. 엔진 팩토리 패턴 적용
6. bom_extractor 정규식 캐싱
7. hybrid_extractor 페이지 이미지 캐싱
8. API 키 로그 마스킹
9. Gemini 가격 최신화

#### 🟢 장기 개선 (P2 - 3~6개월)
10. HWPX/DOCX 입력 지원
11. Sphinx/MkDocs 문서화
12. 병렬 처리 (선택적)
13. 프리셋 레지스트리 (동적 로딩)
14. pyproject.toml 정비 + PyPI 배포
15. GUI 또는 웹 UI (FastAPI + React)

---

## 9. 결론

**ps-docparser는 잘 구조화된 Phase 5 완성도 높은 프로젝트입니다.**

### 강점
- ✅ 3단계 파이프라인 명확
- ✅ 전략 패턴으로 엔진 확장 용이
- ✅ Phase 5 캐싱/배치 처리 완성
- ✅ 모듈별 역할 분리 잘 됨

### 약점
- ⚠️ 단위 테스트 부족
- ⚠️ 일부 에러 처리 미흡
- ⚠️ 범용성은 중간 수준 (특정 도메인 최적화)
- ⚠️ OS 호환성 (macOS 미흡)
- ⚠️ 하드코딩된 경로/버전

### 범용화 핵심 포인트
1. **입력 확장:** HWPX, DOCX 지원
2. **프리셋 레지스트리:** 동적 로딩으로 서드파티 기여 가능
3. **OS 호환성:** macOS Poppler 경로, `shutil.which()` 폴백
4. **설치 UX:** 설정 마법사 (`python -m ps_docparser setup`)
5. **패키징:** `pyproject.toml` + PyPI 배포

---

## 부록: 파일별 라인 수 및 문제점 요약

| 파일 | 줄 | 주요 문제 | 심각도 |
|------|-----|---------|-------|
| main.py | 786 | 함수 길이, I/O 예외 처리 | 중 |
| config.py | 157 | 경로 하드코딩, Poppler 버전 고정 | 높음 |
| hybrid_extractor.py | ~250 | pdf2image 비효율 | 중 |
| bom_extractor.py | ~200 | 정규식 캐싱 없음 | 낮음 |
| test_*.py | ~1000 | 단위 테스트 부족 | 높음 |
| requirements.txt | 9 | 버전 미지정 | 높음 |
| parsers/document_parser.py | ~120 | 타입 검증 없음 | 낮음 |

---

## 10. 수정 페이즈별 계획 (Phase 6 ~ Phase 11)

> **참고:** 기존 Phase 1~5는 기능 구현 완료. Phase 6부터는 **품질 개선 및 범용화** 단계.
> 각 페이즈는 독립적으로 진행 가능하며, 추후 페이즈별 상세 구현 기술서 작성 예정.

---

### 🔴 Phase 6: 긴급 안정화 (P0 - Critical)
**목표:** 현재 배포 환경에서 발생 가능한 즉각적 오류 차단
**예상 기간:** 1주

**주요 작업:**
- [ ] `requirements.txt` 버전 고정 (pdfplumber, openpyxl 등)
- [ ] `config.py` Poppler 경로 동적 감지 (`glob` + `shutil.which`)
- [ ] `main.py` 파일 I/O 예외 처리 (`PermissionError`, `IOError`)
- [ ] API 키 누락 시 시작 시점 경고 추가
- [ ] `.gitignore` `.env` 포함 여부 확인

**영향 범위:** `requirements.txt`, `config.py`, `main.py`

---

### 🟡 Phase 7: 테스트 인프라 구축 (P0 - Critical)
**목표:** 단위 테스트 커버리지 50% 이상 확보, 리팩터링 안전성 확보
**예상 기간:** 2주

**주요 작업:**
- [ ] `pytest` 도입 및 `tests/` 디렉토리 구조 정립
- [ ] 핵심 모듈 단위 테스트 작성
  - `detector.detect_document_type()`
  - `page_spec.parse_page_spec()`
  - `table_cache.TableCache`
  - `bom_extractor.extract_bom()`
- [ ] CI 기본 워크플로우 (GitHub Actions 또는 로컬 스크립트)
- [ ] 코드 커버리지 측정 (`pytest-cov`)

**영향 범위:** `tests/` (신규), `requirements-dev.txt` (신규)

---

### 🟡 Phase 8: 성능 최적화 (P1 - High)
**목표:** 메모리/CPU 사용량 30~80% 절감, 배치 처리 속도 개선
**예상 기간:** 2주

**주요 작업:**
- [ ] `bom_extractor.py` 정규식 모듈 레벨 컴파일 캐싱
- [ ] `hybrid_extractor.py` pdf2image LRU 캐싱 (lazy loading)
- [ ] 크롭 이미지 numpy array 재사용
- [ ] Gemini 가격 최신화 + env 오버라이드 지원
- [ ] 성능 벤치마크 스크립트 작성

**영향 범위:** `extractors/`, `utils/usage_tracker.py`, `config.py`

---

### 🟡 Phase 9: 아키텍처 개선 (P1 - High)
**목표:** 확장성 향상, 코드 중복 제거, 유지보수성 증대
**예상 기간:** 3주

**주요 작업:**
- [ ] 엔진 팩토리 패턴 도입 (`engines/factory.py`)
- [ ] 파이프라인 클래스 캡슐화 (`pipelines/full_pipeline.py`)
- [ ] `parsers/` `TypedDict` 도입으로 타입 안정성 확보
- [ ] `main.py` (786줄) 함수 분리 및 정리
- [ ] API 키 로그 마스킹 구현
- [ ] 입력 검증 강화 (파일 크기, 텍스트 길이)

**영향 범위:** `engines/`, `pipelines/` (신규), `parsers/`, `main.py`, `config.py`

---

### 🟢 Phase 10: 범용화 - 입력 형식 확장 (P2 - Medium)
**목표:** PDF 외 다양한 문서 형식 지원
**예상 기간:** 4주

**주요 작업:**
- [ ] HWPX (한컴) 추출기 (`extractors/hwpx_extractor.py`)
- [ ] DOCX 추출기 (`extractors/docx_extractor.py`)
- [ ] 이미지(PNG/JPG) 직접 OCR 지원
- [ ] 스캔 PDF 자동 감지 및 OCR 강제 전환
- [ ] 입력 형식 통합 디스패처 (`_get_extractor()`)

**영향 범위:** `extractors/`, `main.py`, `detector.py`

---

### 🟢 Phase 11: 범용화 - 프리셋 & 배포 (P2 - Medium)
**목표:** 서드파티 기여 가능 구조, PyPI 배포
**예상 기간:** 4주

**주요 작업:**
- [ ] 프리셋 레지스트리 패턴 (`presets/registry.py`)
- [ ] 동적 프리셋 로딩 (`importlib`)
- [ ] CLI 설정 마법사 (`python -m ps_docparser setup`)
- [ ] `pyproject.toml` 정비
- [ ] `setup.py` → `hatch`/`poetry` 전환 검토
- [ ] MkDocs 또는 Sphinx 문서화
- [ ] macOS 호환성 완비 (Homebrew 경로)
- [ ] PyPI 배포 준비

**영향 범위:** `presets/`, `pyproject.toml` (신규), `docs/` (신규)

---

### 📋 페이즈별 의존성 관계

```
Phase 6 (안정화) ──┐
                   ├─→ Phase 8 (성능)
Phase 7 (테스트) ──┤
                   └─→ Phase 9 (아키텍처) ──→ Phase 10 (입력확장) ──→ Phase 11 (범용화/배포)
```

**병렬 가능:** Phase 6 ↔ Phase 7 동시 진행 가능
**순차 필수:** Phase 9 → Phase 10 → Phase 11

---

### 📌 페이즈별 산출물 목록

| 페이즈 | 코드 | 문서 | 테스트 |
|-------|------|------|-------|
| Phase 6 | 수정 3파일 | 상세 기술서 | 기본 확인 |
| Phase 7 | `tests/` 신규 | 테스트 가이드 | 50%+ 커버리지 |
| Phase 8 | 수정 4파일 | 벤치마크 보고서 | 성능 회귀 테스트 |
| Phase 9 | `engines/factory.py`, `pipelines/` 신규 | 아키텍처 문서 | 리팩터링 테스트 |
| Phase 10 | `hwpx_extractor.py`, `docx_extractor.py` 신규 | 입력 형식 가이드 | 형식별 테스트 |
| Phase 11 | `registry.py`, `pyproject.toml` | 사용자 매뉴얼 | 통합 E2E 테스트 |

---

**각 페이즈별 상세 구현 기술서는 별도 문서로 작성 예정.**

---

**리뷰 완료일:** 2026년 4월 17일
**리뷰 범위:** 매우 철저함 (Very Thorough)
**추천 액션:** Phase 6~7 즉시 시작 (병렬), 이후 Phase 8~11 순차 진행
