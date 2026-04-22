# Phase 12.5 Excel 렌더링 커버리지 확대 상세 구현 기술서

- **작성일**: 2026-04-22
- **작성자**: Claude Opus 4.7
- **대상 브랜치 기준**: `main` (f052ae8, Phase 10+11 완료, 552 passed, coverage 71.82%)
- **선행 조건**: Phase 12 Step 12-2 (`excel_builders.py` 분리) 완료 필수
- **후속 대상 브랜치**: `phase12.5`
- **선행 태그**: `phase12-complete`
- **목표 태그**: `phase12.5-complete`
- **상위 계획서**: `모드별_파이프라인_분석_및_Excel_확장_계획서_20260422.md`

---

## 0. 문서 목적

상위 계획서가 진단한 **Problem B** — "Document 모드 JSON에는 본문·주석·조건·교차참조·메타가 풍부하게 담겨 있으나, Excel 렌더러가 `tables` 키만 소비하여 Excel에서 해당 필드가 누락되는 문제" — 를 해결하는 구현 계획을 기록한다.

본 기술서는 다음을 명시한다:
- 현재 Excel 렌더링 커버리지의 **정량 실측**
- 신규 시트 5종의 **컬럼 레이아웃·스타일·Empty Guard**
- **BOM 모드 회귀 방지** 전략 (신규 시트 자동 미생성)
- Step별 체크포인트와 롤백 단위
- Mock/픽스처 설계 원칙 (Phase 10 테스트 100% 재사용)

---

## 1. 현재 상태 실측 (2026-04-22 기준)

### 1.1 기존 Excel 시트 (4종)

| 시트 | 빌더 함수 | 트리거 조건 | 데이터 소스 |
|---|---|---|---|
| 견적서 | `_build_estimate_sheet()` | 헤더에 "명 칭"+"금 액" | `section.tables[*]` |
| 내역서 | `_build_detail_sheet()` | 헤더에 "품명"+"합계_금액" | `section.tables[*]` |
| 조건 | `_build_condition_sheet()` | 헤더에 "일반사항" or "특기사항" | `section.tables[*]` |
| Table_N | `_build_generic_sheet()` | 위 3종에 해당하지 않는 표 | `section.tables[*]` |

**공통점**: 모두 `section.tables[*]` 만 소비. `clean_text`, `notes`, `conditions`, `cross_references`, `revision_year`, `unit_basis` 필드는 무시된다.

### 1.2 JSON에는 있으나 Excel에 없는 필드

| JSON 필드 | 생성 위치 | 데이터 타입 | 예시 (pumsem) |
|---|---|---|---|
| `clean_text` | `process_section_text()` L322 | str (본문 전체) | "1-1-1 일반사항\n본 품셈은..." |
| `notes` | `extract_notes()` | list[str] | ["본 품셈은 ~ 기준이다", "... 표 참조"] |
| `conditions` | `extract_conditions()` | list[dict] | `[{"type":"가산","condition":"야간작업 시","rate":"25%"}]` |
| `cross_references` | `extract_cross_references()` | list[dict] | `[{"target_section_id":"2-1-3","target_chapter":"제2장","context":"... 제2장 2-1-3 준용"}]` |
| `revision_year` | `process_section_text()` L300 | str ("" or "2024") | "2024" |
| `unit_basis` | `process_section_text()` L308 | str ("" or "m³당") | "m³당" |

### 1.3 사용자 영향

- **pumsem 프리셋**: 본문·주석·가감산·교차참조·보완연도·단위 기준 6종 필드 사용자 수동 재작업
- **estimate 프리셋**: 표지 메타 외 본문이 Excel에 없음
- **범용 (preset=None)**: 전체 문서의 본문이 첫 줄만 Excel 문서 제목으로 사용

---

## 2. Phase 12.5 목표

### 2.1 정량 목표

| 지표 | 현재 | 목표 |
|---|---|---|
| Excel 시트 종류 | 4 | **≥ 9** (+5 신규) |
| JSON→Excel 렌더 필드 수 | 1 (tables) | **7** (+clean_text, notes, conditions, cross_references, revision_year, unit_basis) |
| pytest 수집 케이스 | 552 | **≥ 567** (+15 신규 테스트) |
| 전체 회귀 실패 | 0 | **0 유지** |
| 커버리지 | 71.82% | **≥ 70% 유지** |
| Golden E2E | MATCH | **MATCH 유지** (기존 시트 불변) |
| BOM 모드 출력 | 기존 | **100% 불변** (신규 시트 자동 미생성) |

### 2.2 정성 목표

- 신규 시트 5종은 **JSON 필드가 비어 있을 때 자동 생략** (Empty Guard)
- 기존 4개 시트 빌더는 **0 수정** (회귀 방지)
- `BomPipeline` 출력 Excel은 **바이트 단위 동일** (BOM 모드는 해당 필드가 모두 `[]` / `""` / `None`)
- Phase 12 Step 12-2 산출물 `excel_builders.py`에 **함수 5개 추가만으로 완료**

---

## 3. 범위 (Scope / Non-Scope)

### 3.1 Scope

- `exporters/excel_builders.py`에 시트 빌더 5종 추가
- `exporters/excel_exporter.py` (`_export_impl()`)에 시트 생성 분기 5건 추가
- `exporters/excel_styles.py`에 공통 컬럼 폭 유틸 1건 추가 (선택, 중복 제거용)
- `tests/unit/exporters/test_excel_builders.py` 신규 테스트 15건
- `tests/unit/exporters/test_excel_exporter.py` 통합 테스트 2건 (pumsem 샘플 + BOM 샘플 회귀)
- 시트 순서 결정 (견적서 → 내역서 → 조건 → **본문 → 주석 → 가감산_조건 → 교차참조 → 메타** → Table_N)

### 3.2 Non-Scope

| 항목 | 사유 |
|---|---|
| JSON 스키마 변경 | 기존 필드만 사용. 신규 필드 추가 없음 |
| `parse_markdown()` / `process_section_text()` 수정 | JSON 데이터는 이미 충분 |
| BOM 파이프라인 수정 | Problem A는 Phase 14로 분리 |
| 도면 메타데이터 추출 (DWG/REV/TITLE) | Problem A — Phase 14 |
| 기존 시트(견적서/내역서/조건/Table_N) 로직 수정 | 회귀 방지 — 0 수정 |
| Excel 스타일 테마 변경 | 기존 `_FILL_*` / `_FONT_*` 상수 재사용 |
| 시트명 국제화 (영문 옵션) | Non-Scope. 한국어 고정 |

---

## 4. 아키텍처 결정

### 4.1 신규 시트 vs 기존 시트 확장

- **결정**: **신규 시트**로 분리 (기존 시트 확장하지 않음)
- **이유**:
  - 기존 "조건" 시트는 `headers`에 "일반사항/특기사항"이 있는 **표 렌더링**이고, JSON `conditions[]`는 regex로 추출한 **구조화 dict** (완전히 다른 데이터)
  - 기존 견적서/내역서는 표 행 순서가 원본 레이아웃을 반영 — 본문·주석을 끼워 넣으면 표의 의미가 훼손됨
  - 신규 데이터는 **통합 관점**(모든 섹션의 notes를 한 시트에) 이 유용 → 섹션별 분산보다 시트별 통합이 사용성 높음

### 4.2 시트 순서

```
[1] 견적서           ← 기존, 요약 (가장 중요)
[2] 내역서           ← 기존, 상세
[3] 조건             ← 기존, 일반사항/특기사항 테이블
[4] 본문             ← 신규, clean_text 통합 (섹션별 행)
[5] 주석             ← 신규, notes 통합
[6] 가감산_조건      ← 신규, conditions[] 통합
[7] 교차참조         ← 신규, cross_references[] 통합
[8] 메타데이터       ← 신규, revision_year/unit_basis 통합
[9] Table_N          ← 기존, generic 테이블 (마지막)
```

**근거**: 구조화된 핵심 데이터(견적서/내역서/조건) → 구조화된 보조 데이터(본문/주석) → 구조화된 참조 데이터(조건/참조/메타) → 분류 불가(Table_N) 순.

### 4.3 Empty Guard 원칙

각 신규 빌더는 `sections` 전체에서 해당 필드가 **하나라도 비어있지 않을 때만** 시트 생성. 조건 함수:

```python
def _any_section_has_text(sections):
    return any(s.get("clean_text", "").strip() for s in sections)

def _any_section_has_notes(sections):
    return any(s.get("notes") for s in sections)

def _any_section_has_conditions(sections):
    return any(s.get("conditions") for s in sections)

def _any_section_has_crossrefs(sections):
    return any(s.get("cross_references") for s in sections)

def _any_section_has_meta(sections):
    return any(s.get("revision_year") or s.get("unit_basis") for s in sections)
```

### 4.4 BOM 모드 호환성

`extractors/bom_extractor.py:513-591` `to_sections()`가 BOM 섹션에 다음을 강제 설정:
```python
"clean_text": "",      # Empty Guard → 본문 시트 미생성
"notes": [],           # Empty Guard → 주석 시트 미생성
"conditions": [],      # Empty Guard → 가감산_조건 시트 미생성
"cross_references": [],# Empty Guard → 교차참조 시트 미생성
"revision_year": None, # Empty Guard → 메타 시트 미생성
"unit_basis": None,    # Empty Guard → 메타 시트 미생성
```

**결론**: BOM 모드는 신규 5개 시트 중 **0개가 자동 생성**된다. BOM Excel 출력 **바이트 단위 동일**.

### 4.5 공통 스타일 재사용

Phase 12 Step 12-2 산출물 `exporters/excel_styles.py`의 상수 100% 재사용:
- `_FILL_HEADER` — 헤더 배경 진남색
- `_FONT_HEADER` — 헤더 글자 흰색 bold
- `_FONT_BODY` — 본문 글자
- `_ALIGN_CENTER`, `_ALIGN_LEFT` — 정렬
- `_BORDER_ALL` — 테두리
- `_apply_style()` — 셀 스타일 적용 헬퍼

신규 스타일 상수 추가 **없음**.

---

## 5. Step 분할 개요

| Step | 빌더 | 예상 라인수 | 테스트 수 | 리스크 |
|---|---|---|---|---|
| 12.5-1 | `_build_text_sheet` (본문) | ~40 | 3 | 낮음 |
| 12.5-2 | `_build_notes_sheet` (주석) | ~30 | 3 | 낮음 |
| 12.5-3 | `_build_conditions_sheet` (가감산) | ~35 | 3 | 낮음 |
| 12.5-4 | `_build_crossref_sheet` (교차참조) | ~35 | 3 | 낮음 |
| 12.5-5 | `_build_meta_sheet` (메타) | ~45 | 3 | 낮음 |
| 12.5-6 | `_export_impl` 통합 + Empty Guard + 시트 순서 | ~50 (diff) | 5 (통합) | 중 |

**실행 순서**: 12.5-1~12.5-5는 **독립**하므로 임의 순서 가능. 12.5-6은 5개 빌더 완료 후 마지막에 실행.

---

## 6. Step 12.5-1 — 본문 시트 (`_build_text_sheet`)

### 6.1 함수 시그니처

```python
def _build_text_sheet(ws, sections: list[dict]) -> None:
    """섹션별 clean_text를 행 단위로 덤프."""
```

### 6.2 컬럼 레이아웃

| 열 | 헤더 | 데이터 소스 | 컬럼 폭 |
|---|---|---|---|
| A | 섹션 ID | `section["section_id"]` | 12 |
| B | 부문 | `section["department"]` | 14 |
| C | 장 | `section["chapter"]` | 20 |
| D | 제목 | `section["title"]` | 28 |
| E | 페이지 | `section["page"]` | 7 |
| F | 본문 | `section["clean_text"]` | 80 (wrap) |

### 6.3 스타일

- 행 1: 헤더 행 — `_FILL_HEADER`, `_FONT_HEADER`, `_ALIGN_CENTER`, `_BORDER_ALL`
- 행 2~: 본문 행 — `_FONT_BODY`, `_BORDER_ALL`
  - A~E열: `_ALIGN_CENTER`
  - F열(본문): `_ALIGN_LEFT` + `wrap_text=True`, `row_height=auto`

### 6.4 행 높이

본문이 길 때 자동 확장. `ws.row_dimensions[r].height = None` (기본 auto-fit) + F열 `wrap_text=True`.

### 6.5 Empty Guard

```python
rows_with_text = [s for s in sections if s.get("clean_text", "").strip()]
if not rows_with_text:
    return  # 시트 생성 자체를 스킵 (호출자에서 처리)
```

시트 미생성은 `_export_impl()`의 호출 분기에서 판단 (§11).

### 6.6 테스트 (`test_excel_builders.py::TestBuildTextSheet`)

| # | 테스트 | 검증 |
|---|---|---|
| T1 | `test_single_section_with_text` | 1개 섹션 + clean_text 있음 → 2행 (헤더+1) 생성 |
| T2 | `test_multi_section_header_order` | 다중 섹션 → 컬럼 순서 (ID/부문/장/제목/페이지/본문) |
| T3 | `test_long_text_wraps` | clean_text 500자 → F열 wrap_text=True 적용 |

---

## 7. Step 12.5-2 — 주석 시트 (`_build_notes_sheet`)

### 7.1 함수 시그니처

```python
def _build_notes_sheet(ws, sections: list[dict]) -> None:
    """모든 섹션의 notes를 평탄화하여 통합."""
```

### 7.2 컬럼 레이아웃

| 열 | 헤더 | 데이터 소스 | 컬럼 폭 |
|---|---|---|---|
| A | 섹션 ID | `section["section_id"]` | 12 |
| B | 섹션 제목 | `section["title"]` | 28 |
| C | 페이지 | `section["page"]` | 7 |
| D | 주석 번호 | enumerate (섹션 내 순번) | 8 |
| E | 주석 내용 | `note` (str) | 80 (wrap) |

### 7.3 데이터 평탄화

```python
for s in sections:
    for idx, note in enumerate(s.get("notes", []), start=1):
        append_row(s["section_id"], s["title"], s["page"], idx, note)
```

### 7.4 Empty Guard

`any(s.get("notes") for s in sections)` 이 False면 시트 미생성.

### 7.5 테스트

| # | 테스트 | 검증 |
|---|---|---|
| T1 | `test_single_note` | 1 섹션 1 주석 → 2행 |
| T2 | `test_multi_notes_flatten` | 섹션 A [2 notes], B [3 notes] → 6행 (헤더+5) |
| T3 | `test_note_number_per_section` | 섹션 내 주석 번호가 섹션별로 1부터 재시작 |

---

## 8. Step 12.5-3 — 가감산 조건 시트 (`_build_conditions_sheet`)

### 8.1 함수 시그니처

```python
def _build_conditions_sheet(ws, sections: list[dict]) -> None:
    """JSON conditions[]의 {type,condition,rate} dict를 표로 펼침."""
```

### 8.2 컬럼 레이아웃

| 열 | 헤더 | 데이터 소스 | 컬럼 폭 |
|---|---|---|---|
| A | 섹션 ID | `section["section_id"]` | 12 |
| B | 섹션 제목 | `section["title"]` | 28 |
| C | 페이지 | `section["page"]` | 7 |
| D | 유형 | `cond["type"]` (가산/감산/할증) | 10 |
| E | 조건 | `cond["condition"]` | 50 (wrap) |
| F | 비율 | `cond["rate"]` (예: "25%") | 10 |

### 8.3 유형별 셀 색상 (선택)

`_FILL_SECTION` 재사용 (연청색) — D열에 적용하여 유형 가독성 향상. 생략 시 기본 스타일.

### 8.4 Empty Guard

`any(s.get("conditions") for s in sections)` 이 False면 시트 미생성.

### 8.5 테스트

| # | 테스트 | 검증 |
|---|---|---|
| T1 | `test_single_condition` | 1 조건 dict → 2행 |
| T2 | `test_multiple_types` | "가산"/"감산"/"할증" 혼재 → 모두 렌더 |
| T3 | `test_rate_preserved` | rate 문자열이 원형 보존 ("25%" → "25%") |

---

## 9. Step 12.5-4 — 교차참조 시트 (`_build_crossref_sheet`)

### 9.1 함수 시그니처

```python
def _build_crossref_sheet(ws, sections: list[dict]) -> None:
    """JSON cross_references[]의 {target_section_id,target_chapter,context}를 표로."""
```

### 9.2 컬럼 레이아웃

| 열 | 헤더 | 데이터 소스 | 컬럼 폭 |
|---|---|---|---|
| A | 원본 섹션 ID | `section["section_id"]` | 12 |
| B | 원본 섹션 제목 | `section["title"]` | 28 |
| C | 페이지 | `section["page"]` | 7 |
| D | 대상 장 | `ref["target_chapter"]` | 14 |
| E | 대상 섹션 ID | `ref["target_section_id"]` | 14 |
| F | 참조 문맥 | `ref["context"]` | 60 (wrap) |

### 9.3 Empty Guard

`any(s.get("cross_references") for s in sections)` 이 False면 시트 미생성.

### 9.4 테스트

| # | 테스트 | 검증 |
|---|---|---|
| T1 | `test_single_crossref` | 1 참조 → 2행 |
| T2 | `test_target_chapter_empty` | `target_chapter=""` → D열 공백 렌더 |
| T3 | `test_multi_refs_per_section` | 1 섹션에 3 참조 → 4행 (헤더+3), 모두 동일 A~C |

---

## 10. Step 12.5-5 — 메타 시트 (`_build_meta_sheet`)

### 10.1 함수 시그니처

```python
def _build_meta_sheet(ws, sections: list[dict]) -> None:
    """섹션별 revision_year / unit_basis를 통합."""
```

### 10.2 컬럼 레이아웃

| 열 | 헤더 | 데이터 소스 | 컬럼 폭 |
|---|---|---|---|
| A | 섹션 ID | `section["section_id"]` | 12 |
| B | 섹션 제목 | `section["title"]` | 28 |
| C | 페이지 | `section["page"]` | 7 |
| D | 보완연도 | `section["revision_year"]` (str or "") | 10 |
| E | 단위 기준 | `section["unit_basis"]` (str or "") | 14 |

### 10.3 BOM 모드 호환 (None 처리)

`to_sections()`는 `revision_year=None`, `unit_basis=None`을 반환. Document 모드는 `""` 또는 값. 렌더 시:
```python
rev = s.get("revision_year") or ""  # None/"" 모두 "" 로 정규화
unit = s.get("unit_basis") or ""
```

### 10.4 Empty Guard

둘 중 **하나라도** 값이 있는 섹션이 존재할 때만 시트 생성:
```python
has_meta = any((s.get("revision_year") or s.get("unit_basis")) for s in sections)
```

### 10.5 필터 — 완전 공백 행 제외

`revision_year`·`unit_basis` 모두 비어있는 섹션은 행 추가 스킵 (노이즈 방지).

### 10.6 테스트

| # | 테스트 | 검증 |
|---|---|---|
| T1 | `test_revision_year_only` | unit_basis="" 섹션 → D열만 채워지고 행 렌더 |
| T2 | `test_unit_basis_only` | revision_year="" 섹션 → E열만 채워지고 행 렌더 |
| T3 | `test_both_empty_row_skipped` | 둘 다 비어있는 섹션은 행 추가 스킵 |

---

## 11. Step 12.5-6 — `_export_impl()` 통합

### 11.1 통합 위치

`exporters/excel_exporter.py` `_export_impl()` 기존 구조:
```python
# ── 견적서 시트 ──
if estimate_tables: ...
# ── 내역서 시트 ──
if detail_tables: ...
# ── 조건 시트 ──
if condition_tables: ...
# ── 범용 시트 ──
if generic_tables: ...
# ── 분류된 테이블이 하나도 없을 때 ──
```

**신규 분기 삽입 위치**: "조건 시트" 뒤, "범용 시트" 앞.

### 11.2 통합 코드

```python
# ── 본문 시트 (Phase 12.5) ──
if any(s.get("clean_text", "").strip() for s in sections):
    ws = wb.create_sheet("본문")
    ws.sheet_view.showGridLines = False
    _build_text_sheet(ws, sections)

# ── 주석 시트 ──
if any(s.get("notes") for s in sections):
    ws = wb.create_sheet("주석")
    ws.sheet_view.showGridLines = False
    _build_notes_sheet(ws, sections)

# ── 가감산 조건 시트 ──
if any(s.get("conditions") for s in sections):
    ws = wb.create_sheet("가감산_조건")
    ws.sheet_view.showGridLines = False
    _build_conditions_sheet(ws, sections)

# ── 교차참조 시트 ──
if any(s.get("cross_references") for s in sections):
    ws = wb.create_sheet("교차참조")
    ws.sheet_view.showGridLines = False
    _build_crossref_sheet(ws, sections)

# ── 메타 시트 ──
if any((s.get("revision_year") or s.get("unit_basis")) for s in sections):
    ws = wb.create_sheet("메타데이터")
    ws.sheet_view.showGridLines = False
    _build_meta_sheet(ws, sections)
```

### 11.3 시트명 충돌 방지

기존 시트명: `견적서`, `내역서`, `조건`, `Table_*`, `견적서_N`, `내역서_N`, `데이터`
신규 시트명: `본문`, `주석`, `가감산_조건`, `교차참조`, `메타데이터`

**충돌 없음**. Excel 시트명 31자 제한 → 모든 신규 이름 5자 이하, 문제 없음.

### 11.4 Empty 전체 폴백 처리

기존 `if not estimate_tables and not detail_tables and not condition_tables and not generic_tables: ws_raw = wb.create_sheet("데이터")` 분기는 **변경 없이** 유지. 단, 신규 5개 시트 중 하나라도 생성되면 실질적 "빈 Excel"이 아니므로 "데이터" 시트 폴백이 트리거되지 않도록 조건 추가:

```python
has_any_legacy = estimate_tables or detail_tables or condition_tables or generic_tables
has_any_new = (
    any(s.get("clean_text", "").strip() for s in sections)
    or any(s.get("notes") for s in sections)
    or any(s.get("conditions") for s in sections)
    or any(s.get("cross_references") for s in sections)
    or any((s.get("revision_year") or s.get("unit_basis")) for s in sections)
)
if not has_any_legacy and not has_any_new:
    ws_raw = wb.create_sheet("데이터")
    ws_raw.cell(row=1, column=1, value="⚠ 분류 가능한 데이터가 없습니다.")
```

### 11.5 통합 테스트 (`test_excel_exporter.py`)

| # | 테스트 | 검증 |
|---|---|---|
| IT1 | `test_pumsem_sample_sheets_present` | pumsem 샘플 JSON → `본문/주석/가감산_조건/교차참조/메타데이터` 모두 존재 |
| IT2 | `test_bom_sample_no_new_sheets` | BOM 샘플 JSON → 신규 시트 0개 생성 (BOM 회귀 방지) |
| IT3 | `test_empty_fields_no_sheets` | 모든 신규 필드가 빈 섹션 리스트 → 기존 시트만 (폴백 포함) |
| IT4 | `test_partial_fields_partial_sheets` | notes만 있음 → `주석` 시트만 신규 생성, 다른 신규 시트 없음 |
| IT5 | `test_sheet_order` | 순서 검증: 견적서 → ... → 조건 → 본문 → 주석 → 가감산_조건 → 교차참조 → 메타데이터 → Table_N |

### 11.6 체크포인트

| # | 검증 | 합격 기준 |
|---|---|---|
| CP1 | `pytest tests/unit/exporters/test_excel_builders.py -x` | 신규 15건 전수 통과 |
| CP2 | `pytest tests/unit/exporters/test_excel_exporter.py -x` | 기존 + 신규 통합 5건 통과 |
| CP3 | `pytest` 전체 | **≥ 567 passed** (552 + 15) |
| CP4 | `pytest --cov=exporters/ --cov-report=term-missing` | `excel_builders.py` 신규 함수 커버리지 ≥ 80% |
| CP5 | Golden E2E | **MATCH 유지** (기존 generic.md Golden 불변) |
| CP6 | BOM 샘플 수동 smoke | `creation_2025/` 샘플 → xlsx 시트 목록이 기존과 동일 |
| CP7 | pumsem 샘플 수동 smoke | `pumsem/` 샘플 → 본문·주석·가감산_조건 시트에 실 데이터 렌더 확인 |
| CP8 | `ruff check .`, `ruff format --check .` | 클린 |

---

## 12. Mock/픽스처 설계

### 12.1 픽스처 재사용 (Phase 10 자산 100%)

```python
@pytest.fixture
def pumsem_rich_sections():
    """pumsem 필드가 모두 채워진 섹션 리스트."""
    return [
        {
            "section_id": "1-1-1",
            "title": "일반사항",
            "department": "공통부문",
            "chapter": "제1장 총칙",
            "page": 5,
            "clean_text": "본 품셈은 표준 단위 공사량 산정 기준이다.\n...",
            "tables": [],
            "notes": ["본 품셈은 2024년 기준이다", "야간작업 시 25% 가산"],
            "conditions": [
                {"type": "가산", "condition": "야간작업 시", "rate": "25%"},
                {"type": "감산", "condition": "건설기계 사용 시", "rate": "10%"},
            ],
            "cross_references": [
                {"target_section_id": "2-1-3", "target_chapter": "제2장", "context": "... 제2장 2-1-3 준용"}
            ],
            "revision_year": "2024",
            "unit_basis": "m³당",
        },
        # ... 추가 섹션
    ]

@pytest.fixture
def bom_minimal_sections():
    """BOM 모드 to_sections() 형식 — 신규 필드 모두 빈값."""
    return [
        {
            "section_id": "BOM-1",
            "title": "BILL OF MATERIALS #1",
            "department": None,
            "chapter": None,
            "page": 1,
            "clean_text": "",
            "tables": [{"table_id": "T-BOM-1-01", "type": "BOM_자재",
                        "headers": ["NO", "DESCRIPTION"], "rows": [...], ...}],
            "notes": [],
            "conditions": [],
            "cross_references": [],
            "revision_year": None,
            "unit_basis": None,
        },
    ]

@pytest.fixture
def empty_sections():
    """모든 필드가 빈 섹션 — 폴백 '데이터' 시트 트리거용."""
    return [{
        "section_id": "empty", "title": "", "department": "", "chapter": "",
        "page": 0, "clean_text": "", "tables": [], "notes": [],
        "conditions": [], "cross_references": [],
        "revision_year": "", "unit_basis": "",
    }]
```

### 12.2 실 xlsx 검증 헬퍼

```python
def _read_xlsx_sheets(path: Path) -> list[str]:
    """생성된 xlsx의 시트명 목록 반환 (순서 보존)."""
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True)
    return wb.sheetnames

def _read_xlsx_rows(path: Path, sheet: str) -> list[tuple]:
    """특정 시트의 모든 행을 튜플로 반환."""
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True)
    ws = wb[sheet]
    return [tuple(c.value for c in row) for row in ws.iter_rows()]
```

### 12.3 Mock 비사용 원칙

모든 테스트는 **실제 openpyxl Workbook**에 시트를 생성하여 검증. Mock 대신 **실 .xlsx 파일을 tmp_path에 생성 후 재로드** 방식. 이유:
- openpyxl 스타일 객체는 Mock이 어렵고, Mock 실패가 실제 Excel 호환성 문제를 숨김
- Phase 10이 이미 실 Workbook 기반 테스트 패턴 확립

---

## 13. 롤백·회귀 방지 전략

### 13.1 Step 경계 태깅

```
phase12.5-step1-start    (본문 시트)
phase12.5-step2-start    (주석 시트)
phase12.5-step3-start    (가감산)
phase12.5-step4-start    (교차참조)
phase12.5-step5-start    (메타)
phase12.5-step6-start    (통합)
phase12.5-complete       (완료)
```

각 Step 실패 시 `git reset --hard phase12.5-stepN-start`.

### 13.2 회귀 방지 핵심 3건

1. **기존 시트 불변**: `_build_estimate_sheet`, `_build_detail_sheet`, `_build_condition_sheet`, `_build_generic_sheet` 코드 0줄 변경. PR diff에서 해당 함수 hunk가 나오면 리뷰 거부.
2. **BOM 모드 출력 동일**: CP6 수동 smoke로 검증. 신규 시트 0개 생성 확인.
3. **Golden E2E**: 기존 generic.md → JSON → Excel Golden 파일과 바이트 단위는 아니지만 **시트 목록 + 각 시트 행수 baseline** 유지.

### 13.3 각 Step별 DoD

- [ ] 해당 빌더 단위 테스트 전수 통과
- [ ] 전체 pytest passed 수 감소 없음
- [ ] Coverage gate (70%) 통과
- [ ] ruff 클린
- [ ] Git 태그 부여

### 13.4 중단 지점

Step 12.5-1 ~ 12.5-5는 **독립**하므로 임의 중단 가능. 중단 시 12.5-6 통합만 완료하면 **완료된 빌더 수만큼 시트 추가**되고 미완 빌더 분기는 제외. 즉 "본문 시트만 완료"로 부분 출시 가능.

---

## 14. 리스크 매트릭스

| 리스크 | 발생 영역 | 확률 | 영향 | 완화책 |
|---|---|---|---|---|
| BOM 모드 Excel 시트 추가 (회귀) | Step 12.5-6 | 낮음 | 상 | Empty Guard + CP6 BOM smoke + IT2 테스트 |
| Empty Guard 판정 오류 | Step 12.5-6 | 중 | 중 | `any(s.get(...) ...)` 패턴 일관성 + `test_empty_fields_no_sheets` |
| 시트명 충돌 | Step 12.5-6 | 낮음 | 중 | §11.3 검증 완료, 신규 이름 5자 이하 |
| 컬럼 폭 overflow (긴 본문) | Step 12.5-1 | 중 | 하 | F열 max width 80 + wrap_text=True |
| 메타 시트 None 처리 | Step 12.5-5 | 중 | 중 | `rev or ""` 패턴 + `test_revision_year_only` |
| 시트 순서 무작위 | Step 12.5-6 | 낮음 | 하 | openpyxl `create_sheet` 호출 순서로 결정 + IT5 테스트 |
| 기존 시트 빌더 부작용 | 전체 | 낮음 | 상 | PR에서 기존 4 함수 hunk 거부 |
| Phase 12 Step 12-2 미완 상태에서 착수 | 전체 | 낮음 | 중 | §0 선행 조건 명시, 착수 전 태그 확인 |

---

## 15. DoD 체크리스트 (Phase 12.5 전체)

- [ ] Step 12.5-1 완료: 본문 시트 빌더 + 테스트 3건
- [ ] Step 12.5-2 완료: 주석 시트 빌더 + 테스트 3건
- [ ] Step 12.5-3 완료: 가감산_조건 시트 빌더 + 테스트 3건
- [ ] Step 12.5-4 완료: 교차참조 시트 빌더 + 테스트 3건
- [ ] Step 12.5-5 완료: 메타데이터 시트 빌더 + 테스트 3건
- [ ] Step 12.5-6 완료: `_export_impl()` 통합 + 통합 테스트 5건
- [ ] pytest `≥ 567 passed` 유지
- [ ] `--cov-fail-under=70` 통과
- [ ] Golden E2E MATCH 유지
- [ ] BOM 샘플 수동 smoke 통과 (시트 목록 불변)
- [ ] pumsem 샘플 수동 smoke 통과 (신규 5개 시트 중 해당 필드에 실 데이터)
- [ ] 기존 4개 시트 빌더 함수 0줄 변경 (PR diff 검증)
- [ ] `ruff check .`, `ruff format --check .` 클린
- [ ] Git 태그 `phase12.5-complete` 부여
- [ ] `05_검증_리뷰/Phase12.5_결과보고서_20260422.md` 작성 (신규 시트 5종 렌더 사례 포함)

---

## 16. 타임라인 (예상)

| 시점 | 작업 | 시간 추정 |
|---|---|---|
| D+0 | Phase 12 완료 확인 + `phase12.5-step1-start` 태그 | 10분 |
| D+0 | Step 12.5-1 (본문 시트) + 테스트 | 30분 |
| D+0 | Step 12.5-2 (주석 시트) + 테스트 | 25분 |
| D+0 | Step 12.5-3 (가감산) + 테스트 | 30분 |
| D+0 | Step 12.5-4 (교차참조) + 테스트 | 25분 |
| D+0 | Step 12.5-5 (메타) + 테스트 | 30분 |
| D+0 | Step 12.5-6 (통합) + 통합 테스트 5건 | 45분 |
| D+0 | 수동 smoke (pumsem + BOM) | 20분 |
| D+0 | 결과보고서 작성 + 태그 | 20분 |

총 예상 소요: **약 4시간** (단일 세션에서 완료 가능)

---

## 17. 사용자 영향 — Before/After

### 17.1 pumsem 프리셋 (품셈 문서)

**Before (현재)**: 견적서/내역서/조건/Table_N 최대 4종
**After (Phase 12.5)**: 위 4종 + **본문/주석/가감산_조건/교차참조/메타데이터** 최대 9종
- 본문: 섹션별 전체 텍스트 → 검색·참조 용이
- 주석: 모든 [주] 블록 통합 → 적용 조건 한눈에 파악
- 가감산_조건: "야간 25% 가산" 등 구조화된 조정 조건 → DB 적재 가능한 형식
- 교차참조: "제2장 2-1-3 준용" → 섹션 간 의존 관계 가시화
- 메타: 보완연도/단위 기준 → 버전 관리, 단가 기준 파악

### 17.2 estimate 프리셋 (견적서)

**Before**: 견적서/내역서/조건 + Table_N
**After**: 위 + 본문 시트 (견적 조건·배경 설명 보존)

### 17.3 범용 (preset=None)

**Before**: Table_N 중심 (분류 없음)
**After**: 본문 시트가 주력 + Table_N 보조

### 17.4 BOM 프리셋

**Before**: BOM 표 (Table_N)
**After**: **동일** (신규 시트 자동 미생성 — Empty Guard)

---

## 18. 참조 문서

- 상위 계획서: `모드별_파이프라인_분석_및_Excel_확장_계획서_20260422.md`
- Phase 12 기술서: `Phase12_대형모듈_분해_상세_구현_기술서_20260422.md` (선행 조건)
- Phase 7r 기술서: `Phase7_재수정_상세_구현_기술서_20260420.md` (format 선례)
- 핵심 코드 위치:
  - `exporters/excel_exporter.py:562-681` `_export_impl()` (통합 지점)
  - Phase 12 Step 12-2 산출 예정: `exporters/excel_builders.py` (신규 빌더 추가 대상)
  - Phase 12 Step 12-2 산출 예정: `exporters/excel_styles.py` (재사용 대상)
  - `parsers/text_cleaner.py:324-339` `process_section_text()` (JSON 데이터 소스)
  - `extractors/bom_extractor.py:513-591` `to_sections()` (BOM 모드 빈값 근거)
- Phase 10 테스트 자산: `tests/unit/exporters/test_excel_exporter.py` (픽스처 패턴 재사용)
