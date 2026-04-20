# Phase 7 상세 구현 기술서 — 테스트 인프라 구축

**작성일:** 2026-04-17
**대상 프로젝트:** ps-docparser
**페이즈 목표:** 단위 테스트 커버리지 50% 이상 확보, 리팩터링 안전망 구축, 회귀 방지
**예상 기간:** 2주 (약 10~14 작업일)
**우선순위:** 🔴 P0 - Critical
**선행 페이즈:** Phase 6 (긴급 안정화) 완료 필수

---

## 0. 개요 및 범위

### 0.1 Phase 7의 위치
- **이전 단계(Phase 6):** 코드 안정화 완료 (`validate_config`, `_safe_write_text`, 배치 예외 처리)
- **현재 단계(Phase 7):** 테스트 기반 구축
- **다음 단계(Phase 8):** 성능 최적화 (안전한 리팩터링 기반 필요)

### 0.2 작업 이유

**현재 프로젝트의 테스트 현황:**
```
ps-docparser/
├── test_phase4_unit.py          # Phase 단위 통합 테스트 (엔진 전체)
├── test_phase5_unit1~5.py        # Phase 단위 통합 테스트
├── test_collision.py             # 파일명 충돌 (ad-hoc)
├── test_excel_lock.py            # Excel 잠금 테스트 (ad-hoc)
├── test_folder_lock.py           # 폴더 잠금 테스트 (ad-hoc)
├── test_lock.py                  # 일반 잠금 테스트 (ad-hoc)
├── test_zai_api.py               # Z.ai API 호출 테스트 (ad-hoc)
└── _test_patch_verify.py         # 디버그 스크립트
```

**문제점:**
1. **단위 테스트 부재:** 모두 통합/E2E 성격 — 개별 함수 검증 안 됨
2. **pytest 미도입:** `python test_xxx.py` 방식 → 테스트 러너/픽스처/파라미터라이즈 없음
3. **커버리지 측정 불가:** 어느 코드가 테스트되지 않는지 모름
4. **Mock 사용 없음:** API 호출이 실제 호출에 의존 → CI 불가능, 비용 발생
5. **회귀 감지 어려움:** Phase 8 리팩터링 시 무엇이 깨졌는지 파악 어려움

### 0.3 작업 대상 모듈 (단위 테스트 타겟)

| 우선순위 | 모듈 | 기존 테스트 | 목표 커버리지 |
|--------|------|-----------|-----------|
| 🔴 P0 | `detector.py` | ❌ 없음 | 90%+ |
| 🔴 P0 | `utils/page_spec.py` | ❌ 없음 | 95%+ |
| 🔴 P0 | `utils/io.py` (Phase 6) | ❌ 없음 | 90%+ |
| 🔴 P0 | `cache/table_cache.py` | ❌ 없음 | 85%+ |
| 🔴 P0 | `config.py` (validate_config, detect) | ❌ 없음 | 80%+ |
| 🟡 P1 | `parsers/text_cleaner.py` | ⚠️ 간접 | 70%+ |
| 🟡 P1 | `parsers/table_parser.py` | ⚠️ 간접 | 75%+ |
| 🟡 P1 | `parsers/section_splitter.py` | ⚠️ 간접 | 70%+ |
| 🟡 P1 | `parsers/bom_table_parser.py` | ⚠️ 간접 | 75%+ |
| 🟡 P1 | `extractors/bom_extractor.py` | ⚠️ 간접 | 70%+ |
| 🟡 P1 | `extractors/toc_parser.py` | ⚠️ 간접 | 65%+ |
| 🟢 P2 | `utils/markers.py` | ❌ 없음 | 80%+ |
| 🟢 P2 | `utils/text_formatter.py` | ❌ 없음 | 70%+ |
| 🟢 P2 | `utils/usage_tracker.py` | ❌ 없음 | 75%+ |
| 🟢 P2 | `presets/*.py` | ❌ 없음 | 60%+ |

**전체 목표 커버리지:** 50%+ (최소), 65%+ (스트레치 목표)

### 0.4 완료 기준 (Definition of Done)

- [ ] `tests/` 디렉토리 구조 완성 (unit/integration/fixtures 분리)
- [ ] `pytest` + `pytest-cov` + `pytest-mock` 개발 의존성 설정
- [ ] P0 모듈 5개 단위 테스트 완료 (각 ≥80% 커버리지)
- [ ] P1 모듈 6개 단위 테스트 완료 (각 ≥70% 커버리지)
- [ ] 전체 프로젝트 커버리지 ≥50%
- [ ] `pytest` 단일 명령으로 모든 테스트 실행 성공
- [ ] GitHub Actions (또는 로컬 스크립트) 기본 CI 설정
- [ ] 테스트 작성 가이드 문서 작성

---

## 1. 작업 1: 테스트 인프라 초기 셋업

### 1.1 디렉토리 구조 설계

```
ps-docparser/
├── tests/                              # 신규
│   ├── __init__.py
│   ├── conftest.py                     # 공통 픽스처 (프로젝트 루트)
│   │
│   ├── unit/                           # 단위 테스트
│   │   ├── __init__.py
│   │   ├── test_detector.py
│   │   ├── test_config.py
│   │   │
│   │   ├── utils/
│   │   │   ├── __init__.py
│   │   │   ├── test_page_spec.py
│   │   │   ├── test_io.py
│   │   │   ├── test_markers.py
│   │   │   ├── test_text_formatter.py
│   │   │   └── test_usage_tracker.py
│   │   │
│   │   ├── parsers/
│   │   │   ├── __init__.py
│   │   │   ├── test_text_cleaner.py
│   │   │   ├── test_table_parser.py
│   │   │   ├── test_section_splitter.py
│   │   │   ├── test_bom_table_parser.py
│   │   │   └── test_document_parser.py
│   │   │
│   │   ├── extractors/
│   │   │   ├── __init__.py
│   │   │   ├── test_bom_extractor.py
│   │   │   ├── test_toc_parser.py
│   │   │   └── test_table_utils.py
│   │   │
│   │   ├── cache/
│   │   │   ├── __init__.py
│   │   │   └── test_table_cache.py
│   │   │
│   │   └── presets/
│   │       ├── __init__.py
│   │       ├── test_estimate.py
│   │       ├── test_pumsem.py
│   │       └── test_bom.py
│   │
│   ├── integration/                    # 통합 테스트 (Phase 4~5 기존 이동)
│   │   ├── __init__.py
│   │   ├── test_phase4_pipeline.py     # 기존 test_phase4_unit.py 리팩터
│   │   ├── test_phase5_batch.py        # 기존 test_phase5_unit1~5.py 통합
│   │   └── test_end_to_end.py          # 샘플 PDF → xlsx 전체 파이프라인
│   │
│   └── fixtures/                       # 테스트 데이터
│       ├── __init__.py
│       ├── sample_markdowns/           # MD 샘플
│       │   ├── simple_estimate.md
│       │   ├── bom_page.md
│       │   └── pumsem_section.md
│       ├── sample_pdfs/                # 최소 PDF (Git LFS 불필요한 크기)
│       │   └── tiny_test.pdf
│       ├── sample_jsons/               # JSON 기대값
│       │   └── expected_sections.json
│       └── mock_responses/             # API mock 응답
│           ├── gemini_table.md
│           └── zai_bom.json
│
├── pytest.ini                          # 신규
├── .coveragerc                         # 신규
├── requirements-dev.txt                # 신규
└── .github/
    └── workflows/
        └── ci.yml                      # 신규 (선택)
```

### 1.2 신규 파일: `requirements-dev.txt`

```
# Phase 7: 테스트 및 개발 의존성
# 사용: pip install -r requirements.txt -r requirements-dev.txt

pytest>=8.0.0,<9.0.0
pytest-cov>=5.0.0,<6.0.0
pytest-mock>=3.12.0,<4.0.0

# (선택) 테스트 보조
pytest-xdist>=3.5.0,<4.0.0       # 병렬 실행
pytest-timeout>=2.2.0,<3.0.0     # 타임아웃 방지

# (선택) 린트/포매팅
# ruff>=0.3.0,<1.0.0
# mypy>=1.8.0,<2.0.0
```

### 1.3 신규 파일: `pytest.ini`

```ini
[pytest]
# 테스트 탐색 경로
testpaths = tests

# 테스트 파일/함수 네이밍 규칙
python_files = test_*.py
python_classes = Test*
python_functions = test_*

# 마커 정의 (선택적 스킵용)
markers =
    slow: 1초 이상 걸리는 테스트 (CI에서 --slow 옵션으로만 실행)
    integration: 실제 파일/DB를 사용하는 통합 테스트
    api: 실제 API 호출 (CI에서 기본 스킵)
    windows_only: Windows 전용 테스트
    macos_only: macOS 전용 테스트

# 기본 옵션
addopts =
    --strict-markers
    --tb=short
    -v
    --color=yes
    --durations=10
    -p no:cacheprovider

# 로깅 (테스트 실패 시 로그 출력)
log_cli = false
log_cli_level = WARNING
```

### 1.4 신규 파일: `.coveragerc`

```ini
[run]
source = .
branch = True
omit =
    tests/*
    # 기존 ad-hoc 테스트 파일 제외
    test_phase*.py
    test_*.py
    _test_*.py
    _debug_*.py
    _inspect_*.py
    audit_main.py
    batch_test.py
    inspect_db.py
    verify_phase4.py
    # 외부 라이브러리
    */site-packages/*
    # __init__ 단순 파일
    */__init__.py
    # 캐시/빌드
    .cache/*
    build/*
    dist/*

[report]
precision = 2
show_missing = True
skip_covered = False
exclude_lines =
    pragma: no cover
    def __repr__
    raise NotImplementedError
    if __name__ == .__main__.:
    if TYPE_CHECKING:
    \.\.\.

[html]
directory = htmlcov
```

### 1.5 신규 파일: `tests/conftest.py`

```python
"""
프로젝트 전역 pytest 픽스처.

Why conftest.py:
    모든 테스트 파일에서 자동으로 로드되는 픽스처 정의.
    중복 픽스처 코드를 제거하고 일관된 테스트 데이터 제공.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ── 프로젝트 루트를 sys.path에 추가 ──
# Why: tests/ 에서 ps-docparser 모듈을 import 할 수 있게 함
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ──────────────────────────────────────────────
# 경로 픽스처
# ──────────────────────────────────────────────

@pytest.fixture(scope="session")
def project_root() -> Path:
    """프로젝트 루트 경로."""
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """fixtures 디렉토리 경로."""
    return PROJECT_ROOT / "tests" / "fixtures"


@pytest.fixture(scope="session")
def sample_md_dir(fixtures_dir: Path) -> Path:
    return fixtures_dir / "sample_markdowns"


@pytest.fixture(scope="session")
def sample_pdf_dir(fixtures_dir: Path) -> Path:
    return fixtures_dir / "sample_pdfs"


# ──────────────────────────────────────────────
# 임시 디렉토리 픽스처
# ──────────────────────────────────────────────

@pytest.fixture
def temp_output_dir(tmp_path: Path) -> Path:
    """각 테스트마다 격리된 임시 출력 디렉토리."""
    out = tmp_path / "output"
    out.mkdir(parents=True, exist_ok=True)
    return out


@pytest.fixture
def temp_cache_dir(tmp_path: Path) -> Path:
    """각 테스트마다 격리된 임시 캐시 디렉토리."""
    cache = tmp_path / ".cache"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


# ──────────────────────────────────────────────
# 환경변수 격리
# ──────────────────────────────────────────────

@pytest.fixture
def clean_env(monkeypatch):
    """
    환경변수를 격리한다. 테스트에서 .env 영향을 받지 않도록.
    Why: API 키 등이 실제 환경변수에 있으면 validate_config 테스트가 오염됨.
    """
    env_vars = [
        "GEMINI_API_KEY", "ZAI_API_KEY", "MISTRAL_API_KEY",
        "POPPLER_PATH", "TESSERACT_PATH",
        "DEFAULT_ENGINE", "BOM_DEFAULT_ENGINE",
        "FREE_TIER_DELAY", "CACHE_ENABLED", "CACHE_TTL_DAYS",
    ]
    for var in env_vars:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


# ──────────────────────────────────────────────
# 샘플 데이터 픽스처
# ──────────────────────────────────────────────

@pytest.fixture
def simple_estimate_md(sample_md_dir: Path) -> str:
    """견적서 샘플 MD 텍스트."""
    return (sample_md_dir / "simple_estimate.md").read_text(encoding="utf-8")


@pytest.fixture
def bom_page_md(sample_md_dir: Path) -> str:
    return (sample_md_dir / "bom_page.md").read_text(encoding="utf-8")


# ──────────────────────────────────────────────
# 마커 기반 자동 스킵
# ──────────────────────────────────────────────

def pytest_collection_modifyitems(config, items):
    """
    --run-api, --run-slow 옵션이 없으면 해당 마커 테스트 스킵.
    """
    run_api = config.getoption("--run-api", default=False)
    run_slow = config.getoption("--run-slow", default=False)

    skip_api = pytest.mark.skip(reason="--run-api 옵션으로 실행")
    skip_slow = pytest.mark.skip(reason="--run-slow 옵션으로 실행")

    for item in items:
        if "api" in item.keywords and not run_api:
            item.add_marker(skip_api)
        if "slow" in item.keywords and not run_slow:
            item.add_marker(skip_slow)


def pytest_addoption(parser):
    parser.addoption("--run-api", action="store_true", help="실제 API 호출 테스트 실행")
    parser.addoption("--run-slow", action="store_true", help="느린 테스트 실행")
```

---

## 2. 작업 2: P0 단위 테스트 작성

### 2.1 `tests/unit/test_detector.py`

**대상:** `detector.detect_document_type()`
**목표:** 모든 분기 100% 커버

```python
"""
detector.py 단위 테스트.
"""
import pytest
from detector import detect_document_type


class TestDetectDocumentType:
    """문서 유형 자동 감지 로직 검증."""

    # ── 정상 케이스 ──
    def test_estimate_by_keyword(self):
        text = "견적금액: 1,000,000원\n합계: 1,100,000원"
        assert detect_document_type(text) == "estimate"

    def test_bom_by_bill_of_materials(self):
        text = "BILL OF MATERIALS\nS/N | SPEC | Q'TY"
        assert detect_document_type(text) == "bom"

    def test_bom_by_line_list(self):
        text = "LINE LIST\n| 1 | P-001 | ... |"
        assert detect_document_type(text) == "bom"

    def test_pumsem_by_division(self):
        text = "제1편 토목공사\n제1장 일반사항"
        assert detect_document_type(text) == "pumsem"

    # ── 엣지 케이스 ──
    @pytest.mark.parametrize("text,expected", [
        ("", None),
        ("   \n\n  ", None),
        ("알 수 없는 문서 내용", None),
    ])
    def test_unknown_or_empty(self, text, expected):
        assert detect_document_type(text) == expected

    def test_priority_bom_over_estimate(self):
        """BOM 키워드가 더 강력한 신호"""
        text = "BILL OF MATERIALS\n견적금액도 포함"
        assert detect_document_type(text) == "bom"

    def test_case_insensitive(self):
        text = "bill of materials"
        assert detect_document_type(text) == "bom"
```

**커버 포인트:**
- 각 문서 유형 감지 분기
- 빈 입력 / None
- 대소문자
- 복수 키워드 충돌 시 우선순위
- 한글/영문 혼합

---

### 2.2 `tests/unit/utils/test_page_spec.py`

**대상:** `utils/page_spec.parse_page_spec()`

```python
"""
page_spec.py 단위 테스트.

parse_page_spec의 문법:
    "15"       → [0..14]        (1~15 페이지)
    "1-15"     → [0..14]
    "16-30"    → [15..29]
    "1,3,5-10" → [0, 2, 4..9]
    "20-"      → [19..total-1]
"""
import pytest
from utils.page_spec import parse_page_spec


class TestParsePageSpec:

    @pytest.mark.parametrize("spec,total,expected", [
        ("15", 100, list(range(0, 15))),
        ("1-15", 100, list(range(0, 15))),
        ("16-30", 100, list(range(15, 30))),
        ("1,3,5-10", 100, [0, 2, 4, 5, 6, 7, 8, 9]),
        ("20-", 25, [19, 20, 21, 22, 23, 24]),
        ("1", 10, [0]),
    ])
    def test_valid_specs(self, spec, total, expected):
        assert parse_page_spec(spec, total) == expected

    # ── 엣지 케이스 ──
    def test_none_returns_all(self):
        assert parse_page_spec(None, 5) == [0, 1, 2, 3, 4]

    def test_empty_string(self):
        with pytest.raises(ValueError):
            parse_page_spec("", 10)

    def test_out_of_range(self):
        """총 페이지 초과 지정 시 자동 클램프"""
        result = parse_page_spec("1-100", 10)
        assert result == list(range(0, 10))

    def test_invalid_format(self):
        with pytest.raises(ValueError):
            parse_page_spec("abc", 10)

    def test_reverse_range(self):
        """역순 범위 (10-5) 허용 여부"""
        with pytest.raises(ValueError):
            parse_page_spec("10-5", 100)

    def test_deduplication(self):
        """중복 페이지 제거"""
        result = parse_page_spec("1,2,3,1,2", 10)
        assert result == [0, 1, 2]
```

---

### 2.3 `tests/unit/utils/test_io.py` (Phase 6 산출물)

**대상:** `utils/io._safe_write_text()`

```python
"""
utils/io.py 단위 테스트.

Phase 6에서 도입된 _safe_write_text는 다음을 보장:
- PermissionError → ParserError
- OSError → ParserError
- 부모 디렉토리 자동 생성
"""
import pytest
from pathlib import Path
from unittest.mock import patch, mock_open

from utils.io import _safe_write_text
from main import ParserError  # 또는 utils.errors로 이동 고려


class TestSafeWriteText:

    def test_write_success(self, tmp_path: Path):
        target = tmp_path / "test.md"
        _safe_write_text(target, "hello world")
        assert target.read_text(encoding="utf-8-sig") == "hello world"

    def test_creates_parent_directories(self, tmp_path: Path):
        target = tmp_path / "deep" / "nested" / "dir" / "file.md"
        _safe_write_text(target, "content")
        assert target.exists()

    def test_permission_error_converted(self, tmp_path: Path):
        target = tmp_path / "test.md"
        with patch("builtins.open", side_effect=PermissionError("Access denied")):
            with pytest.raises(ParserError) as exc_info:
                _safe_write_text(target, "content")
            assert "권한 거부" in str(exc_info.value)
            assert "Excel" in str(exc_info.value)  # 힌트 메시지

    def test_os_error_converted(self, tmp_path: Path):
        target = tmp_path / "test.md"
        with patch("builtins.open", side_effect=OSError("Disk full")):
            with pytest.raises(ParserError) as exc_info:
                _safe_write_text(target, "content")
            assert "I/O 오류" in str(exc_info.value)

    @pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "cp949"])
    def test_encodings(self, tmp_path: Path, encoding: str):
        target = tmp_path / f"test_{encoding}.md"
        text = "한글 테스트"
        _safe_write_text(target, text, encoding=encoding)
        assert target.read_text(encoding=encoding) == text

    def test_overwrite_existing(self, tmp_path: Path):
        target = tmp_path / "test.md"
        target.write_text("old")
        _safe_write_text(target, "new")
        assert target.read_text(encoding="utf-8-sig") == "new"
```

---

### 2.4 `tests/unit/cache/test_table_cache.py`

**대상:** `cache/table_cache.TableCache`

```python
"""
table_cache.py 단위 테스트.

TableCache는 SQLite 기반 캐시:
- sha256 파일 해시 + 페이지 번호 + bbox를 키로 사용
- TTL 지난 엔트리 자동 만료
- 캐시 적중률 통계 제공
"""
import pytest
from pathlib import Path
from datetime import datetime, timedelta

from cache.table_cache import TableCache


class TestTableCache:

    @pytest.fixture
    def cache(self, temp_cache_dir: Path):
        db_path = temp_cache_dir / "test.db"
        return TableCache(db_path=db_path, ttl_days=30)

    def test_initial_state(self, cache: TableCache):
        stats = cache.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["total_entries"] == 0

    def test_set_and_get(self, cache: TableCache, tmp_path: Path):
        pdf = tmp_path / "sample.pdf"
        pdf.write_bytes(b"dummy pdf content")

        # Set
        cache.set(pdf, page=0, bbox=(0, 0, 100, 100), result="test_result")

        # Get (적중)
        result = cache.get(pdf, page=0, bbox=(0, 0, 100, 100))
        assert result == "test_result"
        assert cache.get_stats()["hits"] == 1

    def test_miss_different_page(self, cache: TableCache, tmp_path: Path):
        pdf = tmp_path / "sample.pdf"
        pdf.write_bytes(b"content")
        cache.set(pdf, page=0, bbox=(0, 0, 100, 100), result="r0")
        assert cache.get(pdf, page=1, bbox=(0, 0, 100, 100)) is None
        assert cache.get_stats()["misses"] == 1

    def test_miss_different_file(self, cache: TableCache, tmp_path: Path):
        pdf1 = tmp_path / "a.pdf"
        pdf1.write_bytes(b"content1")
        pdf2 = tmp_path / "b.pdf"
        pdf2.write_bytes(b"content2")

        cache.set(pdf1, page=0, bbox=(0, 0, 100, 100), result="r1")
        assert cache.get(pdf2, page=0, bbox=(0, 0, 100, 100)) is None

    def test_ttl_expiration(self, cache: TableCache, tmp_path: Path):
        """TTL 지난 엔트리는 무효화"""
        pdf = tmp_path / "sample.pdf"
        pdf.write_bytes(b"content")

        # 일부러 오래된 타임스탬프로 저장
        cache.set(pdf, page=0, bbox=(0, 0, 100, 100), result="old")
        # DB 직접 조작으로 created_at을 31일 전으로
        cache._set_created_at_for_test(pdf, 0, (0, 0, 100, 100),
                                         datetime.now() - timedelta(days=31))

        assert cache.get(pdf, page=0, bbox=(0, 0, 100, 100)) is None

    def test_same_content_different_filename(self, cache: TableCache, tmp_path: Path):
        """파일명이 달라도 내용이 같으면 캐시 적중 (sha256 기반)"""
        pdf1 = tmp_path / "a.pdf"
        pdf2 = tmp_path / "b.pdf"
        pdf1.write_bytes(b"identical content")
        pdf2.write_bytes(b"identical content")

        cache.set(pdf1, page=0, bbox=(0, 0, 100, 100), result="shared")
        assert cache.get(pdf2, page=0, bbox=(0, 0, 100, 100)) == "shared"

    def test_hit_rate_calculation(self, cache: TableCache, tmp_path: Path):
        pdf = tmp_path / "sample.pdf"
        pdf.write_bytes(b"content")
        cache.set(pdf, page=0, bbox=(0, 0, 100, 100), result="r")

        # 3 hits, 2 misses
        for _ in range(3):
            cache.get(pdf, page=0, bbox=(0, 0, 100, 100))
        for p in [1, 2]:
            cache.get(pdf, page=p, bbox=(0, 0, 100, 100))

        stats = cache.get_stats()
        assert stats["hits"] == 3
        assert stats["misses"] == 2
        assert abs(stats["hit_rate"] - 0.6) < 0.001

    def test_clear(self, cache: TableCache, tmp_path: Path):
        pdf = tmp_path / "sample.pdf"
        pdf.write_bytes(b"content")
        cache.set(pdf, page=0, bbox=(0, 0, 100, 100), result="r")
        cache.clear()
        assert cache.get_stats()["total_entries"] == 0
```

---

### 2.5 `tests/unit/test_config.py`

**대상:** `config.py` - `_detect_poppler_path()`, `_detect_tesseract_path()`, `validate_config()`

```python
"""
config.py 단위 테스트.

Phase 6에서 도입된 validate_config와 경로 감지 함수 검증.
"""
import pytest
import platform
from unittest.mock import patch, MagicMock
from pathlib import Path

import config


class TestDetectPopplerPath:

    def test_env_var_priority(self, monkeypatch, tmp_path):
        existing = tmp_path / "poppler_bin"
        existing.mkdir()
        monkeypatch.setenv("POPPLER_PATH", str(existing))
        assert config._detect_poppler_path() == str(existing)

    def test_env_var_invalid_falls_through(self, monkeypatch):
        monkeypatch.setenv("POPPLER_PATH", "/nonexistent/path")
        # which과 OS 경로 모두 없다고 가정
        with patch("shutil.which", return_value=None):
            with patch("os.path.exists", return_value=False):
                result = config._detect_poppler_path()
                assert result is None

    def test_shutil_which_fallback(self, monkeypatch):
        monkeypatch.delenv("POPPLER_PATH", raising=False)
        with patch("shutil.which", return_value="/usr/bin/pdftotext"):
            assert config._detect_poppler_path() == "/usr/bin"

    @pytest.mark.windows_only
    def test_windows_glob_selects_latest(self, monkeypatch):
        monkeypatch.delenv("POPPLER_PATH", raising=False)
        fake_paths = [
            r"C:\poppler\poppler-23.05.0\Library\bin",
            r"C:\poppler\poppler-25.01.0\Library\bin",
            r"C:\poppler\poppler-24.08.0\Library\bin",
        ]
        with patch("shutil.which", return_value=None):
            with patch("glob.glob", return_value=fake_paths):
                with patch("os.path.exists", return_value=True):
                    with patch("platform.system", return_value="Windows"):
                        result = config._detect_poppler_path()
                        # 최신 25.01.0 선택
                        assert "25.01.0" in result


class TestValidateConfig:

    def test_missing_gemini_key_errors(self, monkeypatch):
        monkeypatch.setattr(config, "GEMINI_API_KEY", None)
        monkeypatch.setattr(config, "DEFAULT_ENGINE", "gemini")
        result = config.validate_config(verbose=False)
        assert any("GEMINI_API_KEY" in e for e in result["errors"])

    def test_valid_gemini_setup(self, monkeypatch):
        monkeypatch.setattr(config, "GEMINI_API_KEY", "fake_key_123")
        monkeypatch.setattr(config, "DEFAULT_ENGINE", "gemini")
        monkeypatch.setattr(config, "POPPLER_PATH", "/fake/poppler")
        result = config.validate_config(verbose=False)
        assert result["errors"] == []

    def test_missing_poppler_is_warning_not_error(self, monkeypatch):
        monkeypatch.setattr(config, "POPPLER_PATH", None)
        monkeypatch.setattr(config, "DEFAULT_ENGINE", "local")  # local은 poppler 불필요
        result = config.validate_config(verbose=False)
        assert result["errors"] == []
        assert any("Poppler" in w for w in result["warnings"])

    def test_tesseract_engine_without_binary_errors(self, monkeypatch):
        monkeypatch.setattr(config, "TESSERACT_PATH", None)
        monkeypatch.setattr(config, "DEFAULT_ENGINE", "tesseract")
        result = config.validate_config(verbose=False)
        assert any("tesseract" in e.lower() for e in result["errors"])
```

---

## 3. 작업 3: P1 단위 테스트 작성

### 3.1 `tests/unit/parsers/test_text_cleaner.py`

```python
"""text_cleaner.py 단위 테스트."""
import pytest
from parsers.text_cleaner import clean_section_text


class TestCleanSectionText:

    def test_removes_excess_whitespace(self):
        text = "안녕하세요\n\n\n\n반갑습니다"
        result = clean_section_text(text)
        assert "\n\n\n" not in result

    def test_preserves_table_markers(self):
        text = "본문\n<!-- TABLE_START -->\n| A | B |\n<!-- TABLE_END -->\n마무리"
        result = clean_section_text(text)
        assert "TABLE_START" in result
        assert "TABLE_END" in result

    def test_metadata_extraction(self):
        """작성일, 작성자 등 메타데이터 추출"""
        text = "작성일: 2026-04-17\n작성자: 홍길동\n본문..."
        result = clean_section_text(text, extract_metadata=True)
        assert result.metadata["date"] == "2026-04-17"
        assert result.metadata["author"] == "홍길동"
```

### 3.2 `tests/unit/parsers/test_table_parser.py`

```python
"""table_parser.py 단위 테스트 — rowspan/colspan 전개."""
import pytest
from parsers.table_parser import parse_html_table


class TestParseHtmlTable:

    def test_simple_table(self):
        html = "<table><tr><td>A</td><td>B</td></tr></table>"
        result = parse_html_table(html)
        assert result == [["A", "B"]]

    def test_rowspan_expansion(self):
        html = '''
        <table>
            <tr><td rowspan="2">헤더</td><td>A</td></tr>
            <tr><td>B</td></tr>
        </table>
        '''
        result = parse_html_table(html)
        assert result[0] == ["헤더", "A"]
        assert result[1] == ["헤더", "B"]  # rowspan 전개

    def test_colspan_expansion(self):
        html = '<table><tr><td colspan="2">합쳐짐</td></tr></table>'
        result = parse_html_table(html)
        assert result == [["합쳐짐", "합쳐짐"]]

    def test_malformed_html(self):
        html = "<table><tr><td>깨진 태그"
        # 비정상 HTML이어도 recovering parser로 일부 추출
        result = parse_html_table(html)
        assert len(result) >= 1
```

### 3.3 `tests/unit/parsers/test_section_splitter.py`

```python
"""section_splitter.py 단위 테스트 — 목차 기반 분할."""
import pytest
from parsers.section_splitter import split_sections


class TestSplitSections:

    def test_split_by_headers(self):
        md = """# 섹션 1
내용 1
# 섹션 2
내용 2"""
        result = split_sections(md)
        assert len(result) == 2
        assert "섹션 1" in result[0]["title"]

    def test_toc_based_split(self, tmp_path):
        toc_data = [{"id": "1.1", "title": "일반사항", "page": 1}]
        md = "<!-- PAGE 1 -->\n일반사항\n본문..."
        result = split_sections(md, toc=toc_data)
        assert result[0]["section_id"] == "1.1"

    def test_no_toc_fallback(self):
        md = "본문만 있음"
        result = split_sections(md)
        assert len(result) == 1
        assert result[0]["section_id"] is not None  # 자동 ID
```

### 3.4 `tests/unit/parsers/test_bom_table_parser.py`

```python
"""bom_table_parser.py 단위 테스트."""
import pytest
from parsers.bom_table_parser import parse_bom_rows


class TestParseBomRows:

    def test_standard_row(self):
        md = "| 1 | PIPE-001 | 10 | EA | 강관 |"
        rows = parse_bom_rows(md)
        assert rows[0]["sn"] == "1"
        assert rows[0]["spec"] == "PIPE-001"

    def test_filter_empty_rows(self):
        md = """| 1 | P-001 | 10 |
| | | |
| 2 | P-002 | 20 |"""
        rows = parse_bom_rows(md)
        assert len(rows) == 2  # 빈 행 제외

    def test_filter_header_repeat(self):
        """반복 헤더 제거"""
        md = """| S/N | SPEC | QTY |
| 1 | P-001 | 10 |
| S/N | SPEC | QTY |
| 2 | P-002 | 20 |"""
        rows = parse_bom_rows(md)
        assert len(rows) == 2
```

### 3.5 `tests/unit/extractors/test_bom_extractor.py`

```python
"""bom_extractor.py 단위 테스트 — 상태머신."""
import pytest
from extractors.bom_extractor import _sanitize_html, BomSection


class TestSanitizeHtml:

    def test_tr_becomes_newline(self):
        html = "<tr><td>A</td></tr><tr><td>B</td></tr>"
        result = _sanitize_html(html)
        assert "\n" in result

    def test_td_becomes_separator(self):
        html = "<td>A</td><td>B</td>"
        result = _sanitize_html(html)
        assert "|" in result

    def test_case_insensitive(self):
        html = "<TR><TD>A</TD></TR>"
        result = _sanitize_html(html)
        assert result  # 대소문자 무관 처리


class TestBomSection:

    def test_creation(self):
        section = BomSection(title="LINE 1", rows=[], page=1)
        assert section.title == "LINE 1"

    def test_row_count(self):
        section = BomSection(title="LINE 1", rows=[{"sn": "1"}, {"sn": "2"}], page=1)
        assert section.row_count == 2
```

### 3.6 `tests/unit/extractors/test_toc_parser.py`

```python
"""toc_parser.py 단위 테스트."""
import pytest
from extractors.toc_parser import parse_toc_json, parse_toc_text


class TestParseTocJson:

    def test_valid_json(self, tmp_path):
        toc_file = tmp_path / "toc.json"
        toc_file.write_text('[{"id":"1.1","title":"개요","page":1}]', encoding="utf-8")
        result = parse_toc_json(str(toc_file))
        assert len(result) == 1
        assert result[0]["id"] == "1.1"

    def test_missing_file(self):
        with pytest.raises(FileNotFoundError):
            parse_toc_json("/nonexistent.json")
```

---

## 4. 작업 4: P2 단위 테스트 작성

### 4.1 `tests/unit/utils/test_markers.py`

```python
"""markers.py 단위 테스트."""
from utils.markers import make_page_marker, make_section_marker, extract_markers


def test_page_marker_format():
    assert make_page_marker(5) == "<!-- PAGE 5 -->"


def test_extract_markers():
    md = "<!-- PAGE 1 -->\n내용\n<!-- PAGE 2 -->\n다음"
    result = extract_markers(md)
    assert result["pages"] == [1, 2]
```

### 4.2 `tests/unit/utils/test_text_formatter.py`

```python
"""text_formatter.py 단위 테스트."""
from utils.text_formatter import merge_broken_lines


def test_merge_broken_korean():
    """줄바꿈으로 쪼개진 한글 병합"""
    text = "안녕하\n세요"
    assert merge_broken_lines(text) == "안녕하세요"


def test_preserve_sentence_end():
    text = "안녕합니다.\n반갑습니다."
    result = merge_broken_lines(text)
    assert "\n" in result  # 문장 종결 후는 유지
```

### 4.3 `tests/unit/utils/test_usage_tracker.py`

```python
"""usage_tracker.py 단위 테스트."""
from utils.usage_tracker import UsageTracker


def test_initial_state():
    tracker = UsageTracker()
    assert tracker.call_count == 0
    assert tracker.total_input_tokens == 0


def test_record_call():
    tracker = UsageTracker()
    tracker.record_call(input_tokens=1000, output_tokens=500)
    assert tracker.call_count == 1
    assert tracker.total_input_tokens == 1000


def test_cost_estimation():
    tracker = UsageTracker()
    tracker.record_call(input_tokens=1_000_000, output_tokens=1_000_000)
    summary = tracker.summary()
    assert "$" in summary
```

### 4.4 `tests/unit/presets/test_estimate.py`

```python
"""presets/estimate.py 단위 테스트."""
from presets.estimate import get_table_type_keywords, extract_cover_metadata


def test_keywords_structure():
    kw = get_table_type_keywords()
    assert "estimate" in kw or "견적" in kw


def test_cover_metadata_extraction():
    md = "견적일자: 2026-04-17\n프로젝트: 배관 지지대"
    result = extract_cover_metadata(md)
    assert result.get("date") == "2026-04-17"
```

---

## 5. 작업 5: 통합 테스트 마이그레이션

### 5.1 기존 테스트 정리

**이동/폐기 방침:**

| 기존 파일 | 조치 | 새 위치 |
|---------|-----|--------|
| `test_phase4_unit.py` | 이동 (pytest 형식으로 리팩터) | `tests/integration/test_phase4_pipeline.py` |
| `test_phase5_unit1~5.py` | 통합 (1개 파일로) | `tests/integration/test_phase5_batch.py` |
| `test_collision.py` | 이동 | `tests/integration/test_file_collision.py` |
| `test_excel_lock.py` | 이동 | `tests/integration/test_file_lock.py` |
| `test_folder_lock.py` | 병합 | `tests/integration/test_file_lock.py` |
| `test_lock.py` | 병합 | `tests/integration/test_file_lock.py` |
| `test_zai_api.py` | 이동 + `@pytest.mark.api` | `tests/integration/test_zai_api.py` |
| `_test_patch_verify.py` | 삭제 (디버그용) | - |
| `_test_phase3.py` | 삭제 | - |
| `_debug_agg.py` | 삭제 | - |
| `_inspect_json.py` | 삭제 | - |

### 5.2 예시: `tests/integration/test_phase4_pipeline.py`

```python
"""
Phase 4 파이프라인 통합 테스트.
기존 test_phase4_unit.py를 pytest 형식으로 변환.
"""
import pytest
from pathlib import Path


@pytest.mark.integration
class TestPhase4Pipeline:

    @pytest.mark.slow
    def test_tesseract_engine_end_to_end(self, sample_pdf_dir, temp_output_dir):
        """Tesseract로 샘플 PDF → MD 전체 파이프라인"""
        from engines.tesseract_engine import TesseractEngine

        engine = TesseractEngine()
        if not engine.is_available():
            pytest.skip("Tesseract 미설치")

        # ... 실제 통합 테스트 로직
```

### 5.3 End-to-End 테스트

```python
# tests/integration/test_end_to_end.py
import pytest
from pathlib import Path
from main import _process_single


@pytest.mark.integration
@pytest.mark.slow
def test_full_pipeline_local_engine(sample_pdf_dir, temp_output_dir):
    """샘플 PDF → MD → JSON → Excel 전체 파이프라인 (local 엔진)"""
    pdf = sample_pdf_dir / "tiny_test.pdf"

    # 가짜 args 객체
    class Args:
        engine = "local"
        output_format = "excel"
        preset = None
        # ... 필수 속성
    args = Args()

    _process_single(args, pdf, temp_output_dir, cache=None, tracker=None)

    # 산출물 확인
    assert list(temp_output_dir.glob("*.md"))
    assert list(temp_output_dir.glob("*.json"))
    assert list(temp_output_dir.glob("*.xlsx"))
```

---

## 6. 작업 6: CI 설정 (선택적)

### 6.1 `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        python-version: ["3.10", "3.11", "3.12"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install Poppler (Linux)
        if: runner.os == 'Linux'
        run: sudo apt-get install -y poppler-utils

      - name: Install Poppler (macOS)
        if: runner.os == 'macOS'
        run: brew install poppler

      - name: Install Poppler (Windows)
        if: runner.os == 'Windows'
        run: choco install poppler -y

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run unit tests
        run: pytest tests/unit --cov --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          file: ./coverage.xml
```

### 6.2 로컬 CI 스크립트 (대안)

```bash
# scripts/run_tests.sh (Linux/macOS)
#!/bin/bash
set -e

echo "=== ps-docparser 로컬 CI ==="

# 단위 테스트 (빠름)
echo "[1/3] 단위 테스트"
pytest tests/unit -v

# 통합 테스트 (느림, 옵션)
if [ "$1" == "--full" ]; then
    echo "[2/3] 통합 테스트"
    pytest tests/integration --run-slow

    echo "[3/3] API 테스트"
    pytest tests/integration --run-api -m api
fi

# 커버리지 리포트
pytest tests/unit --cov --cov-report=html
echo "커버리지 리포트: htmlcov/index.html"
```

```batch
:: scripts/run_tests.bat (Windows)
@echo off
echo === ps-docparser 로컬 CI ===

echo [1/3] 단위 테스트
pytest tests\unit -v
if errorlevel 1 goto :error

if "%1"=="--full" (
    echo [2/3] 통합 테스트
    pytest tests\integration --run-slow
    if errorlevel 1 goto :error

    echo [3/3] API 테스트
    pytest tests\integration --run-api -m api
)

pytest tests\unit --cov --cov-report=html
echo 커버리지 리포트: htmlcov\index.html
goto :eof

:error
echo 테스트 실패
exit /b 1
```

---

## 7. 작업 7: 테스트 가이드 문서

### 7.1 `tests/README.md` (신규)

```markdown
# ps-docparser 테스트 가이드

## 실행 방법

### 단위 테스트만 (빠름, ~30초)
```bash
pytest tests/unit
```

### 전체 테스트 (느림, ~5분)
```bash
pytest --run-slow
```

### API 호출 포함 (비용 발생, 실제 API 키 필요)
```bash
pytest --run-api
```

### 커버리지 리포트
```bash
pytest tests/unit --cov --cov-report=html
open htmlcov/index.html
```

### 특정 모듈만
```bash
pytest tests/unit/parsers
pytest tests/unit/test_detector.py
pytest tests/unit/test_detector.py::TestDetectDocumentType::test_bom_by_line_list
```

## 새 테스트 작성 규칙

### 파일 네이밍
- `tests/unit/<module_path>/test_<module>.py`

### 클래스 구조
```python
class TestFunctionName:
    def test_happy_path(self): ...
    def test_edge_case_empty(self): ...
    def test_error_handling(self): ...
```

### 픽스처 활용
- `tmp_path` — pytest 내장, 테스트별 임시 디렉토리
- `temp_output_dir`, `temp_cache_dir` — conftest.py 정의
- `clean_env` — 환경변수 격리
- `sample_md_dir`, `fixtures_dir` — 샘플 데이터

### Mock 원칙
- API 호출: **반드시** Mock (비용 + CI 환경 고려)
- 파일 I/O: 가능하면 `tmp_path` 사용, 어려우면 Mock
- 외부 바이너리(Poppler, Tesseract): Mock

### 마커 사용
- `@pytest.mark.slow` — 1초 이상
- `@pytest.mark.integration` — 실제 파일/DB
- `@pytest.mark.api` — 실제 API 호출
- `@pytest.mark.windows_only` / `macos_only`

## 커버리지 목표
- 전체: 50%+
- P0 모듈: 80%+
- 새 코드: 90%+ (Phase 8 이후 리뷰 기준)
```

---

## 8. 구현 순서 및 일정 (10일 계획)

| 일차 | 작업 | 산출물 |
|------|------|--------|
| **Day 1** | 인프라 셋업 | pytest.ini, .coveragerc, conftest.py, requirements-dev.txt |
| **Day 2** | P0 테스트 (detector, page_spec) | test_detector.py, test_page_spec.py |
| **Day 3** | P0 테스트 (io, config) | test_io.py, test_config.py |
| **Day 4** | P0 테스트 (table_cache) + 샘플 fixtures | test_table_cache.py, fixtures/ |
| **Day 5** | P1 테스트 (parsers 3개) | test_text_cleaner, test_table_parser, test_section_splitter |
| **Day 6** | P1 테스트 (bom_table_parser, bom_extractor, toc_parser) | 3개 파일 |
| **Day 7** | P2 테스트 (utils 3개) | test_markers, test_text_formatter, test_usage_tracker |
| **Day 8** | P2 테스트 (presets) + 기존 테스트 마이그레이션 | presets tests + integration 이동 |
| **Day 9** | CI 설정 + 커버리지 점검 + 미달 영역 보완 | .github/workflows/ci.yml (또는 scripts/) |
| **Day 10** | 테스트 가이드 + Phase 7 결과 보고서 | tests/README.md, Phase7_결과보고서.md |

### 체크포인트

- **Day 3 EOD**: P0 테스트 3개 완료, 커버리지 최소 25%+
- **Day 6 EOD**: P1 테스트 완료, 커버리지 40%+
- **Day 9 EOD**: 전체 커버리지 50%+ 달성
- **Day 10 EOD**: 완료 기준 전부 충족

---

## 9. 위험 요소 및 대응

| 위험 | 영향도 | 확률 | 대응 |
|------|-------|-----|------|
| 테스트 작성 중 버그 발견 | 중 | 높음 | 버그 우선 수정 후 테스트 작성 (TDD 원칙) |
| API Mock이 실제 응답과 괴리 | 높음 | 중 | fixtures/mock_responses/에 실제 응답 캡처 후 사용 |
| 커버리지 50% 달성 실패 | 중 | 낮음 | P2 일부를 Phase 8~로 이월 가능 |
| 기존 통합 테스트 파괴 | 높음 | 중 | 이동 전 기존 동작 기록, 변환 후 비교 |
| Windows/macOS 별 경로 문제 | 중 | 중 | `Path` 객체 + `pathlib` 일관 사용 강제 |
| Tesseract/Poppler 없는 CI | 높음 | 높음 | CI job에서 apt/brew로 설치 or Mock |

---

## 10. 완료 후 산출물

### 10.1 코드
- `tests/` 디렉토리 전체 (신규)
- `pytest.ini`, `.coveragerc`, `requirements-dev.txt` (신규)
- `.github/workflows/ci.yml` 또는 `scripts/run_tests.*` (신규)

### 10.2 문서
- `tests/README.md` (테스트 가이드)
- `Phase7_결과보고서.md` (변경 내역, 커버리지 결과, 발견된 버그)

### 10.3 메트릭
- 커버리지 리포트 (`htmlcov/index.html`)
- 테스트 실행 시간 로그
- 발견/수정된 버그 목록

---

## 11. Phase 8로의 인계사항

Phase 8(성능 최적화)에서 활용할 Phase 7 산출물:
- **리팩터링 안전망**: 정규식 캐싱, 이미지 캐싱 시 기존 테스트가 regression 감지
- **벤치마크 기반**: `pytest-benchmark` 추가 고려
- **Mock 재활용**: API 호출 캐시 테스트에 기존 mock 활용

---

## 부록 A: Mock 사용 예시

### A.1 Gemini API 호출 Mock
```python
from unittest.mock import patch, MagicMock


def test_gemini_engine_with_mock(monkeypatch):
    mock_response = MagicMock()
    mock_response.text = "| A | B |\n| 1 | 2 |"

    with patch("google.generativeai.GenerativeModel") as MockModel:
        MockModel.return_value.generate_content.return_value = mock_response

        from engines.gemini_engine import GeminiEngine
        engine = GeminiEngine(api_key="fake")
        result = engine.extract_table_from_image(b"fake_image_bytes")

        assert "A" in result
```

### A.2 SQLite Mock (메모리 DB)
```python
def test_cache_with_memory_db():
    from cache.table_cache import TableCache
    cache = TableCache(db_path=":memory:", ttl_days=30)
    # ... 실제 DB 없이 테스트
```

### A.3 파일 시스템 Mock
```python
def test_with_pyfakefs(fs):  # pytest-pyfakefs 플러그인
    fs.create_file("/fake/sample.pdf", contents=b"dummy")
    # 실제 파일 없이 Path 기반 코드 테스트
```

---

## 부록 B: 커버리지 제외 규칙

다음은 `.coveragerc`에서 제외된 항목과 이유:

| 패턴 | 이유 |
|------|------|
| `tests/*` | 테스트 코드 자체 |
| `__init__.py` | 대부분 비어있음 |
| `_debug_*.py`, `_inspect_*.py` | 디버그 전용 |
| `audit_main.py` | 개발 보조 스크립트 |
| `test_phase*.py` | Phase 7 이후 deprecated |

---

## 부록 C: 테스트 실행 예시 출력

```
$ pytest tests/unit --cov --cov-report=term-missing

========================= test session starts =========================
platform win32 -- Python 3.11.8, pytest-8.0.2
collected 87 tests

tests/unit/test_detector.py ........                          [  9%]
tests/unit/test_config.py ............                        [ 22%]
tests/unit/utils/test_page_spec.py ...............            [ 40%]
tests/unit/utils/test_io.py .........                         [ 50%]
tests/unit/cache/test_table_cache.py ........                 [ 59%]
tests/unit/parsers/test_text_cleaner.py ......                [ 66%]
...

---------- coverage: platform win32, python 3.11.8 ----------
Name                          Stmts   Miss  Branch  BrPart  Cover
---------------------------------------------------------------
config.py                        87      9      14      2    89%
detector.py                      42      2       8       0    96%
utils/page_spec.py               38      1       6       0    97%
utils/io.py                      15      0       4       0   100%
cache/table_cache.py             95     12      18       3    86%
parsers/text_cleaner.py         128     31      22       5    76%
...
---------------------------------------------------------------
TOTAL                          2847    856    432     73    68%

========================= 87 passed in 12.34s =========================
```

---

**기술서 작성자:** Claude Opus 4
**작성일:** 2026-04-17
**다음 단계:** 본 기술서 승인 후 Phase 7 구현 착수 (10일 계획)
**관련 문서:**
- `ps-docparser_코드리뷰_보고서.md` §10 Phase 7
- `Phase6_상세_구현_기술서.md` (선행 작업)
- `Phase6_결과보고서.md`
