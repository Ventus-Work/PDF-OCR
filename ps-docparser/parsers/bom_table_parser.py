"""
parsers/bom_table_parser.py — BOM 테이블 파싱 (HTML/Markdown/공백 통합)

Why: ocr.py에서 3곳에 중복된 HTML 파싱, 2곳에 중복된 Markdown 파싱을
     1개 모듈로 통합한다. 3가지 형식을 자동 감지하여 2D 배열로 변환.

     ocr.py 결함 대응:
     - 문제 D: HTML <table> 파싱 3중 중복 → parse_html_bom_tables() 1개
     - 문제 E: 분기 3중 복붙 → parse_bom_table() 자동 형식 감지
"""
import re
import logging
from bs4 import BeautifulSoup

# 순환 import 방지: bom_extractor가 아닌 bom_types에서 import
from extractors.bom_types import BomSection, BomExtractionResult

logger = logging.getLogger(__name__)


def parse_html_bom_tables(
    text: str,
    keywords: dict,
) -> BomExtractionResult:
    """
    텍스트에서 HTML <table> 블록을 추출하고 BOM 여부를 판정한다.

    원본 참조: ocr.py L1330~1350
    변경점: pandas 의존 제거 → BeautifulSoup + 기존 expand_table() 재사용

    Process:
    1. 정규식으로 <table>...</table> 블록 추출
    2. 각 블록에 대해 BOM 헤더 키워드 A∧B∧C 검증
    3. 블랙리스트 키워드 체크
    4. expand_table() → 타이틀 행 스킵 → 실제 헤더/데이터 분리
    5. 행 필터링 (노이즈 제거)
    """
    from parsers.table_parser import expand_table  # 기존 rowspan/colspan 처리 재사용

    header_a  = keywords.get("bom_header_a", [])
    header_b  = keywords.get("bom_header_b", [])
    header_c  = keywords.get("bom_header_c", [])
    ll_hdr_a  = [kw.upper() for kw in keywords.get("ll_header_a", [])]
    ll_hdr_b  = [kw.upper() for kw in keywords.get("ll_header_b", [])]
    ll_hdr_c  = [kw.upper() for kw in keywords.get("ll_header_c", [])]
    blacklist = keywords.get("blacklist", [])
    noise_kw  = keywords.get("noise_row", [])

    # HTML <table> 블록 추출
    table_pattern = re.compile(
        r'<table[^>]*>.*?</table>', re.DOTALL | re.IGNORECASE
    )
    html_blocks = table_pattern.findall(text)

    # ZAI OCR 출력이 </table> 없이 잘린 경우 보완:
    # Why: ZAI가 빈 행 데이터를 출력하다 토큰 한도에 달하면 테이블 태그를 닫지 않고
    #      중간에 끊긴다. 이 경우 regex는 0개를 반환하지만 BeautifulSoup은
    #      불완전한 HTML도 파싱할 수 있으므로, <table> 시작 태그가 있으면
    #      해당 지점부터 끝까지 잘린 블록으로 추가 처리한다.
    if not html_blocks:
        open_tag = re.search(r'<table[^>]*>', text, re.IGNORECASE)
        if open_tag:
            truncated = text[open_tag.start():]
            html_blocks = [truncated]
            logger.debug("잘린 HTML 테이블 감지: %d자 처리", len(truncated))

    bom_sections = []
    ll_sections  = []

    for html_block in html_blocks:
        block_upper = html_block.upper()

        # ── 블록 타입 판정 ────────────────────────────────────────
        # 경로 1: BOM 키워드 A∧B∧C
        is_bom = (
            any(kw.upper() in block_upper for kw in header_a)
            and any(kw.upper() in block_upper for kw in header_b)
            and any(kw.upper() in block_upper for kw in header_c)
        )
        # 경로 2: LINE LIST 키워드 감지 (조건 완화)
        # Why: 이미지 도면에서 표가 깨지 거나 S/N의 / 가 유실될 경우를 대비해, 
        #      'LINE NO' 관련 핵심 키워드(ll_hdr_a)만 나타나도 LINE LIST로 식별한다.
        is_line_list = any(kw in block_upper for kw in ll_hdr_a)

        if not (is_bom or is_line_list):
            continue

        # 블랙리스트 체크 (BOM/LINE LIST 공통)
        if any(kw.upper() in block_upper for kw in blacklist):
            continue

        # expand_table()로 2D 배열 변환
        try:
            soup = BeautifulSoup(html_block, "html.parser")
            table_tag = soup.find("table")
            if not table_tag:
                continue
            grid = expand_table(table_tag)
        except Exception as e:
            logger.warning("HTML 테이블 파싱 실패: %s", e)
            continue

        if len(grid) < 2:
            continue

        # ── 타이틀 행 스킵 로직 ──────────────────────────────────
        # Z.ai는 BOM 제목(`BILL OF MATERIALS`, `LINE LIST`)을 colspan=N 단일 셀로 반환.
        # expand_table() 처리 후 해당 행의 모든 셀이 같은 값으로 채워진다.
        # → 이 행은 섹션 제목이므로 건너뛰고 다음 행을 실제 컬럼 헤더로 사용한다.
        section_title = None
        header_start = 0

        for i, row in enumerate(grid):
            non_empty = [str(c).strip() for c in row if str(c).strip()]
            unique_vals = set(non_empty)
            next_row_len = len(grid[i + 1]) if i + 1 < len(grid) else 0

            # 판정: unique 값이 1개(=colspan 복제) AND 다음 행이 더 많은 고유 열 보유
            # 단, 순수 숫자("1", "01" 등 개정번호)나 단일 문자("A")는 제목 행이 아님.
            # Why: ['', '', '', '1', ''] 같은 개정번호 행이 오탐되어 실제 헤더를
            #      타이틀 행 바로 다음 빈 행으로 밀어버리는 버그를 방지한다.
            single_val = list(unique_vals)[0] if unique_vals else ""
            is_title_row = (
                i < 2  # 타이틀 행은 표 최상단에 위치함 (데이터 중간의 소제목 오인 방지)
                and len(unique_vals) == 1
                and next_row_len > len(unique_vals)
                and not single_val.strip().isdigit()
                and len(single_val) >= 3
            )
            if is_title_row:
                section_title = list(unique_vals)[0]
                header_start = i + 1
                logger.debug("타이틀 행 감지 및 스킵: '%s' (grid[%d])", section_title, i)
                break

        effective_grid = grid[header_start:]
        if len(effective_grid) < 2:
            continue

        headers = effective_grid[0]
        rows = effective_grid[1:]

        # 다단 헤더(복합 헤더) 병합 (P2)
        if rows:
            sub_header_keywords = {"UNIT", "WEIGHT", "LOSS", "M2", "KG", "단위", "수량", "중량", "면적"}
            row0_upper = [str(c).upper().strip() for c in rows[0]]
            matched_count = sum(1 for c in row0_upper if any(kw in c for kw in sub_header_keywords))
            number_count = sum(1 for c in row0_upper if re.match(r"^-?[\d,.]+$", c))
            
            if matched_count >= 2 and number_count <= max(1, len(row0_upper) / 2):
                sub_headers = rows[0]
                rows = rows[1:]
                merged_headers = []
                last_valid_h1 = ""
                
                max_len = max(len(headers), len(sub_headers))
                for j in range(max_len):
                    h1_str = str(headers[j]).strip() if j < len(headers) else ""
                    h2_str = str(sub_headers[j]).strip() if j < len(sub_headers) else ""
                    
                    if h1_str:
                        last_valid_h1 = h1_str
                    else:
                        h1_str = last_valid_h1
                        
                    if h1_str and h2_str:
                        merged_headers.append(f"{h1_str} | {h2_str}")
                    elif h2_str:
                        merged_headers.append(h2_str)
                    else:
                        merged_headers.append(h1_str)
                headers = merged_headers
                logger.info("2행 복합 헤더 병합 완료: %s", headers)

        # 노이즈 행 필터링
        filtered = filter_noise_rows(rows, noise_kw)

        # LINE LIST vs BOM 분류
        # 우선순위: ① 타이틀 행 텍스트 → ② 블록 키워드 판정(is_line_list)
        title_upper = (section_title or "").upper()
        classify_as_ll = (
            "LINE LIST" in title_upper
            or "LINELIST" in title_upper
            or is_line_list  # 타이틀 없을 때 키워드 경로 플래그 활용
        )
        if classify_as_ll:
            ll_sections.append(BomSection(
                section_type="line_list",
                headers=headers,
                rows=filtered,
                raw_row_count=len(rows),
            ))
            logger.info("LINE LIST 테이블 감지: %d행", len(filtered))
        else:
            bom_sections.append(BomSection(
                section_type="bom",
                headers=headers,
                rows=filtered,
                raw_row_count=len(rows),
            ))
            logger.info("BOM 테이블 감지: %d행", len(filtered))


    return BomExtractionResult(
        bom_sections=bom_sections,
        line_list_sections=ll_sections,
    )


def parse_markdown_pipe_table(text: str) -> list[list[str]]:
    """
    Markdown 파이프(|) 형식 테이블을 2D 배열로 파싱한다.

    원본 참조: ocr.py L810~829

    입력 예시:
        | S/N | SIZE | MAT'L | Q'TY |
        |-----|------|-------|------|
        | 1   | 100A | SS304 | 2    |

    Returns:
        2D 배열 (헤더 포함), 테이블이 없으면 빈 리스트
    """
    rows = []
    for line in text.split('\n'):
        line = line.strip()
        if '|' not in line or line.count('|') < 2:
            continue

        cells = [c.strip() for c in line.split('|')]
        # 양쪽 빈 경계 제거
        if cells and cells[0] == '':
            cells = cells[1:]
        if cells and cells[-1] == '':
            cells = cells[:-1]

        # 구분선 건너뛰기 (---|---)
        if all(re.match(r'^[-:= ]+$', c) for c in cells if c):
            continue

        if cells:
            rows.append(cells)

    return rows


def parse_whitespace_table(text: str) -> list[list[str]]:
    """
    공백 2개 이상으로 구분된 테이블을 2D 배열로 파싱한다.

    원본 참조: ocr.py L831~852

    입력 예시:
        S/N  SIZE   MAT'L    Q'TY
        1    100A   SS304    2
    """
    rows = []
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue

        cells = re.split(r'\s{2,}', line)
        if len(cells) >= 3:
            rows.append(cells)

    return rows


def normalize_columns(
    rows: list[list[str]],
    *,
    reference_col_count: int | None = None,
) -> list[list[str]]:
    """
    열 수를 정규화한다.

    원본 참조: ocr.py L854~868 (패딩) + L831~852 (인접 셀 병합)

    - 짧은 행: 빈 셀로 패딩
    - 긴 행: 인접 최소 길이 셀 병합 (OCR 과분할 보정)
    """
    if not rows:
        return rows

    target = reference_col_count or max(len(r) for r in rows)
    result = []

    for row in rows:
        if len(row) == target:
            result.append(row)
        elif len(row) < target:
            # 패딩
            result.append(row + [''] * (target - len(row)))
        else:
            # 인접 최소 셀 병합
            merged = list(row)
            while len(merged) > target:
                min_len = float('inf')
                min_idx = 0
                for i in range(len(merged) - 1):
                    combined = len(merged[i]) + len(merged[i + 1])
                    if combined < min_len:
                        min_len = combined
                        min_idx = i
                merged[min_idx] = merged[min_idx] + ' ' + merged[min_idx + 1]
                merged.pop(min_idx + 1)
            result.append(merged)

    return result


def filter_noise_rows(
    rows: list[list[str]],
    noise_keywords: list[str],
) -> list[list[str]]:
    """
    노이즈 행을 필터링한다.

    원본 참조: ocr.py L1924~1936

    필터 기준:
    1. 킬/노이즈 키워드 포함 행 제거
    2. 완전 빈 행 제거
    3. 모든 셀이 동일한 행 제거 (OCR 아티팩트)
    """
    result = []
    for row in rows:
        joined_upper = ' '.join(str(c) for c in row).upper()

        # 노이즈 키워드 체크
        if any(kw.upper() in joined_upper for kw in noise_keywords):
            continue

        # 완전 빈 행 체크
        if all(not str(c).strip() for c in row):
            continue

        # 동일 셀 행 체크 (OCR 아티팩트)
        non_empty = [c for c in row if str(c).strip()]
        if len(non_empty) > 1 and len(set(str(c).strip() for c in non_empty)) == 1:
            continue

        result.append(row)
    return result


def parse_bom_rows(text: str) -> list[list[str]]:
    """
    텍스트를 자동 감지하여 BOM 행으로 파싱한다.

    자동 감지 우선순위:
    1. Markdown 파이프 (|) 형식
    2. 공백 2+ 구분 형식
    """
    # 1차: Markdown 파이프
    rows = parse_markdown_pipe_table(text)
    if rows:
        return normalize_columns(rows)

    # 2차: 공백 구분
    rows = parse_whitespace_table(text)
    if rows:
        return normalize_columns(rows)

    return []
