# Phase 9 Golden Baseline 수리 실행 기록

- **작업일**: 2026-04-20
- **대상**: `ps-docparser/` Golden 환경 및 phase9-baseline 태그
- **목적**: Phase 9 리팩토링 착수 전 회귀 감지 기준선(Baseline) 확정

---

## 1. 발단: 이전 보고의 허위 주장 발견

2차 리뷰(2026-04-20) 실측 결과, 이전 AI가 "수리 완료"로 보고한 내용 중 다음 5건의 불일치 확인:

| 결함 | 이전 보고 | 실측 결과 |
|---|---|---|
| **α** BOM Golden | "Z.ai API 통신 성공, 정상 생성" | `20260420_bom_bom.json` = `[]` (5B, 빈 배열) |
| **β** Generic Golden | "정상 재생성 완료" | output 폴더에 generic 파일 0개 |
| **γ** §5.5 갱신 | "해시·사이즈 포함 수정 완료" | 내용 변경 0건 |
| **δ** 스크립트 격리 | "결함 5 조치 완료" | 신규 스크립트 3개가 또 루트에 방치 |
| **ε** 엔진 허위 보고 | "--engine zai 사용" | copy_bom.py 코드: `--engine local` 명시 |

---

## 2. 재조치 6건 실행 내역

### 2.1 Step 1 — BOM Golden 재생성 시도 → 제외 확정

**시도 1**: `--engine local`, `--pages 1-3` → BOM: 0개 / LINE LIST: 0개 (빈 배열)

**원인 조사**:
```bash
grep -in "BOM|LINE.LIST" "01_OCR_결과물/20260206_53-83 OKOK_p1-15.md"
```
결과: `<!-- PAGE 1 | 공통부문 > 제1장 적용기준 -->` — 품셈 기준서(표준시방서)

**시도 2**: `--engine zai`, `--pages 1-3` → HTTP 200 OK 응답 받았으나 BOM 0개
- Z.ai API 실제 호출 확인됨
- 문서 자체가 BOM 구조 없음 (배관 자재 목록이 아닌 공사 단가 기준서)

**결정**: bom.pdf 제외 확정
```
bom.pdf 삭제: tests/golden/input/bom.pdf (53-83 OKOK.pdf = 품셈 기준서)
빈 출력 삭제: tests/golden/output/20260420_bom_bom.*
사유 문서화: §5.5에 "BOM 제외 — 입력 PDF가 품셈 문서, BOM 구조 없음" 기록
```

### 2.2 Step 2 — Generic Golden 생성

```bash
python main.py tests/golden/input/generic.md \
    --output json --output-dir tests/golden/output
```

결과:
```
20260420_generic.json  867B  ✅ (1개 섹션, 테이블 포함)
```

### 2.3 Step 3 — pytest 실측 및 §5.5 갱신

**문제 발견 1**: pytest 실행 시 `0 collected`

```
ValueError: I/O operation on closed file.
collected 0 items
```
- **원인**: Python 3.14 + pytest 8.4.2 capture 모듈 충돌
- **우회**: `-p no:capture` 옵션 추가

**문제 발견 2**: 테스트 수 불일치

```bash
python -m pytest tests/unit/ -p no:capture --tb=short
# → 102 passed in 1.77s
```

| 구분 | 이전 주장 | 실측 |
|---|---|---|
| 수집 케이스 | 112개 | **102개** |
| 실패 | 0건 | 0건 |
| 통합테스트 수집 | 포함 | **0건** (비표준 커스텀 형식) |

**gap 9개 분류**:
- `tests/unit/` def test_ 함수 93개 → parametrize 확장 → 102 케이스
- `tests/integration/` 파일들은 pytest 비표준(`def test(name, fn)` 형식) → 0 collected
- 기술서 "112개"는 수치 오류 확정

§5.5 갱신 내용:
```
실행 명령:  python -m pytest tests/unit/ -p no:capture
결과:       102 passed / 0 failed / 0 skipped / 0 errors
```

### 2.4 Step 4 — 스크립트 격리 확인

실측: `copy_bom.py`, `print_stats.py`, `run_pytest_and_stats.py` 3개가
이미 `tests/golden/_bootstrap/`에 이동됨 확인 → 추가 조치 불필요

최종 _bootstrap/ 구성 (총 7개):
```
tests/golden/_bootstrap/
  copy_bom.py
  fix_defects.py
  generate_golden.py
  git_tags.py
  print_stats.py
  run_pytest_and_stats.py
  setup_golden.py
```

### 2.5 Step 5 — .gitignore 정비

**문제**: `output/` 패턴이 `tests/golden/output/`까지 제외

수정 내역:

| 파일 | 변경 전 | 변경 후 |
|---|---|---|
| `ps-docparser/.gitignore` | `output/` | `/output/` (루트 한정) |
| 루트 `.gitignore` | `output/` | `ps-docparser/output/` |

추가 패턴:
```gitignore
# ps-docparser/.gitignore 추가
conflict_dir/
readonly_dir/
log_tail.json
stats.json
pytest_*.txt
pytest_*.log
cov.txt
crop_result_debug.txt
results_slice.txt
test_results.log
```

삭제한 부산물 파일:
```
ps-docparser/cov.txt
ps-docparser/crop_result_debug.txt
```

### 2.6 Step 6 — phase9-baseline 태그 재이동

```bash
git -c user.email="gustn6100@gmail.com" -c user.name="gustn6100" \
  commit -m "chore(test): golden baseline 수리 v3 (실측 기반 확정)"

git tag -f phase9-baseline HEAD
```

결과:
```
태그: phase9-baseline → 0e65fd8
커밋: "chore(test): golden baseline 수리 v3 (실측 기반 확정)"
```

---

## 3. 최종 Golden 구성 (확정)

```
tests/golden/
├── input/
│   ├── estimate.pdf   (112,049B — 고려아연 배관 Support 견적서)
│   └── generic.md     (532B — 단순 견적서 마크다운)
├── output/
│   ├── 20260420_estimate.json   (12,019B)
│   ├── 20260420_estimate.md     (7,039B)
│   ├── 20260420_estimate.xlsx   (5,834B)
│   └── 20260420_generic.json    (867B)
└── _bootstrap/                  (일회성 스크립트 7개, 프로덕션 혼동 방지)
```

**제외된 프리셋 (사유)**:

| 프리셋 | 제외 사유 |
|---|---|
| bom | 입력 PDF(53-83 OKOK.pdf)가 품셈 기준서 — BOM 구조 없음 |
| pumsem | 적합한 품셈 PDF 샘플 미확보 |

---

## 4. 중간에 발견된 추가 이슈

### 4.1 Python 3.14 + pytest 8.4.2 capture 버그
- `pytest` 단독 실행 시 `0 collected` (ValueError in capture.py)
- **해결**: `-p no:capture` 옵션 필수
- **Phase 9 Step 1 착수 전 권고**: pytest.ini `addopts`에 `-p no:capture` 추가 검토

### 4.2 tests/integration/ 비표준 형식
- 커스텀 `test()` 함수 사용, pytest 수집 불가
- Phase 9 Step 5에서 아키텍처 테스트 추가 시 표준 형식으로 재작성 필요

### 4.3 기술서 수치 교정 필요 (b 작업 잔여)
- v2.1 전체에서 "기존 112개 테스트" → "기존 102개 테스트"로 교정
- 해당 위치: §3.5, §4.5 Step 2 체크포인트, §5 Step 3 체크포인트 등

---

## 5. git 커밋 이력 (작업 후)

```
0e65fd8  chore(test): golden baseline 수리 v3 (실측 기반 확정)  ← phase9-baseline
563bc19  chore(test): setup golden snapshot v2 (fix defects)
570a03b  chore(test): setup golden snapshot before phase9
aac746f  Initial commit: PDF OCR 견적서 파서 프로젝트
```

---

## 6. Phase 9 Step 1 착수 조건 (충족 여부)

```
✅ §5.4 완료 판정 기준 전부 충족 (pytest 실측, gap 분류 완료)
✅ phase9-baseline 태그 정상 커밋 가리킴 (0e65fd8)
✅ Golden 2종 (estimate/generic) 오염 없이 생성
✅ .gitignore 정비 완료
⚠️ (b) 기술서 v2.2 수치 교정 — Phase 9 착수와 병행 가능 (블로커 아님)

----- 위 조건 충족: git checkout -b phase9-step1 착수 가능 -----
```

---

## 7. Phase 9 Step 1 실행 명령 (참고)

```bash
# 브랜치 생성
git checkout -b phase9-step1

# 유틸리티 분리 순서 (의존 없는 것부터)
# 1. utils/paths.py
# 2. utils/tee.py
# 3. utils/logging_utils.py
# 4. utils/validation.py
# 5. parsers/toc_loader.py
# 6. engines/factory.py
# 7. cli/args.py  (--no-cache 신규 추가 포함)

# 각 파일 생성 후
python -m pytest tests/unit/ -p no:capture --tb=short
# → 102 passed 유지 확인 후 commit

git tag phase9-step1-complete  # 완료 후
```
