"""
exporters/excel_classifier.py — Excel 출력용 테이블·행 분류 및 숫자 파싱

Why: Phase 12 Step 12-2 분해 결과물.
     테이블 유형 분류(_classify_table), 행 스타일 결정(_row_style),
     숫자 변환(_try_parse_number, _is_number)을 담당하는 분류 모듈.
     openpyxl 의존성 없음 — 순수 Python.

원본: exporters/excel_exporter.py L79~197 (4개 함수 + 2개 정규식 상수)
"""

import re

from parsers.header_utils import normalize_header_text

_PUMSEM_GENERIC_TYPES = {"A_품셈", "B_규모기준", "C_구분설명"}


# ═══════════════════════════════════════════════════════
# 테이블 분류
# ═══════════════════════════════════════════════════════

def _classify_table(table: dict) -> str:
    table_type = str(table.get("type", ""))
    if table_type in _PUMSEM_GENERIC_TYPES:
        return "generic"

    headers = [
        normalize_header_text(str(h).strip())
        for h in table.get("headers", [])
        if str(h).strip()
    ]
    compact_headers = [header.lower().replace(" ", "").replace("\n", "") for header in headers]
    header_str = " ".join(compact_headers)
    header_compact = "".join(compact_headers).replace("_", "")

    row_fragments = []
    for row in table.get("rows", [])[:3]:
        if isinstance(row, dict):
            row_fragments.extend(str(value).strip() for value in row.values())
        elif isinstance(row, (list, tuple)):
            row_fragments.extend(str(value).strip() for value in row)
        else:
            row_fragments.append(str(row).strip())
    row_text = "".join(row_fragments).replace(" ", "").lower()
    combined_text = f"{header_compact}{row_text}"

    condition_keywords = (
        "일반사항",
        "특기사항",
    )
    if any(keyword in combined_text for keyword in condition_keywords):
        return "condition"

    material_quote_headers = ("no", "품목", "치수", "수량", "단가", "단위", "공급가액")
    material_quote_hits = sum(1 for keyword in material_quote_headers if keyword in header_compact)
    if material_quote_hits >= 5:
        return "generic"

    header_counts: dict[str, int] = {}
    for header in headers:
        header_counts[header] = header_counts.get(header, 0) + 1

    has_cost_groups = any(keyword in header_compact for keyword in ("재료비", "노무비", "경비", "합계"))
    has_ambiguous_cost_headers = has_cost_groups and any(
        header_counts.get(keyword, 0) > 1 for keyword in ("단가", "금액")
    )
    if has_ambiguous_cost_headers:
        return "generic"

    if "품명" in header_compact and (
        "합계금액" in header_compact
        or any(keyword in header_compact for keyword in ("재료비", "노무비", "경비", "합계"))
    ):
        return "detail"

    estimate_keywords = (
        "명칭",
        "품명",
        "규격",
        "단위",
        "수량",
        "단가",
        "금액",
        "비고",
    )
    estimate_hanja_keywords = (
        "名稱",
        "規格",
        "單位",
        "數量",
        "單價",
        "金額",
        "備考",
    )
    estimate_hits = sum(1 for keyword in estimate_keywords if keyword in header_compact)
    estimate_hanja_hits = sum(1 for keyword in estimate_hanja_keywords if keyword in header_compact)
    if estimate_hits >= 4 or estimate_hanja_hits >= 4:
        return "estimate"
    if (
        any(keyword in header_compact for keyword in ("명칭", "품명", "名稱"))
        and any(keyword in header_compact for keyword in ("금액", "단가", "金額", "單價"))
    ):
        return "estimate"

    if table_type == "D_기타" and any(keyword in combined_text for keyword in condition_keywords):
        return "condition"

    bom_kws = ["dwgno", "size", "mat'l", "q'ty", "description", "mark", "weight"]
    matched_kws = sum(1 for kw in bom_kws if kw in header_str)
    if table_type in ("BOM_자재", "BOM_LINE_LIST") or matched_kws >= 2:
        return "bom_generic"

    return "generic"


# ═══════════════════════════════════════════════════════
# 숫자 파싱
# ═══════════════════════════════════════════════════════

_RE_NUMBER  = re.compile(r"^-?[\d,]+$")
_RE_NUMERIC = re.compile(r'^-?[\d,]+\.?\d*$')


def _is_number(val: str) -> bool:
    """정수형(콤마 포함) 여부 판별. 스타일 결정에만 사용."""
    return bool(_RE_NUMBER.match(val.strip()))


def _try_parse_number(value: str) -> int | float | None:
    """
    문자열을 숫자로 변환 시도. 변환 불가 시 None 반환.

    보호 규칙:
        선행 0: "0015" → None (식별자/코드 보호)
        대시 단독: "-" → None
        "0", "0.5" 등 정상 숫자는 변환 허용

    Why: Phase 2 try_numeric()은 선행 0 보호를 위해 캐스팅을 제거했다.
         숫자 변환은 Phase 3 Excel 출력 단계에서만 수행한다는 원칙에 따라 여기서 처리.

    [수정 D] 원본: excel_exporter.py L128~160
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


# ═══════════════════════════════════════════════════════
# 행 스타일 결정
# ═══════════════════════════════════════════════════════

_SECTION_KEYWORDS = re.compile(
    r"^(?:\d+\.|[가-힣]\.|[\d]+\)|[\d]+\s+[A-Z]|[IVX]+\.|[-─]|◆)",
    re.MULTILINE,
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

    [수정 F] all([]) == True 함정 수정:
        money_keys가 빈 리스트이면 all()이 True를 반환하여 비금액 테이블의
        모든 비숫자 행이 section으로 오판되는 버그를 방지.
        bool(money_keys)를 선행 조건으로 추가.

    원본: excel_exporter.py L171~197
    """
    first = str(row.get(first_col_key, "")).strip()

    money_keys = [k for k in row if "금액" in k or "금 액" in k]

    # [수정 F] bool(money_keys) 선행 조건
    all_money_empty = bool(money_keys) and all(
        not str(row.get(k, "")).strip() for k in money_keys
    )

    if all_money_empty and first and not _is_number(first):
        return "section"

    if _SUBTOTAL_KEYWORDS.search(first):
        return "subtotal"

    return "body"
