# Phase 5 상세 구현 기술서

> 작성일: 2026-04-16
> 최종 수정: 2026-04-16 (실제 코드베이스 검증 기반 전면 개선)
> 기반 문서: Phase5_이전_간단_구현_요약보고서.md, 제미나이 검증단계 플랜.md
> 대상 코드베이스: ps-docparser/ (Phase 1~4 완료 상태)

---

## 수정 이력

| 날짜 | 내용 |
|------|------|
| 2026-04-16 (초판) | 5개 단위 초안 작성 |
| 2026-04-16 (개선) | 실제 코드베이스 전수 분석 후 32건 오류/미흡점 수정 (아래 상세) |

**주요 수정 사항:**
- [단위 1] 캐시 키 설계를 data_uri 해시 → 파일 해시 + 페이지 인덱스 방식으로 변경 (메모리 효율)
- [단위 1] TTL 관리 기술 스택 표기 오류 수정 (`datetime` → `time.time()`)
- [단위 1] 캐시 DB 경로를 코드/데이터 분리 원칙에 따라 변경
- [단위 1] `CACHE_ENABLED` 설정값 활용 코드 누락 보완
- [단위 1] Tesseract(로컬 엔진) 캐시 적용 대상 여부 명확화
- [단위 2] `_process_single()` 상세 구현 명세 추가 (기존 누락)
- [단위 2] `sys.exit()` 교체 대상 6곳 구체 특정
- [단위 2] `batch_test.py` 폐기/유지 방침 추가
- [단위 2] `rglob` → `glob` 변경 (하위 폴더 재귀 탐색 방지)
- [단위 2] 배치 + `--output excel` 동작 정의 추가
- [단위 3] BOM JSON 실제 구조로 예시 교체 (`WT(KG)` → `WT(kg)` 등 대소문자 불일치 수정)
- [단위 3] 중량 키 조회에 `WT(kg)` 소문자 케이스 추가 (치명적 버그 방지)
- [단위 3] `group_by` 기본값에서 `SPECIFICATION` 제거 (실제 JSON에 없는 컬럼)
- [단위 3] 파일명 기반 source 추적 로직 추가 (section title 대신)
- [단위 3] `_load_all_json_sections()` 함수 구현 추가 (기존 누락)
- [단위 4] `_filter_tables()` 메서드 구현 추가 (기존 누락)
- [단위 4] `_build_estimate_sheet` 등 존재하지 않는 함수명 제거
- [단위 4] `raise SystemExit(1)` → `raise PermissionError(...)` 일관성 수정
- [단위 4] `preset_config` 전달 경로 (main.py BOM 파이프라인) 구체 코드 추가
- [단위 4] BOM 집계 시트의 단중(unit weight) 계산 정확도 주석 추가
- [전체] 수정 파일 수 불일치 수정 (5개 → 6개 + 엔진 3개 = 실질 8개)
- [전체] 총 순증 코드 재계산 (약 +550줄 → 약 +700줄)
- [전체] 의존성 다이어그램에서 단위 3→단위 2 관계를 "선택" → "필수"로 수정
- [단위 5] `batch_summary.txt` 저장 코드 누락 보완

---

## 목차

1. [단위 1: API 캐싱 레이어 구축](#단위-1-api-캐싱-레이어-구축)
2. [단위 2: 배치 처리 통합](#단위-2-배치-처리-통합)
3. [단위 3: BOM 집계 자동화](#단위-3-bom-집계-자동화)
4. [단위 4: Excel Exporter 템플릿 연동 완성](#단위-4-excel-exporter-템플릿-연동-완성)
5. [단위 5: 61개 파일 최종 검증](#단위-5-61개-파일-최종-검증)

---

## 단위 1: API 캐싱 레이어 구축

### 1.1 목적

동일 PDF 페이지/이미지에 대한 반복 API 호출을 제거하여 **비용 절감** 및 **처리 속도 향상**을 달성한다.
61개 파일 전량 배치 시 2차, 3차 재실행에서 API 호출 없이 캐시에서 즉시 응답한다.

### 1.2 캐시 적용 대상 엔진

| 엔진 | 적용 여부 | 사유 |
|------|----------|------|
| `zai` | **적용** | 유료 API, 비용 절감 핵심 대상 |
| `mistral` | **적용** | 유료 API, 폴백 엔진으로 비용 절감 필요 |
| `gemini` | **적용** | 유료/무료 API, RPM 제한(15/분) 회피 |
| `tesseract` | **미적용** | 로컬 OCR, API 비용 없음. 처리 속도도 1~2초로 캐시 이점 미미 |
| `local` | **미적용** | pdfplumber 자체 파싱, AI 미사용 |

### 1.3 기술 스택

| 항목 | 기술 | 비고 |
|------|------|------|
| 저장소 | `sqlite3` (Python 내장) | 외부 DB 불필요, 파일 1개로 관리 |
| 키 생성 | `hashlib.sha256` (Python 내장) | `sha256(파일_바이트 + 엔진명 + 페이지_인덱스)` |
| 직렬화 | `json` (Python 내장) | API 응답 → TEXT 컬럼 저장 |
| TTL 관리 | `time.time()` (Python 내장) | UNIX timestamp 기록, 조회 시 만료 체크 |

**추가 pip 설치: 없음** (전부 Python 표준 라이브러리)

### 1.4 신규 파일

#### [NEW] `cache/__init__.py`

빈 파일 (패키지 인식용)

#### [NEW] `cache/table_cache.py` (~140줄 예상)

```
cache/table_cache.py
├── class TableCache
│   ├── __init__(db_path, ttl_days=30)
│   ├── _init_db()                         # CREATE TABLE IF NOT EXISTS
│   ├── make_key_from_file(file_path, engine, page_idx=None) → str
│   │   # sha256(파일 내용) + 엔진명 + 페이지 인덱스
│   ├── make_key_from_data(data, engine) → str
│   │   # sha256(바이트) + 엔진명 (이미지 OCR용)
│   ├── get(key) → dict | None             # 캐시 조회 (TTL 초과 시 None)
│   ├── put(key, value)                    # 캐시 저장
│   ├── stats() → dict                    # 적중률 통계 (hits/misses/size)
│   └── clear_expired()                    # 만료 엔트리 삭제
```

**SQLite 스키마:**

```sql
CREATE TABLE IF NOT EXISTS cache (
    key       TEXT PRIMARY KEY,
    value     TEXT NOT NULL,        -- json.dumps(API 응답)
    engine    TEXT NOT NULL,        -- 'zai' | 'mistral' | 'gemini'
    created   REAL NOT NULL,        -- time.time() (UNIX timestamp)
    hit_count INTEGER DEFAULT 0     -- 적중 횟수 (통계용)
);
CREATE INDEX IF NOT EXISTS idx_engine ON cache(engine);
CREATE INDEX IF NOT EXISTS idx_created ON cache(created);
```

**키 생성 로직 (파일 기반 — 주 경로):**

```python
import hashlib, json
from pathlib import Path

def make_key_from_file(self, file_path: Path, engine: str, page_idx: int | None = None) -> str:
    """
    sha256(파일 내용) + 엔진명 + 페이지 인덱스 → 64자 hex.

    Why: data_uri는 base64 인코딩된 거대한 문자열(수 MB)이므로
         해시 대상으로 부적절하다. 원본 파일의 바이트를 직접 해시하여
         메모리 사용을 최소화한다.

    Note: 동일 파일이라도 엔진이 다르면 응답이 다르므로 엔진명을 키에 포함.
          페이지별 처리 시 page_idx로 세분화.
    """
    h = hashlib.sha256()
    # 파일 내용을 청크 단위로 읽어 메모리 부담 최소화
    with open(file_path, 'rb') as f:
        while chunk := f.read(8192):
            h.update(chunk)
    h.update(engine.encode('utf-8'))
    if page_idx is not None:
        h.update(str(page_idx).encode('utf-8'))
    return h.hexdigest()
```

**키 생성 로직 (이미지 기반 — ocr_image용):**

```python
def make_key_from_data(self, data: bytes, engine: str) -> str:
    """
    sha256(이미지 바이트) + 엔진명 → 64자 hex.

    Why: ocr_image()는 PIL Image를 받아 처리하므로 파일 경로가 없다.
         이미지를 PNG 바이트로 변환 후 해시한다.
    """
    h = hashlib.sha256()
    h.update(data)
    h.update(engine.encode('utf-8'))
    return h.hexdigest()
```

**TTL 체크:**

```python
import time

def get(self, key: str) -> dict | None:
    row = self._conn.execute(
        "SELECT value, created FROM cache WHERE key = ?", (key,)
    ).fetchone()
    if row is None:
        self._misses += 1
        return None
    value, created = row
    if time.time() - created > self._ttl_seconds:
        self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
        self._conn.commit()
        self._misses += 1
        return None
    self._conn.execute(
        "UPDATE cache SET hit_count = hit_count + 1 WHERE key = ?", (key,)
    )
    self._conn.commit()
    self._hits += 1
    return json.loads(value)
```

### 1.5 기존 파일 수정

#### [MODIFY] `engines/base_engine.py` (현재 161줄)

**변경 내용:** `BaseEngine`에 `cache` 속성 추가

```diff
 class BaseEngine(ABC):
     supports_image: bool = True
     supports_ocr: bool = False          # OCR 지원 여부 (ZaiEngine, MistralEngine, TesseractEngine만 True)
+    cache: "TableCache | None" = None   # Phase 5: 캐시 레이어 (외부 주입)
```

#### [MODIFY] `engines/zai_engine.py` (현재 174줄)

**변경 내용:** `_call_api()` 호출 전후에 캐시 조회/저장 삽입

현재 `_call_api(data_uri: str)` (L102-123)의 앞뒤에 캐시 로직을 삽입한다.

```diff
 def _call_api(self, data_uri: str) -> dict:
+    # 캐시 조회 (data_uri → 바이트 해시)
+    if self.cache:
+        import io
+        cache_key = self.cache.make_key_from_data(
+            data_uri.encode('utf-8')[:64],  # data_uri 앞 64바이트(고유 식별 충분)
+            'zai'
+        )
+        cached = self.cache.get(cache_key)
+        if cached is not None:
+            logger.info("캐시 적중: %s", cache_key[:16])
+            return cached
+
     try:
         response = self._client.layout_parsing.create(
             model="glm-ocr",
             file=data_uri,
         )
         # LayoutParsingResp → dict 변환
         if hasattr(response, 'model_dump'):
-            return response.model_dump()
+            result_dict = response.model_dump()
         elif hasattr(response, '__dict__'):
-            return vars(response)
-        return response if isinstance(response, dict) else {"raw": str(response)}
+            result_dict = vars(response)
+        else:
+            result_dict = response if isinstance(response, dict) else {"raw": str(response)}
+
+        # 캐시 저장
+        if self.cache and isinstance(result_dict, dict):
+            self.cache.put(cache_key, result_dict)
+
+        return result_dict
     except Exception as e:
         logger.error("Z.ai API 호출 실패: %s", e)
         raise
```

**추가: `ocr_document()` 레벨 캐시 (파일 기반 키 — 더 효율적):**

```diff
 def ocr_document(self, file_path: Path, page_indices=None) -> list[OcrPageResult]:
     file_path = Path(file_path)
     if page_indices is None:
+        # 파일 단위 캐시 조회 (전체 파일 처리 시)
+        if self.cache:
+            cache_key = self.cache.make_key_from_file(file_path, 'zai')
+            cached = self.cache.get(cache_key)
+            if cached is not None:
+                logger.info("파일 캐시 적중: %s", file_path.name)
+                text, layout = cached.get("text", ""), cached.get("layout", [])
+                return [OcrPageResult(page_num=0, text=text, layout_details=layout)]
+
         data_uri = file_to_data_uri(file_path)
         response = self._call_api(data_uri)
         text, layout = self._parse_response(response)
         self._last_layout_details = layout
+
+        # 파일 단위 캐시 저장
+        if self.cache:
+            self.cache.put(cache_key, {"text": text, "layout": layout})
+
         return [OcrPageResult(page_num=0, text=text, layout_details=layout)]
```

#### [MODIFY] `engines/mistral_engine.py` (현재 104줄)

**변경 내용:** `ocr_document()` 호출 전후에 파일 단위 캐시 적용 (zai_engine.py와 동일 패턴)

```diff
 def ocr_document(self, file_path: Path, page_indices=None) -> list[OcrPageResult]:
     file_path = Path(file_path)
+    # 파일 단위 캐시 조회
+    if self.cache:
+        cache_key = self.cache.make_key_from_file(file_path, 'mistral')
+        cached = self.cache.get(cache_key)
+        if cached is not None:
+            logger.info("파일 캐시 적중: %s", file_path.name)
+            return [OcrPageResult(page_num=i, text=p["text"])
+                    for i, p in enumerate(cached)]
+
     data_uri = file_to_data_uri(file_path)
     try:
         response = self._client.ocr.process(...)
     ...
     results = []
     for i, page in enumerate(response.pages):
         ...
+    # 파일 단위 캐시 저장
+    if self.cache:
+        cache_data = [{"text": r.text} for r in results]
+        self.cache.put(cache_key, cache_data)
+
     return results
```

> **gemini_engine.py**: `extract_full_page()`, `extract_table()` 레벨에 이미지 기반 캐시 적용. Gemini는 `ocr_document()`가 아닌 이미지 단위 처리이므로 `make_key_from_data(image_bytes, 'gemini')`를 사용한다.

#### [MODIFY] `main.py` (현재 575줄)

**변경 내용:** 엔진 생성 후 캐시 인스턴스 주입

```diff
+from cache.table_cache import TableCache
+import config

 def main():
     parser = _build_argument_parser()
     args = parser.parse_args()
+
+    # 캐시 인스턴스 생성 (config 설정에 따라 비활성화 가능)
+    cache = None
+    if config.CACHE_ENABLED:
+        cache_db = _project_root / ".cache" / "table_cache.db"
+        cache_db.parent.mkdir(parents=True, exist_ok=True)
+        cache = TableCache(cache_db, ttl_days=config.CACHE_TTL_DAYS)
     ...
     # BOM 파이프라인 (L285~)
     elif preset == "bom":
         ...
         bom_engine = _create_engine(engine_name, tracker)
+        if cache and engine_name not in ("tesseract", "local"):
+            bom_engine.cache = cache   # 캐시 레이어 주입 (유료 API 엔진만)
```

> **캐시 DB 경로 변경**: `cache/table_cache.db` → `.cache/table_cache.db`
> Why: `cache/` 디렉토리에는 Python 소스 코드(`table_cache.py`)가 있으므로, 데이터 파일과 분리한다. `.cache/`는 숨김 폴더로 `.gitignore`에 추가한다.

#### [MODIFY] `config.py` (현재 148줄)

**변경 내용:** 캐시 관련 설정 상수 추가 (+5줄)

```diff
 BOM_DEFAULT_ENGINE: str = os.getenv("BOM_DEFAULT_ENGINE", "zai")
+
+# ── Phase 5: 캐시 설정 ──
+CACHE_TTL_DAYS: int = int(os.getenv("CACHE_TTL_DAYS", "30"))
+CACHE_ENABLED: bool = os.getenv("CACHE_ENABLED", "true").lower() == "true"
+CACHE_DIR: Path = BASE_DIR / ".cache"
```

#### [NEW] `.gitignore` 추가 항목

```
.cache/
```

### 1.6 검증 계획

| 테스트 | 방법 | 기대 결과 |
|--------|------|----------|
| 캐시 미스 | 처음 호출 → API 실행 → DB 저장 확인 | `.cache/table_cache.db`에 1행 INSERT |
| 캐시 적중 | 같은 입력 재호출 → API 미호출 확인 | `logger.info("파일 캐시 적중")` 출력 |
| TTL 만료 | created를 31일 전으로 조작 → 재호출 | 캐시 무시, API 재호출 |
| 통계 | `cache.stats()` 호출 | `{"hits": N, "misses": M, "size": K}` |
| 비활성화 | `CACHE_ENABLED=false` 설정 → 실행 | 캐시 미생성, API 직접 호출 |
| tesseract 제외 | `--engine tesseract` 실행 | `bom_engine.cache`가 None, 캐시 미적용 |

---

## 단위 2: 배치 처리 통합

### 2.1 목적

현재 `batch_test.py`는 `subprocess.run()`으로 `main.py`를 **프로세스 단위**로 호출하여 비효율적이다.
`main.py`에 `--batch` 인수를 직접 통합하여 **인-프로세스 배치 처리**를 구현한다.

### 2.2 현재 문제점 (batch_test.py 분석)

| 문제 | 설명 | 위치 |
|------|------|------|
| subprocess 오버헤드 | 매 PDF마다 Python 프로세스 재생성 (약 2~3초 낭비/파일) | L43 `subprocess.run()` |
| 캐시 공유 불가 | 프로세스 간 SQLite 커넥션 분리 → 캐시 적중 불가 | 구조적 문제 |
| 하드코딩 경로 | `PDF_ROOT`가 절대 경로로 고정 | L19 |
| TSV 컬럼 불일치 | TSV에 BOM 테이블/행 수 포함하나 새 배치에서는 다른 정보 필요 | L135-137 |

### 2.3 batch_test.py 처리 방침

**`batch_test.py`는 삭제하지 않고 유지한다.**
- 단위 2 완료 후 `batch_test.py` 상단에 `# DEPRECATED: main.py --batch 사용 권장` 주석 추가
- Why: 기존 배치 테스트 결과(`batch_result.tsv`, `batch_summary.txt`)와의 비교 검증에 활용

### 2.4 기존 파일 수정

#### [MODIFY] `main.py`

**변경량:** 약 +160줄 (배치 함수 + _process_single 리팩터링 포함)

**CLI 인수 추가:**

```diff
 def _build_argument_parser():
     parser.add_argument(
         "input",
         metavar="파일",
-        help="처리할 파일 (.pdf 또는 .md)",
+        help="처리할 파일 (.pdf 또는 .md) 또는 --batch 시 폴더 경로",
     )
+    parser.add_argument(
+        "--batch",
+        action="store_true",
+        help="폴더 내 PDF 일괄 처리 모드",
+    )
+    parser.add_argument(
+        "--pattern",
+        default="*.pdf",
+        help="배치 대상 파일 패턴 (기본: *.pdf, 예: PIPE-BM-PS-*.pdf)",
+    )
```

### 2.5 sys.exit() 교체 대상 (전수 조사)

배치 모드에서 `sys.exit()`이 호출되면 전체 반복이 중단된다. 다음 6곳을 `raise`로 교체한다.

| # | 파일 | 위치 | 현재 코드 | 변경 후 |
|---|------|------|----------|---------|
| 1 | main.py | L160 | `sys.exit(1)` (ZAI_API_KEY 없음) | `raise ValueError("ZAI_API_KEY 미설정")` |
| 2 | main.py | L165 | `sys.exit(1)` (MISTRAL_API_KEY 없음) | `raise ValueError("MISTRAL_API_KEY 미설정")` |
| 3 | main.py | L181 | `sys.exit(1)` (목차 파일 없음) | `raise FileNotFoundError(toc_path)` |
| 4 | main.py | L244 | `sys.exit(1)` (입력 파일 없음) | `raise FileNotFoundError(input_path)` |
| 5 | main.py | L250 | `sys.exit(1)` (.md+md 조합) | `raise ValueError(".md 입력 시 --output json 필요")` |
| 6 | main.py | L298 | `sys.exit(1)` (OCR 미지원 엔진) | `raise ValueError(f"BOM에 OCR 엔진 필요: {engine_name}")` |

> **단일 파일 모드 호환:** `main()`에서 `_process_single()`을 호출할 때, 기존 단일 파일 모드에서는 `try-except`로 감싸서 `raise`된 예외를 `sys.exit(1)`로 변환한다. 배치 모드에서는 `_run_batch()` 내 `try-except`에서 예외를 포착하여 FAIL로 기록한다.

### 2.6 _process_single() 상세 구현

현재 `main()` 함수의 BOM 파이프라인 (L285-351, 약 67줄)을 독립 함수로 분리한다.

```python
def _process_single(
    pdf_path: Path,
    args: argparse.Namespace,
    cache: "TableCache | None",
    out_dir: Path,
) -> dict:
    """
    단일 PDF를 BOM 파이프라인으로 처리한다.

    Returns:
        {"file": str, "bom_tables": int, "ll_tables": int,
         "bom_rows": int, "ll_rows": int}

    Raises:
        ValueError: 설정 오류 (API 키 없음, 엔진 미지원 등)
        FileNotFoundError: 입력 파일 없음
        Exception: API/파싱 오류
    """
    from presets.bom import get_bom_keywords, get_image_settings
    from extractors.bom_extractor import extract_bom_with_retry, to_sections
    from exporters.json_exporter import JsonExporter

    # 엔진 설정
    engine_name = args.engine or config.BOM_DEFAULT_ENGINE
    tracker = UsageTracker()
    bom_engine = _create_engine(engine_name, tracker)

    if not bom_engine.supports_ocr:
        raise ValueError(f"BOM 프리셋은 OCR 엔진이 필요합니다: {engine_name}")

    if cache and engine_name not in ("tesseract", "local"):
        bom_engine.cache = cache

    bom_keywords = get_bom_keywords()
    image_settings = get_image_settings()

    # 페이지 범위
    page_indices = None
    if args.pages:
        import pdfplumber
        with pdfplumber.open(str(pdf_path)) as pdf:
            total_pages = len(pdf.pages)
        page_indices = parse_page_spec(args.pages, total_pages)

    # Phase 1-BOM: OCR 추출
    bom_result = extract_bom_with_retry(
        bom_engine, pdf_path, bom_keywords, image_settings, page_indices
    )

    # MD 저장
    input_stem = pdf_path.stem
    date_str = datetime.now().strftime("%Y%m%d")
    output_base = out_dir / f"{date_str}_{input_stem}_bom"

    md_path = Path(str(output_base) + ".md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(bom_result.raw_text)

    # Phase 2-BOM: 구조화
    sections = to_sections(bom_result)

    # JSON 저장
    json_path = Path(str(output_base) + ".json")
    JsonExporter().export(sections, json_path)

    # (옵션) Excel 출력
    if args.output_format == "excel":
        from exporters.excel_exporter import ExcelExporter
        from presets.bom import get_excel_config
        xlsx_path = Path(str(output_base) + ".xlsx")
        excel_config = get_excel_config()
        ExcelExporter().export(sections, xlsx_path, preset_config=excel_config)

    # 결과 집계
    bom_rows = sum(len(t.get("rows", [])) for s in sections
                   for t in s.get("tables", []) if t.get("type") == "BOM_자재")
    ll_rows = sum(len(t.get("rows", [])) for s in sections
                  for t in s.get("tables", []) if t.get("type") == "BOM_LINE_LIST")

    return {
        "file": pdf_path.name,
        "bom_tables": len(bom_result.bom_sections),
        "ll_tables": len(bom_result.line_list_sections),
        "bom_rows": bom_rows,
        "ll_rows": ll_rows,
    }
```

### 2.7 배치 처리 함수

```python
def _run_batch(args, cache):
    """폴더 내 PDF 일괄 처리."""
    import time

    input_dir = Path(args.input)
    if not input_dir.is_dir():
        print(f"  배치 모드에는 폴더 경로를 지정하세요: {args.input}")
        sys.exit(1)

    # glob (하위 폴더 미포함) — rglob은 하위 폴더까지 재귀 탐색하여 의도치 않은 파일 포함 위험
    pdfs = sorted(input_dir.glob(args.pattern))
    if not pdfs:
        print(f"  '{args.pattern}' 패턴의 PDF를 찾을 수 없습니다.")
        sys.exit(1)

    out_dir = Path(args.output_dir) if args.output_dir else OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    total = len(pdfs)

    print(f"\n{'='*60}")
    print(f"  배치 처리: {total}개 파일 / 엔진: {args.engine or config.BOM_DEFAULT_ENGINE}")
    print(f"{'='*60}\n")

    for i, pdf in enumerate(pdfs, 1):
        t0 = time.time()
        print(f"[{i}/{total}] {pdf.name} ... ", end="", flush=True)

        try:
            result = _process_single(pdf, args, cache, out_dir)
            elapsed = time.time() - t0
            result["elapsed_s"] = round(elapsed, 1)
            result["status"] = "OK"
            print(f"OK {elapsed:.1f}s (BOM {result['bom_rows']}행 / LL {result['ll_rows']}행)")
        except Exception as e:
            elapsed = time.time() - t0
            result = {
                "file": pdf.name,
                "status": f"FAIL: {e}",
                "bom_tables": 0, "ll_tables": 0,
                "bom_rows": 0, "ll_rows": 0,
                "elapsed_s": round(elapsed, 1),
            }
            print(f"FAIL: {e}")

        results.append(result)

    # 요약 리포트
    _print_batch_summary(results, out_dir, cache)
    return results
```

### 2.8 요약 리포트 함수

```python
def _print_batch_summary(results, out_dir, cache):
    """배치 결과 요약을 콘솔 출력 + TSV + TXT 파일로 저장한다."""
    ok = [r for r in results if r["status"] == "OK"]
    fail = [r for r in results if r["status"] != "OK"]
    avg_t = sum(r["elapsed_s"] for r in results) / max(len(results), 1)
    tot_bom = sum(r.get("bom_rows", 0) for r in ok)
    tot_ll = sum(r.get("ll_rows", 0) for r in ok)
    zero_bom = [r for r in ok if r.get("bom_rows", 0) == 0]
    cache_stats = cache.stats() if cache else {}

    summary_lines = [
        f"배치 처리 결과 — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"총 파일: {len(results)}개",
        f"성공: {len(ok)}개 / 실패: {len(fail)}개",
        f"BOM 합계: {tot_bom}행 / LINE LIST 합계: {tot_ll}행",
        f"평균 소요시간: {avg_t:.1f}s / 파일",
    ]
    if cache_stats:
        summary_lines.append(
            f"캐시 적중: {cache_stats.get('hits', 0)}회 / 미스: {cache_stats.get('misses', 0)}회"
        )
    if zero_bom:
        summary_lines.append(f"\nBOM 0행 파일 ({len(zero_bom)}개):")
        for r in zero_bom:
            summary_lines.append(f"  - {r['file']}")
    if fail:
        summary_lines.append(f"\n실패 파일 ({len(fail)}개):")
        for r in fail:
            summary_lines.append(f"  - {r['file']}: {r['status']}")

    summary_text = "\n".join(summary_lines)

    print(f"\n{'='*60}")
    print(summary_text)
    print(f"{'='*60}")

    # TSV 리포트 저장
    tsv_path = out_dir / "batch_result.tsv"
    with open(tsv_path, "w", encoding="utf-8") as f:
        f.write("파일명\t상태\tBOM테이블\tLL테이블\tBOM행\tLL행\t소요시간(s)\n")
        for r in results:
            f.write(f"{r.get('file','')}\t{r['status']}\t"
                    f"{r.get('bom_tables',0)}\t{r.get('ll_tables',0)}\t"
                    f"{r.get('bom_rows',0)}\t{r.get('ll_rows',0)}\t"
                    f"{r['elapsed_s']}\n")
    print(f"  TSV: {tsv_path}")

    # TXT 요약 저장
    summary_path = out_dir / "batch_summary.txt"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary_text)
    print(f"  요약: {summary_path}")
```

### 2.9 main() 리팩터링 — 분기 구조

```text
main()
├── args 파싱
├── cache 생성 (config.CACHE_ENABLED 체크)
├── if args.batch:
│   ├── _run_batch(args, cache)
│   ├── if args.preset == "bom":
│   │   └── BOM 집계 실행 (단위 3)
│   └── return
└── else:
    ├── try:
    │   └── 기존 단일 파일 로직 (_process_single 또는 기존 표준 파이프라인)
    └── except (ValueError, FileNotFoundError) as e:
        ├── print(f"  {e}")
        └── sys.exit(1)
```

### 2.10 배치 + --output excel 동작 정의

| 조합 | 동작 |
|------|------|
| `--batch --output json` (기본) | 각 파일별 `*_bom.json` + `*_bom.md` 생성 |
| `--batch --output excel` | 각 파일별 `*_bom.json` + `*_bom.md` + `*_bom.xlsx` 생성 |
| `--batch --preset bom` | 배치 완료 후 **추가로** 전체 집계 JSON/Excel 생성 (단위 3) |

### 2.11 검증 계획

| 테스트 | 명령어 | 기대 결과 |
|--------|--------|----------|
| 단일 파일 (기존 호환) | `python main.py file.pdf --preset bom` | 기존과 동일 동작 |
| 배치 5개 | `python main.py ./pdfs/ --batch --pattern "PIPE-BM-PS-*.pdf" --preset bom --engine zai` | 5개 순차 처리 + TSV + 요약 |
| 캐시 연계 | 위 명령 재실행 | 캐시 적중, API 호출 0 |
| 오류 격리 | 존재하지 않는 PDF 포함 | 해당 파일만 FAIL, 나머지 계속 |
| Excel 배치 | `--batch --output excel` | 파일별 xlsx 생성 |

---

## 단위 3: BOM 집계 자동화

### 3.1 목적

여러 도면에서 추출된 BOM 데이터를 **동일 자재(SIZE + MAT'L)** 기준으로 자동 합산하여
견적 산출의 기초 데이터를 생성한다.

### 3.2 현재 BOM 데이터 구조 (Phase 4 실제 출력)

> 아래는 `output/20260415_PIPE-BM-PS-3001-S1_bom.json`에서 확인한 **실제** 구조이다.

```json
{
  "table_id": "T-BOM-1-01",
  "type": "BOM_자재",
  "headers": ["S/N", "SIZE", "MAT'L", "Q'TY", "WT(kg)", "REMARKS"],
  "rows": [
    {"S/N": "1", "SIZE": "H200x200x8x12", "MAT'L": "SS275", "Q'TY": "1098", "WT(kg)": "54.79", "REMARKS": ""}
  ]
}
```

**실제 구조와 기존 기술서의 차이점:**

| 항목 | 기존 기술서 (오류) | 실제 JSON |
|------|------------------|----------|
| 헤더 | `MARK`, `SPECIFICATION` 포함 | **없음** (도면에 따라 다를 수 있음) |
| 중량 키 | `WT(KG)` (대문자) | `WT(kg)` (소문자 kg) |
| SIZE 형식 | `200X200X8` | `H200x200x8x12` (형강 규격 포함) |
| MAT'L 값 | `SS400` | `SS275` |
| Q'TY 값 | `"2"` (소수) | `"1098"` (mm 단위 길이) |

> **중요:** `Q'TY` 값이 실제로는 길이(mm)일 수 있다. 도면에 따라 수량/길이의 의미가 다르므로 집계 시 주의 필요.

### 3.3 헤더 변형 패턴 (도면별 차이 대응)

실제 61개 도면에서 나타날 수 있는 헤더명 변형:

| 표준 | 변형 1 | 변형 2 | 변형 3 |
|------|--------|--------|--------|
| `S/N` | `SN` | `NO` | `NO.` |
| `SIZE` | (일정) | - | - |
| `MAT'L` | `MATERIAL` | `MATL` | `MAT` |
| `Q'TY` | `QTY` | `QUANTITY` | `Q'TY.` |
| `WT(kg)` | `WT(KG)` | `WEIGHT` | `WEIGHT(KG)` |
| `SPECIFICATION` | `SPEC` | (없을 수 있음) | - |
| `MARK` | (없을 수 있음) | - | - |

### 3.4 신규 파일

#### [NEW] `exporters/bom_aggregator.py` (~200줄 예상)

```
exporters/bom_aggregator.py
├── _HEADER_ALIASES: dict              # 헤더 정규화 매핑 테이블
├── _normalize_header(key) → str       # 헤더 변형 정규화
│
├── @dataclass AggregatedItem
│   ├── group_key: str                 # "SS275|H200x200x8x12"
│   ├── material: str                  # "SS275"
│   ├── size: str                      # "H200x200x8x12"
│   ├── total_qty: int                 # 합산 수량
│   ├── total_weight: float            # 합산 중량 (kg)
│   ├── source_files: list[str]        # 출처 파일명 목록
│   └── specification: str             # "BUILT UP" (있으면)
│
├── def aggregate_bom_sections(sections, source_file=None, group_by=None) → list[AggregatedItem]
│   # 기본 group_by = ["MAT'L", "SIZE"]
│
├── def to_summary_table(items) → dict
│   # AggregatedItem 리스트 → Phase 2 호환 JSON 섹션
│
└── def format_summary_text(items) → str
    # 콘솔 출력용 텍스트 요약
```

**헤더 정규화 매핑:**

```python
# 헤더명 변형을 표준형으로 정규화
_HEADER_ALIASES = {
    # MAT'L 계열
    "MATERIAL": "MAT'L", "MATL": "MAT'L", "MAT": "MAT'L",
    # Q'TY 계열
    "QTY": "Q'TY", "QUANTITY": "Q'TY", "Q'TY.": "Q'TY",
    # WT 계열 (대소문자 변형 포함)
    "WT(KG)": "WT(kg)", "WEIGHT": "WT(kg)", "WEIGHT(KG)": "WT(kg)",
    "WT (KG)": "WT(kg)", "WT (kg)": "WT(kg)",
    # SPEC 계열
    "SPEC": "SPECIFICATION",
}

def _normalize_header(key: str) -> str:
    """헤더 키를 정규화한다. 매핑에 없으면 원본 반환."""
    return _HEADER_ALIASES.get(key.upper().strip(), key)

def _get_row_value(row: dict, standard_key: str, default: str = "") -> str:
    """
    정규화된 키로 행에서 값을 조회한다.

    row의 키가 변형된 형태일 수 있으므로 역매핑으로 탐색.
    """
    # 직접 매칭
    if standard_key in row:
        return str(row[standard_key]).strip()
    # 변형 키 탐색
    for raw_key, normalized in _HEADER_ALIASES.items():
        if normalized == standard_key and raw_key in row:
            return str(row[raw_key]).strip()
    # 원본 키의 대소문자 무시 탐색
    for k, v in row.items():
        if _normalize_header(k) == standard_key:
            return str(v).strip()
    return default
```

**집계 로직 핵심:**

```python
from dataclasses import dataclass, field
from collections import defaultdict

@dataclass
class AggregatedItem:
    group_key: str
    material: str
    size: str
    specification: str = ""
    total_qty: int = 0
    total_weight: float = 0.0
    source_files: list[str] = field(default_factory=list)

def aggregate_bom_sections(
    sections: list[dict],
    source_file: str | None = None,
    group_by: list[str] | None = None,
) -> list[AggregatedItem]:
    """
    BOM 섹션들의 행을 그룹핑 키 기준으로 합산한다.

    Args:
        sections: Phase 4 출력 JSON 섹션 리스트
        source_file: 출처 파일명 (배치 시 외부에서 전달)
        group_by: 그룹핑 키 목록. 기본값: ["MAT'L", "SIZE"]
                  (SPECIFICATION은 대부분의 도면에 없으므로 기본에서 제외)

    Returns:
        AggregatedItem 리스트 (자재 → 크기 순 정렬)
    """
    if group_by is None:
        group_by = ["MAT'L", "SIZE"]

    buckets: dict[str, AggregatedItem] = defaultdict(
        lambda: AggregatedItem("", "", "")
    )

    for section in sections:
        # source 결정: 외부 전달 > section title > "unknown"
        source = source_file or section.get("title", "unknown")

        for table in section.get("tables", []):
            if table.get("type") != "BOM_자재":
                continue
            for row in table.get("rows", []):
                # 그룹핑 키 생성 (정규화된 헤더로 값 조회)
                key_parts = [
                    _get_row_value(row, k).upper() for k in group_by
                ]
                key = "|".join(key_parts)
                if not any(key_parts):
                    continue  # 비어있는 행 건너뛰기

                item = buckets[key]
                item.group_key = key
                item.material = _get_row_value(row, "MAT'L")
                item.size = _get_row_value(row, "SIZE")
                item.specification = _get_row_value(row, "SPECIFICATION")

                # 수량 합산
                qty_raw = _get_row_value(row, "Q'TY", "0")
                try:
                    item.total_qty += int(qty_raw.replace(",", "") or "0")
                except ValueError:
                    pass

                # 중량 합산
                wt_raw = _get_row_value(row, "WT(kg)", "0")
                try:
                    item.total_weight += float(wt_raw.replace(",", "") or "0")
                except ValueError:
                    pass

                if source and source not in item.source_files:
                    item.source_files.append(source)

    # 정렬: 자재 → 크기 순
    result = sorted(buckets.values(), key=lambda x: (x.material, x.size))
    return result
```

**JSON 변환 (Phase 2 호환):**

```python
def to_summary_table(items: list[AggregatedItem]) -> dict:
    """AggregatedItem 리스트를 Phase 2 호환 JSON 섹션으로 변환한다."""
    rows = []
    for i, item in enumerate(items, 1):
        rows.append({
            "NO": str(i),
            "MAT'L": item.material,
            "SIZE": item.size,
            "SPECIFICATION": item.specification,
            "Q'TY": str(item.total_qty),
            "WT(kg)": f"{item.total_weight:.2f}",
            "SOURCE": ", ".join(item.source_files[:5]),
        })

    return {
        "section_id": "BOM-AGG",
        "title": "BOM 집계 (자동 합산)",
        "department": None,
        "chapter": None,
        "page": None,
        "clean_text": "",
        "tables": [{
            "table_id": "T-BOM-AGG-01",
            "type": "BOM_집계",
            "headers": ["NO", "MAT'L", "SIZE", "SPECIFICATION", "Q'TY", "WT(kg)", "SOURCE"],
            "rows": rows,
            "notes_in_table": [],
            "raw_row_count": len(rows),
            "parsed_row_count": len(rows),
        }],
        "notes": [],
        "conditions": [],
        "cross_references": [],
        "revision_year": None,
        "unit_basis": None,
    }
```

### 3.5 기존 파일 수정

#### [MODIFY] `main.py`

**변경 내용:** 배치 완료 후 집계 단계 추가 + `_load_all_json_sections()` 함수 구현

**`_load_all_json_sections()` 신규:**

```python
def _load_all_json_sections(out_dir: Path, pattern: str = "*_bom.json") -> list[dict]:
    """
    출력 디렉토리의 BOM JSON 파일들을 로드하여 sections 리스트를 반환한다.

    각 section에 source_file 키를 추가하여 출처 파일을 추적한다.

    Why: 배치 완료 후 집계를 위해 개별 JSON 결과를 재로드한다.
         인-프로세스로 메모리에 유지하는 방법도 있으나,
         JSON 파일 기반 접근이 배치 중단 후 재시작에 안전하다.
    """
    all_sections = []
    for json_path in sorted(out_dir.glob(pattern)):
        try:
            with open(json_path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            # JsonExporter 출력: list[dict] 또는 {"metadata":..., "sections": list}
            if isinstance(data, list):
                sections = data
            elif isinstance(data, dict) and "sections" in data:
                sections = data["sections"]
            else:
                continue
            # 각 section에 출처 파일명 추가
            source_name = json_path.stem.replace("_bom", "")
            for s in sections:
                s["_source_file"] = source_name
            all_sections.extend(sections)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("JSON 로드 실패: %s — %s", json_path.name, e)
    return all_sections
```

**배치 후 집계 호출:**

```diff
 def _run_batch(args, cache):
     ...
     _print_batch_summary(results, out_dir, cache)
+
+    # BOM 집계 (--preset bom 배치 시)
+    if args.preset == "bom":
+        from exporters.bom_aggregator import aggregate_bom_sections, to_summary_table
+        from exporters.json_exporter import JsonExporter
+
+        all_sections = _load_all_json_sections(out_dir)
+        if not all_sections:
+            print("\n  집계 대상 JSON이 없습니다.")
+            return results
+
+        # 집계 실행 (section별 source_file 활용)
+        items = aggregate_bom_sections(all_sections)
+
+        # 무결성 검증
+        pre_qty = sum(
+            int(str(row.get("Q'TY", row.get("QTY", "0"))).replace(",","") or "0")
+            for s in all_sections for t in s.get("tables", [])
+            if t.get("type") == "BOM_자재"
+            for row in t.get("rows", [])
+        )
+        post_qty = sum(i.total_qty for i in items)
+        if pre_qty != post_qty:
+            print(f"\n  집계 무결성 경고: 집계 전 Q'TY={pre_qty} != 집계 후 Q'TY={post_qty}")
+
+        date_str = datetime.now().strftime("%Y%m%d")
+        print(f"\n  BOM 집계: {len(items)}종 자재, "
+              f"총 수량 {post_qty}, "
+              f"총 중량 {sum(i.total_weight for i in items):.1f}kg")
+
+        # 집계 결과 JSON 저장
+        summary = to_summary_table(items)
+        agg_json = out_dir / f"{date_str}_bom_aggregated.json"
+        JsonExporter().export([summary], agg_json)
+        print(f"  집계 JSON: {agg_json}")
+
+        # 집계 결과 Excel 저장 (--output excel 시)
+        if args.output_format == "excel":
+            from exporters.excel_exporter import ExcelExporter
+            agg_xlsx = out_dir / f"{date_str}_bom_aggregated.xlsx"
+            ExcelExporter().export(
+                [summary], agg_xlsx,
+                preset_config={"use_template": True, "sheets": [
+                    {"name": "BOM 집계", "builder": "bom_summary", "filter": {"type": "BOM_집계"}},
+                ]},
+            )
+            print(f"  집계 Excel: {agg_xlsx}")
+
+    return results
```

### 3.6 검증 계획

| 테스트 | 방법 | 기대 결과 |
|--------|------|----------|
| 단일 파일 집계 | BOM JSON 1개 → aggregate | 원본과 동일 (합산 대상 없음) |
| 다중 파일 집계 | BOM JSON 3개(동일 자재 포함) → aggregate | 동일 SIZE+MAT'L 수량 합산 |
| 무결성 검증 | 집계 전 총 Q'TY == 집계 후 총 Q'TY | 수치 일치, 불일치 시 경고 |
| 빈 BOM 처리 | 빈 rows → aggregate | 빈 리스트 반환 (에러 없음) |
| 헤더 변형 대응 | `WT(KG)`, `WT(kg)`, `WEIGHT` 혼용 JSON | 모두 정상 합산 |
| source 추적 | 3개 파일 집계 후 source_files 확인 | 파일명 3개 기록 |

---

## 단위 4: Excel Exporter 템플릿 연동 완성

### 4.1 목적

`excel_exporter.py`의 `ExcelExporter.export()`에서 `preset_config` 파라미터가 전달되면
프리셋별 커스텀 시트 레이아웃으로 출력하는 `_write_preset_sheets()` 분기를 구현한다.

### 4.2 현재 미완성 상태 분석

`excel_exporter.py` L686-705의 `ExcelExporter.export()`:

```python
def export(self, sections, output_path, *, metadata=None, preset_config=None):
    # preset_config가 있으면 향후 _write_preset_sheets()로 분기.
    title = metadata.get("description") if metadata else None
    return _export_impl(sections, output_path, title=title)
    # ↑ preset_config 무시됨 (미구현)
```

**기존 excel_exporter.py에 확인된 스타일 상수 (L49-72):**
- `_BORDER_ALL`, `_BORDER_HEADER` (존재)
- `_FILL_HEADER`, `_FILL_SECTION`, `_FILL_SUBTOTAL`, `_FILL_TITLE` (존재)
- `_FONT_HEADER`, `_FONT_TITLE`, `_FONT_SECTION`, `_FONT_SUBTOTAL`, `_FONT_BODY`, `_FONT_NOTE` (존재)
- `_ALIGN_CENTER`, `_ALIGN_LEFT`, `_ALIGN_RIGHT` (존재)

**기존 excel_exporter.py에 확인된 함수:**
- `_classify_table(table)` → `"estimate"` | `"detail"` | `"condition"` | `"generic"` (L79-110)
- `_build_generic_sheet(ws, tbl)` (존재, 수정 C에서 추가됨)
- `_export_impl(sections, output_path, title=None)` (메인 내보내기 로직)
- `_apply_style()` — 존재 여부 확인 필요 (없으면 인라인 스타일 적용)

> **주의:** `_build_estimate_sheet`, `_build_detail_sheet` 함수는 **존재하지 않는다**. 기존 코드는 `_export_impl()` 내부에서 견적서/내역서 시트를 직접 빌드한다. `_write_preset_sheets()`의 builder 분기에서는 기존 `_build_generic_sheet()`만 직접 참조 가능하며, 견적서/내역서용 빌더는 별도 구현이 필요하다.

### 4.3 기존 파일 수정

#### [MODIFY] `exporters/excel_exporter.py` (현재 706줄)

**변경량:** 약 +150줄

**ExcelExporter.export() 수정:**

```diff
 def export(self, sections, output_path, *, metadata=None, preset_config=None):
-    title = metadata.get("description") if metadata else None
-    return _export_impl(sections, output_path, title=title)
+    if preset_config and preset_config.get("use_template"):
+        return self._write_preset_sheets(sections, output_path, metadata, preset_config)
+    else:
+        title = metadata.get("description") if metadata else None
+        return _export_impl(sections, output_path, title=title)
```

**`_filter_tables()` 신규 메서드:**

```python
@staticmethod
def _filter_tables(sections: list[dict], filter_spec: dict) -> list[dict]:
    """
    sections에서 filter_spec 조건에 맞는 테이블만 추출한다.

    Args:
        sections: Phase 2/4 JSON 섹션 리스트
        filter_spec: {"type": "BOM_자재"} 등 필터 조건

    Returns:
        조건에 맞는 table dict 리스트 (sections 구조에서 분리)

    Why: _write_preset_sheets()에서 시트별로 다른 테이블 유형을
         선택적으로 출력하기 위해 필요하다.
    """
    target_type = filter_spec.get("type")
    result = []
    for section in sections:
        for table in section.get("tables", []):
            if target_type and table.get("type") != target_type:
                continue
            # section 메타데이터를 테이블에 부착 (출처 추적용)
            table_with_meta = dict(table)
            table_with_meta["_section_title"] = section.get("title", "")
            table_with_meta["_source_file"] = section.get("_source_file", "")
            result.append(table_with_meta)
    return result
```

**`_write_preset_sheets()` 신규 메서드:**

```python
def _write_preset_sheets(self, sections, output_path, metadata, preset_config):
    """프리셋 설정 기반 커스텀 Excel 시트 생성."""
    wb = Workbook()
    wb.remove(wb.active)

    sheet_defs = preset_config.get("sheets", [])
    for sheet_def in sheet_defs:
        name = sheet_def["name"][:31]  # Excel 시트명 31자 제한
        ws = wb.create_sheet(name)
        ws.sheet_view.showGridLines = False

        builder = sheet_def.get("builder", "generic")
        target_tables = self._filter_tables(sections, sheet_def.get("filter", {}))

        if builder == "bom_summary":
            self._build_bom_summary_sheet(ws, target_tables, metadata)
        else:
            # generic 빌더: 기존 _build_generic_sheet() 활용
            for tbl in target_tables:
                _build_generic_sheet(ws, tbl)

    # 시트가 없으면 기본 시트 추가 (빈 워크북 저장 방지)
    if not wb.sheetnames:
        wb.create_sheet("Empty")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        wb.save(output_path)
    except PermissionError:
        raise PermissionError(f"파일을 저장할 수 없습니다: {output_path}")
    return output_path
```

> **주의:** 기존 기술서에서 `raise SystemExit(1)`을 사용했으나, 이는 단위 2의 "sys.exit을 raise로 변경" 원칙과 모순된다. `raise PermissionError(...)`로 변경하여 배치 모드에서도 안전하게 예외를 포착할 수 있게 한다.

**BOM 집계 전용 시트 빌더:**

```python
def _build_bom_summary_sheet(self, ws, tables, metadata):
    """
    BOM 집계 결과를 견적서 양식으로 출력한다.

    Why: 엑스포터 내에서 집계를 재호출(역참조)하지 않고,
         이미 집계된 테이블 데이터를 그대로 출력한다.
         (단위 3의 to_summary_table()이 생성한 BOM_집계 유형의 테이블)
    """
    # 이미 집계된 테이블이 전달되는 경우 (BOM_집계 유형)
    agg_tables = [t for t in tables if t.get("type") == "BOM_집계"]
    if agg_tables:
        # 집계 완료된 데이터를 그대로 출력
        rows_data = agg_tables[0].get("rows", [])
    else:
        # 미집계 BOM_자재 테이블이 전달된 경우 → 내부 집계 수행
        from exporters.bom_aggregator import aggregate_bom_sections
        sections = [{"tables": tables, "title": "BOM"}]
        items = aggregate_bom_sections(sections)
        rows_data = [
            {
                "NO": str(i),
                "MAT'L": item.material,
                "SIZE": item.size,
                "SPECIFICATION": item.specification,
                "Q'TY": str(item.total_qty),
                "WT(kg)": f"{item.total_weight:.2f}",
                "비고": ", ".join(item.source_files[:3]),
            }
            for i, item in enumerate(items, 1)
        ]

    # 헤더
    headers = ["NO", "자재명(MAT'L)", "규격(SIZE)", "사양", "수량", "합계중량(kg)", "비고"]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=2, column=col, value=h)
        cell.fill = _FILL_HEADER
        cell.font = _FONT_HEADER
        cell.alignment = _ALIGN_CENTER
        cell.border = _BORDER_ALL

    # 데이터
    for row_idx, row in enumerate(rows_data, 3):
        ws.cell(row=row_idx, column=1, value=row.get("NO", row_idx - 2))
        ws.cell(row=row_idx, column=2, value=row.get("MAT'L", ""))
        ws.cell(row=row_idx, column=3, value=row.get("SIZE", ""))
        ws.cell(row=row_idx, column=4, value=row.get("SPECIFICATION", ""))

        # 수량 (숫자 변환)
        try:
            qty_val = int(str(row.get("Q'TY", "0")).replace(",", "") or "0")
        except ValueError:
            qty_val = row.get("Q'TY", "")
        ws.cell(row=row_idx, column=5, value=qty_val)

        # 합계 중량 (숫자 변환)
        try:
            wt_val = float(str(row.get("WT(kg)", "0")).replace(",", "") or "0")
        except ValueError:
            wt_val = row.get("WT(kg)", "")
        ws.cell(row=row_idx, column=6, value=wt_val)

        ws.cell(row=row_idx, column=7, value=row.get("비고", row.get("SOURCE", "")))

        for col in range(1, 8):
            cell = ws.cell(row=row_idx, column=col)
            cell.font = _FONT_BODY
            cell.border = _BORDER_ALL
            if col >= 5:
                cell.number_format = '#,##0.00' if col == 6 else '#,##0'
                cell.alignment = _ALIGN_RIGHT
            else:
                cell.alignment = _ALIGN_LEFT

    # 열 너비 자동 조정
    col_widths = [6, 15, 25, 15, 10, 15, 20]
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
```

> **단중(unit weight) 열 제거**: 기존 기술서에 있던 "단중(kg)" 열을 삭제했다.
> Why: 집계된 데이터에서 `total_weight / total_qty`는 "평균 단중"이며, 서로 다른 길이의 동일 규격 자재가 합산되면 의미 없는 수치가 된다. 혼동을 방지하기 위해 합계중량만 표시한다.

#### [MODIFY] `presets/bom.py` (현재 139줄)

**변경 내용:** `get_excel_config()` 반환값 확장 (+15줄)

```diff
 def get_excel_config() -> dict | None:
-    """
-    Excel 출력 커스텀 설정.
-
-    BOM은 현재 커스텀 시트 레이아웃이 불필요하므로 None 반환
-    → ExcelExporter._build_generic_sheet() 사용.
-
-    향후 BOM 전용 시트 포맷(고정 열 너비, 색상 등)이 필요하면
-    estimate.py처럼 dict 반환으로 확장한다.
-    """
-    return None
+    """BOM 전용 Excel 출력 설정. 3시트 구성: 원본/집계/LINE LIST."""
+    return {
+        "use_template": True,
+        "sheets": [
+            {
+                "name": "BOM 원본",
+                "builder": "generic",
+                "filter": {"type": "BOM_자재"},
+            },
+            {
+                "name": "BOM 집계",
+                "builder": "bom_summary",
+                "filter": {"type": "BOM_자재"},
+            },
+            {
+                "name": "LINE LIST",
+                "builder": "generic",
+                "filter": {"type": "BOM_LINE_LIST"},
+            },
+        ],
+    }
```

### 4.4 main.py BOM 파이프라인 내 preset_config 전달 추가

현재 main.py L339-346의 BOM→Excel 경로에서 `preset_config`를 전달하지 않는 문제를 수정한다.

```diff
 # main.py BOM 파이프라인 (L339~)
 if args.output_format == "excel":
     from exporters.excel_exporter import ExcelExporter
+    from presets.bom import get_excel_config
     xlsx_path = Path(str(output_base) + ".xlsx")
-    ExcelExporter().export(sections, xlsx_path)
+    excel_config = get_excel_config()
+    ExcelExporter().export(sections, xlsx_path, preset_config=excel_config)
     print(f"   Excel: {xlsx_path}")
```

> 이 변경은 단위 2의 `_process_single()`에도 이미 반영되어 있다 (2.6절 참조).

### 4.5 검증 계획

| 테스트 | 방법 | 기대 결과 |
|--------|------|----------|
| BOM → Excel | `--preset bom --output excel` | BOM 원본 + 집계 + LINE LIST 3개 시트 |
| estimate → Excel | `--preset estimate --output excel` | 기존 동작 유지 (`use_template` 없음, `_export_impl()` 경로) |
| 빈 BOM | 빈 sections → export() | "Empty" 시트 1개, 에러 없음 |
| preset_config 전달 | 단일 파일 BOM + excel | preset_config가 ExcelExporter에 전달됨 확인 |
| 배치 집계 Excel | `--batch --output excel` | 파일별 xlsx + 집계 xlsx |

---

## 단위 5: 61개 파일 최종 검증

### 5.1 목적

단위 1~4가 통합된 상태에서 **전체 61개 PIPE-BM-PS PDF**에 대한 엔드투엔드 배치를 실행하여
프로덕션 투입 가능 여부를 판정한다.

### 5.2 실행 명령

```bash
python main.py "G:\My Drive\엑셀\00. 회사업무\피에스산업\견적자료\02. 이전견적서\00. 창녕공장\고려아연 배관 Support 제작_추가 2차_ 견적서" \
    --batch \
    --pattern "PIPE-BM-PS-*.pdf" \
    --preset bom \
    --engine zai \
    --output excel
```

### 5.3 검증 매트릭스

| 검증 항목 | 합격 기준 | 측정 방법 |
|----------|----------|----------|
| 성공률 | >= 95% (58/61 이상) | `batch_result.tsv`의 OK 비율 |
| 평균 처리 시간 | <= 6초/파일 (캐시 미적중 시) | `batch_summary.txt` |
| 캐시 적중률 | 2차 실행 시 100% | `cache.stats()` |
| BOM 행 추출 | 모든 OK 파일에 BOM >= 1행 | TSV의 BOM행 컬럼 > 0 확인 |
| TOTAL WEIGHT 교차검증 | 샘플 5개 이상 원본 도면과 일치 | 수동 비교 |
| 집계 무결성 | sum(개별 Q'TY) == sum(집계 Q'TY) | `_run_batch()` 내 자동 assert (3.5절) |
| Excel 출력 | 모든 OK 파일에 .xlsx 생성 | 파일 존재 확인 |
| 집계 Excel | `*_bom_aggregated.xlsx` 생성 | 파일 존재 + 시트 구성 확인 |

### 5.4 오류 패턴 분석 절차

1. `batch_result.tsv`에서 FAIL 행 필터
2. FAIL 유형 분류: `TIMEOUT` / `API_ERROR` / `PARSE_ERROR` / `0_ROWS`
3. 유형별 대응:
   - `TIMEOUT`: 페이지 수 과다 → `--pages` 범위 제한
   - `API_ERROR`: API 키 만료/한도 → 재시도 또는 엔진 교체
   - `PARSE_ERROR`: 상태머신 미감지 → `presets/bom.py` 앵커/헤더 키워드 추가
   - `0_ROWS`: 도면 구조 비표준 → 개별 샘플 분석, OCR 원문 MD 확인

### 5.5 2차 실행 (캐시 검증)

1차 실행 완료 후 동일 명령을 재실행한다.

**기대 결과:**
- API 호출: 0회 (전량 캐시 적중)
- 처리 시간: < 1초/파일
- `cache.stats()`: hits == 61, misses == 0
- 출력물: 1차와 바이트 단위 동일

### 5.6 산출물

| 산출물 | 경로 | 설명 |
|--------|------|------|
| 배치 TSV | `output/batch_result.tsv` | 파일별 상세 결과 (상태/BOM행/LL행/시간) |
| 배치 요약 | `output/batch_summary.txt` | 통계 요약 텍스트 |
| 개별 BOM JSON | `output/YYYYMMDD_*_bom.json` | 파일별 BOM 추출 결과 (61개) |
| 개별 BOM MD | `output/YYYYMMDD_*_bom.md` | 파일별 OCR 원문 (61개) |
| 개별 BOM Excel | `output/YYYYMMDD_*_bom.xlsx` | 파일별 Excel (3시트) |
| BOM 집계 JSON | `output/YYYYMMDD_bom_aggregated.json` | 전체 자재 합산 |
| BOM 집계 Excel | `output/YYYYMMDD_bom_aggregated.xlsx` | 집계 시트 |
| 캐시 DB | `.cache/table_cache.db` | 재실행 시 즉시 응답 |

---

## 전체 파일 변경 요약

### 신규 파일 (4개)

| 파일 | 단위 | 예상 줄수 |
|------|------|----------|
| `cache/__init__.py` | 1 | 1 |
| `cache/table_cache.py` | 1 | ~140 |
| `exporters/bom_aggregator.py` | 3 | ~200 |
| `test_phase5_unit.py` | 전체 | ~150 |

### 수정 파일 (8개)

| 파일 | 단위 | 변경량 | 비고 |
|------|------|--------|------|
| `config.py` | 1 | +5줄 | 캐시 설정 상수 |
| `engines/base_engine.py` | 1 | +2줄 | cache 속성 추가 |
| `engines/zai_engine.py` | 1 | +25줄 | 파일/이미지 캐시 적용 |
| `engines/mistral_engine.py` | 1 | +15줄 | 파일 캐시 적용 |
| `engines/gemini_engine.py` | 1 | +15줄 | 이미지 캐시 적용 |
| `main.py` | 2,3 | +160줄 | 배치 통합 + 집계 + _process_single |
| `exporters/excel_exporter.py` | 4 | +150줄 | 프리셋 시트 + BOM 빌더 |
| `presets/bom.py` | 4 | +15줄 | Excel 설정 확장 |

### 기타

| 파일 | 변경 |
|------|------|
| `.gitignore` | `.cache/` 추가 |
| `batch_test.py` | 상단에 DEPRECATED 주석 추가 |

### 총 순증 코드: 약 +700줄

| 구분 | 줄수 |
|------|------|
| 신규 파일 합계 | ~491줄 (1+140+200+150) |
| 수정 파일 합계 | ~387줄 (5+2+25+15+15+160+150+15) |
| **총 순증** | **~700줄** (중복 제거 후 실질) |

---

## 의존성 관계 (실행 순서)

```
단위 1 (캐싱) ─────────────────────────────┐
                                            ↓
단위 2 (배치) ← 단위 1 필수 (캐시 공유)     │
                                            ↓
단위 3 (집계) ← 단위 2 필수 (배치 후 JSON 로드하여 집계)
                                            ↓
단위 4 (Excel) ← 단위 3 필수 (집계 시트 빌더)
                                            ↓
단위 5 (검증) ← 단위 1~4 전부 결합 ─────────┘
```

**단위 3 → 단위 2 관계 변경: "선택" → "필수"**
> Why: 단위 3의 집계 로직은 `_run_batch()` 내부에서 호출되며, `_load_all_json_sections()`이 배치로 생성된 JSON 파일들을 로드한다. 배치 없이 단독 집계가 필요하면 별도 CLI 인수(`--aggregate-only`)를 추가해야 하며, 이는 Phase 5 범위를 초과한다.

각 단위는 이전 단위가 완벽히 동작 및 검증된 후에만 다음으로 진행한다.

---

## 부록: 구현 시 주의사항 체크리스트

### A. 엔진별 캐시 적용 차이

| 엔진 | API 호출 메서드 | 캐시 키 방식 | 비고 |
|------|----------------|-------------|------|
| zai | `_call_api(data_uri)` | `make_key_from_file` (ocr_document) + `make_key_from_data` (ocr_image) | 이중 캐시 레이어 |
| mistral | `_client.ocr.process(...)` | `make_key_from_file` | 전체 파일 단위 처리 |
| gemini | `extract_full_page(image)`, `extract_table(image)` | `make_key_from_data` | 이미지 단위 처리 |

### B. JSON 인코딩 일관성

`JsonExporter`는 `encoding="utf-8-sig"` (BOM 포함)으로 저장한다.
`_load_all_json_sections()`에서 로드 시에도 반드시 `encoding="utf-8-sig"`를 사용해야 한다.

### C. Q'TY 값의 의미

실제 BOM 도면에서 Q'TY 값은 다음과 같이 도면마다 다를 수 있다:
- **수량** (정수): "2", "4", "10"
- **길이(mm)**: "1098", "1037" (H형강의 컷팅 길이)

집계 시 동일 규격의 길이를 합산하면 총 필요 길이가 되므로, 숫자 합산 자체는 유효하다.
다만 결과 해석 시 Q'TY가 "수량"인지 "길이"인지 사용자 확인이 필요하다.

---

> 작성일: 2026-04-16 | Phase 5 상세 구현 기술서 (단위 1~5)
> 최종 수정: 2026-04-16 (실제 코드베이스 검증 기반 32건 개선)
