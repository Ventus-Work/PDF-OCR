# Phase 3 범용성 진단 — 수정 보고서

## 리뷰 결과

### 문제 1: `excel_exporter._classify_table()` — 치명적 (확인됨)

**위치:** `exporters/excel_exporter.py:71-101`

**현상:** 하드코딩된 3개 패턴만 인식하고, 나머지는 전부 `"unknown"` → `export()`의 451번 줄에서 무조건 스킵.

```
일반사항/특기사항     → "condition"
품명 + 합계_금액     → "detail"
명칭 + 금액          → "estimate"
type=="D_기타"       → "condition"
그 외 전부           → "unknown" → 데이터 유실
```

**실제 유실 시나리오:**

| 테이블 유형 | 헤더 예시 | 분류 결과 |
|---|---|---|
| BOM | ITEM NO \| TAG NO \| SERVICE \| QTY | **unknown → 유실** |
| 거래명세서 | 품목 \| 수량 \| 단가 \| 공급가액 | **unknown → 유실** |
| 자재 리스트 | NO \| 품명 \| 규격 \| 수량 \| 단가 \| 금액 | **unknown → 유실** (금액은 있지만 "명칭"이 없음) |
| 공문서 테이블 | 항목 \| 내용 \| 비고 | **unknown → 유실** |

**근본 원인 2가지:**

1. **폴백 없음** — `"unknown"`이 곧 "스킵"이다. 범용 시트(raw dump)로 보내는 경로가 없음. 480-484번 줄의 `"데이터"` 시트는 **전체 테이블이 0개일 때만** 생성되므로, 견적서 1개 + BOM 3개인 경우 견적서만 출력되고 BOM 3개는 조용히 사라짐.

2. **외부 확장 불가** — `_classify_table()`은 파라미터 없이 하드코딩된 패턴만 사용. 프리셋에서 export 규칙을 주입할 수 있는 설계가 아님.

**심각도:** `_classify_table()`이 건설 품셈 견적서 포맷(명칭/금액, 품명/합계_금액)에만 맞춰져 있어서, **이 파이프라인이 범용 문서 파서라는 설계 의도와 완전히 모순됨.**

---

### 문제 2: `table_parser.classify_table()` — 설계 제한 (확인됨)

**위치:** `parsers/table_parser.py:242-307`

**현상:** `type_keywords=None`(프리셋 없음) → 모든 테이블이 `"general"` 반환.

**문제의 연쇄 효과:**

```
main.py: --preset 없이 실행
  → type_keywords = None  (line 219)
  → classify_table() returns "general"  (line 271-272)
  → table dict에 type="general" 저장  (parse_single_table:569)
  → _classify_table()에서 type 힌트 활용 불가  (line 96-99, "D_기타"만 체크)
  → 헤더 패턴 매칭 3개만으로 판별 시도
  → 대부분 "unknown" → 유실
```

다만, 이 함수 자체의 설계는 의도적으로 올바른 부분이 있다:
- `type_keywords=None` → `"general"` 반환은 **"키워드가 없으니 분류할 수 없다"는 정직한 응답**
- 건설 품셈 키워드(인부, 철공 등)를 범용 모드에서 적용하지 않는 것은 SRP 준수

**진짜 문제는 이 함수가 아니라**, `"general"` 타입을 받은 후단(`_classify_table`)이 이를 활용하지 못하는 것. 즉, **Phase 2 → Phase 3 사이에 "general" 타입 테이블의 처리 경로가 없음.**

---

### 문제 3: `_build_detail_sheet()._col_widths` — 경미 (확인됨, 추가 발견 있음)

**위치:** `exporters/excel_exporter.py:351-358`

**현상:** 13개 하드코딩 키만 있고, 미등록 키는 `_col_widths.get(key, 12)` → 기본폭 12.

이건 단순 기능 저하로 **치명적이지 않다.**

**그러나 더 심각한 관련 문제 발견:**

`_DETAIL_HEADER_GROUPS` (239-249번 줄)도 하드코딩되어 있어, **등록되지 않은 헤더 컬럼은 폭이 좁은 게 아니라 아예 출력에서 제외됨:**

```python
# line 267-271: existing에 있지만 _DETAIL_HEADER_GROUPS에 없는 컬럼은 col_order에 안 들어감
active_groups = [
    (grp, [sub for sub in subs if sub in existing])
    for grp, subs in _DETAIL_HEADER_GROUPS        # ← 이 13개 키만 인식
    if any(sub in existing for sub in subs)
]
```

실질적 영향은 제한적 — `_build_detail_sheet()`는 `_classify_table()`이 `"detail"`로 분류한 테이블(품명+합계_금액 헤더)에만 호출되므로, 해당 포맷에서 13개 이외의 컬럼이 나올 가능성은 낮음.

---

### 문제 4: `_try_parse_number()` 미구현 — 숫자가 문자열로 저장됨

**위치:** `exporters/excel_exporter.py:197-198`, `331`

**현상:** 모든 셀 값을 `str(row.get(h, "")).strip()`으로 기록한다. Excel에서 숫자가 문자열 타입으로 저장되어 **SUM, AVERAGE, 정렬, 차트가 동작하지 않음.**

```python
# excel_exporter.py L197-198 (견적서 시트)
val = str(row.get(h, "")).strip()
cell = ws.cell(row=row_idx, column=col_idx, value=val)  # ← 항상 문자열

# excel_exporter.py L330-331 (내역서 시트)
val = str(row.get(key, "")).strip()
cell = ws.cell(row=row_idx, column=col_idx, value=val)  # ← 항상 문자열
```

**기술서 대비:** `Phase3_상세_구현_기술서.md` L547-585에 `_try_parse_number()` 스펙이 이미 존재:

| 입력 | 기대 결과 | 설명 |
|---|---|---|
| `"15,000,000"` | `15000000` (int) | 콤마 제거 후 정수 변환 |
| `"3.14"` | `3.14` (float) | 소수점 변환 |
| `"0015"` | `None` → 문자열 유지 | 선행 0 = 식별자/코드 보호 |
| `"-"` | `None` → 문자열 유지 | 대시 단독 |
| `"SUS304"` | `None` → 문자열 유지 | 비숫자 |

**심각도:** 중간. 데이터는 유실되지 않지만, **업무용 Excel로서 기능하지 못함.** 사용자가 금액 합계를 수동으로 재입력해야 하는 상황.

**설계 의도 참고:** Phase 2의 `try_numeric()` 제거(데이터 무결성 보호)는 올바르다. 숫자 변환은 Phase 3 Excel 출력 단계에서만 수행하는 것이 기술서의 설계 원칙. 현재 구현이 이 원칙을 따르되, Phase 3에서도 변환하지 않은 것이 문제.

---

### 문제 5: `_build_condition_sheet()` 중복 제거 알고리즘 결함 — 데이터 파편화

**위치:** `exporters/excel_exporter.py:387-398`

**현상:** `seen_right`라는 단일 `set`에 모든 열·모든 행의 텍스트를 누적하고, 한 번이라도 등장한 텍스트는 이후 무조건 빈칸(`""`)으로 치환한다.

```python
seen_right: set[str] = set()                    # ← 전역 set (열·행 구분 없음)
for row_idx, row in enumerate(rows, start=2):
    for col_idx, h in enumerate(headers, start=1):
        val = str(row.get(h, "")).strip()
        if col_idx > 1 and val in seen_right and val:
            display_val = ""                     # ← 어디서든 본 적 있으면 삭제
        else:
            display_val = val
            if col_idx > 1 and val:
                seen_right.add(val)              # ← 열 무관하게 전역 등록
```

**원래 의도:** Phase 2의 `expand_table()`이 rowspan을 전개하면서 동일 값이 수직으로 반복되는 것을 suppression하려 한 것.

**실제 결함:**

| 행 | 열2 값 | 열3 값 | 결과 |
|---|---|---|---|
| 2행 | "현장 납품" | "30일 이내" | 정상 출력 |
| 5행 | "견적 유효기간" | "현장 납품" | ← 열3 "현장 납품"은 2행 열2에서 이미 `seen_right`에 등록됨 → **빈칸 처리** |
| 10행 | "현장 납품" | "별도 협의" | ← 열2 "현장 납품"도 이미 등록됨 → **빈칸 처리** |

다른 열, 다른 행이어도 같은 텍스트면 무조건 삭제. 데이터가 파편화되어 조건 시트가 읽을 수 없는 상태가 됨.

**올바른 구현:** 전역 set이 아닌, **같은 열의 직전 행(바로 위 행) 값**과 비교하여 연속 중복만 suppression.

**심각도:** 높음. 조건 시트(일반사항/특기사항)에서 동일 문구가 여러 위치에 나오면 즉시 발동.

---

### 문제 6: 헤더 없는 테이블의 무조건 유실

**위치:** `exporters/excel_exporter.py:173`, `263`, `375` — 세 빌더 공통 도입부

**현상:** 모든 시트 빌더가 `if not headers: return`으로 시작하며, 데이터 행(`rows`)이 존재하더라도 헤더가 빈 배열이면 조용히 폐기한다.

```python
# _build_estimate_sheet() L173
headers = table.get("headers", [])
if not headers:
    return          # ← rows에 100줄이 있어도 여기서 끝

# _build_detail_sheet() L263, _build_condition_sheet() L375 — 동일 패턴
```

**발생 확률:** 현재 Phase 2 파서 경로에서는 `headers`가 빈 리스트(`[]`)로 올 확률이 매우 낮다 — `expand_table()`이 최소 1행을 반환하고 그것이 headers가 되기 때문. 단, 다음 경우에는 발생 가능:
- `.json` 직접 입력 시 사용자가 headers 필드를 누락하거나 빈 배열로 작성
- 외부 시스템에서 생성한 JSON을 파이프라인에 연결하는 경우

**심각도:** 낮음 (현재 경로에서는 거의 안 발동). 단, 문제 1의 수정(generic 폴백) 후에도 이 가드가 남아 있으므로, `_build_generic_sheet()`에는 헤더 없는 경우의 폴백(rows 키 기반 헤더 자동 생성 또는 경고 로그)을 추가할 것을 권장.

---

### 문제 7: `wb.save()` PermissionError 미처리 — 파이프라인 크래시

**위치:** `exporters/excel_exporter.py:489`

**현상:** 생성할 `.xlsx` 파일이 Excel 프로그램에서 이미 열려 있으면, Windows 파일 락으로 인해 `PermissionError: [Errno 13] Permission denied`가 발생한다. 이에 대한 try-except가 없어 **파이프라인 전체가 크래시.**

```python
# L489 — 예외 처리 없음
wb.save(output_path)    # ← 파일 열려 있으면 PermissionError로 즉시 뻗음
```

**현재 상태:** `main.py:424-429`에 최상위 `except Exception`이 있어 프로세스는 종료되지 않지만, 에러 메시지가 파이썬 원본 트레이스백이라 사용자가 원인을 파악하기 어렵다.

**심각도:** 높음. Windows에서 Excel 파일 자동화의 **가장 빈번한 1순위 에러.** 사용자가 이전 결과물을 Excel에서 열어본 채로 재실행하는 시나리오는 일상적.

---

### 문제 8: `_row_style()` — `all([]) == True` 함정으로 구분행 오판

**위치:** `exporters/excel_exporter.py:133-137`

**현상:** 파이썬 `all()` 함수의 언어적 특성 — 빈 iterable에 대해 `True`를 반환 — 으로 인한 잠복 버그.

```python
money_keys = [k for k in row if "금액" in k or "금 액" in k]
all_money_empty = all(not str(row.get(k, "")).strip() for k in money_keys)
#                 ↑ money_keys가 []이면 all([]) → True

if all_money_empty and first and not _is_number(first):
    return "section"    # ← 금액 컬럼이 없는 테이블에서 모든 비숫자 행이 구분행으로 오판
```

**현재 상태:** `_row_style()`은 `_build_estimate_sheet()`와 `_build_detail_sheet()`에서만 호출됨. 이 두 빌더는 "금액" 헤더가 있는 테이블에서만 실행되므로, `money_keys`가 빈 리스트가 될 수 없다. **따라서 현재는 발동하지 않음.**

**수정 A/B/C 적용 후 상태:** `_build_generic_sheet()`에서 `_row_style()`을 재사용하면 **즉시 폭발:**
- BOM 테이블(ITEM NO | TAG NO | QTY) → "금액" 헤더 없음
- `money_keys = []` → `all_money_empty = True`
- 첫 셀이 "Pipe Support"(비숫자) → `return "section"`
- **모든 데이터 행이 파란 배경 구분행으로 렌더링**

**심각도:** 현재 잠복, 1단계 수정 후 확정 발동. 수정 C(`_build_generic_sheet()`)에서 `_row_style()`을 사용하지 않더라도, 향후 재사용 시 반드시 터지는 시한폭탄이므로 근본 수정 필요.

**수정:** `all_money_empty = money_keys and all(...)` — 단 1단어(`money_keys and`) 추가로 해결.

---

## 종합 평가

### 설계·범용성 문제 (의미론적 결함)

| 문제 | 심각도 | 데이터 유실 | 수정 우선순위 |
|---|---|---|---|
| 1. `_classify_table()` 폐쇄적 분류 | **치명** | 패턴 불일치 시 전체 테이블 유실 | 1순위 |
| 2. `classify_table()` general 미활용 | **높음** | 문제 1과 연쇄하여 유실 증폭 | 1순위 (1과 함께) |
| 4. `_try_parse_number()` 미구현 | **중간** | 없음 (기능 장애) | 2순위 |
| 3. `_col_widths` 하드코딩 | **낮음** | 없음 (레이아웃 저하만) | 3순위 |

### 런타임·로직 결함 (물리적 버그)

| 문제 | 심각도 | 현재 발동 | 수정 후 발동 | 수정 우선순위 |
|---|---|---|---|---|
| 5. `seen_right` 전역 dedup → 데이터 파편화 | **높음** | 조건 시트에서 발동 | 동일 | 1순위 |
| 7. `wb.save()` PermissionError 미처리 | **높음** | 파일 열림 시 즉시 | 동일 | 1순위 |
| 8. `all([]) == True` 구분행 오판 | **높음** | 잠복 | 수정 C 적용 시 **즉시 폭발** | 1순위 (수정 C와 동봉 필수) |
| 6. `if not headers: return` 무조건 폐기 | **낮음** | 거의 안 발동 | `.json` 입력 시 가능 | 2순위 (경고 추가) |

---

## 상세 기술서 갭 분석

`Phase3_상세_구현_기술서.md`에 설계된 항목 vs 현재 구현 상태를 대조한 결과, **9개 항목 중 2개만 구현 완료, 7개 미구현:**

| # | 항목 | 기술서 위치 | 현재 구현 | 상태 |
|---|---|---|---|---|
| 1 | `base_exporter.py` (ABC 클래스) | L114-160 | 파일 없음 | **미구현** |
| 2 | `ExcelExporter` 클래스 구조 | L187 (Strategy Pattern) | 함수형 `export()` | **설계 불일치** |
| 3 | `_write_generic_sheets()` 범용 시트 | L238-271 | 없음 → `"unknown"` 스킵 | **미구현 = 문제 1** |
| 4 | `_write_table_to_sheet()` 범용 테이블 기록 | L324-382 | 없음 | **미구현** |
| 5 | `_try_parse_number()` 숫자 변환 | L547-585 | 없음 (전부 문자열) | **미구현 = 문제 4** |
| 6 | `json_exporter.py` 분리 | L629-683 | `main.py` 인라인 | **미구현** |
| 7 | `presets/estimate.py` 견적서 프리셋 | L687-886 | 파일 없음 | **미구현** |
| 8 | `detector.py` 문서 유형 자동 감지 | L890-976 | 파일 없음 | **미구현** |
| 9 | `.json` 입력 지원 | L1047-1061 | 없음 | **미구현** |
| 10 | `templates/견적서_양식.xlsx` 갑지 | L84 | 폴더 없음 | **미구현** |
| — | `exporters/__init__.py` | L100-110 | 9줄 존재 | 구현됨 |
| — | `main.py` --output excel 분기 | L1088-1111 | 동작함 | 구현됨 (함수형) |

**파일 존재 현황 검증 결과:**

```
ps-docparser/
├── exporters/
│   ├── __init__.py              ✅ 존재
│   ├── excel_exporter.py        ⚠️ 존재하나 함수형 (클래스 미전환)
│   ├── base_exporter.py         ❌ 없음
│   └── json_exporter.py         ❌ 없음
├── presets/
│   ├── pumsem.py                ✅ 존재
│   └── estimate.py              ❌ 없음
├── detector.py                  ❌ 없음
└── templates/                   ❌ 폴더 자체 없음
```

**핵심 시사점:** 현재 수정 보고서의 3개 문제만 고치면 끝이 아니다. 기술서 설계의 약 70%가 미구현 상태이며, 문제 1(데이터 유실)과 문제 4(숫자 문자열화)는 기술서에 이미 해결책이 설계되어 있으나 구현이 안 된 것.

---

## 구체적 수정 설계

### 수정 A: `_classify_table()` 폴백 → `"generic"` 반환

**대상:** `exporters/excel_exporter.py:101`

```python
# 변경 전 (L101)
return "unknown"

# 변경 후
return "generic"
```

분류 불가 테이블을 "스킵 대상"이 아닌 "범용 처리 대상"으로 전환.

---

### 수정 B: `export()` 함수에 generic 분기 추가

**대상:** `exporters/excel_exporter.py:430-451`

```python
# 변경 전 (L443-451)
for tbl in section.get("tables", []):
    kind = _classify_table(tbl)
    if kind == "estimate":
        estimate_tables.append(tbl)
    elif kind == "detail":
        detail_tables.append(tbl)
    elif kind == "condition":
        condition_tables.append(tbl)
    # "unknown" → 스킵

# 변경 후
generic_tables: list[dict] = []        # ← 추가

for tbl in section.get("tables", []):
    kind = _classify_table(tbl)
    if kind == "estimate":
        estimate_tables.append(tbl)
    elif kind == "detail":
        detail_tables.append(tbl)
    elif kind == "condition":
        condition_tables.append(tbl)
    elif kind == "generic":             # ← 추가
        generic_tables.append(tbl)

# ... 기존 시트 빌드 후 ...

# ── 범용 시트 (분류 불가 테이블) ──     # ← 추가
for i, tbl in enumerate(generic_tables, start=1):
    sheet_name = f"Table_{i}" if len(generic_tables) > 1 else "Table"
    ws_gen = wb.create_sheet(sheet_name[:31])
    ws_gen.sheet_view.showGridLines = False
    _build_generic_sheet(ws_gen, tbl)
```

---

### 수정 C: `_build_generic_sheet()` 신규 함수

**대상:** `exporters/excel_exporter.py` — 신규 추가 (기술서 L324-382 `_write_table_to_sheet()` 참조)

```python
def _build_generic_sheet(ws, table: dict):
    """
    범용 테이블 시트 — 헤더/데이터를 원본 그대로 기록한다.

    Why: 분류 불가 테이블(BOM, 거래명세서, 공문서 등)을 유실하지 않고
         원데이터를 그대로 Excel에 옮긴다. 사용자가 수동 재편집 가능.
    """
    headers = table.get("headers", [])
    rows    = table.get("rows", [])

    if not headers:
        return

    # ── 헤더 행 ──
    for col_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        _apply_style(cell, fill=_FILL_HEADER, font=_FONT_HEADER,
                     align=_ALIGN_CENTER, border=_BORDER_ALL)
    ws.row_dimensions[1].height = 20

    # ── 데이터 행 ──
    for row_idx, row in enumerate(rows, start=2):
        ws.row_dimensions[row_idx].height = 16
        for col_idx, h in enumerate(headers, start=1):
            val = str(row.get(h, "")).strip()
            cell = ws.cell(row=row_idx, column=col_idx)

            # 숫자 감지 → 숫자 타입으로 기록 + 콤마 포맷
            numeric = _try_parse_number(val)
            if numeric is not None:
                cell.value = numeric
                cell.number_format = '#,##0'
                _apply_style(cell, font=_FONT_BODY, align=_ALIGN_RIGHT,
                             border=_BORDER_ALL)
            else:
                cell.value = val
                _apply_style(cell, font=_FONT_BODY,
                             align=_ALIGN_CENTER if col_idx == 1 else _ALIGN_LEFT,
                             border=_BORDER_ALL)

    # ── 열 너비 자동 조정 ──
    for col_idx, h in enumerate(headers, start=1):
        # 헤더 텍스트 길이 기반 (한글 2바이트)
        header_len = sum(2 if ord(c) > 127 else 1 for c in h)
        width = max(header_len + 4, 10)
        # 데이터 셀 중 최대 길이도 고려
        for row in rows:
            val = str(row.get(h, ""))
            val_len = sum(2 if ord(c) > 127 else 1 for c in val)
            width = max(width, val_len + 2)
        ws.column_dimensions[get_column_letter(col_idx)].width = min(width, 50)
```

---

### 수정 D: `_try_parse_number()` 숫자 변환 함수 추가

**대상:** `exporters/excel_exporter.py` — 신규 추가 (기술서 L547-585 스펙 준수)

```python
_RE_NUMERIC = re.compile(r'^-?[\d,]+\.?\d*$')

def _try_parse_number(value: str) -> int | float | None:
    """
    문자열을 숫자로 변환 시도. 실패 시 None.

    Phase 2에서 의도적으로 제거한 숫자 변환을
    Phase 3 Excel 출력 단계에서만 수행한다.

    선행 0 보호: "0015" → None (식별자/코드)
    대시 단독:   "-"    → None
    """
    if not isinstance(value, str) or not value.strip():
        return None

    val = value.strip()

    if val == "-":
        return None

    # 선행 0 보호 ("0015" → 변환 안 함, "0" "0.5" → 변환 허용)
    stripped = val.replace(",", "").lstrip("-")
    if len(stripped) > 1 and stripped[0] == "0" and stripped[1] != ".":
        return None

    numeric_str = val.replace(",", "")
    try:
        if "." in numeric_str:
            return float(numeric_str)
        return int(numeric_str)
    except ValueError:
        return None
```

이 함수는 수정 C의 `_build_generic_sheet()`에서 사용되며, 기존 `_build_estimate_sheet()`, `_build_detail_sheet()`에도 적용하여 모든 시트에서 숫자 셀이 올바르게 동작하도록 한다.

---

### 수정 E: `_build_condition_sheet()` 중복 제거 알고리즘 교체

**대상:** `exporters/excel_exporter.py:387-398`

전역 `set` 기반 dedup → **같은 열의 직전 행 비교** 방식으로 교체.

```python
# 변경 전
seen_right: set[str] = set()
for row_idx, row in enumerate(rows, start=2):
    for col_idx, h in enumerate(headers, start=1):
        val = str(row.get(h, "")).strip()
        if col_idx > 1 and val in seen_right and val:
            display_val = ""
        else:
            display_val = val
            if col_idx > 1 and val:
                seen_right.add(val)

# 변경 후
prev_row_vals: dict[int, str] = {}    # 열 인덱스 → 직전 행 값
for row_idx, row in enumerate(rows, start=2):
    ws.row_dimensions[row_idx].height = 16
    for col_idx, h in enumerate(headers, start=1):
        val = str(row.get(h, "")).strip()
        # 같은 열의 직전 행과 동일한 값이면 suppression (rowspan 전개 중복 제거)
        if col_idx > 1 and val and val == prev_row_vals.get(col_idx):
            display_val = ""
        else:
            display_val = val
        prev_row_vals[col_idx] = val    # 현재 값을 직전 행으로 갱신
        cell = ws.cell(row=row_idx, column=col_idx, value=display_val)
        _apply_style(cell, font=_FONT_BODY, align=_ALIGN_LEFT, border=_BORDER_ALL)
```

**변경 핵심:** `seen_right: set` → `prev_row_vals: dict[int, str]`. 열 단위로 **바로 직전 행**과만 비교하므로:
- 2행 열2 "현장 납품" → 출력
- 5행 열3 "현장 납품" → 열3의 직전(4행) 값과 다름 → **정상 출력** (기존: 삭제됨)
- 연속 중복(rowspan 전개)만 정확히 suppression

---

### 수정 F: `_row_style()` — `all([]) == True` 함정 수정

**대상:** `exporters/excel_exporter.py:134`

```python
# 변경 전 (L134)
all_money_empty = all(not str(row.get(k, "")).strip() for k in money_keys)

# 변경 후
all_money_empty = bool(money_keys) and all(not str(row.get(k, "")).strip() for k in money_keys)
```

1단어 추가(`bool(money_keys) and`). `money_keys`가 빈 리스트이면 `all_money_empty = False`가 되어, 금액 컬럼이 없는 테이블에서 일반 행이 구분행으로 오판되는 것을 방지.

**필수 사유:** 수정 C(`_build_generic_sheet()`)에서 `_row_style()`을 직접 사용하지 않더라도, 향후 코드 확장 시 재사용되면 즉시 발동하는 시한폭탄. 근본 원인을 제거하는 것이 안전.

---

### 수정 G: `wb.save()` PermissionError 처리

**대상:** `exporters/excel_exporter.py:487-490`

```python
# 변경 전 (L489)
wb.save(output_path)
return output_path

# 변경 후
try:
    wb.save(output_path)
except PermissionError:
    print(f"\n⚠️  파일을 저장할 수 없습니다: {output_path}")
    print(f"    → 해당 파일이 Excel 등 다른 프로그램에서 열려 있는지 확인하세요.")
    print(f"    → 파일을 닫은 후 다시 실행해주세요.")
    raise SystemExit(1)
return output_path
```

파이썬 트레이스백 대신, 사용자가 즉시 이해 가능한 한국어 메시지 출력 후 우아하게 종료.

---

### 수정 H: 헤더 없는 테이블 방어 코드 추가

**대상:** `_build_generic_sheet()` (수정 C) 내부

수정 C의 `_build_generic_sheet()`에서 `if not headers: return` 대신 rows 키 기반 폴백 추가:

```python
# 수정 C 내 변경
headers = table.get("headers", [])
rows    = table.get("rows", [])

if not headers and rows:
    # rows의 첫 행 dict 키를 헤더로 사용 (폴백)
    if isinstance(rows[0], dict):
        headers = list(rows[0].keys())
    if not headers:
        print(f"    ⚠️ 헤더·키 없는 테이블 스킵: {table.get('table_id', '?')}")
        return
elif not headers:
    return
```

기존 3개 빌더(`_build_estimate_sheet`, `_build_detail_sheet`, `_build_condition_sheet`)의 `if not headers: return`은 유지 — 이들은 이미 특정 헤더 패턴으로 분류된 테이블만 받으므로 headers가 비어있으면 진짜 비정상.

---

### 수정 요약

| 수정 ID | 대상 | 변경 유형 | 해결 문제 | 변경량 |
|---|---|---|---|---|
| A | `_classify_table()` L101 | 1줄 변경 (`"unknown"` → `"generic"`) | 문제 1 | ~1줄 |
| B | `export()` L430-490 | 분기 추가 + generic 시트 생성 | 문제 1 | ~15줄 |
| C | `_build_generic_sheet()` | 신규 함수 | 문제 1 완성 | ~45줄 |
| D | `_try_parse_number()` | 신규 함수 | 문제 4 | ~20줄 |
| E | `_build_condition_sheet()` L387-398 | dedup 알고리즘 교체 | 문제 5 | ~10줄 |
| F | `_row_style()` L134 | 1줄 조건 추가 | 문제 8 | ~1줄 |
| G | `export()` L489 | try-except 래핑 | 문제 7 | ~6줄 |
| H | `_build_generic_sheet()` 내부 | 폴백 분기 | 문제 6 | ~5줄 |

총 변경량: 기존 코드 수정 ~15줄, 신규 코드 ~90줄.

---

## 구현 실행 순서

```
1단계 (최소 수정 — 데이터 유실 제거 + 런타임 버그 수정):
  ├── 수정 A: "unknown" → "generic" (1줄)
  ├── 수정 F: _row_style() all([]) 수정 (1줄) ← 수정 C 적용 전 필수 선행
  ├── 수정 C: _build_generic_sheet() (신규 ~45줄)
  ├── 수정 H: _build_generic_sheet() 내 헤더 폴백 (~5줄)
  ├── 수정 B: export()에 generic 분기 추가 (~15줄)
  ├── 수정 E: _build_condition_sheet() dedup 교체 (~10줄)
  └── 수정 G: wb.save() PermissionError 처리 (~6줄)
  결과: 데이터 유실 0, 조건 시트 파편화 해소, 파일 락 크래시 방지.

2단계 (Excel 활용도 확보):
  ├── 수정 D: _try_parse_number() (신규 ~20줄)
  ├── 기존 _build_estimate_sheet()에 숫자 변환 적용
  └── 기존 _build_detail_sheet()에 숫자 변환 적용
  결과: 금액 열이 숫자 타입 → SUM/정렬/차트 동작.

3단계 (아키텍처 정비 — 선택적):
  ├── base_exporter.py ABC 클래스 도입
  ├── excel_exporter.py 클래스화 (함수형 → Strategy Pattern)
  ├── json_exporter.py 분리 (main.py 인라인 → 독립 모듈)
  └── presets/estimate.py 견적서 프리셋 추가
  결과: 기술서 설계에 완전 합치. 신규 프리셋 확장 용이.

4단계 (부가 기능 — 선택적):
  ├── detector.py 문서 유형 자동 감지
  ├── .json 입력 직접 지원
  └── templates/견적서_양식.xlsx 갑지 템플릿
  결과: UX 개선. --preset 없이도 자동 감지 가능.
```

**1단계 주의사항:** 수정 F(`_row_style()` 수정)는 반드시 수정 C(`_build_generic_sheet()`) 이전 또는 동시에 적용해야 함. 수정 C만 먼저 적용하면 `all([]) == True` 버그가 즉시 발동하여 범용 시트의 모든 행이 구분행(파란 배경)으로 오렌더링됨.

**1~2단계 수행 시 진단된 8개 문제가 모두 해결된다.** 총 변경량 약 105줄.
3~4단계는 기술서 설계 완전 이행을 위한 것으로, 기능적으로는 1~2단계로 충분.

---

## 검증 계획

### 1단계 검증 (데이터 유실 제거 + 런타임 버그 수정)

**수정 A/B/C — 범용 시트 출력:**

| 검증 항목 | 방법 | 기대 결과 |
|---|---|---|
| 분류 불가 테이블 보존 | BOM 헤더(ITEM NO/TAG NO/QTY) 테이블 입력 | `Table_1` 시트에 원본 그대로 출력 |
| 기존 분류 영향 없음 | 견적서 PDF 재실행 | 견적서/내역서/조건 시트 기존과 동일 |
| 혼합 문서 | 견적서 1개 + BOM 3개 포함 JSON | 견적서 시트 + Table_1~3 시트 (총 4+시트) |
| 빈 테이블 | headers만 있고 rows 빈 테이블 | 헤더만 있는 시트 생성 (에러 없음) |

**수정 E — 조건 시트 dedup 교체:**

| 검증 항목 | 방법 | 기대 결과 |
|---|---|---|
| 연속 중복 suppression | 일반사항 열에서 동일 값 3행 연속 | 첫 행만 출력, 2~3행은 빈칸 (rowspan 전개 정상 처리) |
| 비연속 동일 값 보존 | 2행 열2 "현장 납품" + 8행 열3 "현장 납품" | 양쪽 모두 **정상 출력** (기존: 8행이 빈칸) |
| 다른 열 동일 값 보존 | 열2 "30일" + 열3 "30일" (같은 행) | 양쪽 모두 정상 출력 |

**수정 F — `_row_style()` all([]) 수정:**

| 검증 항목 | 방법 | 기대 결과 |
|---|---|---|
| 금액 컬럼 없는 테이블 | BOM(ITEM/TAG/QTY) 테이블에서 `_row_style()` 호출 | 모든 행이 `"body"` 반환 (기존: 전부 `"section"`) |
| 금액 컬럼 있는 테이블 | 기존 견적서 테이블 | 기존과 동일 동작 (구분행/소계행 정상 감지) |

**수정 G — PermissionError 처리:**

| 검증 항목 | 방법 | 기대 결과 |
|---|---|---|
| 파일 열림 상태 | `.xlsx`를 Excel에서 연 채로 재실행 | `"⚠️ 파일을 저장할 수 없습니다"` 메시지 + 우아한 종료 (트레이스백 없음) |
| 정상 상태 | 파일 닫힌 상태 실행 | 기존과 동일 (정상 저장) |

**수정 H — 헤더 없는 테이블 폴백:**

| 검증 항목 | 방법 | 기대 결과 |
|---|---|---|
| headers=[], rows=[{dict}] | rows의 dict 키에서 헤더 자동 생성 | 시트에 키 기반 헤더 + 데이터 출력 |
| headers=[], rows=[] | 완전 빈 테이블 | 조용히 스킵 (크래시 없음) |

### 2단계 검증 (숫자 변환)

| 검증 항목 | 입력 | 기대 결과 |
|---|---|---|
| 콤마 금액 | `"15,000,000"` | 셀 값 `15000000` (int), 포맷 `#,##0` |
| 소수점 | `"3.14"` | 셀 값 `3.14` (float) |
| 선행 0 보호 | `"0015"` | 셀 값 `"0015"` (문자열 유지) |
| 대시 | `"-"` | 셀 값 `"-"` (문자열 유지) |
| 비숫자 | `"SUS304"` | 셀 값 `"SUS304"` (문자열 유지) |
| Excel SUM | 금액 열에 `=SUM()` 수식 수동 입력 | 정상 합산 (문자열 에러 아님) |

### 회귀 테스트 (기존 기능 보존)

| 검증 항목 | 명령어 | 기대 결과 |
|---|---|---|
| Phase 1 | `python main.py "견적서.pdf"` | MD 출력 변경 없음 |
| Phase 2 | `python main.py "추출.md" --output json --preset pumsem` | JSON 출력 변경 없음 |
| Phase 3 기존 | `python main.py "추출.md" --output excel` | 견적서/내역서/조건 시트 구조 동일, 금액 열만 숫자 타입으로 개선 |

---

> 최초 작성: 2026-04-14 | 1차 보완: 2026-04-14 (갭 분석, 수정 설계, 검증 계획, 실행 순서 추가) | 2차 보완: 2026-04-14 (런타임 버그 4건 추가 — 문제 5~8, 수정 E~H, 검증 항목 확장)
