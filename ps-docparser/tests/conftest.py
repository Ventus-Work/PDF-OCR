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
