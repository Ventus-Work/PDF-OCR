"""
parsers/table_parser.py — HTML 테이블 파싱 및 구조 분석

Why: Phase 1의 AI 엔진이 출력한 HTML <table>에는 rowspan/colspan이 포함되어 있어
     단순 파싱으로는 2D 배열로 복원이 안 된다.
     이 모듈이 셀 병합을 전개하고, 헤더/데이터/주석 행을 분류하여
     JSON-ready 구조체로 변환한다.

원본:
    standalone_parser/html_utils.py (전체, 6개 함수)
    standalone_parser/parser.py L170~318 (6개 함수)

변경점 (원본 대비):
    - [리뷰 반영 1] classify_table(): _LABOR_ROW_KEYWORDS 하드코딩 제거
      → type_keywords["A_품셈_행키워드"]로 외부 주입 (SRP 준수)
    - [리뷰 반영 2] _make_soup(): lxml → html.parser 폴백 구조 도입
      (Windows C 컴파일러 없는 환경 대응)
    - [리뷰 반영 3] try_numeric(): int/float 캐스팅 제거, strip()만 수행
      (선행 0 소실, 콤마 포맷 파괴 방지)

Dependencies: beautifulsoup4 (필수), lxml (선택 — 미설치 시 html.parser 폴백)
"""

import html as html_module
import re

try:
    from bs4 import BeautifulSoup, Tag
except ImportError:
    raise ImportError(
        "parsers/table_parser.py에 beautifulsoup4 패키지가 필요합니다.\n"
        "설치: pip install beautifulsoup4 lxml"
    )


# ══════════════════════════════════════════════════════════
# 내부 유틸리티
# ══════════════════════════════════════════════════════════

def _make_soup(html: str) -> BeautifulSoup:
    """
    lxml 우선, 실패 시 html.parser 폴백으로 BeautifulSoup을 생성한다.

    Why: lxml은 속도와 malformed HTML 처리에서 우수하지만,
         Windows에서 C 컴파일러 없이 설치 실패가 빈번하다.
         html.parser는 Python 내장이므로 추가 설치 불필요.
         성능 차이는 이 프로젝트 사용 규모(수십 테이블)에서 무시 가능.

    [리뷰 반영 2]
    """
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


# ══════════════════════════════════════════════════════════
# html_utils.py 이식 (6개 함수)
# ══════════════════════════════════════════════════════════

def expand_table(table_tag: Tag) -> list[list[str]]:
    """
    HTML 테이블의 rowspan/colspan을 전개하여 2D 배열로 반환.

    Why: AI 엔진(Gemini 등)이 생성한 HTML에는 셀 병합이 포함되어 있다.
         단순하게 <tr>/<td>를 순회하면 병합 셀이 누락되거나 열이 어긋난다.
         이 함수는 그리드 방식으로 rowspan/colspan을 미리 전개하여
         완전한 2D 배열을 보장한다.

    Args:
        table_tag: BeautifulSoup Tag 객체 (<table>)

    Returns:
        list[list[str]]: 전개된 셀 값의 2D 배열.
        빈 tbody인 경우에도 thead 행은 포함하여 반환.

    원본: standalone_parser/html_utils.py L8~61
    """
    rows = table_tag.find_all("tr")
    if not rows:
        return []

    # 최대 열 수 추정 (colspan 합산)
    max_cols = 0
    for row in rows:
        cols = 0
        for cell in row.find_all(["td", "th"]):
            colspan = int(cell.get("colspan", 1))
            cols += colspan
        max_cols = max(max_cols, cols)

    if max_cols == 0:
        return []

    # 2D 그리드 초기화 (None = 아직 채워지지 않음)
    grid = [[None] * max_cols for _ in range(len(rows))]

    for r_idx, row in enumerate(rows):
        col_idx = 0
        for cell in row.find_all(["td", "th"]):
            # rowspan에 의해 이미 채워진 셀 건너뛰기
            while col_idx < max_cols and grid[r_idx][col_idx] is not None:
                col_idx += 1
            if col_idx >= max_cols:
                break

            rowspan = int(cell.get("rowspan", 1))
            colspan = int(cell.get("colspan", 1))
            text = extract_cell_text(cell)

            # rowspan × colspan 범위를 동일 값으로 채움
            for dr in range(rowspan):
                for dc in range(colspan):
                    nr, nc = r_idx + dr, col_idx + dc
                    if nr < len(grid) and nc < max_cols:
                        grid[nr][nc] = text

            col_idx += colspan

    # None(미채움 셀) → 빈 문자열
    for r in range(len(grid)):
        for c in range(max_cols):
            if grid[r][c] is None:
                grid[r][c] = ""

    return grid


def extract_cell_text(cell: Tag) -> str:
    """
    셀 요소에서 텍스트를 추출한다. 특수 인라인 태그는 텍스트 표기로 변환.

    변환 규칙:
        <sup>X</sup> → ^X  (예: 10<sup>-7</sup> → 10^-7)
        <sub>X</sub> → _X
        <br>, <br/>  → 공백

    Args:
        cell: BeautifulSoup Tag 객체 (<td> 또는 <th>)

    Returns:
        str: 정제된 셀 텍스트

    원본: standalone_parser/html_utils.py L64~80
    """
    inner = cell.decode_contents()
    inner = re.sub(r'<sup[^>]*>(.*?)</sup>', r'^\1', inner, flags=re.DOTALL)
    inner = re.sub(r'<sub[^>]*>(.*?)</sub>', r'_\1', inner, flags=re.DOTALL)
    inner = re.sub(r'<br\s*/?\s*>', ' ', inner, flags=re.IGNORECASE)
    inner = re.sub(r'<[^>]+>', ' ', inner)
    inner = html_module.unescape(inner)
    return clean_cell_text(inner)


def clean_cell_text(text: str) -> str:
    """
    셀 텍스트 정제 — 비파괴 공백 제거, 연속 공백 정리.

    Args:
        text: 원본 텍스트

    Returns:
        str: 정제된 텍스트

    원본: standalone_parser/html_utils.py L83~89
    """
    text = text.replace('\xa0', ' ')  # non-breaking space → 일반 공백
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def parse_html_table(html: str) -> list[list[str]]:
    """
    HTML 문자열에서 테이블을 파싱하여 2D 배열로 반환하는 편의 래퍼.

    Args:
        html: <table>...</table>을 포함하는 HTML 문자열

    Returns:
        list[list[str]]: rowspan/colspan 전개된 2D 배열. 테이블 없으면 [].

    원본: standalone_parser/html_utils.py L92~98
    변경점: [리뷰 반영 2] BeautifulSoup(html, "lxml") → _make_soup(html) 폴백 구조
    """
    soup = _make_soup(html)
    table = soup.find("table")
    if not table:
        return []
    return expand_table(table)


def extract_tables_from_text(text: str) -> list[dict]:
    """
    텍스트에서 모든 <table>...</table>을 추출하여 위치 정보와 함께 반환.

    Why: 섹션 raw_text에는 HTML 테이블과 일반 텍스트가 혼재한다.
         이 함수가 테이블의 시작/끝 위치를 기록하여 텍스트와 테이블을 분리할 때 사용.

    Args:
        text: 마크다운 + HTML 혼합 텍스트

    Returns:
        list[dict]: [{"html": str, "start": int, "end": int}, ...]
                    (빈 리스트 = 테이블 없음)

    원본: standalone_parser/html_utils.py L101~115
    """
    tables = []
    pattern = re.compile(r'<table[^>]*>.*?</table>', re.DOTALL | re.IGNORECASE)
    for m in pattern.finditer(text):
        tables.append({
            "html": m.group(),
            "start": m.start(),
            "end": m.end(),
        })
    return tables


def remove_tables_from_text(text: str) -> str:
    """
    텍스트에서 모든 <table>...</table> 태그를 제거한다.

    Why: 테이블 파싱 후 텍스트 정제를 위해 HTML 테이블 블록을 제거.

    Args:
        text: HTML 테이블이 포함된 텍스트

    Returns:
        str: 테이블이 제거된 텍스트 (앞뒤 공백 제거)

    원본: standalone_parser/html_utils.py L118~121
    """
    return re.sub(
        r'<table[^>]*>.*?</table>', '', text, flags=re.DOTALL | re.IGNORECASE
    ).strip()


# ══════════════════════════════════════════════════════════
# parser.py Table Parser 섹션 이식 (6개 함수)
# ══════════════════════════════════════════════════════════

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

    원본: standalone_parser/parser.py L174~196
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
    #   원본: 함수 내부 하드코딩 → 범용 파서 설계 위반
    #   수정: type_keywords["A_품셈_행키워드"]로 완전 분리
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

    원본: standalone_parser/parser.py L198~202
    """
    if not row:
        return False
    non_numeric = sum(
        1 for v in row if v and not re.match(r'^[\d,.\-\s]*$', v)
    )
    return non_numeric > len(row) * 0.5


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

    원본: standalone_parser/parser.py L204~214
    """
    if not grid or len(grid) < 2:
        return 1

    # 첫 행에 중복 값이 있으면 colspan으로 병합된 다단 헤더 가능성
    has_dup_first = len(set(grid[0])) < len(grid[0])

    if has_dup_first and len(grid) >= 4:
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

    원본: standalone_parser/parser.py L216~228
    """
    if n_header_rows == 1:
        return [h.strip() for h in grid[0]]

    headers = []
    n_cols = len(grid[0])
    for c in range(n_cols):
        parts = []
        for r in range(n_header_rows):
            val = grid[r][c].strip() if r < len(grid) and c < len(grid[r]) else ""
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

    원본: standalone_parser/parser.py L230~245
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
    원본: standalone_parser/parser.py L247~260
    변경점: int()/float() 캐스팅 완전 제거 → strip()만 수행

    Args:
        val: 셀 값 문자열

    Returns:
        str: 앞뒤 공백이 제거된 문자열 (타입 변환 없음)
    """
    if not isinstance(val, str):
        return val
    return val.strip()


def parse_single_table(
    html: str,
    section_id: str,
    table_idx: int,
    type_keywords: dict = None,
) -> dict | None:
    """
    단일 HTML 테이블을 구조화된 딕셔너리로 파싱한다.

    Why: expand_table()로 2D 배열을 얻은 뒤 헤더/데이터/주석을 분리하고,
         헤더 키 기반 dict 리스트로 변환하여 JSON 직렬화가 용이한 구조를 만든다.

    Args:
        html: <table>...</table> HTML 문자열
        section_id: 섹션 ID (table_id 생성에 사용)
        table_idx: 섹션 내 테이블 순번 (1부터 시작)
        type_keywords: 테이블 유형 분류 키워드 (None=범용, "general" 반환)

    Returns:
        dict | None:
            None이면 파싱 불가 (빈 테이블 등)
            {
                "table_id": "T-{section_id}-{idx:02d}",
                "type": str,               # classify_table() 결과
                "headers": list[str],
                "rows": list[dict],        # 헤더 키 기반 dict (값은 항상 str)
                "notes_in_table": list[str],
                "raw_row_count": int,
                "parsed_row_count": int,
            }

    원본: standalone_parser/parser.py L262~302
    변경점:
        - type_keywords 파라미터 추가 → classify_table()에 전달
        - try_numeric() 변경에 따라 rows의 값은 항상 str
    """
    soup = _make_soup(html)
    table_tag = soup.find("table")
    if not table_tag:
        return None

    grid = expand_table(table_tag)
    if not grid:
        return None

    table_id = f"T-{section_id}-{table_idx:02d}"

    # 헤더만 있고 데이터 없는 경우
    if len(grid) < 2:
        headers = [h.strip() for h in grid[0]]
        return {
            "table_id": table_id,
            "type": classify_table(headers, [], type_keywords),
            "headers": headers,
            "rows": [],
            "notes_in_table": [],
            "raw_row_count": 0,
            "parsed_row_count": 0,
        }

    n_header_rows = detect_header_rows(grid)
    headers = build_composite_headers(grid, n_header_rows)
    n_cols = len(headers)

    data_rows, note_rows = [], []
    for row in grid[n_header_rows:]:
        if is_note_row(row, n_cols):
            note_rows.append(" ".join(c for c in row if c.strip()))
        else:
            data_rows.append(row)

    table_type = classify_table(headers, data_rows, type_keywords)

    rows_as_dicts = []
    for row in data_rows:
        row_dict = {}
        for j, header in enumerate(headers):
            val = row[j] if j < len(row) else ""
            key = header if header else f"col_{j}"
            row_dict[key] = try_numeric(val)  # [리뷰 반영 3] str 유지
        # 모든 값이 빈 행 제외
        if any(v for v in row_dict.values() if v != "" and v is not None):
            rows_as_dicts.append(row_dict)

    return {
        "table_id": table_id,
        "type": table_type,
        "headers": headers,
        "rows": rows_as_dicts,
        "notes_in_table": note_rows,
        "raw_row_count": len(grid) - n_header_rows,
        "parsed_row_count": len(rows_as_dicts),
    }


def process_section_tables(
    section: dict,
    type_keywords: dict = None,
) -> dict:
    """
    섹션 dict 내의 모든 HTML 테이블을 파싱하여 섹션 dict에 추가한다.

    Why: 섹션의 raw_text에 여러 개의 <table>이 있을 수 있다.
         각 테이블을 parse_single_table()로 처리하고, 결과를 "tables" 키에 저장.
         테이블을 제거한 나머지 텍스트는 "text_without_tables" 키에 저장.

    Args:
        section: split_sections()가 반환한 섹션 dict
        type_keywords: 테이블 유형 분류 키워드 (None=범용)

    Returns:
        dict: 입력 section + "tables" 키 + "text_without_tables" 키 추가된 dict

    원본: standalone_parser/parser.py L304~318
    변경점: parse_single_table()에 type_keywords 전달
    """
    raw_text = section.get("raw_text", "")
    section_id = section.get("section_id", "unknown")
    table_htmls = extract_tables_from_text(raw_text)

    parsed_tables = []
    for idx, table_info in enumerate(table_htmls, 1):
        result = parse_single_table(table_info["html"], section_id, idx, type_keywords)
        if result:
            parsed_tables.append(result)

    return {
        **section,
        "tables": parsed_tables,
        "text_without_tables": remove_tables_from_text(raw_text),
    }
