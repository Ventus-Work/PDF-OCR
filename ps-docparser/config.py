"""
config.py — ps-docparser 전역 설정 모듈

Why: API 키, Poppler 경로, 엔진 설정을 한 곳에서 관리한다.
     각 모듈이 직접 .env를 로딩하면 실행 위치에 따라 경로가 달라지는 충돌이 발생한다.
     이 모듈 한 곳에서 로딩을 일원화하여 어느 디렉토리에서 실행해도 동일하게 동작한다.

이식 원본: step1_extract_gemini_v33.py L25~101
"""

import os
import platform
import logging
from pathlib import Path

from dotenv import load_dotenv

# ── .env 탐색 순서: 프로젝트 루트 → 상위 → cwd ──
# Why: 프로젝트 루트에 .env를 두는 것이 표준이지만,
#      어느 경로에서 실행해도 찾을 수 있도록 3군데를 순서대로 탐색한다.
BASE_DIR = Path(__file__).resolve().parent
_env_candidates = [
    BASE_DIR / ".env",
    BASE_DIR.parent / ".env",
    Path.cwd() / ".env",
]
for _env_path in _env_candidates:
    if _env_path.exists():
        load_dotenv(_env_path)
        break

# ── 로깅 설정 ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── API 키 및 모델 ──
def _parse_env_list(*env_names: str) -> tuple[str, ...]:
    """Parse comma/newline/semicolon-separated environment values."""

    values: list[str] = []
    for env_name in env_names:
        raw_value = os.getenv(env_name)
        if not raw_value:
            continue
        normalized = raw_value.replace("\r", "\n")
        for chunk in normalized.replace(";", "\n").replace(",", "\n").split("\n"):
            stripped = chunk.strip()
            if stripped:
                values.append(stripped)
    return tuple(values)


GEMINI_API_KEYS: tuple[str, ...] = _parse_env_list("GEMINI_API_KEYS", "GEMINI_API_KEY")
GEMINI_API_KEY: str | None = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else None
GEMINI_KEY_MAX_CALLS: int = int(os.getenv("GEMINI_KEY_MAX_CALLS", "20"))
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
ZAI_API_KEY: str | None = os.getenv("ZAI_API_KEY")

# ── 기본 엔진 선택 ──
# Why: .env의 DEFAULT_ENGINE으로 기본값을 지정하되, CLI의 --engine이 최우선이다.
#      이 값은 main.py에서 --engine 미지정 시 폴백으로만 사용된다.
DEFAULT_ENGINE: str = os.getenv("DEFAULT_ENGINE", "gemini")

# ── 무료 티어 딜레이 ──
# Why: Gemini 무료 티어는 15 RPM(분당 요청) 제한이 있다.
#      4초 간격 = 분당 최대 15회로 제한 이내 유지.
FREE_TIER_DELAY: int = int(os.getenv("FREE_TIER_DELAY", "4"))


def _detect_poppler_path() -> str | None:
    """
    Poppler 바이너리 경로를 자동 감지한다.

    탐색 순서:
        1. 환경변수 POPPLER_PATH (모든 플랫폼)
        2. 시스템 PATH (shutil.which)
        3. OS별 기본 설치 경로 (glob 패턴 매칭)

    Returns:
        str | None: 바이너리 디렉토리 경로 또는 None
    """
    import shutil
    import glob

    # 1순위: 환경변수 (사용자 직접 지정)
    env_path = os.environ.get("POPPLER_PATH")
    if env_path and os.path.exists(env_path):
        return env_path

    # 2순위: 시스템 PATH에서 poppler 바이너리 탐색
    # Why pdftotext: poppler 설치 시 항상 포함되는 대표 바이너리
    which_result = shutil.which("pdftotext")
    if which_result:
        return os.path.dirname(which_result)

    # 3순위: OS별 기본 경로
    system = platform.system()
    candidates: list[str] = []

    if system == "Windows":
        # glob으로 버전 무관 검색
        candidates.extend(sorted(
            glob.glob(r"C:\poppler\poppler-*\Library\bin"),
            reverse=True,  # 최신 버전 우선
        ))
        candidates.extend([
            r"C:\Program Files\poppler\Library\bin",
            r"C:\poppler\bin",
            r"C:\tools\poppler\bin",  # chocolatey
        ])
    elif system == "Darwin":  # macOS
        candidates.extend([
            "/opt/homebrew/bin",      # Apple Silicon (M1/M2/M3)
            "/usr/local/bin",          # Intel Homebrew
            "/opt/local/bin",          # MacPorts
        ])
    else:  # Linux
        candidates.extend([
            "/usr/bin",
            "/usr/local/bin",
        ])

    for path in candidates:
        if os.path.exists(path):
            return path

    # 못 찾음 — 경고 로그
    logger.warning(
        "Poppler 경로를 찾을 수 없습니다. "
        "pdf2image 사용 시 오류가 발생할 수 있습니다. "
        "설치 방법: Windows=choco install poppler, "
        "macOS=brew install poppler, Linux=apt install poppler-utils"
    )
    return None


# ── Poppler 경로 (모듈 로드 시 1회 탐색) ──
POPPLER_PATH: str | None = _detect_poppler_path()

# ── 출력 기본 폴더 ──
# Why: config에서 정의해두면 main.py와 테스트에서 동일한 경로를 참조한다.
OUTPUT_DIR: Path = BASE_DIR / "output"

# ── 테이블 bbox 검증 상수 (이식 원본: L97~101) ──
# 페이지 높이 대비 이 비율 미만이면 "헤더만 잡힌" 비정상 테이블로 판단
TABLE_MIN_HEIGHT_RATIO: float = 0.08  # 8%
# 크롭 시 아래쪽 추가 패딩 (포인트 단위)
TABLE_BOTTOM_EXTRA_PADDING: int = 40

# ── Phase 4: OCR 엔진 설정 ──
# 참고: ZAI_API_KEY는 L43에서 이미 정의됨
MISTRAL_API_KEY: str | None = os.getenv("MISTRAL_API_KEY")

# Document pipeline OCR fallback settings
DOCUMENT_OCR_FALLBACK_ORDER: tuple[str, ...] = ("zai", "mistral", "tesseract")
DOCUMENT_MIN_VISIBLE_CHARS: int = 200
DOCUMENT_MIN_VISIBLE_CHARS_PER_PAGE: int = 80
DOCUMENT_MIN_STRUCTURED_CHARS: int = 400


def _detect_tesseract_path() -> str | None:
    import shutil

    # 1순위: 환경변수
    env_path = os.environ.get("TESSERACT_PATH")
    if env_path and Path(env_path).exists():
        return env_path

    # 2순위: 시스템 PATH
    path = shutil.which("tesseract")
    if path:
        return path

    # 3순위: OS별 기본 경로
    system = platform.system()
    candidates: list[str] = []
    if system == "Windows":
        candidates = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ]
    elif system == "Darwin":
        candidates = [
            "/opt/homebrew/bin/tesseract",
            "/usr/local/bin/tesseract",
        ]
    else:  # Linux
        candidates = [
            "/usr/bin/tesseract",
            "/usr/local/bin/tesseract",
        ]

    for p in candidates:
        if Path(p).exists():
            return p

    return None


# ⚠️ 반드시 _detect_tesseract_path() 정의 이후에 배치 (NameError 방지)
TESSERACT_PATH: str | None = os.getenv("TESSERACT_PATH") or _detect_tesseract_path()

BOM_DEFAULT_ENGINE: str = os.getenv("BOM_DEFAULT_ENGINE", "zai")

# ── Phase 5: 캐시 설정 ──
# Why CACHE_ENABLED: 개발/디버깅 시 캐시를 끄고 API 응답 원문을 직접 확인해야 할 때 사용.
#                    CACHE_ENABLED=false (환경변수)로 비활성화한다.
CACHE_TTL_DAYS: int = int(os.getenv("CACHE_TTL_DAYS", "30"))
CACHE_ENABLED: bool = os.getenv("CACHE_ENABLED", "true").lower() == "true"
# Why .cache (숨김 폴더): cache/ 에는 Python 소스(table_cache.py)가 있으므로
#                         데이터 파일과 분리한다. (이미 .gitignore에 등록됨)
CACHE_DIR: Path = BASE_DIR / ".cache"

# ── Phase 8: AI 엔진 요금 설정 (환경변수 오버라이드 지원) ──
# Why: Gemini 가격은 모델/플랜별로 자주 변경된다.
#      하드코딩 대신 env 우선으로 참조 → 코드 변경 없이 요금 갱신 가능.
GEMINI_INPUT_PRICE_PER_M: float  = float(os.getenv("GEMINI_INPUT_PRICE",  "0.10"))
GEMINI_OUTPUT_PRICE_PER_M: float = float(os.getenv("GEMINI_OUTPUT_PRICE", "0.40"))
GEMINI_PRICING_MODEL: str        = os.getenv("GEMINI_PRICING_MODEL", "gemini-2.0-flash")


def validate_config(verbose: bool = True) -> dict:
    """
    시작 시점에 설정 유효성을 검증하고 경고를 출력한다.

    Returns:
        dict: {"warnings": [...], "errors": [...], "info": [...]}
    """
    result = {"warnings": [], "errors": [], "info": []}

    # 1. Poppler 검증
    if POPPLER_PATH:
        result["info"].append(f"Poppler: {POPPLER_PATH}")
    else:
        result["warnings"].append(
            "Poppler 미검출 — pdf2image 기반 엔진(gemini, mistral) 사용 불가"
        )

    # 2. API 키 검증 (엔진별)
    engine = DEFAULT_ENGINE
    if engine == "gemini" and not GEMINI_API_KEYS:
        result["errors"].append(
            "DEFAULT_ENGINE=gemini이나 GEMINI_API_KEY 또는 GEMINI_API_KEYS가 없습니다. "
            ".env 파일 확인 또는 --engine local 사용하세요."
        )
    elif engine == "zai" and not ZAI_API_KEY:
        result["errors"].append(
            "DEFAULT_ENGINE=zai이나 ZAI_API_KEY가 없습니다."
        )
    elif engine == "mistral" and not MISTRAL_API_KEY:
        result["errors"].append(
            "DEFAULT_ENGINE=mistral이나 MISTRAL_API_KEY가 없습니다."
        )

    # 3. Tesseract 검증 (engine=tesseract 시에만)
    if engine == "tesseract" and not TESSERACT_PATH:
        result["errors"].append(
            "DEFAULT_ENGINE=tesseract이나 tesseract 바이너리를 찾을 수 없습니다."
        )

    # 4. 로그 출력
    if verbose:
        for msg in result["info"]:
            logger.info(f"✅ {msg}")
        for msg in result["warnings"]:
            logger.warning(f"⚠️  {msg}")
        for msg in result["errors"]:
            logger.error(f"❌ {msg}")

    return result
