# Phase 6 상세 구현 기술서 — 긴급 안정화 (Critical Stabilization)

**작성일:** 2026-04-17
**대상 프로젝트:** ps-docparser
**페이즈 목표:** 현재 배포 환경에서 발생 가능한 즉각적 오류를 차단하고, 다른 환경(신규 PC, 버전 업데이트 등)에서도 안정적으로 작동하도록 기반을 다진다.
**예상 기간:** 1주 (약 5~7 작업일)
**우선순위:** 🔴 P0 - Critical

---

## 0. 개요 및 범위

### 0.1 Phase 6의 위치
- **이전 단계(Phase 1~5):** 기능 구현 완료 (PDF→MD→JSON→Excel, 배치+캐싱)
- **현재 단계(Phase 6):** 품질/안정성 확보
- **다음 단계(Phase 7):** 테스트 인프라 구축

### 0.2 작업 대상 파일

| 파일 | 변경 유형 | 라인 수 변화 |
|------|---------|-----------|
| `requirements.txt` | 버전 범위 추가 | 8 → 8 |
| `config.py` | 함수 리팩터링 + 검증 추가 | 157 → ~200 |
| `main.py` | try/except 블록 추가 (3곳) | 786 → ~810 |
| `.gitignore` | 확인 (이미 `.env` 포함됨) | 변경 없음 |
| `.env.example` | 필수 항목 주석 강화 | 소폭 변경 |

### 0.3 완료 기준 (Definition of Done)

- [ ] 모든 의존성에 상/하한 버전이 명시됨
- [ ] Poppler가 다른 버전으로 설치되어도 자동 감지됨
- [ ] macOS (Homebrew) 환경에서도 Poppler 경로 감지됨
- [ ] Excel이 파일을 점유 중이어도 배치 처리가 계속 진행됨
- [ ] API 키 누락 시 실행 직후 명확한 경고 출력
- [ ] 기존 테스트가 모두 통과함 (regression 없음)

---

## 1. 작업 1: requirements.txt 버전 고정

### 1.1 배경 및 필요성

**현재 상태** (`requirements.txt`):
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

**문제점:**
- 버전 미지정 → `pip install -r requirements.txt` 시 항상 최신 버전 설치
- `openpyxl`이 3.2.0에서 API 변경되면 `excel_exporter.py`가 즉시 깨짐
- `google-generativeai` 1.0.0 릴리즈 시 API 시그니처 변경 가능성
- 신규 PC 설치 시 예상치 못한 오류 발생

### 1.2 구현 방안

**변경 후** (`requirements.txt`):
```
# PDF 처리
pdfplumber>=0.11.0,<1.0.0
pdf2image>=1.17.0,<2.0.0
Pillow>=11.0.0,<12.0.0

# AI / OCR 엔진
google-generativeai>=0.8.0,<1.0.0

# 설정 & 파싱
python-dotenv>=1.0.0,<2.0.0
beautifulsoup4>=4.12.0,<5.0.0
lxml>=5.0.0,<6.0.0

# Excel 출력
openpyxl>=3.1.0,<4.0.0

# (선택) OCR 엔진 — 설치되어 있지 않으면 해당 엔진만 비활성화
# pytesseract>=0.3.10,<1.0.0
# mistralai>=0.4.0,<1.0.0
# zai>=0.1.0,<1.0.0
```

### 1.3 버전 선정 근거

| 패키지 | 하한 | 상한 | 근거 |
|--------|------|------|------|
| pdfplumber | 0.11.0 | <1.0.0 | 0.11에서 bbox API 안정화 |
| google-generativeai | 0.8.0 | <1.0.0 | Gemini 2.0 Flash 지원 시작점 |
| pdf2image | 1.17.0 | <2.0.0 | Python 3.10+ 공식 지원 |
| Pillow | 11.0.0 | <12.0.0 | 2024년 LTS 계열 |
| openpyxl | 3.1.0 | <4.0.0 | 3.1.x에서 hyperlink API 안정 |

### 1.4 검증 방법

```bash
# 1. 기존 환경 백업
pip freeze > requirements_backup.txt

# 2. 가상환경 새로 생성 및 설치 테스트
python -m venv venv_test
venv_test\Scripts\activate
pip install -r requirements.txt

# 3. 주요 기능 smoke test
python main.py --help
python main.py sample.pdf --engine local --output md
```

### 1.5 위험 요소 및 완화

| 위험 | 발생 확률 | 완화 방안 |
|------|---------|---------|
| 하한 버전이 구형 Python과 충돌 | 낮음 | Python 3.10+ 전제, 문서에 명시 |
| 상한 제한이 보안 패치 차단 | 중간 | 메이저 버전 범위만 제한, 패치는 허용 |
| 선택 패키지(mistralai 등) 설치 실패 | 중간 | 주석 처리 + README에 별도 설치 안내 |

---

## 2. 작업 2: config.py Poppler/Tesseract 경로 감지 개선

### 2.1 배경 및 필요성

**현재 상태** (`config.py:71-89`):
```python
if platform.system() == "Windows":
    candidates = [
        r"C:\poppler\poppler-24.08.0\Library\bin",  # ← 버전 하드코딩!
        r"C:\Program Files\poppler\Library\bin",
        r"C:\poppler\bin",
    ]
```

**문제점:**
1. `poppler-24.08.0` 버전 하드코딩 → 25.x로 업데이트 시 감지 실패
2. macOS Homebrew 경로 미지원 (`/usr/local/bin`, `/opt/homebrew/bin`)
3. Linux 표준 경로만 시도, `shutil.which()` 폴백 없음
4. Tesseract는 `shutil.which()` 사용하지만 Poppler는 사용 안 함 (일관성 부족)

### 2.2 구현 방안

#### 2.2.1 `_detect_poppler_path()` 개선

**개선 후 함수 구조:**

```python
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
```

#### 2.2.2 `_detect_tesseract_path()` 통일성 확보

현재 이미 `shutil.which()` 사용 중 → 맥 Homebrew 경로만 보강

```python
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
```

### 2.3 API 키 검증 로직 추가

`config.py` 하단에 신규 함수 추가:

```python
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
    if engine == "gemini" and not GEMINI_API_KEY:
        result["errors"].append(
            "DEFAULT_ENGINE=gemini이나 GEMINI_API_KEY가 없습니다. "
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
```

### 2.4 main.py에서 호출

```python
# main.py 상단 import 부분
from config import validate_config

# main() 함수 시작 직후
def main():
    args = _parse_args()

    # ── 설정 검증 (Phase 6) ──
    validation = validate_config(verbose=True)
    if validation["errors"] and not args.force:
        print("설정 오류로 중단합니다. --force 옵션으로 강제 실행 가능.")
        sys.exit(1)

    # ... 기존 로직
```

---

## 3. 작업 3: main.py 파일 I/O 예외 처리

### 3.1 배경 및 필요성

**현재 상태** (`main.py:504-510`):
```python
md_path = _get_output_path(out_dir, str(input_path), page_indices_local)
with open(md_path, "w", encoding="utf-8-sig") as f:
    f.write(md)
print(f"  MD 출력: {md_path.name} ({len(md):,} bytes)")
```

**문제점:**
- 출력 파일을 Excel 등 외부 프로그램이 열고 있으면 `PermissionError` 발생
- 디스크 공간 부족 시 `OSError` 발생
- 경로가 너무 길거나 잘못된 문자 포함 시 `OSError` 발생
- **배치 처리 시 1건 실패 → 전체 중단**

### 3.2 구현 방안

#### 3.2.1 Helper 함수 추가

`main.py` 상단(import 부분 바로 아래)에 helper 함수 추가:

```python
def _safe_write_text(path: Path, content: str, encoding: str = "utf-8-sig") -> None:
    """
    안전한 파일 쓰기. I/O 예외를 ParserError로 표준화한다.

    Raises:
        ParserError: 파일 쓰기 실패 시 (배치 처리가 해당 파일만 스킵)
    """
    try:
        # 부모 디렉토리 자동 생성
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding=encoding) as f:
            f.write(content)
    except PermissionError as e:
        raise ParserError(
            f"파일 쓰기 권한 거부: {path.name}\n"
            f"  → 파일이 다른 프로그램(Excel 등)에서 열려있는지 확인하세요.\n"
            f"  상세: {e}"
        )
    except OSError as e:
        # 디스크 공간 부족, 경로 너무 길음, 잘못된 문자 등
        raise ParserError(
            f"파일 I/O 오류: {path.name}\n"
            f"  → 디스크 공간/경로 길이/파일명 문자를 확인하세요.\n"
            f"  상세: {e}"
        )
```

#### 3.2.2 적용 위치

**적용 지점 1: MD 파일 저장** (`main.py:507`)
```python
# 변경 전
with open(md_path, "w", encoding="utf-8-sig") as f:
    f.write(md)

# 변경 후
_safe_write_text(md_path, md)
```

**적용 지점 2: JSON 파일 저장** (`exporters/json_exporter.py`)
```python
# 동일한 패턴 적용
_safe_write_text(json_path, json.dumps(sections, ensure_ascii=False, indent=2))
```

**적용 지점 3: Excel 저장은 openpyxl의 `wb.save()`가 이미 예외 발생**
→ 배치 루프에서 잡아서 continue 처리

#### 3.2.3 배치 루프 개선

**현재 상태 (추정)** — `main.py` 배치 처리 부분:
```python
for pdf in pdf_files:
    _process_single(args, pdf, ...)  # 1건 실패 시 raise → 전체 중단
```

**개선 후:**
```python
failed: list[tuple[str, str]] = []
succeeded: list[str] = []

for pdf in pdf_files:
    try:
        _process_single(args, pdf, ...)
        succeeded.append(pdf.name)
    except ParserError as e:
        # 사용자 정의 예외 → 스킵하고 계속
        failed.append((pdf.name, str(e)))
        logger.error(f"❌ {pdf.name}: {e}")
        continue
    except KeyboardInterrupt:
        # Ctrl+C는 전체 중단
        print("\n사용자 중단.")
        break
    except Exception as e:
        # 예상 못한 예외 → 로그 남기고 스킵
        failed.append((pdf.name, f"예상 못한 오류: {type(e).__name__}: {e}"))
        logger.exception(f"❌ {pdf.name}: 예상 못한 오류")
        continue

# 배치 요약
print(f"\n=== 배치 처리 완료 ===")
print(f"성공: {len(succeeded)}건")
print(f"실패: {len(failed)}건")
if failed:
    print("\n실패 목록:")
    for name, err in failed:
        print(f"  - {name}: {err[:100]}")
```

### 3.3 검증 시나리오

| 시나리오 | 기대 동작 |
|---------|---------|
| 정상 파일 | 성공 |
| 출력 파일을 Excel로 열어둔 상태 | ParserError, 다음 파일 계속 |
| 디스크 공간 0 | ParserError, 명확한 메시지 |
| 존재하지 않는 출력 폴더 | 자동 생성 후 성공 |
| Ctrl+C | 즉시 중단 + 요약 출력 |

---

## 4. 작업 4: .gitignore 및 .env.example 확인/보강

### 4.1 .gitignore 현재 상태 (확인 완료)

```
.env           ✅ 이미 포함됨
.cache/        ✅ 이미 포함됨
__pycache__/   ✅ 이미 포함됨
output/        ✅ 이미 포함됨
*.log          ✅ 이미 포함됨
```

**추가 권장 항목:**
```
# Phase 6 추가
venv_test/             # 테스트 가상환경
*.pyc
.pytest_cache/         # Phase 7 대비
.coverage              # Phase 7 대비
htmlcov/               # Phase 7 대비
*.egg-info/            # Phase 11 대비 (PyPI 배포)
dist/                  # Phase 11 대비
build/                 # Phase 11 대비
```

### 4.2 .env.example 보강

**현재 추정** — `.env.example` 은 730 바이트

**권장 구조:**
```bash
# ============================================
# ps-docparser 환경변수 설정
# Copy this file to .env and fill in your values
# ============================================

# ── 필수 (사용하려는 엔진 중 최소 1개) ──
# Gemini (권장, 무료 티어 15 RPM)
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.0-flash

# Z.ai GLM-OCR (BOM 특화)
ZAI_API_KEY=

# Mistral Pixtral OCR (폴백)
MISTRAL_API_KEY=

# ── 기본 엔진 선택 ──
# 옵션: gemini | zai | mistral | local | tesseract
DEFAULT_ENGINE=gemini
BOM_DEFAULT_ENGINE=zai

# ── 외부 바이너리 경로 (자동 감지 우선, 수동 오버라이드 필요 시) ──
# POPPLER_PATH=C:\poppler\poppler-24.08.0\Library\bin
# TESSERACT_PATH=C:\Program Files\Tesseract-OCR\tesseract.exe

# ── 무료 티어 딜레이 (초) ──
# Gemini 무료: 15 RPM = 4초 권장
FREE_TIER_DELAY=4

# ── 캐시 (Phase 5) ──
CACHE_ENABLED=true
CACHE_TTL_DAYS=30
```

---

## 5. 구현 순서 및 일정

### 5.1 권장 작업 순서

| 일차 | 작업 | 산출물 | 검증 |
|------|------|--------|------|
| 1일차 | requirements.txt 버전 고정 | requirements.txt | pip install 성공 |
| 1일차 | .env.example 보강 | .env.example | 수동 검토 |
| 2일차 | config.py Poppler/Tesseract 개선 | config.py | 각 OS에서 감지 확인 |
| 3일차 | config.py validate_config() 추가 | config.py | 각 누락 시나리오 |
| 4일차 | main.py _safe_write_text() 추가 | main.py | 파일 점유 시나리오 |
| 5일차 | main.py 배치 루프 개선 | main.py | 일부 실패 시나리오 |
| 6일차 | 통합 검증 (회귀 테스트) | 검증 보고서 | 기존 기능 regression 없음 |
| 7일차 | Phase 6 결과 보고서 작성 | Phase6_결과보고서.md | - |

### 5.2 체크포인트

- [ ] **Day 1 EOD**: requirements.txt 설치 재검증 완료
- [ ] **Day 3 EOD**: config.py 단독 실행 시 validate_config() 정상 출력
- [ ] **Day 5 EOD**: 의도적으로 Excel 파일 점유 후 배치 실행 → 스킵 확인
- [ ] **Day 7 EOD**: Phase 6 결과 보고서 작성 완료

---

## 6. 위험 요소 및 대응

| 위험 | 영향도 | 확률 | 대응 |
|------|-------|-----|------|
| 새 Poppler 감지 로직이 기존 감지 경로를 놓침 | 높음 | 낮음 | 기존 경로 모두 후보 리스트에 포함 |
| validate_config()의 errors가 너무 엄격 | 중 | 중 | `--force` 옵션으로 강제 실행 허용 |
| _safe_write_text 도입으로 기존 I/O 동작 변경 | 중 | 낮음 | 동일한 성공 시 동작 유지, 실패 시만 ParserError |
| 배치 루프의 except Exception이 버그 은폐 | 높음 | 중 | logger.exception()으로 전체 트레이스 로그 |
| requirements.txt 상한이 실제 breaking에서 발생 안 함 | 낮음 | 낮음 | Phase 7의 CI에서 최소/최대 버전 조합 테스트 |

---

## 7. 완료 후 산출물

### 7.1 코드 변경사항
- `requirements.txt` (버전 명시)
- `config.py` (경로 감지 + validate_config)
- `main.py` (_safe_write_text + 배치 루프 개선)
- `.env.example` (주석 보강)

### 7.2 문서
- `Phase6_결과보고서.md` (변경 내역, 검증 결과, 이슈)

### 7.3 테스트 증거
- 각 OS(Windows/macOS/Linux)에서 Poppler 감지 로그
- Excel 점유 시나리오에서 배치 스킵 로그
- API 키 누락 시 validate_config() 출력 캡처

---

## 8. Phase 7로의 인계사항

Phase 7(테스트 인프라)에서 다룰 Phase 6 관련 항목:
- `validate_config()`의 단위 테스트
- `_safe_write_text()`의 단위 테스트 (mock 활용)
- `_detect_poppler_path()`, `_detect_tesseract_path()`의 모킹 테스트
- 배치 루프의 예외 처리 통합 테스트

---

## 부록 A: 변경 전/후 요약 비교

### A.1 requirements.txt
```diff
- pdfplumber
+ pdfplumber>=0.11.0,<1.0.0
- google-generativeai
+ google-generativeai>=0.8.0,<1.0.0
  (이하 8개 항목 동일 패턴)
```

### A.2 config.py `_detect_poppler_path()`
```diff
  if platform.system() == "Windows":
      candidates = [
-         r"C:\poppler\poppler-24.08.0\Library\bin",
+         *sorted(glob.glob(r"C:\poppler\poppler-*\Library\bin"), reverse=True),
          r"C:\Program Files\poppler\Library\bin",
          r"C:\poppler\bin",
      ]
+ elif platform.system() == "Darwin":
+     candidates = ["/opt/homebrew/bin", "/usr/local/bin", "/opt/local/bin"]
+ else:  # Linux
+     candidates = ["/usr/bin", "/usr/local/bin"]
```

### A.3 main.py 파일 쓰기
```diff
- with open(md_path, "w", encoding="utf-8-sig") as f:
-     f.write(md)
+ _safe_write_text(md_path, md)
```

---

**기술서 작성자:** Claude Opus 4
**작성일:** 2026-04-17
**다음 단계:** 본 기술서 승인 후 Phase 6 구현 착수
**관련 문서:** `ps-docparser_코드리뷰_보고서.md` §10 Phase 6
