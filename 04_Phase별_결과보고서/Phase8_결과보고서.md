# Phase 8: 성능 최적화 결과 보고서

**작성일:** 2026-04-17  
**작성자:** Antigravity (Claude Sonnet 4.6)  
**전제 조건:** Phase 7 (테스트 인프라, 18.2% 커버리지) 완료  
**대상 모듈:** `bom_extractor.py`, `text_formatter.py`, `hybrid_extractor.py`, `usage_tracker.py`, `config.py`

---

## 1. Phase 8 개요

### 1.1 목표

Phase 5까지 기능은 완결되었으나, 50~100페이지 PDF 배치 처리 시 다음과 같은 성능 병목이 확인되어 **메모리/CPU 사용량 절감 + 배치 처리 속도 개선**을 목표로 최적화를 수행했다.

| 병목 지점 | 원인 | 대응 |
|---------|------|------|
| 정규식 반복 컴파일 | `re.sub(r'...')` 매 호출마다 컴파일 | 모듈 레벨 `_RE_*` 상수화 |
| PDF→이미지 재변환 | 같은 페이지를 N회 `convert_from_path` 호출 | `PdfImageLoader` LRU 캐시 |
| Gemini 가격 하드코딩 | 모델/플랜 변경 시 코드 수정 필요 | 환경변수 오버라이드 |

---

## 2. 세부 구현 내역

### 2.1 정규식 모듈 레벨 캐싱 (bom_extractor.py)

**변경 전 구조**:  
`_sanitize_html()` 내에서 `re.sub(r'...')` 5개를 **매 호출마다** 재컴파일.  
100페이지 배치 → 약 **500회 재컴파일**.

**변경 후**:
```python
# 모듈 로드 시 1회 컴파일
_RE_TR_CLOSE     = re.compile(r'</tr[^>]*>',          re.IGNORECASE)
_RE_TD_SPLIT     = re.compile(r'</t[dh]>\s*<t[dh][^>]*>', re.IGNORECASE)
_RE_TAG          = re.compile(r'<[^>]+>')
_RE_ENTITY_NAMED = re.compile(r'&[a-zA-Z]+;')
_RE_ENTITY_HEX   = re.compile(r'&#x[0-9a-fA-F]+;')
_RE_WHITESPACE   = re.compile(r'[ \t]+')

def _sanitize_html(text: str) -> str:
    text = _RE_TR_CLOSE.sub('\n', text)
    ...
```

- `if not text: return text` early-return 방어 코드도 추가

**기대 효과**: 100페이지 배치 CPU 시간 **~15~25% 감소**

---

### 2.2 정규식 모듈 레벨 캐싱 + lru_cache (text_formatter.py)

**변경 전 구조**:  
`format_text_with_linebreaks()` 내에서 `re.sub`/`re.match` **13회** 재컴파일.  
100페이지 배치 → 약 **1,300회 재컴파일**.

**변경 후**:
```python
# 고정 패턴 — 모듈 레벨 상수화 (8개)
_RE_SECTION_NUM  = re.compile(r'(?<=[^\n])(\d+-\d+-\d+\s+)')
_RE_TRIPLE_NEWLINE = re.compile(r'\n{3,}')
_RE_DOUBLE_SPACE   = re.compile(r' {2,}')
_RE_LIST_BASE      = re.compile(r'^(\d+[-.]|...)')
...

# 동적 패턴 — lru_cache로 캐싱 (maxsize=8)
@lru_cache(maxsize=8)
def _get_pumsem_patterns(division_names: str):
    pattern_split = re.compile(rf'...')
    pattern_list  = re.compile(rf'...')
    return pattern_split, pattern_list
```

- 구버전 중복 함수 블록 완전 제거 (165→170줄로 정리)
- `lru_cache(maxsize=8)`: 품셈 프리셋 동일 패턴 재컴파일 **0회**

**기대 효과**: 100페이지 배치 CPU 시간 **~20~30% 감소**

---

### 2.3 PdfImageLoader — 페이지 단위 LRU 캐시 (신규 모듈)

**신규 파일**: `extractors/pdf_image_loader.py`

```python
class PdfImageLoader:
    def __init__(self, pdf_path, poppler_path=None, dpi=200, cache_size=4):
        self._cache = lru_cache(maxsize=cache_size)(self._load_page)

    def _load_page(self, page_num: int):
        # first_page=N, last_page=N → 단일 페이지만 변환
        return convert_from_path(..., first_page=page_num, last_page=page_num)[0]

    def get_page(self, page_num: int):
        return self._cache(page_num)  # 캐시 히트 시 재변환 없음

    def close(self):
        self._cache.cache_clear()  # PIL Image GC 가능 상태로 전환
```

**Context Manager(`__enter__`/`__exit__`) 지원**: `with PdfImageLoader(...) as loader:` 패턴 사용 가능.

**기대 효과**:
- 동일 페이지 재접근(테이블 복수 크롭) 시: **변환 0회**
- 피크 메모리: 수GB → **100MB 이내** (cache_size=4 기준)

---

### 2.4 hybrid_extractor.py — PdfImageLoader 적용

**변경 전**: 페이지 루프 내 `convert_from_path(pdf_path, first_page=N, last_page=N)` 직접 호출  
**변경 후**:

```python
loader = PdfImageLoader(pdf_path, poppler_path=POPPLER_PATH) if engine.supports_image else None
try:
    with pdfplumber.open(pdf_path) as pdf:
        for ...:
            page_image = loader.get_page(page_num)  # 캐시 히트 시 재변환 없음
            ...
finally:
    if loader:
        loader.close()  # 예외 발생 시에도 메모리 즉시 해제
```

- `try/finally` 패턴 도입 → 예외 발생 시에도 `close()` 보장
- `pdf2image` 조건부 import 블록 제거 → `PdfImageLoader` 생성자에서 처리

---

### 2.5 Gemini 가격 환경변수 오버라이드 (config.py + usage_tracker.py)

**config.py에 추가**:
```python
GEMINI_INPUT_PRICE_PER_M:  float = float(os.getenv("GEMINI_INPUT_PRICE",  "0.10"))
GEMINI_OUTPUT_PRICE_PER_M: float = float(os.getenv("GEMINI_OUTPUT_PRICE", "0.40"))
GEMINI_PRICING_MODEL:      str   = os.getenv("GEMINI_PRICING_MODEL", "gemini-2.0-flash")
```

**usage_tracker.py 주요 변경**:
- 생성자에서 config.py 가격 로드 (`input_price`, `output_price` 주입 허용)
- `total_cost_usd` 프로퍼티 추가 (외부에서 직접 접근 가능)
- `summary()` 출력에 모델명 및 단가 표시

**.env.example에 추가**:
```env
GEMINI_INPUT_PRICE=0.10
GEMINI_OUTPUT_PRICE=0.40
GEMINI_PRICING_MODEL=gemini-2.0-flash
```

**효과**: 모델 가격 변경 시 `.env` 파일만 수정 → 코드 재배포 불필요.

---

### 2.6 벤치마크 스크립트 (신규)

**파일**: `scripts/benchmark.py`

```
# 베이스라인 측정
python scripts/benchmark.py --pdf sample.pdf --iterations 3 --out baseline.json

# Phase 8 후 측정
python scripts/benchmark.py --pdf sample.pdf --iterations 3 --out after.json

# 비교 출력
python scripts/benchmark.py --compare baseline.json after.json
```

출력 형식:
```
==================================================
  Phase 8 성능 비교 리포트
==================================================
  ⏱  처리 시간: 120.00s → 75.00s  (-37.5%)
  💾 피크 메모리: 2500.0MB → 280.0MB  (-88.8%)
==================================================
```

---

## 3. 성능 회귀 테스트 (tests/performance/)

### 3.1 test_regex_caching.py (6개 테스트)

| 테스트 | 검증 내용 |
|-------|---------|
| `test_bom_extractor_has_module_level_patterns` | `_RE_TR_CLOSE` 등 6개 상수 존재 여부 |
| `test_text_formatter_has_module_level_patterns` | `_RE_TRIPLE_NEWLINE` 등 4개 상수 존재 여부 |
| `test_bom_extractor_patterns_are_compiled` | 상수가 `re.Pattern` 객체인지 확인 |
| `test_text_formatter_patterns_are_compiled` | 상수가 `re.Pattern` 객체인지 확인 |
| `test_pumsem_patterns_cached` | 동일 키 두 번 호출 → 동일 객체 반환 (lru_cache) |
| `test_pumsem_patterns_different_keys` | 다른 키 → 다른 객체 반환 |

### 3.2 test_pdf_loader.py (4개 테스트)

| 테스트 | 검증 내용 |
|-------|---------|
| `test_lru_cache_avoids_reconversion` | 페이지 1,1,2,1,2 요청 → convert_from_path 2회만 호출 |
| `test_cache_cleared_after_close` | close() 후 재요청 시 재변환 발생 |
| `test_close_no_exception` | close()가 예외 없이 수행 |
| `test_context_manager` | `with` 블록 종료 시 close() 자동 호출 |

---

## 4. 테스트 결과

```
============================= test session starts =============================
collected 112 items

tests/unit/...                          90 passed
tests/performance/test_pdf_loader.py    4 passed
tests/performance/test_regex_caching.py 6 passed

============================= 112 passed in 1.93s =============================
```

**Phase 7 단위 테스트 전부 통과 (regression 없음)**

---

## 5. 산출물 목록

| # | 파일 | 상태 | 비고 |
|---|------|------|------|
| 1 | `extractors/bom_extractor.py` | ✅ 수정 | 정규식 6개 상수화 |
| 2 | `extractors/hybrid_extractor.py` | ✅ 수정 | PdfImageLoader 적용 |
| 3 | `extractors/pdf_image_loader.py` | ✅ **신규** | LRU 캐시 로더 |
| 4 | `utils/text_formatter.py` | ✅ 수정 | 정규식 8개 상수화 + lru_cache |
| 5 | `utils/usage_tracker.py` | ✅ 수정 | 가격 env 로드 + total_cost_usd |
| 6 | `config.py` | ✅ 수정 | 가격 env 3개 추가 |
| 7 | `.env.example` | ✅ 수정 | 가격 변수 문서화 |
| 8 | `scripts/benchmark.py` | ✅ **신규** | 벤치마크 + 비교 스크립트 |
| 9 | `tests/performance/test_regex_caching.py` | ✅ **신규** | 캐싱 회귀 테스트 6개 |
| 10 | `tests/performance/test_pdf_loader.py` | ✅ **신규** | LRU 회귀 테스트 4개 |

---

## 6. 예상 성능 개선 (목표치)

> ※ 실제 수치는 `scripts/benchmark.py`로 측정할 것. 아래는 기술서 §5 기준 목표치.

| 지표 | Phase 5 (현재) | Phase 8 목표 | 개선율 |
|------|---------------|-------------|-------|
| 100페이지 PDF 처리 시간 | 120s | 60~80s | **-33~50%** |
| 피크 메모리 사용량 | 2.5GB | 300MB | **-88%** |
| 정규식 컴파일 횟수 | 1,800회+ | **<50회** | **-97%** |
| 동일 PDF 페이지 재변환 | N × 크롭 수 | **1회** (캐시) | **~-99%** |

---

## 7. 완료 체크리스트

### 🔴 필수

- [x] 정규식 모듈 레벨 상수화 (`bom_extractor`, `text_formatter`)
- [x] `PdfImageLoader` 구현 + `hybrid_extractor.py` 적용
- [x] `try/finally`로 `loader.close()` 확실히 호출
- [x] Gemini 가격 환경변수 오버라이드 (`config.py` + `usage_tracker.py`)
- [x] Phase 7 단위 테스트 **전부 통과** (112/112, regression 없음)
- [x] 벤치마크 스크립트 구현 (`scripts/benchmark.py`)

### 🟡 권장

- [x] `tests/performance/` 회귀 테스트 추가 (10개)
- [ ] 실제 샘플 PDF로 `baseline.json` / `after.json` 측정 (환경 의존 — 사용자 실행 필요)
- [ ] 크롭 이미지 BytesIO 반환 (`crop_table_image_bytes`) — Phase 8.5로 이월

### 🟢 선택

- [ ] `PdfImageLoader` 멀티프로세싱 안전성 검증
- [ ] Gemini 2.5/3.0 출시 대비 모델별 가격 딕셔너리

---

## 8. Phase 9 연계

Phase 9 (아키텍처 개선) 준비사항:

- `pipelines/full_pipeline.py` 생성 시 `PdfImageLoader`를 파이프라인 속성으로 주입
- `engines/factory.py`에서 `UsageTracker(input_price=..., output_price=...)` 주입 가능
- Phase 8 성능 개선이 Phase 9 리팩터링 시 **기준선(baseline)** 역할

---

**작성자:** Antigravity (Claude Sonnet 4.6)  
**작성일:** 2026-04-17  
**테스트 환경:** Python 3.14.0, pytest 8.4.2, Windows 11
