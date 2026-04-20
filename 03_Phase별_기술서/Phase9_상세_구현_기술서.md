# Phase 9: 아키텍처 개선 상세 구현 기술서 (v2.1 개선판)

**작성일:** 2026-04-17
**작성자:** Claude Opus 4
**개정:** v1 (15일 WBS) → v2 (5-Step) → **v2.1 (리뷰 이슈 3건 + 제안 1건 반영)**
**전제 조건:** Phase 6~8 완료 (테스트 112개 통과 상태)
**대상 모듈:** `main.py`, `engines/`, `parsers/`, 신규 `pipelines/` + 6개 유틸 모듈 + `cli/args.py`

---

## 0. 개정 이력 (v1 → v2 → v2.1)

### v1 → v2
| 변경점 | v1 | v2 |
|-------|----|----|
| 일정 구조 | 15일 WBS (Day 1~15) | **5-Step 체크포인트** (단계별 커밋/검증) |
| `_process_single()` 이식 | 개괄 설명 | **L280~600 구간별 매핑 테이블** 추가 |
| 회귀 방지 | 단위 테스트 의존 | **Golden File E2E + 프리셋별 검증 매트릭스** 추가 |
| 롤백 전략 | 언급 없음 | **Git tag + Step별 커밋 롤백 절차** 명문화 |
| 프리셋 검증 | "회귀 검증" 단어만 | **bom/pumsem/estimate/범용 4종 개별 체크리스트** |

### v2 → v2.1 (리뷰 반영)

| # | 리뷰 이슈 | 근거 (실측) | v2.1 반영 지점 |
|---|---------|----------|--------------|
| **1** 🔴 | `DocumentPipeline`이 `zai/mistral/tesseract` 거부해야 함 | `main.py:434-448` — 표준 파이프라인은 `gemini`/`local`만 허용, 그 외 `ParserError` | §4.4에 `_validate_engine()` 추가 + 제약 명문화 |
| **2** 🟡 | `--no-cache` 옵션 부재 | `main.py:169` — 현재 `--force`만 존재, `--no-cache` grep 결과 0건 | §6.4 `args.no_cache` 사용 전제 제거 또는 argparse에 옵션 추가 결정 (§6.4-B) |
| **3** 🟡 | `bom_aggregator` 귀속 미결 | `main.py:703-741` — 배치 BOM 완료 시 `export_aggregated_excel()` 자동 호출 | §4.3 BomPipeline 책임 구분 + §6.3 매핑 테이블에 L703~741 행 추가 |
| **제안** | `_build_argument_parser()` 분리 필수화 | `main.py:92~173` = **82줄** → 분리 없이는 ≤350줄 불가 | Step 1 산출물에 `cli/args.py` 추가 + §6.4에서 "필수"로 격상 |

---

## 1. 현황 분석 (검증 완료)

### 1.1 실측치
```
main.py                  792줄
_process_single()        323줄 (L280~602, 단일 함수 내 프리셋 4분기 혼재)
```

### 1.2 프리셋 분기 위치
| 프리셋 | 분기 라인 | 특징 |
|-------|---------|------|
| `pumsem` | L328 | `division_names`, `parse_patterns`, `type_keywords` 로드 |
| `estimate` | L339 | `type_keywords` + `excel_config` 로드 |
| `bom` | L348 | 독립 파이프라인 (OCR → BOM 구조화 → 출력) |
| 범용(None) | L557 (암묵) | 모든 프리셋 None + MD 입력 시 폴백 |

### 1.3 핵심 문제 (변경 없음)
1. **엔진 생성 로직 갇힘** — `main.py::_create_engine()` 외부 재사용 불가
2. **`_process_single()` 혼재** — 프리셋별 분기가 한 함수에 뒤섞여 테스트 어려움
3. **타입 불안전** — 파서 반환 `list[dict]`, IDE 자동완성 불가
4. **보안 공백** — API 키 로그 마스킹 없음
5. **검증 공백** — 거대 PDF/긴 텍스트 입력 시 OOM 위험

---

## 2. 5-Step 구현 계획 (v2 핵심)

### 📋 단계 요약

| Step | 내용 | 신규 파일 | 수정 파일 | 위험도 | 체크포인트 |
|------|------|---------|---------|-------|---------|
| **1** | 신규 유틸리티 + `cli/args.py` 분리 | **7개** (v2.1) | 0개 | 🟢 낮음 | 112개 테스트 + 신규 **23개** |
| **2** | `pipelines/` 패키지 설계·구현 (`_validate_engine` 포함) | 5개 | 0개 | 🟡 중간 | Step 1 테스트 + 파이프라인 **10개** |
| **3** | `parsers/types.py` TypedDict 도입 | 1개 | 2개 (annotation) | 🟢 낮음 | mypy 통과 |
| **4** | **main.py 슬림화 792→≤350줄** | 0개 | 1개 (main.py) | 🔴 **높음** | **E2E Golden + 프리셋 4종** |
| **5** | 아키텍처·파이프라인 테스트 추가 | 6개 | 0개 | 🟢 낮음 | 180+개 테스트 통과 |

### 🚦 진행 원칙
1. **각 Step 완료 시 Git tag 또는 커밋** — 롤백 지점 확보
2. **직전 Step 테스트 통과 없이 다음 Step 진입 금지**
3. **Step 4 진입 전 필수 선행:** Step 1~3 완료 + **E2E Golden File 생성** (§2.4.1)

---

## 3. Step 1: 신규 유틸리티 분리 🟢

**기간:** 4~5일 | **위험:** 낮음 (모두 독립 모듈)

### 3.1 산출물 목록

| # | 파일 | 줄수 | 의존 |
|---|------|-----|------|
| 1.1 | `engines/factory.py` | 120 | `engines/base_engine` 만 |
| 1.2 | `utils/logging_utils.py` | 70 | stdlib only |
| 1.3 | `utils/validation.py` | 60 | stdlib only |
| 1.4 | `utils/tee.py` | 30 | stdlib only |
| 1.5 | `utils/paths.py` | 25 | stdlib only |
| 1.6 | `parsers/toc_loader.py` | 40 | `extractors/toc_parser` |
| **1.7** | **`cli/args.py`** (신규·v2.1 격상) | **~90** | argparse only (main.py L92~173 이식) |

> **제안 반영:** `_build_argument_parser()`는 현재 `main.py:92~173` = **82줄**. 이걸 분리하지 않으면 Step 4에서 main.py 350줄 목표 달성이 물리적으로 어려움. 따라서 v2.1에서 **선택 → 필수**로 격상.

### 3.1.1 `cli/args.py` 설계 요점

```python
# cli/args.py
import argparse
from config.paths import OUTPUT_DIR, DEFAULT_ENGINE


def build_argument_parser() -> argparse.ArgumentParser:
    """main.py L92~173 순수 이식 + Phase 9에서 `--no-cache` 추가."""
    parser = argparse.ArgumentParser(prog="ps-docparser", ...)
    # ... 기존 --engine, --text-only, --toc, --pages, --output-dir,
    #     --preset, --output, --force 그대로 복사 ...

    # 🆕 Phase 9 (v2.1 이슈 2 해결): --no-cache 옵션 신설
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="TableCache 비활성화 (디버깅/재처리 시)",
    )
    return parser
```

**원칙:** 기존 옵션은 **순수 복사** (동작 변경 금지). `--no-cache`만 신규 추가.

### 3.2 `engines/factory.py` — 레지스트리 팩토리

```python
"""
engines/factory.py — 엔진 팩토리 (데코레이터 + 레지스트리 패턴)

Why: main.py::_create_engine() 외부 분리 → OCP(개방폐쇄) 준수.
     신규 엔진 추가 시 @register_engine 데코레이터만 추가하면 끝.
"""
from typing import Callable, Protocol
from engines.base_engine import BaseEngine


class EngineSpec(Protocol):
    def __call__(self, tracker=None) -> BaseEngine: ...


_ENGINE_REGISTRY: dict[str, EngineSpec] = {}


def register_engine(name: str):
    def decorator(factory_func: EngineSpec):
        _ENGINE_REGISTRY[name] = factory_func
        return factory_func
    return decorator


@register_engine("gemini")
def _create_gemini(tracker=None) -> BaseEngine:
    import config
    from engines.gemini_engine import GeminiEngine
    if not config.GEMINI_API_KEY:
        raise ValueError(".env에 GEMINI_API_KEY가 설정되지 않았습니다.")
    return GeminiEngine(config.GEMINI_API_KEY, config.GEMINI_MODEL, tracker)


@register_engine("local")
def _create_local(tracker=None) -> BaseEngine:
    from engines.local_engine import LocalEngine
    return LocalEngine()


@register_engine("zai")
def _create_zai(tracker=None) -> BaseEngine:
    import config
    from engines.zai_engine import ZaiEngine
    if not config.ZAI_API_KEY:
        raise ValueError(".env에 ZAI_API_KEY가 설정되지 않았습니다.")
    return ZaiEngine(config.ZAI_API_KEY, tracker=tracker)


@register_engine("mistral")
def _create_mistral(tracker=None) -> BaseEngine:
    import config
    from engines.mistral_engine import MistralEngine
    if not config.MISTRAL_API_KEY:
        raise ValueError(".env에 MISTRAL_API_KEY가 설정되지 않았습니다.")
    return MistralEngine(config.MISTRAL_API_KEY, tracker=tracker)


@register_engine("tesseract")
def _create_tesseract(tracker=None) -> BaseEngine:
    import config
    from engines.tesseract_engine import TesseractEngine
    return TesseractEngine(tesseract_path=config.TESSERACT_PATH)


def create_engine(name: str, tracker=None) -> BaseEngine:
    if name not in _ENGINE_REGISTRY:
        available = ", ".join(sorted(_ENGINE_REGISTRY.keys()))
        raise ValueError(f"알 수 없는 엔진: {name} (사용 가능: {available})")
    return _ENGINE_REGISTRY[name](tracker=tracker)


def list_available_engines() -> list[str]:
    return sorted(_ENGINE_REGISTRY.keys())
```

### 3.3 `utils/logging_utils.py` — API 키 마스킹

```python
import logging
import re

_SECRET_PATTERNS = [
    (re.compile(r'(sk-[a-zA-Z0-9_\-]{20,})'), 'sk-***MASKED***'),
    (re.compile(r'(AIza[a-zA-Z0-9_\-]{35})'), 'AIza***MASKED***'),
    (re.compile(
        r'(["\']?(api_key|API_KEY|GEMINI_API_KEY|ZAI_API_KEY|MISTRAL_API_KEY)["\']?\s*[:=]\s*["\']?)([^"\'\s]{8,})'
    ), r'\1***MASKED***'),
]


def mask_secrets(text: str) -> str:
    if not text:
        return text
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class MaskingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = mask_secrets(record.msg)
        if record.args:
            record.args = tuple(
                mask_secrets(str(a)) if isinstance(a, str) else a
                for a in record.args
            )
        return True


def install_masking_filter(logger: logging.Logger = None):
    target = logger or logging.getLogger()
    if not any(isinstance(f, MaskingFilter) for f in target.filters):
        target.addFilter(MaskingFilter())
```

### 3.4 `utils/validation.py` — 입력 검증

```python
from pathlib import Path

MAX_PDF_SIZE_MB = 500
MAX_PAGES = 2000
MAX_TEXT_LENGTH = 10_000_000


class ValidationError(ValueError):
    """입력 검증 실패 (ParserError와 별도 — 재시도 불가)."""


def validate_pdf_path(path, max_size_mb: int = MAX_PDF_SIZE_MB) -> Path:
    p = Path(path)
    if not p.exists():
        raise ValidationError(f"파일을 찾을 수 없습니다: {path}")
    if not p.is_file():
        raise ValidationError(f"파일이 아닙니다: {path}")
    if p.suffix.lower() != ".pdf":
        raise ValidationError(f"PDF 파일이 아닙니다: {path}")
    size_mb = p.stat().st_size / (1024 * 1024)
    if size_mb > max_size_mb:
        raise ValidationError(
            f"PDF 크기 초과: {size_mb:.1f}MB > {max_size_mb}MB "
            f"(--max-size 옵션으로 상향 가능)"
        )
    return p


def validate_page_count(total_pages: int, max_pages: int = MAX_PAGES) -> None:
    if total_pages > max_pages:
        raise ValidationError(
            f"페이지 수 초과: {total_pages} > {max_pages} "
            f"(--pages 옵션으로 부분 처리 권장)"
        )


def validate_text_length(text: str, max_length: int = MAX_TEXT_LENGTH) -> None:
    if len(text) > max_length:
        raise ValidationError(f"텍스트 길이 초과: {len(text):,} > {max_length:,}")


def validate_output_dir(path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    test_file = p / ".write_check"
    try:
        test_file.touch()
        test_file.unlink()
    except (PermissionError, OSError) as e:
        raise ValidationError(f"출력 디렉토리 쓰기 불가: {path} ({e})")
    return p
```

### 3.5 Step 1 테스트 (23개, v2.1 +3개)

```
tests/unit/engines/test_factory.py         (5개)
tests/unit/utils/test_logging_utils.py     (6개)
tests/unit/utils/test_validation.py        (6개)
tests/unit/utils/test_tee.py               (2개)
tests/unit/utils/test_paths.py             (1개)
tests/unit/cli/test_args.py                (3개, v2.1 신규)
  ├─ test_build_parser_all_options_present
  ├─ test_no_cache_flag_default_false
  └─ test_no_cache_flag_enabled_when_passed
```

### ✅ Step 1 체크포인트
- [ ] 신규 7개 파일 생성 완료 (cli/args.py 포함)
- [ ] 신규 23개 테스트 통과
- [ ] **기존 112개 테스트 100% 통과** (회귀 없음)
- [ ] `cli/args.py`에 **기존 옵션 완전 복사** 확인 (regression 방지)
- [ ] `cli/args.py`에 `--no-cache` 옵션 신규 추가 확인
- [ ] `git tag phase9-step1-complete`
- [ ] `main.py` 여전히 792줄 (아직 수정 금지)

---

## 4. Step 2: `pipelines/` 패키지 🟡

**기간:** 5~7일 | **위험:** 중간 (파이프라인 설계 품질이 Step 4 성공 좌우)

### 4.1 산출물 목록

| # | 파일 | 줄수 | 역할 |
|---|------|-----|------|
| 2.1 | `pipelines/__init__.py` | 5 | 공개 API 노출 |
| 2.2 | `pipelines/base.py` | 80 | `PipelineContext` + `BasePipeline` ABC |
| 2.3 | `pipelines/bom_pipeline.py` | 150 | BOM 전용 (OCR→구조화→출력) |
| 2.4 | `pipelines/document_pipeline.py` | 180 | pumsem/estimate/범용 통합 |
| 2.5 | `pipelines/factory.py` | 25 | 프리셋 → 파이프라인 매핑 |

### 4.2 `pipelines/base.py`

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PipelineContext:
    """파이프라인 실행 컨텍스트 — 공유 상태 집중."""
    input_path: Path
    output_dir: Path
    args: object          # argparse.Namespace
    cache: object = None  # TableCache | None
    tracker: object = None


class BasePipeline(ABC):
    def __init__(self, context: PipelineContext):
        self.ctx = context

    @abstractmethod
    def run(self) -> None:
        """파이프라인 실행 (검증 → 추출 → 파싱 → 출력)."""

    # ── 공통 헬퍼 ──
    def _get_output_base(self, suffix: str = "") -> Path:
        from datetime import datetime
        date_str = datetime.now().strftime("%Y%m%d")
        return self.ctx.output_dir / f"{date_str}_{self.ctx.input_path.stem}{suffix}"

    def _resolve_pages(self) -> list[int] | None:
        if not self.ctx.args.pages:
            return None
        import pdfplumber
        from utils.page_spec import parse_page_spec
        with pdfplumber.open(str(self.ctx.input_path)) as pdf:
            total = len(pdf.pages)
        return parse_page_spec(self.ctx.args.pages, total)
```

### 4.3 `pipelines/bom_pipeline.py` — main.py L348~480 이식

**책임 범위:**
- ✅ **포함:** 단일 PDF OCR → BOM 구조화 → JSON/Excel 개별 파일 출력
- ❌ **제외 (v2.1 이슈 3 해결):** `export_aggregated_excel()` 배치 집계 로직

**`bom_aggregator` 귀속 결정표**

| 로직 | 원본 위치 | 귀속 | 근거 |
|-----|---------|------|------|
| `BomPipeline.run()` (개별 파일 처리) | main.py L348~480 | `pipelines/bom_pipeline.py` | 단일 책임 |
| 배치 집계 (L703~741) | main.py 배치 루프 안쪽 | **main.py 잔존 → `cli/batch_runner.py`로 이전 가능** | 배치 루프 자체가 main.py의 오케스트레이션 책임 |
| `exporters/bom_aggregator.py` | 기존 모듈 | **변경 없음** (기존 유지) | 이미 잘 분리된 상태 |

**결론:** `BomPipeline`은 **단일 PDF 1건만** 처리. 집계 로직은 main.py (또는 얇은 `cli/batch_runner.py`)에 남겨두고 `BomPipeline`을 n회 호출 후 후처리로 `export_aggregated_excel()`를 부른다.

```python
# main.py 잔존 (or cli/batch_runner.py) 예시
for pdf in pdf_files:
    pipeline = BomPipeline(ctx_for(pdf))
    result = pipeline.run()
    if result.ok:
        succeeded.append(pdf.name)

# 배치 완료 후 집계 (원본 L703~741 그대로)
if args.preset == "bom" and args.output_format == "excel" and succeeded:
    from exporters.bom_aggregator import export_aggregated_excel
    export_aggregated_excel(json_files, agg_path)
```

### 4.4 `pipelines/document_pipeline.py` — main.py L320~346, L481~602 이식

프리셋 분기 내부화:
```python
class DocumentPipeline(BasePipeline):
    # v2.1 이슈 1 해결: 표준 파이프라인 허용 엔진 화이트리스트
    # 근거: main.py L434~448 — gemini/local 외 엔진은 ParserError
    ALLOWED_ENGINES = frozenset({"gemini", "local"})

    def run(self):
        # 0. 엔진 제약 검증 (v2.1 신규)
        self._validate_engine(self.ctx.args.engine)
        # 1. 프리셋 리소스 로딩
        preset_data = self._load_preset(self.ctx.args.preset)
        # 2. 엔진 생성 (text_only 모드면 None)
        engine = None if self.ctx.args.text_only else \
                 create_engine(self.ctx.args.engine, tracker=self.ctx.tracker)
        # 3. Phase 1: PDF → MD (or MD 직접 입력)
        md_text = self._extract_or_load_md(engine, preset_data)
        # 4. Phase 2: MD → JSON
        if self.ctx.args.output_format in ("json", "excel"):
            sections = parse_markdown(md_text, ...)
            self._export_json_or_excel(sections, preset_data)

    def _validate_engine(self, engine_name: str | None) -> None:
        """
        표준 파이프라인(문서/견적서/품셈)은 gemini/local만 허용.
        zai/mistral/tesseract는 BOM 전용이므로 BomPipeline에서만 사용.

        근거: main.py L446~448 원본 동작 보존
            raise ParserError("표준 파이프라인에서 지원하지 않는 엔진: ...
                               BOM 전용 엔진은 --preset bom과 함께 사용하세요.")
        """
        if self.ctx.args.text_only:
            return  # 엔진 불필요
        name = engine_name or self.ctx.args.engine or DEFAULT_ENGINE
        if name not in self.ALLOWED_ENGINES:
            raise ParserError(
                f"표준 파이프라인에서 지원하지 않는 엔진: {name}. "
                f"BOM 전용 엔진(zai/mistral/tesseract)은 --preset bom과 함께 사용하세요."
            )

    def _load_preset(self, preset: str) -> dict:
        if preset == "pumsem":
            from presets.pumsem import get_division_names, get_parse_patterns, get_table_type_keywords
            return {...}
        elif preset == "estimate":
            ...
        return {}  # 범용
```

**대칭 원칙:** `BomPipeline`은 역으로 `ALLOWED_ENGINES = {"zai", "mistral", "tesseract", "local"}` 화이트리스트 보유 → 엔진-파이프라인 호환성 이중 보증.

### 4.5 Step 2 테스트 (10개, v2.1 +2개)

```
tests/unit/pipelines/test_base.py              (2개: 컨텍스트 + ABC)
tests/unit/pipelines/test_bom_pipeline.py      (3개: mock 기반)
tests/unit/pipelines/test_document_pipeline.py (3개, v2.1 +1)
  ├─ test_pumsem_preset_loads_resources
  ├─ test_estimate_preset_loads_resources
  └─ test_validate_engine_rejects_zai_mistral_tesseract   🆕 v2.1 이슈 1
tests/unit/pipelines/test_factory.py           (2개, v2.1 +1)
  ├─ test_preset_to_pipeline_mapping
  └─ test_bom_pipeline_rejects_gemini_engine              🆕 v2.1 대칭
```

### ✅ Step 2 체크포인트
- [ ] 5개 파일 생성 완료
- [ ] 신규 10개 파이프라인 테스트 통과 (v2.1 `_validate_engine` 포함)
- [ ] **기존 135개 테스트(112+23) 전부 통과**
- [ ] `git tag phase9-step2-complete`
- [ ] `main.py` 아직 수정 안 함 (Step 4 보류)

---

## 5. Step 3: `parsers/types.py` TypedDict 🟢

**기간:** 1~2일 | **위험:** 낮음 (타입 annotation만 추가)

### 5.1 신규 파일

```python
# parsers/types.py
from typing import TypedDict, Literal, NotRequired


class TableCell(TypedDict):
    text: str
    rowspan: NotRequired[int]
    colspan: NotRequired[int]


class ParsedTable(TypedDict):
    type: Literal["general", "bom", "line_list", "material", "cost"]
    headers: list[str]
    rows: list[list[TableCell]]
    page: NotRequired[int]


class ParsedSection(TypedDict):
    section_id: str
    title: str
    division: NotRequired[str]
    chapter: NotRequired[str]
    text: str
    tables: list[ParsedTable]
    metadata: NotRequired[dict]


class TocEntry(TypedDict):
    page: int
    section_id: str
    title: str
    division: NotRequired[str]
    chapter: NotRequired[str]
```

### 5.2 수정 파일

| 파일 | 변경 |
|-----|------|
| `parsers/document_parser.py::parse_markdown()` | 반환 타입 `list[dict]` → `list[ParsedSection]` |
| `parsers/section_splitter.py::split_sections()` | 반환 타입 annotation 추가 |

**내부 구현은 그대로** — annotation만 추가하여 IDE/mypy 지원.

### ✅ Step 3 체크포인트
- [ ] `parsers/types.py` 생성
- [ ] `parse_markdown()`, `split_sections()` 반환 타입 annotation
- [ ] `mypy parsers/` 통과 (또는 `# type: ignore` 임시 허용 범위 명시)
- [ ] **기존 145개 테스트(112+23+10) 전부 통과**
- [ ] `git tag phase9-step3-complete`

---

## 6. Step 4: main.py 슬림화 🔴 **최고 위험 단계**

**기간:** 5~7일 | **위험:** 🔴 **높음** (배치 처리 회귀 시 전체 영향)

### 6.1 선행 필수 조건 (SKIP 금지)

```
✅ Step 1~3 완료 + 모든 테스트 통과
✅ E2E Golden File 생성 (§6.2)
✅ 프리셋 4종 기대 출력 저장 (§6.3)
✅ git tag phase9-step3-complete 태그 확인
```

### 6.2 E2E Golden File 생성 (Step 4 착수 전)

```bash
# Phase 8 상태로 베이스라인 생성
mkdir -p tests/golden/input tests/golden/expected

# 각 프리셋별 최소 샘플 PDF 1개씩 투입
python main.py tests/golden/input/estimate_sample.pdf \
    --output json --out-dir tests/golden/expected/estimate

python main.py tests/golden/input/bom_sample.pdf \
    --preset bom --engine local \
    --out-dir tests/golden/expected/bom

python main.py tests/golden/input/pumsem_sample.pdf \
    --preset pumsem --output json \
    --out-dir tests/golden/expected/pumsem

python main.py tests/golden/input/generic.md \
    --output json --out-dir tests/golden/expected/generic
```

→ 4종 JSON 결과를 **골든 파일**로 커밋.

### 6.3 `_process_single()` 이식 매핑 테이블 (320줄 → 0줄)

| main.py 현재 라인 | 대상 모듈 | 비고 |
|----------------|---------|------|
| L92~173 (`_build_argument_parser`) | **`cli/args.py::build_argument_parser`** | v2.1 제안 — 필수 분리. `--no-cache` 신규 추가 |
| L280~305 (진입부, is_md_input 체크) | `DocumentPipeline.run()` | MD 입력 판별 |
| L306~326 (args 체크 + 프리셋 진입) | `DocumentPipeline._preconditions()` | |
| L328~337 (pumsem 리소스 로드) | `DocumentPipeline._load_preset("pumsem")` | |
| L339~346 (estimate 리소스 로드) | `DocumentPipeline._load_preset("estimate")` | |
| **L348~480 (BOM 전용 블록)** | **`BomPipeline.run()`** | ⚠️ 가장 큰 덩어리 |
| L434~448 (엔진 화이트리스트 ParserError) | `DocumentPipeline._validate_engine()` | v2.1 이슈 1 — 제약 보존 |
| L481~555 (Phase 1: hybrid_extractor 호출) | `DocumentPipeline._extract_md()` | |
| L557~601 (Phase 2: parse_markdown + 출력) | `DocumentPipeline._parse_and_export()` | |
| **L703~741 (배치 BOM 집계)** | **main.py 잔존** (또는 `cli/batch_runner.py`) | v2.1 이슈 3 — 파이프라인 외부 후처리 |

**이식 원칙:**
1. **복사 후 비교** — 원본 블록 주석 처리, 파이프라인 구현 추가
2. **한 프리셋씩** — pumsem → estimate → 범용 → bom 순 (리스크 낮은 것부터)
3. **각 프리셋 이식 후 E2E Golden 비교** (§6.2)

### 6.4 main.py 최종 구조 (목표 ≤ 350줄)

```python
# main.py
import argparse
from pathlib import Path

from cli.args import build_argument_parser  # v2.1: 필수 분리 (82줄 → main.py 350줄 달성 전제)
from pipelines.factory import create_pipeline
from pipelines.base import PipelineContext
from utils.logging_utils import install_masking_filter
from utils.tee import Tee
from utils.validation import ValidationError, validate_pdf_path, validate_output_dir
from utils.usage_tracker import UsageTracker
from cache.table_cache import TableCache


class ParserError(Exception):
    """복구 불가 처리 오류."""


def _collect_inputs(args) -> list[Path]:
    """args.input을 파일 목록으로 확장 (단일/디렉토리/글롭)."""
    ...


def _setup_tracker_and_cache(args):
    tracker = UsageTracker()
    cache = None if args.no_cache else TableCache()
    return tracker, cache


def main():
    install_masking_filter()

    parser = build_argument_parser()
    args = parser.parse_args()

    out_dir = validate_output_dir(args.output_dir)
    tracker, cache = _setup_tracker_and_cache(args)

    inputs = _collect_inputs(args)
    for input_path in inputs:
        try:
            ctx = PipelineContext(
                input_path=input_path, output_dir=out_dir,
                args=args, cache=cache, tracker=tracker,
            )
            pipeline = create_pipeline(ctx)
            pipeline.run()
        except ValidationError as e:
            print(f"⚠️  입력 검증 실패 ({input_path.name}): {e}")
            continue
        except ParserError as e:
            print(f"❌ {input_path.name}: {e}")
            continue
        except KeyboardInterrupt:
            print("\n🛑 사용자 중단"); break
        except Exception as e:
            print(f"❌ 예상치 못한 오류 ({input_path.name}): {e}")
            if args.debug:
                import traceback; traceback.print_exc()
            continue

    print(tracker.summary())


if __name__ == "__main__":
    main()
```

### 6.5 프리셋별 회귀 검증 매트릭스 (v2 핵심 추가)

| 프리셋 | 샘플 입력 | 기대 출력 | 검증 명령 | 통과 기준 |
|-------|---------|---------|---------|---------|
| **범용** | `generic.md` | JSON (단일 섹션) | `diff -r out expected/generic` | 구조 동일 |
| **pumsem** | `pumsem_sample.pdf` | JSON (부문/장 분할) | `diff -r out expected/pumsem` | `section_id`, `division` 일치 |
| **estimate** | `estimate_sample.pdf` | JSON + Excel | 시트명/행수 비교 | 테이블 타입 일치 |
| **bom** | `bom_sample.pdf` | BOM JSON | bom_sections/line_list_sections 개수 | 개수 + 첫 행 일치 |

### 6.6 롤백 절차 (회귀 발견 시)

```bash
# Step 4 진행 중 회귀 발견 시
git reset --hard phase9-step3-complete   # 🔴 주의: 확인 후 실행
# 원인 분석 후 해당 프리셋만 재이식
```

> **주의:** `git reset --hard`는 로컬 변경 손실. 반드시 변경사항 백업 후 실행.
> 대안: `git revert <commit>` (히스토리 보존)

### ✅ Step 4 체크포인트
- [ ] main.py ≤ 350줄 달성
- [ ] **프리셋 4종 E2E Golden 통과**
- [ ] 기존 145개 테스트 통과 (회귀 없음)
- [ ] 샘플 PDF 배치 10개 연속 처리 시 메모리/시간 Phase 8 수준 유지
- [ ] `git tag phase9-step4-complete`

---

## 7. Step 5: 아키텍처·파이프라인 테스트 추가 🟢

**기간:** 2~3일 | **위험:** 낮음

### 7.1 신규 테스트 (6개 파일, 30+ 테스트)

| 파일 | 테스트 개수 | 목적 |
|-----|---------|------|
| `tests/architecture/test_module_dependencies.py` | 5 | 의존 방향 검증 |
| `tests/architecture/test_main_slim.py` | 2 | main.py 줄수/함수 길이 회귀 방지 |
| `tests/architecture/test_factory_registry.py` | 3 | 팩토리 무결성 |
| `tests/e2e/test_preset_regression.py` | 4 | 4종 프리셋 Golden 비교 |
| `tests/integration/test_pipeline_flow.py` | 6+ | 파이프라인 end-to-end (mock) |
| `tests/performance/test_phase8_preserved.py` | 3 | Phase 8 성능 유지 확인 |

### 7.2 아키텍처 테스트 예시

```python
# tests/architecture/test_module_dependencies.py
import ast
from pathlib import Path
ROOT = Path(__file__).parent.parent.parent


def _imports_of(file_path: Path) -> set[str]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            for n in node.names:
                imports.add(n.name.split(".")[0])
    return imports


class TestDependencyDirection:
    def test_engines_do_not_import_pipelines(self):
        for py in (ROOT / "engines").glob("*.py"):
            assert "pipelines" not in _imports_of(py)

    def test_parsers_do_not_import_engines(self):
        for py in (ROOT / "parsers").glob("*.py"):
            assert "engines" not in _imports_of(py)

    def test_main_does_not_import_engine_modules_directly(self):
        # main.py는 engines.factory만 사용해야 함
        imports = _imports_of(ROOT / "main.py")
        for banned in ["engines.gemini_engine", "engines.zai_engine", "engines.mistral_engine"]:
            assert banned not in str(imports)


class TestMainSlim:
    def test_main_line_count(self):
        lines = (ROOT / "main.py").read_text(encoding="utf-8").count("\n")
        assert lines <= 400, f"main.py 과대: {lines}줄 (목표 ≤ 350)"

    def test_no_function_over_80_lines(self):
        tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                length = (node.end_lineno or 0) - node.lineno
                assert length <= 80, f"{node.name} 과대: {length}줄"
```

### ✅ Step 5 체크포인트
- [ ] 30+ 신규 테스트 통과
- [ ] **총 테스트 수 ≥ 180개** 통과
- [ ] `git tag phase9-complete`
- [ ] `Phase9_결과보고서.md` 작성

---

## 8. 전체 리스크 매트릭스 (v2 강화)

| 리스크 | 발생 확률 | 영향도 | 완화책 |
|-------|---------|-------|-------|
| **Step 4에서 프리셋 회귀 발생** | 중 | 🔴 고 | E2E Golden + 프리셋별 이식 순서 + 롤백 태그 |
| 순환 임포트 (pipelines ↔ engines) | 중 | 중 | `TYPE_CHECKING` + 지연 import |
| TypedDict mypy 실패 | 낮음 | 낮음 | annotation만 추가, 구현 그대로 유지 |
| API 키 마스킹 오탐 | 낮음 | 낮음 | 비-비밀 문자열 테스트로 검증 |
| 검증 상한값이 기존 처리 차단 | 중 | 중 | `--max-size`/`--max-pages` CLI 오버라이드 |
| Step 4 일정 지연 | 중 | 중 | 프리셋 1개 이식 후 체크포인트 확보 |
| **Step 4 중 다른 Step 수정 필요 발견** | 중 | 고 | Step 4 중단 → 해당 Step로 되돌아가 수정 → Step 4 재개 |

---

## 9. 전체 산출물 종합 (22개)

### 📂 신규 파일 (16개)

| 카테고리 | 파일 |
|---------|------|
| 팩토리 (1) | `engines/factory.py` |
| 파이프라인 (5) | `pipelines/__init__.py`, `base.py`, `bom_pipeline.py`, `document_pipeline.py`, `factory.py` |
| 유틸리티 (5) | `utils/logging_utils.py`, `validation.py`, `tee.py`, `paths.py`, `parsers/toc_loader.py` |
| 타입 (1) | `parsers/types.py` |
| 선택적 분리 (1) | `cli/args.py` (Step 4 중 필요 시) |
| 테스트 (6) | Step 1+2+5 테스트 파일 |
| 골든 입력 (4) | `tests/golden/input/` 4종 샘플 |

### 📝 수정 파일 (4개)

| 파일 | 변경 |
|-----|------|
| `main.py` | 792줄 → ≤ 350줄 |
| `parsers/document_parser.py` | 반환 타입 annotation |
| `parsers/section_splitter.py` | 반환 타입 annotation |
| `.env.example` | (선택) 검증 상한 변수 추가 |

---

## 10. 예상 효과

| 지표 | Phase 8 현재 | Phase 9 후 목표 | 개선 |
|------|------------|---------------|------|
| `main.py` 줄수 | 792 | **≤ 350** | -55% |
| 가장 긴 함수 | 323줄 (`_process_single`) | **≤ 50** | -84% |
| 엔진 추가 시 수정 파일 | 2개 | **1개** | -50% |
| 파이프라인 단위 테스트 | 불가 | **가능** | ✅ |
| API 키 로그 노출 위험 | 있음 | **자동 마스킹** | ✅ |
| 입력 검증 | 없음 | **3종 상한** | ✅ |
| 파서 반환 타입 | `list[dict]` | **TypedDict** | ✅ |
| 전체 테스트 수 | 112 | **180+** | +60% |
| E2E 회귀 테스트 | 없음 | **프리셋 4종 Golden** | ✅ |

---

## 11. Step별 진행 결정 트리

```
[Step 1 착수]
    └─→ 20개 신규 테스트 + 112개 기존 테스트 통과?
           ├─ YES → git tag phase9-step1-complete → Step 2 진입
           └─ NO  → 해당 유틸리티 재설계 (Step 2 진입 금지)

[Step 2 착수]
    └─→ 8개 파이프라인 테스트 통과 + Step 1 테스트 유지?
           ├─ YES → git tag phase9-step2-complete → Step 3 진입
           └─ NO  → 파이프라인 설계 재검토

[Step 3 착수]
    └─→ mypy 통과 + 기존 테스트 유지?
           ├─ YES → git tag phase9-step3-complete → Step 4 진입 (E2E Golden 생성)
           └─ NO  → annotation 조정

[Step 4 착수 ⚠️ 최고 위험]
    └─→ 프리셋 1개 이식 → E2E Golden 비교
           ├─ 일치 → 다음 프리셋
           └─ 불일치 → 즉시 롤백 (phase9-step3-complete로) → 원인 분석
    └─→ 4종 프리셋 모두 통과?
           ├─ YES → git tag phase9-step4-complete → Step 5 진입
           └─ NO  → 롤백 → 재설계

[Step 5 착수]
    └─→ 180+개 테스트 통과?
           ├─ YES → git tag phase9-complete → 보고서 작성
           └─ NO  → 테스트 보완
```

---

## 12. Phase 10 연계

Phase 10 (HWPX, DOCX 입력 확장):
- `pipelines/factory.py` 구조 **그대로 재사용** — `HwpxPipeline`, `DocxPipeline` 클래스만 추가
- `engines/factory.py` 패턴을 **`loaders/factory.py`** 로 복제 (PDF/HWPX/DOCX 로더 레지스트리)
- `parsers/types.py` 타입 정의 **공통 사용**

---

## 13. v1 → v2 개선 요약

| 영역 | v1 | v2 |
|------|----|----|
| 계획 단위 | 15일 WBS (개별 Day) | **5-Step 체크포인트** (커밋/롤백 지점) |
| Step 4 상세도 | "리팩터링 진행" | **L280~602 이식 매핑 테이블** |
| 회귀 방지 | 단위 테스트만 | **E2E Golden File + 프리셋 4종 매트릭스** |
| 롤백 | 언급 없음 | **Step별 Git tag + 결정 트리** |
| 위험 명시 | "main.py 리팩터링 위험" | **🔴 고위험 Step 4 단독 관리** |

---

**기술서 작성자:** Claude Opus 4
**기술서 작성일:** 2026-04-17
**개정 이력:** v1 (2026-04-17) → v2 (2026-04-17, 리뷰 반영)
**참조 문서:**
- `ps-docparser_코드리뷰_보고서.md` §Phase 9 (L711~723)
- `Phase8_결과보고서.md` (현재 상태 기준, 테스트 112개 통과)
- `ps-docparser/main.py` (792줄, `_process_single` 323줄)
- `ps-docparser/engines/base_engine.py` (엔진 계약)
