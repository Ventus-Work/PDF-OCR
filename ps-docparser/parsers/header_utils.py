"""
parsers/header_utils.py — 테이블 헤더/행 분류 유틸리티

Why: table_parser.py 분해(Phase 12 Step 12-1) 결과물.
     테이블 유형 분류·헤더 구조 분석·주석행 판별에 집중하는 순수 유틸 모듈.
     HTML 파싱 의존성 없음 (bs4 불필요).

원본: parsers/table_parser.py L242~480 (6개 함수)
"""

import re
import unicodedata


_RE_ASCII_ALNUM = re.compile(r"[A-Za-z0-9]")
_RE_CJK_OR_HANGUL = re.compile(
    r"[\u1100-\u11ff\u3130-\u318f\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7a3]"
)


def normalize_header_text(value: str) -> str:
    """
    헤더 문자열을 비교/조합하기 쉬운 canonical 형태로 정규화한다.

    Why:
        OCR/로컬 추출 결과에는 "단 가", "금 액", "單 價"처럼 글자 사이가
        떨어진 헤더가 자주 섞여 들어온다. 이 상태로는 다단 헤더 조합과
        이후 Excel 분류에서 동일 열로 인식되지 않으므로, 헤더 전용 정규화가 필요하다.
    """
    if value is None:
        return ""

    text = unicodedata.normalize("NFKC", str(value)).replace("\n", " ").strip()
    if not text:
        return ""

    if "_" in text:
        parts = [normalize_header_text(part) for part in text.split("_")]
        return "_".join(part for part in parts if part)

    text = re.sub(r"\s+", " ", text).strip()
    if (
        " " in text
        and _RE_CJK_OR_HANGUL.search(text)
        and not _RE_ASCII_ALNUM.search(text)
    ):
        text = text.replace(" ", "")

    return text


def _normalize_header_rows(grid: list[list[str]], n_header_rows: int) -> list[list[str]]:
    """헤더 행을 정규화하고 같은 길이로 패딩한다."""
    n_cols = max((len(row) for row in grid[:n_header_rows]), default=0)
    normalized_rows: list[list[str]] = []

    for row in grid[:n_header_rows]:
        normalized = [normalize_header_text(cell) for cell in row[:n_cols]]
        if len(normalized) < n_cols:
            normalized.extend([""] * (n_cols - len(normalized)))
        normalized_rows.append(normalized)

    return normalized_rows


def _forward_fill_parent_headers(header_rows: list[list[str]]) -> list[list[str]]:
    """
    다단 헤더의 상위 빈 칸을 좌측 부모 헤더로 보완한다.

    Why:
        colspan 이 확장된 결과 `["재료비", "", "노무비", ""]` 형태가 생기면,
        같은 열의 하위 헤더("금액" 등)와 단순 세로 결합 시 bare key 만 남는다.
        하위 헤더가 존재하는 경우에만 부모를 우측 전개해 `재료비_금액` 같은
        완전한 composite key 를 만든다.
    """
    if len(header_rows) < 2:
        return header_rows

    filled_rows = [row[:] for row in header_rows]
    n_rows = len(filled_rows)
    n_cols = len(filled_rows[0]) if filled_rows else 0

    for row_idx in range(n_rows - 1):
        last_parent = ""
        for col_idx in range(n_cols):
            current = filled_rows[row_idx][col_idx]
            if current:
                last_parent = current
                continue

            has_child = any(
                filled_rows[child_row][col_idx]
                for child_row in range(row_idx + 1, n_rows)
            )
            if last_parent and has_child:
                filled_rows[row_idx][col_idx] = last_parent

    return filled_rows


def classify_table(
    headers: list[str],
    rows: list[list[str]],
    type_keywords: dict = None,
) -> str:
    """
    테이블 헤더와 행 데이터를 분석하여 유형을 분류한다.

    Why: 품셈 문서에는 노무 단가표(A_품셈), 규모 기준표(B_규모기준),
         구분/내용 설명표(C_구분설명) 등 유형별로 다른 후처리가 필요하다.

    Args:
        headers: 헤더 문자열 리스트
        rows: 데이터 행 리스트 (list[str] 또는 list[dict])
        type_keywords: 유형 판별 키워드 딕셔너리.
                       None이면 "general" 반환 (범용 모드, 키워드 스캔 없음).
                       pumsem 프리셋 시 TABLE_TYPE_KEYWORDS 주입.
                       지원 키: "A_품셈", "A_품셈_행키워드", "B_규모기준", "C_구분설명"

    Returns:
        str: "general" | "A_품셈" | "B_규모기준" | "C_구분설명" | "D_기타"

    원본: table_parser.py L242~307
    변경점:
        - type_keywords=None → "general" 반환 (범용 모드)
        - [리뷰 반영 1] _LABOR_ROW_KEYWORDS 하드코딩 제거
          → type_keywords["A_품셈_행키워드"]로 외부 주입
    """
    # ── 범용 모드: 키워드 없으면 분류 불가 ──
    if not type_keywords:
        return "general"

    header_text = " ".join(headers).lower()

    # A 유형 판별 (헤더 키워드 매칭)
    a_keywords = type_keywords.get("A_품셈", [])
    if sum(1 for kw in a_keywords if kw in header_text) >= 2:
        return "A_품셈"

    # A 유형 보조 판별 (행 데이터 키워드 매칭)
    # [리뷰 반영 1] 노동자 직종 키워드를 presets에서 주입받는다.
    a_row_keywords = type_keywords.get("A_품셈_행키워드", [])
    if a_row_keywords and rows and len(rows) >= 2:
        labor_row_count = 0
        for row in rows:
            first_val = ""
            if isinstance(row, dict):
                first_val = str(list(row.values())[0]).replace(" ", "") if row else ""
            elif isinstance(row, (list, tuple)):
                first_val = str(row[0]).replace(" ", "") if row else ""
            if any(kw in first_val for kw in a_row_keywords):
                labor_row_count += 1
        if labor_row_count >= 2:
            return "A_품셈"

    # B, C 유형 판별
    if any(kw in header_text for kw in type_keywords.get("B_규모기준", [])):
        return "B_규모기준"
    if len(headers) == 2 and any(
        kw in header_text for kw in type_keywords.get("C_구분설명", [])
    ):
        return "C_구분설명"

    return "D_기타"


def _is_header_like_row(row: list[str]) -> bool:
    """
    행이 헤더처럼 보이는지 판단한다 (비숫자 셀 비율 > 50%).

    Why: 다단 헤더 감지를 위해 헤더 행과 데이터 행을 구분해야 한다.
         숫자보다 문자가 많으면 헤더 행으로 간주.

    Args:
        row: 셀 값 리스트

    Returns:
        bool: True면 헤더 유사 행

    원본: table_parser.py L310~330
    """
    if not row:
        return False
    non_numeric = sum(
        1 for v in row if v and not re.match(r'^[\d,.\-\s]*$', v)
    )
    return non_numeric > len(row) * 0.5


def _is_repeated_section_marker_row(row: list[str]) -> bool:
    """
    행 전체가 같은 구역명으로 반복 전개된 경우를 감지한다.

    예: <td colspan="13">1. TT03</td> 가 expand_table() 이후 모든 열에
    "1. TT03" 으로 채워지면, 헤더 3행이 아니라 구역 구분 행으로 보아야 한다.
    """
    non_empty = [str(cell).strip() for cell in row if str(cell).strip()]
    if len(non_empty) < 2:
        return False

    normalized = [normalize_header_text(cell) for cell in non_empty]
    if len(set(normalized)) != 1:
        return False

    marker = normalized[0]
    return bool(re.match(r"^\d+\.\s*\S+$", marker))


def detect_header_rows(grid: list[list[str]]) -> int:
    """
    2D 그리드에서 헤더 행 수를 결정한다 (1~3행).

    Why: 일부 테이블은 헤더가 2~3행에 걸쳐 있다.
         (예: "재료비" 아래에 "단가", "금액"이 분리된 경우)
         첫 행에 중복 값이 있거나 후속 행이 헤더 패턴이면 다단 헤더로 판단.

    Args:
        grid: expand_table()이 반환한 2D 배열

    Returns:
        int: 헤더 행 수 (1, 2, 또는 3)

    원본: table_parser.py L333~367
    """
    if not grid or len(grid) < 2:
        return 1

    # 첫 행에 중복 값이 있으면 colspan으로 병합된 다단 헤더 가능성
    has_dup_first = len(set(grid[0])) < len(grid[0])

    if has_dup_first and len(grid) >= 4:
        if _is_repeated_section_marker_row(grid[2]):
            return 2
        if (
            _is_header_like_row(grid[1])
            and _is_header_like_row(grid[2])
            and not _is_header_like_row(grid[3])
        ):
            return 3

    if has_dup_first and len(grid) >= 3:
        if _is_header_like_row(grid[1]):
            return 2

    return 1


def build_composite_headers(grid: list[list[str]], n_header_rows: int) -> list[str]:
    """
    다단 헤더 행을 하나의 헤더 리스트로 병합한다.

    Why: 2행 이상 헤더의 경우 상위 헤더와 하위 헤더를 "_"로 연결하여
         열별로 고유한 키를 생성한다.
         (예: "재료비" + "단가" → "재료비_단가")

    Args:
        grid: 2D 배열
        n_header_rows: 헤더 행 수 (detect_header_rows() 결과)

    Returns:
        list[str]: 열별 헤더 문자열 리스트

    원본: table_parser.py L370~399
    """
    if not grid:
        return []

    normalized_rows = _normalize_header_rows(grid, n_header_rows)
    if n_header_rows <= 1:
        return normalized_rows[0] if normalized_rows else []

    normalized_rows = _forward_fill_parent_headers(normalized_rows)

    headers = []
    n_cols = len(normalized_rows[0]) if normalized_rows else 0
    for c in range(n_cols):
        parts = []
        for r in range(n_header_rows):
            val = normalized_rows[r][c]
            if val and val not in parts:
                parts.append(val)
        headers.append("_".join(parts) if len(parts) > 1 else (parts[0] if parts else ""))
    return headers


def is_note_row(row: list[str], total_cols: int = 0) -> bool:
    """
    행이 주석/비고 행인지 판단한다.

    Why: 테이블 하단에 [주], ①②, 대시로 시작하는 비고 행이 있는 경우
         데이터 행과 분리하여 "notes_in_table"으로 보존해야 한다.

    감지 패턴 (한국 기술문서 범용 표기법):
        [주], 〔주〕, 【주】로 시작
        ①②③...⑩ 원문자로 시작
        ㉮㉯㉰...㉷ 원문자로 시작
        "- " 또는 "– "로 시작
        "비 고"로 시작
        단일 비어있지 않은 셀이 길거나 특정 패턴

    참고: 이 패턴들([주], ①② 등)은 한국 기술문서 범용 표기법이므로
          프리셋 분기 없이 항상 적용한다.

    Args:
        row: 셀 값 리스트
        total_cols: 전체 열 수 (단일 셀 span 감지용)

    Returns:
        bool: True면 주석 행

    원본: table_parser.py L402~455
    """
    text = " ".join(row).strip()
    if not text:
        return False

    non_empty = [c for c in row if c.strip()]

    if re.search(r'\[주\]|〔주〕|【주】', text):
        return True
    if re.search(r'^[①②③④⑤⑥⑦⑧⑨⑩]', text):
        return True
    if re.search(r'^[㉮㉯㉰㉱㉲㉳㉴㉵㉶㉷]', text):
        return True
    if text.startswith("- ") or text.startswith("– "):
        return True
    if re.match(r'^비\s*고', text):
        return True

    if len(non_empty) == 1:
        cell_text = non_empty[0]
        if len(cell_text) > 50:
            return True
        if re.match(r'^\(\d{4}\)\s*.+', cell_text):
            return True
        if re.match(r'^\d+-\d+(?:-\d+)?\s+.{4,}', cell_text):
            return True

    return False


def try_numeric(val: str) -> str:
    """
    셀 값 정제 — 공백 정리만 수행, 숫자 캐스팅은 하지 않는다.

    Why: 범용 파서 단계에서 int/float 변환을 하면 아래 문제가 발생한다:
         - "0015" → 15 : 식별번호/코드의 선행 0 소실
         - "15,000,000" → 15000000 : 콤마 포맷 비가역적 파괴
         숫자 변환은 DB 적재(Phase 3) 또는 도메인 프리셋에서
         명시적으로 수행해야 한다.

    [리뷰 반영 3]
    원본: table_parser.py L458~480
    변경점: int()/float() 캐스팅 완전 제거 → strip()만 수행

    Args:
        val: 셀 값 문자열

    Returns:
        str: 앞뒤 공백이 제거된 문자열 (타입 변환 없음)
    """
    if not isinstance(val, str):
        return val
    return val.strip()
