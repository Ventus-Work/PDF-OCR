# Phase 9 기술서 v2 → v2.1 리뷰 검증 보고서

**작성일:** 2026-04-17
**작성자:** Claude Opus 4
**검증 대상:** 사용자 제공 "Phase9 기술서 v2 리뷰" (이슈 3건 + 제안 1건)
**검증 방법:** `ps-docparser/main.py` 실제 코드와 리뷰 주장 직접 대조
**결과:** **리뷰 100% 타당** → Phase9_상세_구현_기술서.md v2.1로 전면 반영

---

## 1. 리뷰 개요

사용자 리뷰 요약:
- ✅ **잘 된 점 4건** — v2에서 도입한 5-Step 체크포인트, 이식 매핑 테이블, E2E Golden File, 결정 트리
- ⚠️ **수정 필요 3건** — 엔진 제약 미명시(🔴), `--no-cache` 불일치(🟡), bom_aggregator 귀속 미결(🟡)
- 💡 **추가 제안 1건** — `_build_argument_parser()` 분리 필수화

---

## 2. 리뷰 정확성 검증 (실측 대조)

### 2.1 이슈 1: DocumentPipeline 엔진 제약 🔴

**리뷰 주장:**
> `create_engine()`은 zai/mistral/tesseract도 생성하는데, DocumentPipeline은 이들을 허용하면 안 됩니다. `_validate_engine(engine)` 메서드로 이 제약을 명시해야 합니다.

**실측 (`ps-docparser/main.py:434~448`):**
```python
elif engine_name in ("gemini",):          # ← gemini만 허용
    from engines.gemini_engine import GeminiEngine
    engine = GeminiEngine(api_key=GEMINI_API_KEY, model=GEMINI_MODEL, tracker=tracker)
    print(f"  엔진: GeminiEngine (모델: {GEMINI_MODEL})")
elif engine_name == "local":              # ← local 허용
    from engines.local_engine import LocalEngine
    engine = LocalEngine()
    print("  엔진: LocalEngine (API 없음, Poppler 불필요)")
else:
    raise ParserError(f"표준 파이프라인에서 지원하지 않는 엔진: {engine_name}. "
                      f"BOM 전용 엔진은 --preset bom과 함께 사용하세요.")
```

**판정: ✅ 리뷰 정확.**
- 표준 파이프라인은 `gemini`/`local`만 허용
- `zai`/`mistral`/`tesseract` 투입 시 `ParserError` 명시
- 이 제약이 기술서 v2 §4.4 `DocumentPipeline.run()` 코드에 누락되어 있었음

---

### 2.2 이슈 2: `--no-cache` argparse 불일치 🟡

**리뷰 주장:**
> 현재 `_build_argument_parser()`에 `--no-cache` 옵션이 없습니다. `--force` 옵션만 있음. 이 옵션을 추가하려면 Step 1 또는 Step 4 진입 전에 parser 수정이 필요합니다.

**실측:**
- `grep -n "no_cache\|--no-cache" main.py` → **결과 0건**
- `main.py:169` 유일한 관련 옵션:
  ```python
  parser.add_argument(
      "--force",
      action="store_true",
      help="설정 오류가 있어도 강제로 실행 (Phase 6)",
  )
  ```

**판정: ✅ 리뷰 정확.**
- 기술서 v2 §6.4 예제 코드 `cache = None if args.no_cache else TableCache()`가 존재하지 않는 속성을 참조
- Step 1 단계에서 `cli/args.py` 분리 시 `--no-cache` 신규 추가 필수

---

### 2.3 이슈 3: BomPipeline에서 bom_aggregator 로직 누락 🟡

**리뷰 주장:**
> `main.py:703~741`: 배치 BOM 완료 시 집계 Excel 자동 생성 로직이 있습니다. 기술서 §4.3 BomPipeline에 이 집계 로직 이식 여부가 언급되지 않았습니다.

**실측 (`ps-docparser/main.py:703~741`):**
```python
# ── Phase 5 단위 4: 배치 BOM 집계 xlsx 자동 생성 ──
if args.preset == "bom" and args.output_format == "excel" and succeeded:
    print()
    print("── BOM 배치 집계 ──")
    try:
        from exporters.bom_aggregator import export_aggregated_excel
        from datetime import datetime as _dt

        date_str = _dt.now().strftime("%Y%m%d")
        json_files: list[Path] = []
        for pdf_name in succeeded:
            stem = Path(pdf_name).stem
            candidates = list(out_dir.glob(f"*_{stem}_bom.json"))
            if candidates:
                json_files.append(sorted(candidates)[-1])

        if json_files:
            agg_path = out_dir / f"{date_str}_BOM집계.xlsx"
            # ... (중복 방지 + export_aggregated_excel 호출)
            result = export_aggregated_excel(json_files, agg_path)
```

**판정: ✅ 리뷰 정확.**
- 배치 루프 **바깥**에서 실행되는 후처리 로직 (파이프라인 1회 호출 범위 초과)
- `BomPipeline`은 단일 PDF 처리만 책임져야 → 집계는 main.py 또는 `cli/batch_runner.py`에 귀속

**v2.1 결정 논리:**
| 로직 | 원본 | 귀속 | 이유 |
|-----|-----|------|-----|
| 단일 PDF BOM OCR → 구조화 → 개별 JSON/Excel | L348~480 | `pipelines/bom_pipeline.py` | 단일 책임 |
| N개 성공 JSON → 1개 집계 Excel | L703~741 | **main.py 잔존 / cli/batch_runner.py 이전 가능** | 배치 오케스트레이션 |
| `export_aggregated_excel()` 함수 자체 | `exporters/bom_aggregator.py` | **변경 없음** | 이미 잘 분리됨 |

---

### 2.4 제안: `_build_argument_parser()` 분리 필수화 💡

**리뷰 주장:**
> `_build_argument_parser()` 현재 82줄이므로 분리하는 것이 350줄 마진에 필수입니다. 선택이 아닌 필수로 격상 권장합니다.

**실측 (`ps-docparser/main.py:92~173`):**
- `def _build_argument_parser()` 시작: L92
- `return parser` 종료: L173
- **라인 수 = 173 - 92 + 1 = 82줄** (리뷰 숫자 정확)

**판정: ✅ 리뷰 정확.**

**필수화 근거:**
- Step 4 목표: `main.py 792줄 → ≤350줄`
- 잔존 요구 로직: `main()` 진입부 + 배치 루프 + BOM 집계 후처리 + 2~3개 헬퍼
- `_build_argument_parser` 82줄을 잔존시키면 실질 가용 마진 = 350 - 82 - (기타) ≈ 200줄
- 200줄로는 배치 루프(L640~741 ≈ 100줄) + 진입 헬퍼 수용 불가
- **결론: 분리 없이는 350줄 달성 불가능** → 선택 아닌 **필수**

---

## 3. v2 → v2.1 반영 내역

### 3.1 수정된 섹션

| 섹션 | v2 상태 | v2.1 반영 |
|-----|-------|---------|
| §0 개정 이력 | v1→v2 표만 | **v2→v2.1 표 추가** (이슈 4건 매핑) |
| §2 5-Step 요약 테이블 | 6+5+1+0+6 파일 | **7**+5+1+0+6 (`cli/args.py` 추가) |
| §3.1 Step 1 산출물 | 6개 파일 | **7개** (1.7 `cli/args.py` 신설) |
| §3.1.1 `cli/args.py` 설계 | 없음 | **신설** — `--no-cache` 신규 옵션 명시 |
| §3.5 Step 1 테스트 | 20개 | **23개** (`test_args.py` 3개 추가) |
| §3.5 Step 1 체크포인트 | 6개 항목 | **8개** (cli/args.py 복사·신규 플래그 검증) |
| §4.3 BomPipeline 책임 | 단순 "L348~480 이식" | **책임 범위 표 + 집계 분리 예제 코드** 추가 |
| §4.4 DocumentPipeline | `create_engine` 직접 호출 | **`_validate_engine()` + `ALLOWED_ENGINES` 화이트리스트** 추가 |
| §4.4 BomPipeline 대칭 | 없음 | `ALLOWED_ENGINES = {zai, mistral, tesseract, local}` 명시 |
| §4.5 Step 2 테스트 | 8개 | **10개** (`_validate_engine`, BomPipeline 대칭 각 +1) |
| §4.5 Step 2 체크포인트 | 기존 132개 | **기존 135개(112+23)** |
| §5 Step 3 체크포인트 | 기존 140개 | **기존 145개(112+23+10)** |
| §6 Step 4 체크포인트 | 기존 140개 | **기존 145개** |
| §6.3 이식 매핑 테이블 | 7행 | **9행** (L92~173 cli/args, L434~448 validate, L703~741 aggregator) |
| §6.4 main.py 최종 구조 | `cli.args` import "선택" | **"v2.1: 필수 분리"** 주석 |

### 3.2 신규 테스트 케이스 (5개)

```
tests/unit/cli/test_args.py
  ├─ test_build_parser_all_options_present          (기존 옵션 완전 복사 검증)
  ├─ test_no_cache_flag_default_false                (미전달 시 False)
  └─ test_no_cache_flag_enabled_when_passed          (--no-cache 시 True)

tests/unit/pipelines/test_document_pipeline.py
  └─ test_validate_engine_rejects_zai_mistral_tesseract   (v2.1 이슈 1)

tests/unit/pipelines/test_factory.py
  └─ test_bom_pipeline_rejects_gemini_engine              (v2.1 대칭 원칙)
```

### 3.3 수치 최종 정리

| 구분 | v2 | v2.1 |
|-----|-----|------|
| 기술서 줄 수 | 825줄 | **889줄** (+64) |
| Step 1 신규 파일 | 6개 | **7개** |
| Step 1 테스트 | 20개 | **23개** |
| Step 2 테스트 | 8개 | **10개** |
| Step 3 누적 테스트 | 140개 | **145개** |
| Step 5 목표 테스트 | 180+ | **185+** |

---

## 4. 종합 평가

| 항목 | 등급 | 코멘트 |
|------|------|-------|
| 리뷰 주장 정확성 | **A+** | 3건 모두 실측 코드와 라인 번호까지 일치 |
| 리뷰 우선순위 판단 | **A+** | 이슈 1은 🔴(보안·회귀), 2~3은 🟡(기능 누락) — 타당 |
| 수정 제안 구체성 | **A** | `_validate_engine()` 메서드명까지 제시 |
| 추가 제안 근거 | **A+** | 82줄 수치 + 350줄 마진 계산 정확 |

**결론:**
리뷰는 **실측 기반의 즉시 반영 가능한 품질** 수준이었고, v2.1 반영으로 기술서의 다음 두 가지 심각한 리스크를 제거함:
1. 🔴 **잘못된 엔진-파이프라인 조합이 런타임까지 살아남는 보안·회귀 구멍** (이슈 1)
2. 🟡 **Step 4 구현 시점에 존재하지 않는 argparse 속성 참조로 인한 즉시 실패** (이슈 2)

---

## 5. 후속 조치

### 🟢 Phase 9 실행 전 (선행 필수)

1. ✅ **v2.1 기술서 확정** — 완료 (2026-04-17)
2. [ ] `tests/golden/input/` 에 샘플 PDF 4종 수집 (estimate / bom / pumsem / generic)
3. [ ] 현재 Phase 8 상태로 Golden File 생성 (§6.2 명령 실행)
4. [ ] `git tag phase9-baseline` — Phase 8 종단 태그 확보

### 🟢 Phase 9 Step 1 착수 시

5. [ ] Step 1 착수 전 `git checkout -b phase9-step1`
6. [ ] 6개 유틸 + `cli/args.py` 순서대로 추출 (의존 없는 순: paths → tee → logging → validation → toc_loader → factory → args)
7. [ ] 각 파일 생성 직후 해당 테스트 작성 → pytest 통과 확인 → commit
8. [ ] 전 파일 완료 후 `git tag phase9-step1-complete`

---

## 6. 관련 문서

- `Phase9_상세_구현_기술서.md` (v2.1, 889줄) — 본문서의 반영 대상
- `Phase8_결과보고서_검증리뷰.md` — Phase 8 종단 상태 검증
- `ps-docparser/main.py` (792줄) — 리팩터링 대상 원본

---

**검증 환경:**
- 작업 디렉터리: `G:\My Drive\...\ps-docparser\`
- 검증 시각: 2026-04-17
- 검증한 파일: `main.py` L92~173 (parser), L434~448 (engine 제약), L703~741 (bom 집계)

**검증자:** Claude Opus 4
