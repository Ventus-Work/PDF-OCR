# Phase 7 결과보고서 검증 리뷰

**검증일:** 2026-04-17
**검증 대상:** `Phase7_결과보고서.md`
**검증 방법:** 기술서(`Phase7_상세_구현_기술서.md`) 대비 실제 파일 시스템 점검

---

## ✅ 제대로 구현된 항목

### 인프라 (100% 완료)
| 항목 | 위치 | 상태 |
|------|------|------|
| `requirements-dev.txt` | 루트 | ✅ |
| `pytest.ini` | 루트 | ✅ |
| `.coveragerc` | 루트 | ✅ |
| `tests/conftest.py` | tests/ | ✅ |
| `tests/unit/` + `tests/integration/` | tests/ | ✅ |

### P0 단위 테스트 (5/5 완료)
| 파일 | 보고서 주장 커버리지 | 상태 |
|------|---------------|-----|
| `tests/unit/test_detector.py` | - | ✅ |
| `tests/unit/test_config.py` | - | ✅ |
| `tests/unit/utils/test_page_spec.py` | 92% | ✅ |
| `tests/unit/utils/test_io.py` | 100% | ✅ |
| `tests/unit/cache/test_table_cache.py` | 89% | ✅ |

### 기존 테스트 마이그레이션
- 루트의 `test_*.py`, `_test_*.py`, `audit_main.py`, `batch_test.py`, `verify_phase4.py` 모두 `tests/integration/`으로 이관 완료 ✅

---

## ❌ 구현되지 않은 항목 (기술서 대비 중대한 누락)

### 🔴 이슈 1: P1 단위 테스트 **전부 누락** (6개 모듈)

기술서 §3에 명시된 P1 테스트가 **완전히 미구현**:

| 누락된 디렉토리 | 포함되어야 할 파일 |
|---------------|-------------------|
| `tests/unit/parsers/` | test_text_cleaner, test_table_parser, test_section_splitter, test_bom_table_parser, test_document_parser |
| `tests/unit/extractors/` | test_bom_extractor, test_toc_parser, test_table_utils |

**검증:** `ls tests/unit/parsers/` → "No such file or directory"

### 🔴 이슈 2: P2 단위 테스트 **전부 누락** (4개+ 모듈)

| 누락된 경로 | 포함되어야 할 파일 |
|-----------|-------------------|
| `tests/unit/utils/` 내 | test_markers.py, test_text_formatter.py, test_usage_tracker.py |
| `tests/unit/presets/` | test_estimate.py, test_pumsem.py, test_bom.py |

**현재 `tests/unit/utils/`에 있는 것:** `test_io.py`, `test_page_spec.py` 2개만

### 🔴 이슈 3: `tests/fixtures/` 디렉토리 자체 없음

기술서 §1.1에서 정의한:
- `fixtures/sample_markdowns/` (simple_estimate.md, bom_page.md 등)
- `fixtures/sample_pdfs/tiny_test.pdf`
- `fixtures/mock_responses/`

**모두 미생성** → `conftest.py`의 `sample_md_dir`, `bom_page_md` 픽스처가 **실제로 동작 불가** (파일 없으면 FileNotFoundError)

### 🟡 이슈 4: CI 설정 누락
- `.github/workflows/ci.yml` 없음 (옵션이지만 기술서 §6.1에서 권장)
- `scripts/run_tests.sh` / `run_tests.bat` 없음

### 🟡 이슈 5: 테스트 가이드 문서 누락
- `tests/README.md` 없음 (기술서 §7에서 요구)

---

## ⚠️ 품질 이슈

### 이슈 6: 디버그 스크립트를 삭제하지 않고 integration/에 이관

기술서 §5.1 표에서 **"삭제"** 로 지정된 파일들이 `tests/integration/`에 **그대로 이관**됨:

```
tests/integration/
  ├── _debug_agg.py          ← 기술서: "삭제" → 실제: 이관됨
  ├── _inspect_json.py        ← 기술서: "삭제" → 실제: 이관됨
  ├── _test_patch_verify.py   ← 기술서: "삭제" → 실제: 이관됨
  ├── _test_phase3.py         ← 기술서: "삭제" → 실제: 이관됨
  ├── audit_main.py           ← 기술서: 언급 없음, 원래 개발 스크립트
  ├── batch_test.py           ← 기술서: 언급 없음
  └── verify_phase4.py        ← 기술서: 언급 없음
```

**영향:** pytest가 `_test_*.py`는 수집하지 않지만(언더스코어 접두), `audit_main.py`, `batch_test.py`, `verify_phase4.py`는 **수집 대상**이 될 수 있어 `pytest tests/integration` 시 **의도치 않은 동작** 가능

### 이슈 7: 중복 파일 (Google Drive 동기화 충돌)

```
tests/integration/
  ├── test_phase4_pipeline.py
  └── {20ce254c-39fc-11f1-ac6a-8c880b0930ab}test_phase4_pipeline.py   ← UUID 접두 중복
```

**조치 필요:** UUID 접두 파일 삭제 (Google Drive 동기화 오류 잔재)

### 이슈 8: lock 관련 테스트가 병합되지 않음

기술서 §5.1 지시:
> `test_lock.py` + `test_excel_lock.py` + `test_folder_lock.py` → 병합 → `test_file_lock.py`

실제:
```
tests/integration/
  ├── test_excel_lock.py       ← 그대로
  ├── test_folder_lock.py      ← 그대로
  └── test_lock.py             ← 그대로
```
**병합 안 됨**

---

## 📉 보고서 자체의 문제

### 이슈 9: 전체 커버리지 수치 미공개

- 기술서 §0.2 완료 기준: "전체 프로젝트 커버리지 ≥50%"
- 보고서 §2.3: 개별 모듈 커버리지(100%, 92%, 89%)만 기재
- **전체 프로젝트 커버리지 수치 없음** → 50% 달성 여부 확인 불가

**현실적 추정:**
- P0만 구현(5개 모듈), P1/P2 **0개**
- 전체 ~15개 모듈 중 5개 = **약 33% 커버리지 추정**
- **50% 목표 미달 가능성 높음**

### 이슈 10: 보고서가 P1/P2 미착수를 명시적으로 보고하지 않음

보고서 §2.3은 "P0 모듈 테스트 작성을 완료"라고만 적고, P1/P2에 대한 **언급 자체가 없음** → 독자가 전체 완료로 오해 가능

### 이슈 11: 10일 일정 대비 실제 산출물 평가

| 기술서 일정 | 기대 산출물 | 실제 산출물 |
|----------|----------|----------|
| Day 1~4 (인프라+P0) | 5개 테스트 파일 | ✅ 5개 |
| Day 5~6 (P1) | 6개 테스트 파일 | ❌ 0개 |
| Day 7~8 (P2+마이그레이션) | 4개 + 이관 | ⚠️ 이관만 (P2 0개, 병합/삭제 미완) |
| Day 9 (CI) | CI 설정 | ❌ 없음 |
| Day 10 (문서) | README + 보고서 | ❌ README 없음 / 보고서만 |

**실 진행률 약 40~50%** 로 평가

---

## 🛠 권장 후속 조치

### 🔴 반드시 (Phase 8 진입 전)

1. **P1 테스트 최소 3개 추가 확보**
   - `test_text_cleaner.py`, `test_table_parser.py`, `test_bom_extractor.py`
   - Phase 8에서 리팩터링할 `bom_extractor.py`(정규식 캐싱)는 **필수**

2. **`tests/fixtures/` 디렉토리 생성**
   - 최소한 `sample_markdowns/bom_page.md`, `simple_estimate.md` 2개
   - 없으면 `conftest.py`의 픽스처가 런타임 에러

3. **디버그 파일 정리**
   - `_debug_agg.py`, `_inspect_json.py`, `_test_phase3.py`, `_test_patch_verify.py` **삭제**
   - `audit_main.py`, `batch_test.py`, `verify_phase4.py`는 `scripts/` 또는 `tools/` 디렉토리로 분리 (테스트 아님)
   - `{20ce254c-...}test_phase4_pipeline.py` **즉시 삭제** (동기화 충돌 잔재)

4. **전체 커버리지 수치 측정 후 보고**
   - `pytest tests/unit --cov --cov-report=term` 실행
   - 보고서에 수치 기재

### 🟡 권장

5. Lock 테스트 3개 → `test_file_lock.py` 병합
6. `tests/README.md` 작성
7. 로컬 CI 스크립트(`scripts/run_tests.bat`) 최소한 추가

### 🟢 선택

8. GitHub Actions `.github/workflows/ci.yml` (Git 사용 안 하면 불필요)
9. P2 테스트 (markers, text_formatter, usage_tracker)

---

## 📊 종합 평가

| 항목 | 등급 | 코멘트 |
|------|------|-------|
| 인프라 셋업 | **A** | pytest.ini, .coveragerc, conftest.py 완벽 |
| P0 단위 테스트 | **A-** | 5/5 완료, 버그 발견 및 수정 |
| P1 단위 테스트 | **F** | **0/6 전혀 구현 안 됨** |
| P2 단위 테스트 | **F** | **0/4 전혀 구현 안 됨** |
| 기존 테스트 마이그레이션 | **C** | 이관은 했으나 삭제/병합 미완 |
| Fixtures | **F** | 디렉토리 자체 없음 |
| 문서화 | **D** | tests/README 없음 |
| 보고서 정확성 | **C** | P1/P2 누락을 명시 안 함, 전체 커버리지 수치 없음 |

**종합: 계획의 약 40~50% 진행** — Phase 8 진입 전에 최소 위 🔴 항목 4개는 완료 필요합니다. 특히 **fixtures 없이는 conftest.py가 사실상 작동 불가**하므로 시급합니다.

---

**검증자:** Claude Opus 4
**검증 일자:** 2026-04-17
**관련 문서:**
- `Phase7_상세_구현_기술서.md`
- `Phase7_결과보고서.md`

---

---

# 📝 Phase 7 결과보고서 재검증 (2차)

**재검증일:** 2026-04-17
**사유:** 사용자가 Phase7_결과보고서.md 재구현 후 덮어쓰기 완료

이전 리뷰 대비 **대부분의 🔴 이슈가 해결**되었습니다. 다만 일부 새로운 품질 이슈가 있습니다.

## ✅ 이전 리뷰 지적사항 해결 현황

### 🔴 Critical 이슈 (이전)
| # | 이전 문제 | 현재 상태 |
|---|---------|---------|
| 1 | P1 테스트 0/6 | **3/6 추가** (text_cleaner, table_parser, bom_extractor) ✅ |
| 2 | `tests/fixtures/` 없음 | **생성됨** (simple_estimate.md, bom_page.md) ✅ |
| 3 | 디버그 파일 정리 안 됨 | **삭제+이동 완료** ✅ |
| 4 | 전체 커버리지 미공개 | **9.5% 공개** ✅ (정직) |

### 🟡 Warning 이슈 (이전)
| # | 이전 문제 | 현재 상태 |
|---|---------|---------|
| 5 | Lock 테스트 병합 안 됨 | **`test_file_lock.py`로 병합** ✅ |
| 6 | `tests/README.md` 없음 | **생성됨** (29줄) ✅ |
| 7 | 로컬 CI 스크립트 없음 | **`scripts/run_tests.bat` 생성** ✅ |

### 🔴 이전 지적의 구체 검증 결과
```
tools/
├── audit_main.py         ← 이전 'tests/integration'에 방치 → 분리 ✅
├── batch_test.py         ← 이전 'tests/integration'에 방치 → 분리 ✅
└── verify_phase4.py      ← 이전 'tests/integration'에 방치 → 분리 ✅

_debug_agg.py, _inspect_json.py, _test_patch_verify.py, _test_phase3.py
→ 전부 삭제됨 ✅

{20ce254c-...}test_phase4_pipeline.py  ← UUID 중복 삭제됨 ✅
```

---

## ⚠️ 새롭게 발견된 이슈

### 🔴 이슈 A: 전체 커버리지 **9.5%** — 기술서 목표 50%에 **크게 미달**

**기술서 §0.4 완료 기준:**
> "전체 프로젝트 커버리지 ≥50%"

**현재:** 9.5% → **목표 대비 1/5 수준**

보고서 §3은 "코어/엔진 부하가 큰 통합/리포팅 부분 제외"라 설명하지만, 실제 원인은:
- P1 테스트 **절반만** 구현 (3/6)
- P2 테스트 **전혀** 구현 안 됨 (0/4)
- parsers/document_parser.py, extractors/hybrid_extractor.py 등 대형 모듈 미커버

**이 보고서는 완료된 Phase 보고가 아니라 "중간 결과" 성격입니다.**

### 🔴 이슈 B: P1 테스트 파일이 **너무 빈약**

라인 수 검증:
```
tests/unit/parsers/test_text_cleaner.py    →  24 줄
tests/unit/parsers/test_table_parser.py    →  18 줄
tests/unit/extractors/test_bom_extractor.py →  14 줄
                                     합계 →  56 줄 (3개 파일)
```

**비교:**
- P0 파일 평균 100+ 줄 예상
- 기술서 §3에 제시된 테스트 케이스 수: 모듈당 3~6개
- 실제 구현된 테스트 함수 수 추정: **모듈당 1~2개** (smoke test 수준)

**의미:** 파일은 생겼지만 실제 검증 깊이가 **기술서 기대 대비 20~30%** 수준

### 🔴 이슈 C: Fixtures 샘플이 **거의 비어있음**

```
tests/fixtures/sample_markdowns/simple_estimate.md  →  3 줄
tests/fixtures/sample_markdowns/bom_page.md          →  4 줄
```

의미 있는 테스트 샘플이라기보다 **placeholder** 수준. 파서 검증의 실질적 가치 제한적.

### 🟡 이슈 D: P1 테스트 3개 여전히 누락

| 구현 | 누락 |
|------|------|
| ✅ test_text_cleaner.py | ❌ test_section_splitter.py |
| ✅ test_table_parser.py | ❌ test_bom_table_parser.py |
| ✅ test_bom_extractor.py | ❌ test_document_parser.py |
| | ❌ test_toc_parser.py |

### 🟡 이슈 E: 보고서의 "완료" 표현이 과장

보고서 §2.3 제목: **"P0 & P1 단위 테스트 구현 및 개선 사항"**

실제로는:
- P0: 5/5 완료 (100%) ✓
- P1: 3/6 완료 (50%)
- P2: 0/4 완료 (0%)

**"P1 단위 테스트 구현"이라 쓰면 독자는 완료로 이해 가능** → 실제 부분 완료임을 명시해야 함

### 🟢 이슈 F: `scripts/run_tests.bat`이 너무 단순

현재 내용:
```batch
@echo off
rem ps-docparser Unit Tests Runner
echo Running Unit Tests and calculating coverage...
pytest tests\unit -v --cov --cov-report=term-missing
```

기술서 §6.2에 제시한 구조(단계 구분, --full 옵션, 에러 처리) 대비 **매우 단순화**됨. 동작은 하지만 기능 한정적.

---

## 📊 종합 재평가

| 항목 | 1차 등급 | 2차 등급 | 변화 |
|------|---------|---------|------|
| 인프라 셋업 | A | A | - |
| P0 단위 테스트 | A- | A- | - |
| P1 단위 테스트 | F | **C+** | ⬆️ (0→3개, 단 내용 빈약) |
| P2 단위 테스트 | F | F | - |
| 마이그레이션 정리 | C | **A** | ⬆️ (삭제+병합 완료) |
| Fixtures | F | **C** | ⬆️ (존재하지만 내용 빈약) |
| 문서화 | D | **B** | ⬆️ (README 생성) |
| 보고서 정확성 | C | **B-** | ⬆️ (수치 공개, 단 표현 과장) |
| **전체 커버리지 달성도** | 추정 33% | **9.5%** | ⬇️ (실측 결과 더 낮음) |

---

## 🛠 2차 권장 후속 조치

### 🔴 Phase 8 진입 전 필수

1. **P1 테스트 내용 보강**
   - 기존 3개 파일(text_cleaner, table_parser, bom_extractor)을 **기술서 §3 수준으로 확장**
   - 현재 14~24줄 → 각 60~100줄 목표

2. **Fixtures MD 샘플 실질화**
   - `simple_estimate.md`: 최소 20줄 이상 (목차, 표 포함)
   - `bom_page.md`: 최소 30줄 (BOM 상태머신 검증 가능한 분량)

3. **Phase 8에서 리팩터링할 `bom_extractor.py` 집중 강화**
   - Phase 8 정규식 캐싱 리팩터링 시 regression 감지 필수
   - `_sanitize_html()` 외 `BomSection`, 상태머신 로직 테스트 추가

### 🟡 권장

4. 커버리지 목표 **재설정**: 50% → 단기 30%, 중기 50% (현실적)
5. 보고서 §2.3 표현 수정: "P1 중 3개 구현, 3개 이월"
6. `run_tests.bat`에 단계별 출력 + 실패 시 errorlevel 처리 추가

### 🟢 선택

7. P1 나머지 (section_splitter, bom_table_parser, document_parser, toc_parser) 추가
8. P2 테스트 시작

---

## 🎯 2차 결론

**1차 리뷰 대비 뚜렷한 개선** — 인프라/정리/병합/문서 측면은 **A 등급**으로 상승.

하지만 **테스트 실질 내용 부족**이 최대 이슈:
- 🟢 **껍데기(인프라)는 완벽**
- 🔴 **알맹이(테스트 로직)는 얕음**

**권장:** Phase 8 진입 전, 위 🔴 1~3번 항목에 **1~2일 추가 투자**하여 P1 3개 파일의 테스트를 기술서 수준으로 확장. 그 후 Phase 8 리팩터링이 regression 위험 없이 진행 가능합니다.

특히 `bom_extractor.py`는 Phase 8의 핵심 리팩터링 대상이므로 **현재 14줄 테스트로는 안전망 역할 불가**합니다.

---

**2차 검증자:** Claude Opus 4
**2차 검증 일자:** 2026-04-17
**상태 비교:**
- 1차 검증: 계획의 40~50% 진행
- 2차 검증: 계획의 **65~75% 진행** (인프라 완성, 테스트 내용 부족)

---

---

# 📝 Phase 7 결과보고서 3차 검증 (상세)

**3차 검증일:** 2026-04-17
**사유:** 사용자가 Phase7_결과보고서.md 2차 업데이트 (커버리지 9.5%→15.0%, P1/P2 전 모듈 테스트 파일 추가)

## 📈 이전 리뷰 피드백 반영 현황

### ✅ 해결된 항목

| # | 2차 리뷰 지적 | 3차 반영 상태 |
|---|---------|-----------|
| A | 전체 커버리지 9.5% → 50% 미달 | 15.0%로 상승 + **목표 재설정 인정** ✅ |
| D | P1 3개 누락 (section_splitter, bom_table_parser, document_parser, toc_parser) | **전부 추가** ✅ |
| E | 보고서 "완료" 표현 과장 | 목표치 재검토 명시 ✅ |
| - | (Phase 6 잔존) json_exporter.py _safe_write_text 미사용 | **해결됨** `utils/io.py` 승격 후 json_exporter.py에서 import ✅ |

### 🆕 신규 추가된 테스트 파일 (8개)

```
tests/unit/
├── extractors/
│   ├── test_table_utils.py         ← 신규 (16줄)
│   └── test_toc_parser.py          ← 신규 (7줄)
├── parsers/
│   ├── test_bom_table_parser.py    ← 신규 (24줄)
│   ├── test_document_parser.py     ← 신규 (8줄)
│   └── test_section_splitter.py    ← 신규 (15줄)
└── utils/
    ├── test_markers.py              ← 신규 (9줄)
    ├── test_text_formatter.py       ← 신규 (9줄)
    └── test_usage_tracker.py        ← 신규 (11줄)
```

**기존 6개 + 신규 8개 = 총 16개 테스트 파일** (기술서 요구치 대부분 충족)

### 🎯 Phase 6 잔존 이슈까지 해결

`utils/io.py:16` — `_safe_write_text` 정의
`exporters/json_exporter.py:44-47`:
```python
from utils.io import _safe_write_text
...
_safe_write_text(output_path, json_str, encoding="utf-8-sig")
```
→ **Phase 6 결과보고서 검증에서 지적했던 "허위 주장" 이슈가 Phase 7에서 구조적으로 해결**됨

---

## 🔴 여전히 남아있는 중대 이슈

### 이슈 1: **"파일 존재 전략"** — 테스트 깊이 절망적으로 얕음

테스트 함수 개수 검증:

| 파일 | 라인 수 | 테스트 함수 수 | 상태 |
|------|--------|-----------|------|
| test_toc_parser.py | 7줄 | **1개** | 🔴 |
| test_document_parser.py | 8줄 | **1개** | 🔴 |
| test_markers.py | 9줄 | **1개** | 🔴 |
| test_text_formatter.py | 9줄 | **1개** | 🔴 |
| test_usage_tracker.py | 11줄 | **1개** | 🔴 |
| test_bom_extractor.py | 14줄 | **1개** | 🔴 (Phase 8 핵심!) |
| test_section_splitter.py | 15줄 | **2개** | 🟡 |
| test_table_utils.py | 16줄 | **1개** | 🔴 |
| test_table_parser.py | 18줄 | **3개** | 🟡 |
| test_bom_table_parser.py | 24줄 | **2개** | 🟡 |
| test_text_cleaner.py | 24줄 | **3개** | 🟡 |

**13개 중 6개(46%)가 단 1개 테스트 함수만 가진 smoke test 수준**

기술서 §2~§3에서 각 모듈당 **3~6개 테스트 케이스** 요구 → **미달 파일 다수**

### 이슈 2: `bom_extractor.py` 테스트 개선 **무시됨** (2회 연속)

2차 리뷰 §2차 권장 후속 조치 §1~3에서 **가장 강조**한 항목:
> **3. Phase 8에서 리팩터링할 `bom_extractor.py` 집중 강화**
> - `_sanitize_html()` 외 `BomSection`, 상태머신 로직 테스트 추가

**3차 현재 상태:**
```python
# tests/unit/extractors/test_bom_extractor.py (14줄, 1개 테스트)
class TestBomExtractor:
    def test_sanitize_html(self):
        html = "<table><tr><td>SIZE</td><td>PIPE</td></tr></table>"
        sanitized = _sanitize_html(html)
        assert "<table>" not in sanitized
        assert "|" in sanitized
        assert "SIZE | PIPE" in sanitized
```

- **변화 없음** (2차와 동일 14줄, 1개 테스트)
- `BomSection` 데이터클래스 테스트 없음
- 상태머신 로직 테스트 없음
- **Phase 8의 최대 리스크로 그대로 남아있음**

### 이슈 3: Fixtures **개선 전무** (2회 연속 무시)

```
tests/fixtures/sample_markdowns/
├── bom_page.md          →  4줄 (2차 리뷰 때와 동일)
└── simple_estimate.md   →  3줄 (2차 리뷰 때와 동일)
```

- 2차 리뷰 §권장 🔴 2 "Fixtures MD 샘플 실질화" (최소 20줄, 30줄) → **완전 무시**
- **`conftest.py`의 `simple_estimate_md`, `bom_page_md` 픽스처가 사실상 껍데기**
- 실제 파서 검증 가치 제한적

### 이슈 4: 커버리지 15%도 사실 부풀림 가능성

**"15%"의 해석 주의:**
- 16개 테스트 파일 × 대부분 1개 함수 × smoke test 수준
- **문장 실행률(statement coverage)** 15%이지 **분기 커버리지(branch)** 는 더 낮을 가능성
- `.coveragerc`에 `branch = True`로 설정되어 있으니 15%가 branch 포함일 수는 있음 (보고서 해석 불명)

### 이슈 5: 보고서 §3의 설명 불일치

보고서 §3:
> "검증 리뷰 🔴 이슈 1 피드백을 우선적으로 수용하여 ... **P1/P2 전 모듈에 대한 테스트 파일 구축 및 컴포넌트 호출 검증을 신속 완료**"

**실제:**
- "테스트 파일 구축" ✅ 맞음
- "컴포넌트 호출 검증" → 대부분 1회 호출만 하는 smoke test → **검증 완료라 보기 어려움**

---

## 📊 3회 검증 비교 종합

| 항목 | 1차 등급 | 2차 등급 | **3차 등급** | 추세 |
|------|-----|-----|---------|------|
| 인프라 | A | A | A | - |
| P0 테스트 | A- | A- | A- | - |
| P1 테스트 | F | C+ | **B-** | ⬆️ 파일 확충 |
| P2 테스트 | F | F | **C** | ⬆️ 파일 추가 (내용 얕음) |
| 마이그레이션 | C | A | A | - |
| Fixtures | F | C | **C** | ⚠️ 개선 없음 |
| 문서화 | D | B | B | - |
| 보고서 정확성 | C | B- | **B** | ⬆️ 솔직한 수치 |
| Phase 6 잔존 | - | - | **A** | ⬆️ json_exporter 해결 |
| **전체 커버리지** | 미공개 | 9.5% | **15.0%** | ⬆️ +5.5%p |
| **테스트 깊이** | N/A | 빈약 | **여전히 빈약** | ⚠️ 변화 미미 |

---

## 🛠 3차 권장 후속 조치

### 🔴 Phase 8 진입 전 필수 (여전히 유효)

1. **`bom_extractor.py` 테스트 반드시 확장** ⚠️
   - 현재 14줄 1개 테스트 → **최소 50줄, 5개 테스트**
   - 검증 대상:
     - `_sanitize_html()` 다양한 HTML 패턴
     - `BomSection` 데이터클래스 (title, rows, row_count)
     - 상태머신의 섹션 전환
     - 엣지 케이스 (빈 테이블, 깨진 HTML)
   - **Phase 8 리팩터링 안전망으로 이것 없이는 진입 위험**

2. **Fixtures MD 실질화** (여전히 미해결)
   - `simple_estimate.md` 20줄 이상 (목차+표 포함)
   - `bom_page.md` 30줄 이상 (BOM 전형 예시)
   - 없으면 conftest.py 픽스처가 placeholder

3. **1개 함수만 있는 smoke test 6개 보강**
   - 우선순위: `test_table_utils`, `test_section_splitter`, `test_document_parser`
   - 각 최소 3개 테스트 함수로 확장

### 🟡 권장

4. 커버리지 해석 명확화: statement vs branch 명시
5. `test_toc_parser.py` 7줄 → TOC JSON/TXT 파싱 분기 포함

### 🟢 선택

6. 통합 테스트 실행 검증 (지금은 단위 테스트만 `scripts/run_tests.bat`)

---

## 🎯 3차 결론

### 긍정적 변화
- **Phase 6 잔존 이슈(`json_exporter.py` `_safe_write_text` 미사용) 해결** → 구조적 일관성 확보
- **커버리지 수치 상승** (9.5% → 15%) 및 목표 재설정 **솔직한 인정**
- **테스트 파일 수** 기술서 요구치 대부분 충족 (16개)

### 우려점
- **"파일 존재 ≠ 테스트 존재"** — smoke test 수준이 여전히 과반
- **Phase 8 최대 리스크인 `bom_extractor.py` 테스트 보강이 2회 연속 무시됨** (2번 연속 우선 권고 기각)
- **Fixtures가 여전히 placeholder 수준**

### 진행률 평가
- 1차: 40~50%
- 2차: 65~75%
- **3차: 75~80%** (파일 완성도↑, 내용 깊이↓)

### 최종 권고
**Phase 8 진입 가능**하나, 위 🔴 1번(`bom_extractor.py` 테스트 확장)은 **Phase 8 시작 직후 첫 작업으로 반드시 수행** 권장. 리팩터링 전에 안전망을 갖춘 후 정규식 캐싱 작업 진행해야 합니다.

---

**3차 검증자:** Claude Opus 4
**3차 검증 일자:** 2026-04-17
**상태 비교:**
- 1차 검증: 계획의 40~50% 진행
- 2차 검증: 계획의 65~75% 진행
- 3차 검증: 계획의 **75~80% 진행** (파일 완성도↑, 테스트 내용 깊이 과제 남음)

---

# 🛠 3차 리뷰 후속 조치 상세 구현 가이드

> 3차 리뷰에서 지적된 🔴 이슈 3가지를 **즉시 구현 가능한 형태**로 풀어 정리합니다.
> 각 섹션은 **복사 → 저장 → 실행** 순으로 진행 가능합니다.

## 📂 작업 체크리스트 (한눈에)

- [ ] 🔴 **A.** `tests/unit/extractors/test_bom_extractor.py` **확장** (14줄→75줄, 1개→7개 테스트)
- [ ] 🔴 **B.** `tests/fixtures/sample_markdowns/simple_estimate.md` **실질화** (3줄→25줄)
- [ ] 🔴 **C.** `tests/fixtures/sample_markdowns/bom_page.md` **실질화** (4줄→35줄)
- [ ] 🔴 **D.** `tests/unit/extractors/test_table_utils.py` **확장** (16줄→45줄, 1개→4개 테스트)
- [ ] 🔴 **E.** `tests/unit/parsers/test_section_splitter.py` **확장** (15줄→55줄, 2개→6개 테스트)
- [ ] 🔴 **F.** `tests/unit/parsers/test_document_parser.py` **확장** (8줄→40줄, 1개→4개 테스트)
- [ ] 🟡 **G.** `tests/unit/extractors/test_toc_parser.py` **확장** (7줄→35줄, 1개→4개 테스트)
- [ ] 🟡 **H.** P2 smoke test 3개 확장 (markers, text_formatter, usage_tracker)
- [ ] 🟢 **I.** 커버리지 재측정 및 보고서에 statement/branch 명시

---

## A. `test_bom_extractor.py` 확장 — **Phase 8 최우선**

### A.1 왜 우선인가
Phase 8 리팩터링 대상인 `bom_extractor.py`는 상태머신(IDLE → BOM_SCAN → BOM_DATA 등)과 `_sanitize_html` HTML→파이프 변환 5단계를 포함합니다. 현재 1개 테스트로는 정규식 캐싱 리팩터링 후 **regression 감지 불가**합니다.

### A.2 추가해야 할 테스트 케이스 (총 7개)

| # | 테스트 함수 | 검증 대상 |
|---|----------|---------|
| 1 | `test_sanitize_html_basic` (기존) | 기본 `<table><tr><td>` 제거 |
| 2 | `test_sanitize_html_rows_split` | `</tr>` → `\n` 변환 |
| 3 | `test_sanitize_html_entities` | `&amp;`, `&#x27;`, `&nbsp;` 등 HTML 엔티티 제거 |
| 4 | `test_sanitize_html_empty_input` | 빈 문자열/공백만 입력 |
| 5 | `test_bom_section_dataclass` | `BomSection(title, rows, row_count)` 속성 |
| 6 | `test_extract_bom_state_machine_idle_to_bom` | IDLE → BOM_SCAN 전환 (앵커 키워드) |
| 7 | `test_extract_bom_kill_keyword_ends_section` | kill 키워드로 섹션 종료 |

### A.3 구현 템플릿 (전문 복사용)

```python
"""
bom_extractor.py 단위 테스트 (P1) - Phase 8 안전망
"""
import pytest
from extractors.bom_extractor import _sanitize_html, extract_bom
from extractors.bom_types import BomSection


class TestSanitizeHtml:
    def test_sanitize_html_basic(self):
        html = "<table><tr><td>SIZE</td><td>PIPE</td></tr></table>"
        sanitized = _sanitize_html(html)
        assert "<table>" not in sanitized
        assert "|" in sanitized
        assert "SIZE | PIPE" in sanitized

    def test_sanitize_html_rows_split(self):
        html = "<tr><td>A</td></tr><tr><td>B</td></tr>"
        sanitized = _sanitize_html(html)
        # </tr>이 개행으로 변환되어 2행이 되어야 함
        non_empty_lines = [l for l in sanitized.split("\n") if l.strip()]
        assert len(non_empty_lines) == 2

    def test_sanitize_html_entities(self):
        html = "Size&amp;Type &#x27;PIPE&#x27; &nbsp;END"
        sanitized = _sanitize_html(html)
        assert "&amp;" not in sanitized
        assert "&#x27;" not in sanitized
        assert "&nbsp;" not in sanitized
        assert "&" in sanitized  # &amp; → & 로 복원

    def test_sanitize_html_empty_input(self):
        assert _sanitize_html("") == ""
        assert _sanitize_html("   ").strip() == ""

    def test_sanitize_html_nested_tags(self):
        # 중첩 태그도 모두 제거되어야 함
        html = "<div><span><b>TEXT</b></span></div>"
        sanitized = _sanitize_html(html)
        assert "<" not in sanitized
        assert ">" not in sanitized
        assert "TEXT" in sanitized


class TestBomSection:
    def test_bom_section_fields(self):
        section = BomSection(title="BOM", rows=[["1", "PIPE"]], row_count=1)
        assert section.title == "BOM"
        assert section.row_count == 1
        assert len(section.rows) == 1

    def test_bom_section_empty(self):
        section = BomSection(title="LINE LIST", rows=[], row_count=0)
        assert section.row_count == 0
        assert section.rows == []


class TestExtractBomStateMachine:
    @pytest.fixture
    def minimal_keywords(self):
        return {
            "anchor_bom": ["BILL OF MATERIAL", "BOM"],
            "anchor_ll": ["LINE LIST"],
            "bom_header_a": ["ITEM"],
            "bom_header_b": ["SIZE"],
            "bom_header_c": ["QTY"],
            "ll_header_a": ["LINE"],
            "ll_header_b": ["FROM"],
            "ll_header_c": ["TO"],
            "kill": ["NOTES", "END OF BOM"],
            "noise_row": [],
            "rev_markers": [],
        }

    def test_extract_bom_empty_text(self, minimal_keywords):
        res = extract_bom("", minimal_keywords)
        # 빈 입력 시 섹션 없음
        assert res is not None
        assert len(getattr(res, "sections", [])) == 0

    def test_extract_bom_no_anchor(self, minimal_keywords):
        # 앵커 키워드 없는 텍스트는 IDLE 유지
        text = "그냥 텍스트입니다. 표도 없습니다."
        res = extract_bom(text, minimal_keywords)
        assert len(getattr(res, "sections", [])) == 0
```

> **참고:** `extract_bom()`의 리턴 타입(`BomExtractionResult`)이 프로젝트 정의에 따라 속성명이 다를 수 있으므로 `getattr(res, "sections", [])` 식으로 방어적 접근. 실제 구조 확인 후 `assert res.sections == []`로 명시화 권장.

### A.4 예상 커버리지 상승
`bom_extractor.py` (200줄+) 대상 커버리지 ~5% → ~35% (`_sanitize_html` 전 5단계 + 상태머신 초기 분기 포함)

---

## B & C. Fixtures MD 실질화

### B.1 `tests/fixtures/sample_markdowns/simple_estimate.md` (25줄)

**목적:** 목차/제목/표/주석행 등 파서의 기본 분기를 모두 타게 하는 최소 샘플.

```markdown
# 견적서 샘플 (단순형)

<!-- PAGE 1 -->

## 제1편 일반사항

### 제1장 공사개요

본 공사는 배관 서포트 제작 및 설치를 포함한다.

### 제2장 시공범위

- 배관 서포트 제작
- 현장 설치
- 도장 공사

<!-- PAGE 2 -->

## 제2편 내역서

| 품명 | 규격 | 수량 | 단가 | 금액 |
|------|------|------|------|------|
| PIPE | 6" SCH40 | 10 | 12,000 | 120,000 |
| ELBOW | 6" 90° | 4 | 8,000 | 32,000 |
| [주] 상기 단가는 부가세 별도 | | | | |

합계: 152,000원
```

### C.1 `tests/fixtures/sample_markdowns/bom_page.md` (35줄)

**목적:** `bom_extractor.py` 상태머신의 **전체 전이**(IDLE→BOM_SCAN→BOM_DATA→IDLE)를 자극하는 샘플.

```markdown
<!-- PAGE 15 -->

## BILL OF MATERIAL

| ITEM | SIZE | DESCRIPTION | QTY | UNIT |
|------|------|-------------|-----|------|
| 1    | 6"   | PIPE CS SCH40 | 10  | M    |
| 2    | 6"   | ELBOW 90 LR   | 4   | EA   |
| 3    | 6"   | TEE EQUAL     | 2   | EA   |
| 4    | 6"   | FLANGE WN     | 8   | EA   |

NOTES:
1. All dimensions in mm unless noted otherwise.
2. Material: ASTM A106 Gr.B

<!-- PAGE 16 -->

## LINE LIST

| LINE NO | FROM | TO | SIZE | SPEC | INSUL |
|---------|------|-----|------|------|-------|
| P-001   | V-101 | P-101 | 6"  | CS150 | HOT |
| P-002   | P-101 | E-201 | 4"  | CS150 | -   |
| P-003   | E-201 | V-201 | 4"  | CS150 | HOT |

END OF LINE LIST

---

## 기타

이 이후는 BOM/LL 외 섹션입니다. (상태머신이 IDLE로 복귀해야 함)
```

### B/C 공통 효과
- `conftest.py`의 `simple_estimate_md`, `bom_page_md` 픽스처가 의미 있는 입력을 반환
- `test_document_parser.py`, `test_bom_extractor.py`, `test_section_splitter.py` 등이 **실제 파싱 경로**를 타도록 확장 가능

---

## D. `test_table_utils.py` 확장 (4개 테스트)

```python
import pytest
from extractors.table_utils import detect_tables


class DummyLine:
    def __init__(self, x0, y0, x1, y1):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1


class DummyTable:
    def __init__(self, bbox):
        self.bbox = bbox
    def extract(self):
        return [["A", "B"], ["1", "2"]]


class DummyPage:
    def __init__(self, lines=None, tables=None, width=612, height=792):
        self.width = width
        self.height = height
        self.lines = lines or []
        self._tables = tables or []
    def find_tables(self, table_settings=None):
        return self._tables


class TestDetectTables:
    def test_no_tables(self):
        page = DummyPage()
        assert detect_tables(page) == []

    def test_single_table(self):
        page = DummyPage(tables=[DummyTable(bbox=(0, 0, 100, 50))])
        res = detect_tables(page)
        assert len(res) == 1

    def test_multiple_tables(self):
        page = DummyPage(tables=[
            DummyTable(bbox=(0, 0, 100, 50)),
            DummyTable(bbox=(0, 100, 100, 150)),
        ])
        res = detect_tables(page)
        assert len(res) == 2

    def test_empty_page_with_lines_only(self):
        # 라인만 있고 실제 테이블은 없는 경우
        page = DummyPage(
            lines=[DummyLine(0, 0, 100, 0)],
            tables=[],
        )
        assert detect_tables(page) == []
```

> **주의:** `detect_tables()` 실제 시그니처/리턴 타입에 맞춰 `DummyTable` 속성 조정. 현재 리턴이 `list[dict]`인지 `list[Table]`인지 확인 후 assertion 구체화.

---

## E. `test_section_splitter.py` 확장 (6개 테스트)

```python
import pytest
from parsers.section_splitter import parse_section_markers, parse_page_markers


class TestParseSectionMarkers:
    def test_single_marker(self):
        text = "<!-- SECTION: S-1 | 일반사항 | 부문:건축 | 장:제1장 -->"
        m = parse_section_markers(text)
        assert len(m) == 1
        assert m[0]["section_id"] == "S-1"
        assert m[0]["title"] == "일반사항"

    def test_multiple_markers(self):
        text = (
            "<!-- SECTION: S-1 | 일반사항 | 부문:건축 | 장:제1장 -->\n"
            "본문\n"
            "<!-- SECTION: S-2 | 내역서 | 부문:토목 | 장:제2장 -->\n"
        )
        m = parse_section_markers(text)
        assert len(m) == 2
        assert m[1]["section_id"] == "S-2"

    def test_no_marker_returns_empty(self):
        assert parse_section_markers("일반 텍스트만") == []

    def test_malformed_marker_ignored(self):
        # 파이프 구분자 부족 → 무시되어야 함
        text = "<!-- SECTION: S-X -->"
        m = parse_section_markers(text)
        # 최소한 크래시 없이 빈 리스트 또는 부분 파싱
        assert isinstance(m, list)


class TestParsePageMarkers:
    def test_single_page(self):
        text = "<!-- PAGE 10 -->"
        m = parse_page_markers(text)
        assert len(m) == 1
        assert m[0]["page"] == 10

    def test_multiple_pages(self):
        text = "<!-- PAGE 1 -->\nA\n<!-- PAGE 2 -->\nB\n<!-- PAGE 3 -->"
        m = parse_page_markers(text)
        assert [x["page"] for x in m] == [1, 2, 3]
```

---

## F. `test_document_parser.py` 확장 (4개 테스트)

```python
import pytest
from pathlib import Path
from parsers.document_parser import parse_markdown


FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "sample_markdowns"


class TestParseMarkdown:
    def test_empty_returns_empty_list(self):
        res = parse_markdown("")
        assert isinstance(res, list)
        assert res == []

    def test_returns_list_for_valid_input(self):
        md = "# 제목\n\n본문 내용입니다." * 20  # 길이 충족
        res = parse_markdown(md)
        assert isinstance(res, list)

    def test_with_simple_estimate_fixture(self):
        path = FIXTURES / "simple_estimate.md"
        if not path.exists():
            pytest.skip("fixture not yet populated")
        content = path.read_text(encoding="utf-8")
        res = parse_markdown(content)
        assert isinstance(res, list)
        # 목차/제편/제장 분기가 최소 하나는 잡혀야 함
        assert len(res) > 0

    def test_short_input_no_crash(self):
        # 너무 짧은 입력도 크래시 없이 리스트 반환
        for s in ["a", "짧음", "# H"]:
            res = parse_markdown(s)
            assert isinstance(res, list)
```

---

## G. `test_toc_parser.py` 확장 (4개 테스트)

```python
import pytest
from extractors.toc_parser import _normalize_section_name


class TestNormalizeSectionName:
    def test_basic(self):
        assert _normalize_section_name("제1편   토목공사") == _normalize_section_name("제1편 토목공사")

    def test_preserves_korean(self):
        res = _normalize_section_name("제2장 구조물")
        assert "제2장" in res
        assert "구조물" in res

    def test_strips_extra_whitespace(self):
        res = _normalize_section_name("  제3편   건축   ")
        assert res.strip() == res  # 앞뒤 공백 없음
        assert "  " not in res     # 중복 공백 없음

    def test_empty_input(self):
        assert _normalize_section_name("") == ""
```

---

## H. P2 smoke test 3개 확장 샘플

### H.1 `test_markers.py` (4개 테스트)

```python
import pytest
from utils.markers import build_page_marker


class TestBuildPageMarker:
    def test_basic(self):
        ctx = {"division": "제1편", "chapter": "제1장"}
        marker = build_page_marker(10, ctx)
        assert "PAGE 10" in marker
        assert "제1장" in marker

    def test_empty_context(self):
        marker = build_page_marker(1, {})
        assert "PAGE 1" in marker

    def test_high_page_number(self):
        marker = build_page_marker(999, {"division": "D", "chapter": "C"})
        assert "999" in marker

    def test_division_included(self):
        marker = build_page_marker(5, {"division": "제2편", "chapter": "제3장"})
        assert "제2편" in marker or "제3장" in marker
```

### H.2 `test_text_formatter.py` — 실제 export 함수 대상 3~4개 테스트

### H.3 `test_usage_tracker.py` — 토큰/비용 누적 로직 3~4개 테스트

---

## I. 커버리지 측정 명확화

### I.1 실행 명령
```bash
cd ps-docparser
pytest tests/unit --cov --cov-report=term-missing --cov-report=html
```

### I.2 보고서에 명시할 항목
- **Statement coverage**: XX.X%
- **Branch coverage**: YY.Y%
- **모듈별 Top 5 미커버 파일**: (e.g., `parsers/document_parser.py 8%`, `extractors/hybrid_extractor.py 3%`)
- **htmlcov/index.html** 위치 공유 (로컬)

---

## 📊 구현 완료 시 예상 효과

| 항목 | 현재 | 구현 후 기대 |
|------|------|-----------|
| `test_bom_extractor.py` | 14줄, 1개 함수 | **75줄, 7개 함수** |
| `bom_extractor.py` 커버리지 | ~5% | **~35%** |
| Fixtures 유효성 | placeholder | **실파싱 가능 샘플** |
| smoke test 비율 | 46% (6/13) | **<20%** |
| 전체 커버리지 | 15.0% | **22~25% 추정** |
| Phase 8 진입 안정성 | 🔴 위험 | 🟢 안전망 확보 |

---

## 🚦 작업 우선순위 권장

1. **Day 1**: A (bom_extractor) + B·C (fixtures) → Phase 8 최소 안전망
2. **Day 2**: D·E·F·G (4개 테스트 확장) → 파서 분기 커버
3. **Day 3**: H (P2 3개) + I (커버리지 재측정 & 보고서) → 정리 및 문서화

**1~2일 투자**로 현재 75~80% 진행 상태를 **90~95%** 까지 끌어올릴 수 있습니다.

---

**가이드 작성자:** Claude Opus 4
**가이드 작성일:** 2026-04-17
**참조 문서:**
- `Phase7_상세_구현_기술서.md` §2~§3 (원본 테스트 케이스 요구)
- `ps-docparser/extractors/bom_extractor.py` (상태머신 구조)
- `ps-docparser/tests/conftest.py` (픽스처 연결 지점)
