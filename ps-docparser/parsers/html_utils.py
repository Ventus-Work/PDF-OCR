"""
parsers/html_utils.py — HTML 테이블 저수준 파싱 유틸리티

Why: table_parser.py 분해(Phase 12 Step 12-1) 결과물.
     HTML 구조 파싱에만 집중하는 순수 유틸 모듈.
     오케스트레이션 로직(parse_single_table, process_section_tables)은
     table_parser.py에 유지.

원본: parsers/table_parser.py L40~235 (7개 함수)
"""

import html as html_module
import re

try:
    from bs4 import BeautifulSoup, Tag
except ImportError:
    raise ImportError(
        "parsers/html_utils.py에 beautifulsoup4 패키지가 필요합니다.\n"
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

    [리뷰 반영 2] 원본: table_parser.py L40~54
    """
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


# ══════════════════════════════════════════════════════════
# HTML 파싱 유틸 (원본: standalone_parser/html_utils.py)
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

    원본: table_parser.py L61~126
    """
    rows = table_tag.find_all("tr")
    if not rows:
        return []

    # 2D 그리드 초기화 (None = 아직 채워지지 않음)
    # rowspan 때문에 아래 행의 실제 열 수가 단순 colspan 합보다 커질 수 있어,
    # 고정 max_cols를 미리 잡지 않고 채우면서 동적으로 확장한다.
    grid: list[list[str | None]] = [[] for _ in range(len(rows))]

    for r_idx, row in enumerate(rows):
        col_idx = 0
        for cell in row.find_all(["td", "th"]):
            # rowspan에 의해 이미 채워진 셀 건너뛰기
            while col_idx < len(grid[r_idx]) and grid[r_idx][col_idx] is not None:
                col_idx += 1

            rowspan = int(cell.get("rowspan", 1))
            colspan = int(cell.get("colspan", 1))
            text = extract_cell_text(cell)
            required_cols = col_idx + colspan
            for grid_row in grid:
                if len(grid_row) < required_cols:
                    grid_row.extend([None] * (required_cols - len(grid_row)))

            # rowspan × colspan 범위를 동일 값으로 채움
            for dr in range(rowspan):
                for dc in range(colspan):
                    nr, nc = r_idx + dr, col_idx + dc
                    if nr < len(grid):
                        if len(grid[nr]) <= nc:
                            grid[nr].extend([None] * (nc + 1 - len(grid[nr])))
                        grid[nr][nc] = text

            col_idx += colspan

    max_cols = max((len(row) for row in grid), default=0)
    if max_cols == 0:
        return []

    # None(미채움 셀) → 빈 문자열
    for r in range(len(grid)):
        if len(grid[r]) < max_cols:
            grid[r].extend([None] * (max_cols - len(grid[r])))
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

    원본: table_parser.py L129~152
    """
    inner = cell.decode_contents()
    inner = re.sub(r'<sup[^>]*>(.*?)</sup>', r'^\1', inner, flags=re.DOTALL)
    inner = re.sub(r'<sub[^>]*>(.*?)</sub>', r'_\1', inner, flags=re.DOTALL)
    inner = re.sub(r'<br\s*/?\\s*>', ' ', inner, flags=re.IGNORECASE)
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

    원본: table_parser.py L155~169
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

    원본: table_parser.py L172~189
    변경점: [리뷰 반영 2] _make_soup() 폴백 구조 사용
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

    원본: table_parser.py L192~216
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

    원본: table_parser.py L219~235
    """
    return re.sub(
        r'<table[^>]*>.*?</table>', '', text, flags=re.DOTALL | re.IGNORECASE
    ).strip()
