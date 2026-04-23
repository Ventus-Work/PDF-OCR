"""
exporters/excel_classifier.py — Excel 출력용 테이블·행 분류 및 숫자 파싱

Why: Phase 12 Step 12-2 분해 결과물.
     테이블 유형 분류(_classify_table), 행 스타일 결정(_row_style),
     숫자 변환(_try_parse_number, _is_number)을 담당하는 분류 모듈.
     openpyxl 의존성 없음 — 순수 Python.

원본: exporters/excel_exporter.py L79~197 (4개 함수 + 2개 정규식 상수)
"""

import re


# ═══════════════════════════════════════════════════════
# 테이블 분류
# ═══════════════════════════════════════════════════════

def _classify_table(table: dict) -> str:
    """
    headers 패턴으로 테이블 목적을 판별한다.

    반환값:
        "estimate"   견적서 요약 (NO/명 칭/금 액/...)
        "detail"     내역서 상세 (품명/합계_금액/...)
        "condition"  조건 (일반사항/특기사항)
        "generic"    분류 불가 → Table_N 시트로 원본 보존  [수정 A]

    원본: excel_exporter.py L79~110
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
    if ("명칭" in header_str or "명 칭" in header_str) and (
        "금액" in header_str or "금 액" in header_str
    ):
        return "estimate"

    # type 힌트로 보조 판별
    t = table.get("type", "")
    if t == "D_기타":
        return "condition"

    # [P3] BOM-specific generic 판별 강화 (최소 2개 이상 키워드 일치 또는 명시적 타입)
    bom_kws = ["dwgno", "size", "mat'l", "q'ty", "description", "mark", "weight"]
    matched_kws = sum(1 for kw in bom_kws if kw in header_str)
    
    if t in ("BOM_자재", "BOM_LINE_LIST") or matched_kws >= 2:
        return "bom_generic"

    # [수정 A] "unknown" → "generic": 스킵 대신 범용 처리 경로로 전환
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
