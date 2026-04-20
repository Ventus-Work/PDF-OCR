"""
exporters/excel_exporter.py — Phase 3: JSON → Excel 변환기

Why:
    parse_markdown()이 반환하는 sections JSON을 받아
    사람이 보기 좋은 Excel 견적서로 변환한다.

    테이블 유형(type) 기반 자동 시트 분류:
        헤더에 "명 칭" + "금 액" 포함  → 견적서 (요약 테이블)
        헤더에 "품명" + "합계_금액" 포함 → 내역서 (상세 테이블)
        헤더에 "일반사항" 또는 "특기사항" 포함 → 조건
        그 외 → generic (Table_N 시트에 원본 그대로 보존)  ← [수정 A]

    출력 구조:
        견적서.xlsx
            견적서    ← T-doc-01 스타일 (NO/명칭/규격/단위/수량/단가/금액/비고)
            내역서    ← T-doc-03 스타일 (품명/규격/단위/수량/재료비~합계/비고)
            조건      ← T-doc-02 스타일 (일반사항/특기사항) [선택, 있을 때만]
            Table_N   ← 범용 시트 (BOM, 거래명세서 등 분류 불가 테이블)  ← [수정 C]

공개 API:
    export(sections, output_path, *, title=None) → Path

수정 이력 (Phase3_수정_보고서.md 기준):
    수정 A: _classify_table() "unknown" → "generic" 반환
    수정 B: export() generic 분기 + Table_N 시트 생성
    수정 C: _build_generic_sheet() 신규 함수
    수정 D: _try_parse_number() 신규 함수 (기술서 L547-585 스펙)
    수정 E: _build_condition_sheet() dedup set → prev_row_vals dict
    수정 F: _row_style() all([]) == True 함정 수정
    수정 G: wb.save() PermissionError 처리
    수정 H: _build_generic_sheet() 내 헤더 없는 테이블 폴백
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl import Workbook
from openpyxl.styles import (
    Alignment, Border, Font, PatternFill, Side
)
from openpyxl.utils import get_column_letter


# ═══════════════════════════════════════════════════════
# 1. 스타일 상수
# ═══════════════════════════════════════════════════════

_THIN = Side(style="thin")
_THICK = Side(style="medium")
_BORDER_ALL = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_BORDER_HEADER = Border(left=_THICK, right=_THICK, top=_THICK, bottom=_THICK)

_FILL_HEADER  = PatternFill("solid", fgColor="1F3864")   # 진남색
_FILL_SECTION = PatternFill("solid", fgColor="D6E4F0")   # 연청색 (구분행)
_FILL_SUBTOTAL = PatternFill("solid", fgColor="FFF2CC")  # 연노랑 (소계/합계행)
_FILL_TITLE   = PatternFill("solid", fgColor="2E75B6")   # 중간 파랑 (문서 제목)

_FONT_HEADER  = Font(name="맑은 고딕", bold=True, color="FFFFFF", size=9)
_FONT_TITLE   = Font(name="맑은 고딕", bold=True, color="FFFFFF", size=11)
_FONT_SECTION = Font(name="맑은 고딕", bold=True, size=9)
_FONT_SUBTOTAL = Font(name="맑은 고딕", bold=True, color="C00000", size=9)
_FONT_BODY    = Font(name="맑은 고딕", size=9)
_FONT_NOTE    = Font(name="맑은 고딕", italic=True, size=8, color="595959")

_ALIGN_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
_ALIGN_LEFT   = Alignment(horizontal="left",   vertical="center", wrap_text=True)
_ALIGN_RIGHT  = Alignment(horizontal="right",  vertical="center")


# ═══════════════════════════════════════════════════════
# 2. 테이블 분류 헬퍼
# ═══════════════════════════════════════════════════════

def _classify_table(table: dict) -> str:
    """
    headers 패턴으로 테이블 목적을 판별한다.

    반환값:
        "estimate"   견적서 요약 (NO/명 칭/금 액/...)
        "detail"     내역서 상세 (품명/합계_금액/...)
        "condition"  조건 (일반사항/특기사항)
        "generic"    분류 불가 → Table_N 시트로 원본 보존  [수정 A: "unknown" → "generic"]
    """
    headers = [h.lower().replace(" ", "") for h in table.get("headers", [])]
    header_str = " ".join(headers)

    # 조건 테이블: 일반사항 또는 특기사항
    if "일반사항" in header_str or "특기사항" in header_str:
        return "condition"

    # 내역서: 품명 + 합계_금액 (복합 헤더)
    if "품명" in header_str and "합계_금액" in header_str:
        return "detail"

    # 견적서: 명칭(명 칭) + 금액(금 액)
    if ("명칭" in header_str or "명 칭" in header_str) and ("금액" in header_str or "금 액" in header_str):
        return "estimate"

    # type 힌트로 보조 판별
    t = table.get("type", "")
    if t == "D_기타":
        return "condition"

    # [수정 A] "unknown" → "generic": 스킵 대신 범용 처리 경로로 전환
    return "generic"


# ═══════════════════════════════════════════════════════
# 3. 숫자 파싱 헬퍼
# ═══════════════════════════════════════════════════════

_RE_NUMBER = re.compile(r"^-?[\d,]+$")

def _is_number(val: str) -> bool:
    return bool(_RE_NUMBER.match(val.strip()))


# [수정 D] _try_parse_number(): 기술서 L547-585 스펙 구현
# Phase 2의 try_numeric()은 선행 0 보호를 위해 캐스팅을 제거했다.
# 숫자 변환은 Phase 3 Excel 출력 단계에서만 수행한다는 기술서 원칙에 따라 여기서 처리.
_RE_NUMERIC = re.compile(r'^-?[\d,]+\.?\d*$')

def _try_parse_number(value: str) -> int | float | None:
    """
    문자열을 숫자로 변환 시도. 변환 불가 시 None 반환.

    보호 규칙:
        선행 0: "0015" → None (식별자/코드 보호)
        대시 단독: "-" → None
        "0", "0.5" 등 정상 숫자는 변환 허용
    """
    if not isinstance(value, str) or not value.strip():
        return None

    val = value.strip()

    if val == "-":
        return None

    # 패턴 먼저 확인 (숫자+콤마+소수점+음수 구조만 허용)
    if not _RE_NUMERIC.match(val):
        return None

    # 선행 0 보호 ("0015" → None, "0" → 0, "0.5" → 0.5)
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


_SECTION_KEYWORDS = re.compile(
    r"^(?:\d+\.|[가-힣]\.|[\d]+\)|[\d]+\s+[A-Z]|[IVX]+\.|[-─]|◆)",
    re.MULTILINE
)
_SUBTOTAL_KEYWORDS = re.compile(
    r"소\s*계|합\s*계|소계|합계|총합계|계\s*$|간접비|직접비\s*소계"
)

def _row_style(row: dict, first_col_key: str) -> str:
    """
    행의 렌더링 스타일을 결정한다.

    반환:
        "section"   구분/그룹 제목행 (배경: 연청색)
        "subtotal"  소계/합계행 (글자: 빨강, 배경: 연노랑)
        "body"      일반 데이터 행
    """
    first = str(row.get(first_col_key, "")).strip()

    # 금액 컬럼이 모두 비어 있고 첫 셀에 구분명 → section
    money_keys = [k for k in row if "금액" in k or "금 액" in k]

    # [수정 F] all([]) == True 함정 수정
    # money_keys가 빈 리스트이면 all()이 True를 반환하여 비금액 테이블의
    # 모든 비숫자 행이 section으로 오판되는 버그를 방지.
    # bool(money_keys)를 선행 조건으로 추가: 빈 리스트 → False → section 판별 건너뜀.
    all_money_empty = bool(money_keys) and all(not str(row.get(k, "")).strip() for k in money_keys)

    if all_money_empty and first and not _is_number(first):
        return "section"

    if _SUBTOTAL_KEYWORDS.search(first):
        return "subtotal"

    return "body"


# ═══════════════════════════════════════════════════════
# 4. 셀 스타일 적용 헬퍼
# ═══════════════════════════════════════════════════════

def _apply_style(cell, fill=None, font=None, align=None, border=_BORDER_ALL):
    if fill:
        cell.fill = fill
    if font:
        cell.font = font
    if align:
        cell.alignment = align
    if border:
        cell.border = border


# ═══════════════════════════════════════════════════════
# 5. 견적서 시트 빌더
# ═══════════════════════════════════════════════════════

def _build_estimate_sheet(ws, table: dict, doc_title: str):
    """
    견적서 시트(요약 테이블) 작성.

    컬럼 레이아웃: NO | 명칭 | 규격 | 단위 | 수량 | 단가 | 금액 | 비고
    """
    headers = table.get("headers", [])
    rows    = table.get("rows", [])

    if not headers:
        return

    # ── 문서 제목 행 ──
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    title_cell = ws.cell(row=1, column=1, value=doc_title or "견  적  서")
    _apply_style(title_cell, fill=_FILL_TITLE, font=_FONT_TITLE,
                 align=_ALIGN_CENTER, border=_BORDER_HEADER)
    ws.row_dimensions[1].height = 28

    # ── 헤더 행 ──
    for col_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=2, column=col_idx, value=h)
        _apply_style(cell, fill=_FILL_HEADER, font=_FONT_HEADER,
                     align=_ALIGN_CENTER, border=_BORDER_ALL)
    ws.row_dimensions[2].height = 20

    # ── 데이터 행 ──
    first_key = headers[0]
    for row_idx, row in enumerate(rows, start=3):
        style = _row_style(row, first_key)
        ws.row_dimensions[row_idx].height = 16

        for col_idx, h in enumerate(headers, start=1):
            raw_val = str(row.get(h, "")).strip()
            cell = ws.cell(row=row_idx, column=col_idx)

            # [수정 D] 숫자 변환 적용: 금액·단가 컬럼 → int/float로 저장
            numeric = _try_parse_number(raw_val)
            if numeric is not None and col_idx >= 5:
                cell.value = numeric
                cell.number_format = '#,##0'
            else:
                cell.value = raw_val

            val = raw_val  # 스타일 판별용

            if style == "section":
                _apply_style(cell, fill=_FILL_SECTION, font=_FONT_SECTION,
                             align=_ALIGN_LEFT, border=_BORDER_ALL)
            elif style == "subtotal":
                _apply_style(cell, fill=_FILL_SUBTOTAL, font=_FONT_SUBTOTAL,
                             align=_ALIGN_RIGHT if (_is_number(val) or numeric is not None) else _ALIGN_LEFT,
                             border=_BORDER_ALL)
            else:
                if numeric is not None and col_idx >= 5:
                    _apply_style(cell, font=_FONT_BODY, align=_ALIGN_RIGHT, border=_BORDER_ALL)
                elif col_idx == 1:
                    _apply_style(cell, font=_FONT_BODY, align=_ALIGN_CENTER, border=_BORDER_ALL)
                else:
                    _apply_style(cell, font=_FONT_BODY, align=_ALIGN_LEFT, border=_BORDER_ALL)

    # ── 주석 행 ──
    notes = table.get("notes_in_table", [])
    if notes:
        note_row = len(rows) + 3
        note_cell = ws.cell(row=note_row, column=1,
                            value="※ " + " / ".join(notes))
        _apply_style(note_cell, font=_FONT_NOTE, align=_ALIGN_LEFT, border=None)
        ws.merge_cells(start_row=note_row, start_column=1,
                       end_row=note_row, end_column=len(headers))

    # ── 컬럼 폭 설정 ──
    col_widths = {1: 6, 2: 28, 3: 14, 4: 6, 5: 7, 6: 14, 7: 14, 8: 12}
    for col_idx in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = col_widths.get(col_idx, 12)


# ═══════════════════════════════════════════════════════
# 6. 내역서 시트 빌더
# ═══════════════════════════════════════════════════════

# 내역서 복합 헤더 그룹 정의
# (그룹명, 포함 서브헤더 키워드 목록)
_DETAIL_HEADER_GROUPS = [
    ("품명",   ["품명"]),
    ("규격",   ["규격"]),
    ("단위",   ["단위"]),
    ("수량",   ["수량"]),
    ("재료비", ["재료비_단가", "재료비_금액"]),
    ("노무비", ["노무비_단가", "노무비_금액"]),
    ("경비",   ["경비_단가",   "경비_금액"]),
    ("합계",   ["합계_단가",   "합계_금액"]),
    ("비고",   ["비고"]),
]


def _build_detail_sheet(ws, table: dict, doc_title: str):
    """
    내역서 시트(상세 테이블) 작성.

    복합 헤더 2행 구조:
        행1: 품명 | 규격 | 단위 | 수량 | 재료비(병합) | 노무비(병합) | 경비(병합) | 합계(병합) | 비고
        행2:  -   |  -   |  -   |  -   | 단가 | 금액  | 단가 | 금액 | 단가 | 금액 | 단가 | 금액 |  -
    """
    headers = table.get("headers", [])
    rows    = table.get("rows", [])

    if not headers:
        return

    # 실제 존재하는 헤더 필터링 (부분 일치 허용, e.g. "품명_1. FILTER PRESS AREA" -> "품명" 매칭)
    existing = set(headers)
    active_groups = []
    for grp, subs in _DETAIL_HEADER_GROUPS:
        active_subs = []
        for exact_sub in subs:
            # 완전 일치 먼저 확인
            if exact_sub in existing:
                active_subs.append(exact_sub)
            else:
                # 부분 일치 찾기 (키워드로 시작하는 컬럼명 허용)
                for exist_header in existing:
                    if exist_header.startswith(exact_sub + "_") or exist_header == exact_sub:
                        active_subs.append(exist_header)
                        break # 첫 번째 매칭만 사용

        if active_subs:
            active_groups.append((grp, active_subs))

    # 컬럼 순서 결정 (active_groups 기준 평탄화)
    col_order = []
    for _, subs in active_groups:
        col_order.extend(subs)

    total_cols = len(col_order)
    if total_cols == 0:
        return  # 매칭되는 헤더가 없으면 처리 불가


    # ── 문서 제목 행 ──
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_cols)
    title_cell = ws.cell(row=1, column=1, value=doc_title or "내  역  서")
    _apply_style(title_cell, fill=_FILL_TITLE, font=_FONT_TITLE,
                 align=_ALIGN_CENTER, border=_BORDER_HEADER)
    ws.row_dimensions[1].height = 28

    # ── 그룹 헤더 행 (행2) ──
    col_cursor = 1
    for grp_name, subs in active_groups:
        span = len(subs)
        if span > 1:
            ws.merge_cells(start_row=2, start_column=col_cursor,
                           end_row=2, end_column=col_cursor + span - 1)
        cell = ws.cell(row=2, column=col_cursor, value=grp_name)
        _apply_style(cell, fill=_FILL_HEADER, font=_FONT_HEADER,
                     align=_ALIGN_CENTER, border=_BORDER_ALL)
        # 병합 오른쪽 셀에도 스타일 적용 (openpyxl 요구사항)
        for extra in range(1, span):
            c = ws.cell(row=2, column=col_cursor + extra)
            _apply_style(c, fill=_FILL_HEADER, font=_FONT_HEADER,
                         align=_ALIGN_CENTER, border=_BORDER_ALL)
        col_cursor += span
    ws.row_dimensions[2].height = 18

    # ── 서브 헤더 행 (행3) ──
    for col_idx, sub_key in enumerate(col_order, start=1):
        # 서브 헤더 표시명: "재료비_단가" → "단가", 단일 컬럼은 그룹명 이미 표시
        if "_" in sub_key:
            label = sub_key.split("_")[1]
        else:
            label = ""  # 단일 컬럼은 그룹 행에서 이미 표시; 서브행은 비워둠
        cell = ws.cell(row=3, column=col_idx, value=label)
        _apply_style(cell, fill=_FILL_HEADER, font=_FONT_HEADER,
                     align=_ALIGN_CENTER, border=_BORDER_ALL)

        # 단일 컬럼(label이 빈 경우): 그룹 행(2)과 병합
        if not label:
            ws.merge_cells(start_row=2, start_column=col_idx,
                           end_row=3, end_column=col_idx)
    ws.row_dimensions[3].height = 18

    # ── 데이터 행 ──
    first_key = col_order[0] if col_order else headers[0]
    for row_idx, row in enumerate(rows, start=4):
        style = _row_style(row, first_key)
        ws.row_dimensions[row_idx].height = 16

        for col_idx, key in enumerate(col_order, start=1):
            raw_val = str(row.get(key, "")).strip()
            cell = ws.cell(row=row_idx, column=col_idx)

            is_money = key.endswith(("_단가", "_금액")) or key == "수량"

            # [수정 D] 금액/단가/수량 컬럼에 숫자 변환 적용
            numeric = _try_parse_number(raw_val) if is_money else None
            if numeric is not None:
                cell.value = numeric
                cell.number_format = '#,##0'
            else:
                cell.value = raw_val

            val = raw_val  # 스타일 판별용

            if style == "section":
                _apply_style(cell, fill=_FILL_SECTION, font=_FONT_SECTION,
                             align=_ALIGN_LEFT, border=_BORDER_ALL)
            elif style == "subtotal":
                _apply_style(cell, fill=_FILL_SUBTOTAL, font=_FONT_SUBTOTAL,
                             align=_ALIGN_RIGHT if (numeric is not None or is_money) else _ALIGN_LEFT,
                             border=_BORDER_ALL)
            else:
                if numeric is not None and is_money:
                    _apply_style(cell, font=_FONT_BODY, align=_ALIGN_RIGHT, border=_BORDER_ALL)
                elif col_idx == 1:
                    _apply_style(cell, font=_FONT_BODY, align=_ALIGN_LEFT, border=_BORDER_ALL)
                else:
                    _apply_style(cell, font=_FONT_BODY, align=_ALIGN_CENTER, border=_BORDER_ALL)

    # ── 컬럼 폭 설정 ──
    _col_widths = {
        "품명": 30, "규격": 14, "단위": 6, "수량": 8,
        "재료비_단가": 11, "재료비_금액": 11,
        "노무비_단가": 11, "노무비_금액": 11,
        "경비_단가": 11,   "경비_금액": 11,
        "합계_단가": 11,   "합계_금액": 11,
        "비고": 12,
    }
    for col_idx, key in enumerate(col_order, start=1):
        width = _col_widths.get(key, 12)
        ws.column_dimensions[get_column_letter(col_idx)].width = width


# ═══════════════════════════════════════════════════════
# 7. 조건 시트 빌더
# ═══════════════════════════════════════════════════════

def _build_condition_sheet(ws, table: dict):
    """
    조건 시트(일반사항/특기사항) 작성.
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
        ws.column_dimensions[get_column_letter(col_idx)].width = 45
    ws.row_dimensions[1].height = 18

    # ── 데이터 행 ──
    # [수정 E] seen_right(전역 set) → prev_row_vals(열 단위 직전 행 비교)
    # Why: 전역 set은 열/행 구분 없이 누적하여 다른 열·행의 동일 단어까지 삭제했다.
    # 올바른 suppression은 rowspan 전개로 인한 '같은 열의 수직 반복'만 제거해야 한다.
    prev_row_vals: dict[int, str] = {}  # 열 인덱스 → 직전 행 값
    for row_idx, row in enumerate(rows, start=2):
        ws.row_dimensions[row_idx].height = 16
        for col_idx, h in enumerate(headers, start=1):
            val = str(row.get(h, "")).strip()
            # 같은 열의 직전 행과 동일한 값이면 suppression (rowspan 전개 중복 제거)
            if col_idx > 1 and val and val == prev_row_vals.get(col_idx):
                display_val = ""
            else:
                display_val = val
            prev_row_vals[col_idx] = val  # 현재 값을 직전 행으로 갱신
            cell = ws.cell(row=row_idx, column=col_idx, value=display_val)
            _apply_style(cell, font=_FONT_BODY, align=_ALIGN_LEFT, border=_BORDER_ALL)


# ═══════════════════════════════════════════════════════
# 8. 범용 시트 빌더 [수정 C + 수정 H]
# ═══════════════════════════════════════════════════════

def _build_generic_sheet(ws, table: dict):
    """
    범용 테이블 시트 — 헤더/데이터를 원본 그대로 기록한다.

    Why: 분류 불가 테이블(BOM, 거래명세서, 공문서 등)을 유실하지 않고
         원데이터를 그대로 Excel에 옮긴다. 사용자가 수동 재편집 가능.

    [수정 H] 헤더 없는 테이블 폴백:
        headers=[], rows=[dict] → rows의 첫 dict 키를 헤더로 자동 생성
        headers=[], rows=[]    → 조용히 스킵
    """
    headers = table.get("headers", [])
    rows    = table.get("rows", [])

    # [수정 H] 헤더 없는 경우 폴백: rows의 키에서 헤더 자동 생성
    if not headers and rows:
        if isinstance(rows[0], dict):
            headers = list(rows[0].keys())
        if not headers:
            print(f"    ⚠️ 헤더·키 없는 테이블 스킵: {table.get('table_id', '?')}")
            return
    elif not headers:
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
            raw_val = str(row.get(h, "")).strip()
            cell = ws.cell(row=row_idx, column=col_idx)

            # [수정 D] 숫자 감지 → 숫자 타입으로 기록 + 콤마 포맷
            numeric = _try_parse_number(raw_val)
            if numeric is not None:
                cell.value = numeric
                cell.number_format = '#,##0'
                _apply_style(cell, font=_FONT_BODY, align=_ALIGN_RIGHT,
                             border=_BORDER_ALL)
            else:
                cell.value = raw_val
                _apply_style(cell, font=_FONT_BODY,
                             align=_ALIGN_CENTER if col_idx == 1 else _ALIGN_LEFT,
                             border=_BORDER_ALL)

    # ── 열 너비 자동 조정 (한글 2바이트 기준) ──
    for col_idx, h in enumerate(headers, start=1):
        header_len = sum(2 if ord(c) > 127 else 1 for c in h)
        width = max(header_len + 4, 10)
        for row in rows:
            val = str(row.get(h, ""))
            val_len = sum(2 if ord(c) > 127 else 1 for c in val)
            width = max(width, val_len + 2)
        ws.column_dimensions[get_column_letter(col_idx)].width = min(width, 50)


# ═══════════════════════════════════════════════════════
# 9. 공개 API
# ═══════════════════════════════════════════════════════

def _export_impl(
    sections: list[dict[str, Any]],
    output_path: str | Path,
    *,
    title: str | None = None,
) -> Path:
    """
    sections JSON을 Excel 파일로 변환한다.

    Args:
        sections:     parse_markdown()이 반환한 섹션 리스트
        output_path:  저장할 .xlsx 경로
        title:        문서 제목 (None이면 section title 또는 파일명 사용)

    Returns:
        저장된 Path 객체
    """
    wb = Workbook()
    # 기본 시트 제거
    wb.remove(wb.active)

    doc_title = title or ""

    # sections 전체를 순회하면서 테이블을 수집·분류
    estimate_tables:  list[dict] = []
    detail_tables:    list[dict] = []
    condition_tables: list[dict] = []
    generic_tables:   list[dict] = []  # [수정 B] generic 대기열 추가

    for section in sections:
        # 문서 제목 우선순위: 인수 > section.title > clean_text 첫 줄
        if not doc_title:
            doc_title = section.get("title", "")
        if not doc_title:
            clean = section.get("clean_text", "")
            doc_title = clean.split("\n")[0].strip()[:60] if clean else ""

        for tbl in section.get("tables", []):
            kind = _classify_table(tbl)
            if kind == "estimate":
                estimate_tables.append(tbl)
            elif kind == "detail":
                detail_tables.append(tbl)
            elif kind == "condition":
                condition_tables.append(tbl)
            elif kind == "generic":          # [수정 B] "unknown" 스킵 대신 generic 수집
                generic_tables.append(tbl)

    # ── 견적서 시트 ──
    if estimate_tables:
        ws_est = wb.create_sheet("견적서")
        ws_est.sheet_view.showGridLines = False
        _build_estimate_sheet(ws_est, estimate_tables[0], doc_title)
        # 2개 이상이면 뒤에 추가 시트
        for i, tbl in enumerate(estimate_tables[1:], start=2):
            ws_extra = wb.create_sheet(f"견적서_{i}")
            ws_extra.sheet_view.showGridLines = False
            _build_estimate_sheet(ws_extra, tbl, doc_title)

    # ── 내역서 시트 ──
    if detail_tables:
        ws_det = wb.create_sheet("내역서")
        ws_det.sheet_view.showGridLines = False
        _build_detail_sheet(ws_det, detail_tables[0], doc_title)
        for i, tbl in enumerate(detail_tables[1:], start=2):
            ws_extra = wb.create_sheet(f"내역서_{i}")
            ws_extra.sheet_view.showGridLines = False
            _build_detail_sheet(ws_extra, tbl, doc_title)

    # ── 조건 시트 ──
    if condition_tables:
        ws_cond = wb.create_sheet("조건")
        ws_cond.sheet_view.showGridLines = False
        _build_condition_sheet(ws_cond, condition_tables[0])

    # ── 범용 시트 (분류 불가 테이블) [수정 B] ──
    if generic_tables:
        for i, tbl in enumerate(generic_tables, start=1):
            title = tbl.get("title", "")
            if title:
                # If multiple generics have same title, append _i
                sheet_name = f"{title}_{i}" if len(generic_tables) > 1 and sum(1 for t in generic_tables if t.get("title") == title) > 1 else title
            else:
                sheet_name = f"Table_{i}" if len(generic_tables) > 1 else "Table"
                
            ws_gen = wb.create_sheet(sheet_name[:31])  # Excel 시트명 31자 제한
            ws_gen.sheet_view.showGridLines = False
            _build_generic_sheet(ws_gen, tbl)

    # ── 분류된 테이블이 하나도 없을 때 ── 원시 덤프
    if not estimate_tables and not detail_tables and not condition_tables and not generic_tables:
        ws_raw = wb.create_sheet("데이터")
        ws_raw.cell(row=1, column=1,
                    value="⚠ 분류 가능한 테이블이 없습니다. JSON을 확인하세요.")
        ws_raw.cell(row=1, column=1).font = Font(color="FF0000", bold=True)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # [수정 G] wb.save() PermissionError 처리
    # Why: Windows에서 Excel 파일이 열려 있는 채로 재실행하면 PermissionError 발생.
    # 파이썬 트레이스백 대신 사용자가 즉시 이해할 수 있는 한국어 메시지로 안내.
    try:
        wb.save(output_path)
    except PermissionError as e:
        from utils.io import ParserError
        raise ParserError(
            f"파일 저장 (권한 거부): {output_path.name}\n"
            f"  → 해당 파일이 Excel 등 다른 프로그램에서 열려 있는지 확인하세요.\n"
            f"  상세: {e}"
        )
    except OSError as e:
        from utils.io import ParserError
        raise ParserError(
            f"파일 저장 (I/O 오류): {output_path.name}\n"
            f"  → 디스크 공간이나 경로 길이를 확인하세요.\n"
            f"  상세: {e}"
        )

    return output_path


# ── 하위 호환 공개 API 별칭 ──
# Why: 기존 코드(main.py, _test_phase3.py)에서
#      from exporters.excel_exporter import export as excel_export 사용.
#      _export_impl으로 rename 후 이 별칭이 기존 import를 투명하게 유지.
export = _export_impl


# ── Phase 3-B: BaseExporter 클래스 인터페이스 ──

from exporters.base_exporter import BaseExporter  # noqa: E402


class ExcelExporter(BaseExporter):
    """JSON 섹션 리스트를 Excel 워크북으로 변환한다."""

    file_extension = ".xlsx"

    def export(
        self,
        sections: list[dict],
        output_path: Path,
        *,
        metadata: dict | None = None,
        preset_config: dict | None = None,
    ) -> Path:
        """
        BaseExporter 인터페이스 구현.

        현재는 _export_impl()에 위임한다.
        preset_config가 있으면 향후 _write_preset_sheets()로 분기.

        Why: _export_impl()은 수정 A~H로 실전 검증되었다.
             전면 리팩터 대신 위임 패턴으로 안전하게 클래스 인터페이스를 제공.
             Phase 4 이후 점진적으로 로직을 클래스 내부로 이전한다.
        """
        title = metadata.get("description") if metadata else None
        return _export_impl(sections, output_path, title=title)
