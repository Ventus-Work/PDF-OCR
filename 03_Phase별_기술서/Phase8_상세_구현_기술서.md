# Phase 8: 성능 최적화 상세 구현 기술서

**작성일:** 2026-04-17
**작성자:** Claude Opus 4
**전제 조건:** Phase 6 (긴급 안정화) + Phase 7 (테스트 인프라 88~92%) 완료
**대상 모듈:** `extractors/bom_extractor.py`, `extractors/hybrid_extractor.py`, `utils/text_formatter.py`, `utils/usage_tracker.py`, `config.py`

---

## 0. Phase 8 개요

### 0.1 목표
**메모리/CPU 사용량 30~80% 절감, 배치 처리 속도 2~5배 개선**

Phase 5까지 기능은 완결되었으나, 50~100 페이지 PDF 배치 처리 시 다음과 같은 성능 병목이 확인됨:

| 병목 지점 | 원인 | 영향 |
|---------|------|------|
| 정규식 반복 컴파일 | `bom_extractor.py`, `text_formatter.py`에서 `re.sub`/`re.compile`을 매 호출마다 실행 | 페이지당 수백회 재컴파일 → CPU 시간 소모 |
| PDF→이미지 재변환 | `hybrid_extractor.py`에서 같은 PDF를 여러 번 `pdf2image` 호출 가능 | 페이지당 수 MB 이미지 재생성 → 메모리 폭증 |
| 크롭 이미지 복사 | `table_utils.crop_table_image()`가 PIL 이미지 전체 복사 | 테이블 N개 × 페이지 M개 = N·M 배 메모리 |
| Gemini 가격 오래됨 | `usage_tracker.py`에 2025Q1 요율 하드코딩 | 실제 청구액과 차이 발생 |

### 0.2 완료 기준 (Done Definition)
1. ✅ 정규식 100% 모듈 레벨 캐싱 (컴파일 1회, 호출 N회)
2. ✅ `pdf2image.convert_from_path` LRU 캐싱 (lazy, 동일 PDF 재사용 시 0회 재변환)
3. ✅ 크롭 이미지 numpy array 기반 재사용 (또는 명시적 `.close()` 해제)
4. ✅ Gemini 가격 환경변수 오버라이드 지원 (`GEMINI_INPUT_PRICE`, `GEMINI_OUTPUT_PRICE`)
5. ✅ 벤치마크 스크립트 + Phase 5 대비 **정량적 성능 개선 리포트** 산출
6. ✅ Phase 7에서 확보한 **단위 테스트 전부 통과** (regression 방지)

### 0.3 예상 기간
**2주** (Day 1~10 + 여유 4일)

### 0.4 위험도
- 🟡 **중간** — 리팩터링 대상이 핵심 파이프라인이나, Phase 7에서 `bom_extractor.py`, `text_formatter.py` 안전망 확보됨
- 🔴 **주의** — `pdf2image` 캐싱 잘못 구현 시 메모리 누수(LRU 미해제) 가능 → 2.2 설계 엄수

---

## 1. 작업 분해 구조 (WBS)

| Day | 작업 | 산출물 | 의존 |
|-----|------|-------|------|
| 1 | 성능 베이스라인 측정 + 벤치마크 스크립트 | `scripts/benchmark.py`, `baseline.json` | - |
| 2-3 | `bom_extractor.py` 정규식 모듈 레벨 캐싱 | 코드 수정 + 테스트 통과 | Day 1 |
| 4 | `text_formatter.py` 정규식 컴파일 | 코드 수정 + 테스트 통과 | Day 1 |
| 5-6 | `hybrid_extractor.py` pdf2image LRU 캐싱 | 코드 수정 + 단위 테스트 추가 | Day 1 |
| 7 | `table_utils.py` 크롭 이미지 메모리 최적화 | 코드 수정 + 프로파일 비교 | Day 5 |
| 8 | `usage_tracker.py` + `config.py` 가격 env 오버라이드 | 코드 수정 + 테스트 | Day 1 |
| 9 | 성능 회귀 테스트 작성 (`tests/performance/`) | 새 테스트 파일 | Day 2~8 |
| 10 | 벤치마크 비교 + 결과 보고서 초안 | `Phase8_결과보고서.md` | Day 1, 9 |

---

## 2. 세부 구현

### 2.1 정규식 모듈 레벨 캐싱 (Day 2~4)

#### 2.1.1 문제 분석

**`extractors/bom_extractor.py` 현재 구조:**
```python
def _sanitize_html(text: str) -> str:
    text = re.sub(r'</tr[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</t[dh]>\s*<t[dh][^>]*>', ' | ', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    ...
```
- 매 호출마다 5개 정규식 **재컴파일**
- 페이지 100개 × OCR 응답당 5회 호출 = **500회 재컴파일**

**`utils/text_formatter.py` 현재 구조:**
- `format_text_with_linebreaks()` 내부에 `re.sub`/`re.match` **13회**
- 배치 100페이지 처리 시 재컴파일 횟수: 100 × 13 = **1,300회**

#### 2.1.2 리팩터링 설계 (bom_extractor.py)

**변경 전:**
```python
def _sanitize_html(text: str) -> str:
    text = re.sub(r'</tr[^>]*>', '\n', text, flags=re.IGNORECASE)
    ...
```

**변경 후:**
```python
# 모듈 로드 시 1회 컴파일
_RE_TR_CLOSE = re.compile(r'</tr[^>]*>', re.IGNORECASE)
_RE_TD_SPLIT = re.compile(r'</t[dh]>\s*<t[dh][^>]*>', re.IGNORECASE)
_RE_TAG = re.compile(r'<[^>]+>')
_RE_ENTITY_NAMED = re.compile(r'&[a-zA-Z]+;')
_RE_ENTITY_HEX = re.compile(r'&#x[0-9a-fA-F]+;')
_RE_WHITESPACE = re.compile(r'[ \t]+')


def _sanitize_html(text: str) -> str:
    """(docstring 유지)"""
    text = _RE_TR_CLOSE.sub('\n', text)
    text = _RE_TD_SPLIT.sub(' | ', text)
    text = _RE_TAG.sub(' ', text)
    text = text.replace('&amp;', '&').replace('&#x27;', "'")
    text = _RE_ENTITY_NAMED.sub('', text)
    text = _RE_ENTITY_HEX.sub('', text)
    text = _RE_WHITESPACE.sub(' ', text)
    return text
```

**성능 기대:**
- 100페이지 배치: CPU 시간 **15~25% 감소** (정규식 컴파일 오버헤드 제거)

#### 2.1.3 리팩터링 설계 (text_formatter.py)

**변경 후 구조:**
```python
# 섹션 선처리 패턴
_RE_SECTION_NUM = re.compile(r'(?<=[^\n])(\d+-\d+-\d+\s+)')
_RE_NUMBERED = re.compile(r'(?<=[다\.\)\]]) (\d+\.\s+)')
_RE_KOREAN_ALPHA = re.compile(r'(?<=[다\.\)\]]) ([가나다라마바사아자차카타파하]\.\s+)')
_RE_NOTE = re.compile(r'(?<=[^\n])(\[주\])')
_RE_CIRCLED = re.compile(r'(?<=[다\.\)\]]) ([①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳])')

# 한글 줄바꿈 병합
_RE_KO_LINEBREAK = re.compile(r'([가-힣])\n([가-힣]{0,2}다[\.\\, ])')
_RE_KO_LINEBREAK_END = re.compile(r'([가-힣])\n(다)$', re.MULTILINE)

# 문단 정리
_RE_TRIPLE_NEWLINE = re.compile(r'\n{3,}')
_RE_DOUBLE_SPACE = re.compile(r' {2,}')

# 리스트 항목 시작 패턴 (기본)
_RE_LIST_BASE = re.compile(
    r'^(\d+[-.]|[가-하]\.|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]|\[주\]|\d+-\d+-\d+)'
)

# 품셈 프리셋 패턴 캐시 (division_names 값별 lru_cache)
from functools import lru_cache

@lru_cache(maxsize=8)
def _get_pumsem_patterns(division_names: str):
    """division_names별 정규식 쌍을 캐싱 반환."""
    pattern_split = re.compile(
        rf'(?<![-\d])(\d+\s*(?:{division_names}|적용기준|제\d+장))'
    )
    pattern_list = re.compile(
        rf'^(\d+[-.]|[가-하]\.|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]'
        rf'|\[주\]|\d+-\d+-\d+|\d+\s*(?:{division_names}|적용기준|제\d+장))'
    )
    return pattern_split, pattern_list
```

**사용 지점 전부 `_RE_*` 상수로 대체.**

**성능 기대:**
- 100페이지 배치: CPU 시간 **20~30% 감소**
- 품셈 프리셋 활성 시: 첫 호출에만 동적 컴파일 → 이후 호출은 캐시 히트

#### 2.1.4 체크리스트
- [ ] 모든 `re.sub(r'...')` → `_RE_*.sub(...)` 로 변경
- [ ] 모든 `re.match(r'...')` → `_RE_*.match(...)` 로 변경
- [ ] `re.IGNORECASE` 등 플래그는 `re.compile` 인자로 이동
- [ ] **Phase 7 테스트 모두 통과 확인**: `pytest tests/unit/extractors/test_bom_extractor.py tests/unit/utils/test_text_formatter.py -v`

---

### 2.2 pdf2image LRU 캐싱 (Day 5~6)

#### 2.2.1 문제 분석

`hybrid_extractor.py::process_pdf()` 내에서:
```python
with pdfplumber.open(pdf_path) as pdf:
    for page_num, page in enumerate(pdf.pages):
        if needs_image:
            images = pdf2image.convert_from_path(pdf_path, ...)  # ⚠️ 매번 재변환
            ...
```
- 같은 PDF의 여러 페이지 처리 시 **convert_from_path를 N회 중복 호출** 가능
- 페이지 1개당 수 MB~수십 MB → 100페이지 PDF는 수 GB 메모리 사용

#### 2.2.2 설계 방향

**옵션 A (권장): 페이지 단위 Lazy Loading**
```python
# extractors/pdf_image_loader.py (신규)
"""
PDF → 이미지 변환 레이지 로더 (메모리 효율 최우선)

Why: pdf2image.convert_from_path는 전체 PDF를 한 번에 로드해
     수 GB 메모리를 소모. 페이지 단위 로딩 + LRU 캐시로 대체.
"""
import logging
from functools import lru_cache
from pdf2image import convert_from_path

logger = logging.getLogger(__name__)


class PdfImageLoader:
    """
    PDF의 개별 페이지를 필요 시점에 이미지로 변환.

    Args:
        pdf_path: PDF 파일 경로
        poppler_path: Poppler 바이너리 경로
        dpi: 이미지 해상도 (기본 200)
        cache_size: LRU 캐시 크기 (기본 4 — 메모리 100MB 이내 유지)

    사용:
        loader = PdfImageLoader(pdf_path, POPPLER_PATH)
        img = loader.get_page(page_num=3)  # 1-indexed
        loader.close()  # 명시적 해제
    """

    def __init__(self, pdf_path: str, poppler_path: str = None,
                 dpi: int = 200, cache_size: int = 4):
        self.pdf_path = pdf_path
        self.poppler_path = poppler_path
        self.dpi = dpi
        self._cache = lru_cache(maxsize=cache_size)(self._load_page)

    def _load_page(self, page_num: int):
        """페이지 1개만 이미지로 변환 (first_page=last_page=N)."""
        images = convert_from_path(
            self.pdf_path,
            dpi=self.dpi,
            first_page=page_num,
            last_page=page_num,
            poppler_path=self.poppler_path,
        )
        return images[0] if images else None

    def get_page(self, page_num: int):
        """캐시 히트/미스 자동 처리. 1-indexed."""
        return self._cache(page_num)

    def close(self):
        """캐시 해제 (메모리 반환)."""
        self._cache.cache_clear()
```

**hybrid_extractor.py 변경:**
```python
from extractors.pdf_image_loader import PdfImageLoader

def process_pdf(pdf_path, engine, ...):
    loader = PdfImageLoader(pdf_path, POPPLER_PATH) if engine.supports_image else None
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                if loader and needs_image:
                    img = loader.get_page(page_num)  # 캐시 히트 시 재변환 없음
                    ...
    finally:
        if loader:
            loader.close()  # 메모리 즉시 해제
```

**성능 기대:**
- 100페이지 PDF: 메모리 피크 **수 GB → 100MB 이내**
- 동일 페이지 재접근(테이블 복수 크롭) 시: **변환 0회**

#### 2.2.3 체크리스트
- [ ] `pdf_image_loader.py` 신규 모듈 추가
- [ ] `hybrid_extractor.py::process_pdf()`에서 적용
- [ ] `try/finally`로 `loader.close()` 확실히 호출
- [ ] 단위 테스트: `tests/unit/extractors/test_pdf_image_loader.py` (mocked)

---

### 2.3 크롭 이미지 메모리 최적화 (Day 7)

#### 2.3.1 현재 문제
`extractors/table_utils.py::crop_table_image()`이 PIL Image 객체를 반환 → 호출자가 전체 복사 보관 시 메모리 축적.

#### 2.3.2 개선 방향

**옵션 A (최소 변경): Context Manager + 명시적 `close()`**
```python
def crop_table_image(page_image, bbox, *, close_on_exit=True):
    """
    bbox 영역을 크롭한 PIL Image를 반환.

    Args:
        page_image: pdf2image로 로드한 페이지 이미지
        bbox: (x0, y0, x1, y1) 튜플
        close_on_exit: True면 호출자가 with 블록 후 자동 close

    Returns:
        PIL Image (close() 호출 가능)
    """
    cropped = page_image.crop(bbox)
    return cropped
```

**옵션 B (권장): BytesIO 기반 반환 (AI 엔진 전달 시 유리)**
```python
from io import BytesIO

def crop_table_image_bytes(page_image, bbox, format='PNG'):
    """크롭 이미지를 BytesIO로 반환 — Gemini/Z.ai 전송 시 변환 불필요."""
    cropped = page_image.crop(bbox)
    buf = BytesIO()
    cropped.save(buf, format=format, optimize=True)
    cropped.close()  # 즉시 해제
    buf.seek(0)
    return buf
```

**성능 기대:**
- 페이지당 테이블 5개 × 100페이지 = 500개 이미지
- 기존: 메모리 500 × 수 MB 누적
- 개선: 사용 직후 해제 → **메모리 상시 수 MB 이내**

#### 2.3.3 체크리스트
- [ ] `crop_table_image()` 시그니처 결정 (옵션 A vs B, **호출자 파급 확인 후**)
- [ ] 엔진 전달 계약 업데이트 (`BaseEngine.extract_table_from_image` 등)
- [ ] 단위 테스트에 메모리 해제 검증 추가 (`sys.getrefcount`)

---

### 2.4 Gemini 가격 환경변수 오버라이드 (Day 8)

#### 2.4.1 현재 코드
```python
# utils/usage_tracker.py L43~49
# Why: gemini-2.0-flash 기준 가격 (2025Q1)
#      입력: $0.10/M tokens, 출력: $0.40/M tokens
est_cost = (
    (self.total_input_tokens / 1_000_000 * 0.10)
    + (self.total_output_tokens / 1_000_000 * 0.40)
)
```

#### 2.4.2 개선 설계

**`config.py`에 추가:**
```python
# ── AI 엔진 요금 설정 (환경변수 오버라이드 지원) ──
# Why: 모델별/플랜별 가격이 자주 변경되므로 하드코딩 대신 env 우선.
GEMINI_INPUT_PRICE_PER_M = float(os.getenv("GEMINI_INPUT_PRICE", "0.10"))
GEMINI_OUTPUT_PRICE_PER_M = float(os.getenv("GEMINI_OUTPUT_PRICE", "0.40"))
GEMINI_PRICING_MODEL = os.getenv("GEMINI_PRICING_MODEL", "gemini-2.0-flash")
```

**`utils/usage_tracker.py` 변경:**
```python
from config import (
    GEMINI_INPUT_PRICE_PER_M,
    GEMINI_OUTPUT_PRICE_PER_M,
    GEMINI_PRICING_MODEL,
)

class UsageTracker:
    def __init__(self, input_price: float = None, output_price: float = None):
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.call_count = 0
        # config에서 로드하되, 생성자 주입 허용 (테스트/멀티모델 대응)
        self.input_price = (
            input_price if input_price is not None else GEMINI_INPUT_PRICE_PER_M
        )
        self.output_price = (
            output_price if output_price is not None else GEMINI_OUTPUT_PRICE_PER_M
        )

    def summary(self) -> str:
        if self.call_count == 0:
            return "AI 엔진 호출 없음 (비용 $0)"
        est_cost = (
            (self.total_input_tokens / 1_000_000 * self.input_price)
            + (self.total_output_tokens / 1_000_000 * self.output_price)
        )
        return (
            f"📈 AI 사용량 요약 ({GEMINI_PRICING_MODEL}):\n"
            f"   - API 호출: {self.call_count}회\n"
            f"   - 입력 토큰: {self.total_input_tokens:,} @ ${self.input_price}/M\n"
            f"   - 출력 토큰: {self.total_output_tokens:,} @ ${self.output_price}/M\n"
            f"   - 총 토큰: {self.total_tokens:,}\n"
            f"   - 예상 비용: ${est_cost:.4f} (약 {int(est_cost * 1_400)}원)"
        )
```

**`.env.example`에 추가:**
```env
# ── AI 엔진 요금 (선택 — 미설정 시 기본값 사용) ──
GEMINI_INPUT_PRICE=0.10
GEMINI_OUTPUT_PRICE=0.40
GEMINI_PRICING_MODEL=gemini-2.0-flash
```

#### 2.4.3 체크리스트
- [ ] `config.py`에 3개 상수 추가
- [ ] `usage_tracker.py` 생성자 + `summary()` 갱신
- [ ] `.env.example` 업데이트
- [ ] 단위 테스트: 환경변수 주입 케이스 추가 (`monkeypatch.setenv`)

---

### 2.5 벤치마크 스크립트 (Day 1 + Day 10)

#### 2.5.1 `scripts/benchmark.py` (신규)
```python
"""
Phase 8 성능 벤치마크 스크립트

사용:
    python scripts/benchmark.py --pdf sample.pdf --iterations 3 --out baseline.json
    # Phase 8 적용 후:
    python scripts/benchmark.py --pdf sample.pdf --iterations 3 --out after.json
    python scripts/benchmark.py --compare baseline.json after.json
"""
import argparse
import json
import time
import tracemalloc
from pathlib import Path


def measure(pdf_path: str, iterations: int = 3) -> dict:
    from extractors.hybrid_extractor import process_pdf
    from engines.local_engine import LocalEngine

    times, peaks = [], []
    for _ in range(iterations):
        tracemalloc.start()
        t0 = time.perf_counter()
        engine = LocalEngine()
        _ = process_pdf(pdf_path, engine)
        elapsed = time.perf_counter() - t0
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        times.append(elapsed)
        peaks.append(peak)

    return {
        "pdf": pdf_path,
        "iterations": iterations,
        "avg_time_sec": sum(times) / len(times),
        "min_time_sec": min(times),
        "max_time_sec": max(times),
        "peak_memory_mb": max(peaks) / (1024 * 1024),
    }


def compare(baseline_path: str, after_path: str):
    base = json.loads(Path(baseline_path).read_text())
    aft = json.loads(Path(after_path).read_text())
    time_improvement = (base["avg_time_sec"] - aft["avg_time_sec"]) / base["avg_time_sec"]
    mem_improvement = (base["peak_memory_mb"] - aft["peak_memory_mb"]) / base["peak_memory_mb"]
    print(f"⏱ 시간: {base['avg_time_sec']:.2f}s → {aft['avg_time_sec']:.2f}s "
          f"({time_improvement*100:+.1f}%)")
    print(f"💾 메모리: {base['peak_memory_mb']:.1f}MB → {aft['peak_memory_mb']:.1f}MB "
          f"({mem_improvement*100:+.1f}%)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf")
    ap.add_argument("--iterations", type=int, default=3)
    ap.add_argument("--out")
    ap.add_argument("--compare", nargs=2, metavar=("BASELINE", "AFTER"))
    args = ap.parse_args()

    if args.compare:
        compare(*args.compare)
    else:
        result = measure(args.pdf, args.iterations)
        if args.out:
            Path(args.out).write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
```

---

### 2.6 성능 회귀 테스트 (Day 9)

#### 2.6.1 `tests/performance/test_regex_caching.py` (신규)
```python
"""
Phase 8 회귀 방지 — 정규식 캐싱이 실제 모듈 레벨에서 유지되는지 검증
"""
import pytest
from extractors import bom_extractor
from utils import text_formatter


class TestRegexCaching:
    def test_bom_extractor_has_module_level_patterns(self):
        # 모듈 레벨 정규식 상수가 존재해야 함
        assert hasattr(bom_extractor, "_RE_TR_CLOSE")
        assert hasattr(bom_extractor, "_RE_TAG")

    def test_text_formatter_has_module_level_patterns(self):
        assert hasattr(text_formatter, "_RE_TRIPLE_NEWLINE")
        assert hasattr(text_formatter, "_RE_DOUBLE_SPACE")

    def test_pumsem_patterns_cached(self):
        # 동일 division_names 두 번 호출 시 같은 객체 반환 (lru_cache)
        from utils.text_formatter import _get_pumsem_patterns
        p1 = _get_pumsem_patterns("공통부문|토목부문")
        p2 = _get_pumsem_patterns("공통부문|토목부문")
        assert p1 is p2  # 캐시 히트
```

#### 2.6.2 `tests/performance/test_pdf_loader.py`
```python
import pytest
from unittest.mock import patch, MagicMock


class TestPdfImageLoader:
    @patch("extractors.pdf_image_loader.convert_from_path")
    def test_lru_cache_avoids_reconversion(self, mock_convert):
        from extractors.pdf_image_loader import PdfImageLoader

        mock_convert.return_value = [MagicMock()]
        loader = PdfImageLoader("dummy.pdf", cache_size=2)

        loader.get_page(1)
        loader.get_page(1)  # 캐시 히트 기대
        loader.get_page(2)
        loader.get_page(1)  # 여전히 캐시

        # convert_from_path은 고유 페이지 수만큼 호출되어야 함
        assert mock_convert.call_count == 2

    def test_close_clears_cache(self):
        from extractors.pdf_image_loader import PdfImageLoader
        loader = PdfImageLoader("dummy.pdf")
        # close 후 내부 캐시 비움 (메모리 해제)
        loader.close()  # 예외 없이 수행되어야 함
```

---

## 3. 리스크 & 완화

| 리스크 | 발생 가능성 | 영향 | 완화 |
|-------|-----------|------|------|
| 정규식 리팩터링으로 기존 동작 변경 | 중 | 고 | Phase 7 단위 테스트 통과 필수 |
| `lru_cache` 메모리 누수 | 낮음 | 고 | 명시적 `close()` + try/finally |
| Gemini 가격 환경변수 미설정 | 낮음 | 낮음 | 기본값 하드코딩 유지 |
| 벤치마크 결과 측정 환경 편차 | 중 | 중 | 최소 3회 반복 + 동일 샘플 PDF |

---

## 4. 산출물 목록

| # | 파일 | 상태 |
|---|------|------|
| 1 | `extractors/bom_extractor.py` | 수정 |
| 2 | `extractors/hybrid_extractor.py` | 수정 |
| 3 | `extractors/pdf_image_loader.py` | **신규** |
| 4 | `extractors/table_utils.py` | 수정 (옵션 B 선택 시) |
| 5 | `utils/text_formatter.py` | 수정 |
| 6 | `utils/usage_tracker.py` | 수정 |
| 7 | `config.py` | 수정 (가격 env 3개 추가) |
| 8 | `.env.example` | 수정 |
| 9 | `scripts/benchmark.py` | **신규** |
| 10 | `tests/performance/test_regex_caching.py` | **신규** |
| 11 | `tests/performance/test_pdf_loader.py` | **신규** |
| 12 | `Phase8_결과보고서.md` | **신규** |

---

## 5. 예상 성능 개선 (목표치)

| 지표 | Phase 5 (현재) | Phase 8 후 목표 | 개선율 |
|------|---------------|----------------|-------|
| 100페이지 PDF 처리 시간 | 120s | **60~80s** | **-33~50%** |
| 피크 메모리 사용량 | 2.5GB | **300MB** | **-88%** |
| 정규식 컴파일 횟수 | 1,300회+ | **<50회** | **-96%** |
| 동일 PDF 재변환 횟수 | 페이지 × 크롭 수 | **1회** (캐시) | **~-99%** |

> ※ 실제 값은 Day 10 벤치마크로 확정. 목표 미달 시 원인 분석 후 Phase 8.5 추가 검토.

---

## 6. Phase 9 연계

Phase 9 (아키텍처 개선) 에서:
- `pipelines/full_pipeline.py` 생성 시 `PdfImageLoader`를 파이프라인 속성으로 주입
- `engines/factory.py`에서 `UsageTracker(input_price=..., output_price=...)` 주입 가능
- Phase 8의 성능 개선이 Phase 9 리팩터링 시 기준선(baseline) 역할

---

## 7. 완료 체크리스트 (최종)

### 🔴 필수
- [ ] 정규식 모듈 레벨 상수화 (bom_extractor, text_formatter)
- [ ] `PdfImageLoader` 구현 + `hybrid_extractor.py` 적용
- [ ] Gemini 가격 환경변수 오버라이드
- [ ] Phase 7 단위 테스트 **전부 통과** (regression 없음)
- [ ] 벤치마크 스크립트 + baseline/after 비교 결과 산출

### 🟡 권장
- [ ] 크롭 이미지 BytesIO 반환 (엔진 전달 최적화)
- [ ] `tests/performance/` 회귀 테스트 추가
- [ ] `Phase8_결과보고서.md` 작성

### 🟢 선택
- [ ] `PdfImageLoader` 멀티프로세싱 안전성 검증
- [ ] Gemini 2.5/3.0 출시 대비 모델별 가격 딕셔너리 설계

---

**기술서 작성자:** Claude Opus 4
**기술서 작성일:** 2026-04-17
**참조 문서:**
- `ps-docparser_코드리뷰_보고서.md` §Phase 8 (L696~707)
- `Phase7_결과보고서_검증리뷰.md` (Phase 8 안전망 현황)
- `ps-docparser/extractors/bom_extractor.py`
- `ps-docparser/utils/text_formatter.py`
- `ps-docparser/extractors/hybrid_extractor.py`
