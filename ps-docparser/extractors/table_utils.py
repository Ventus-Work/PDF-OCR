"""
extractors/table_utils.py — 테이블 감지, bbox 검증/보정, 이미지 크롭 유틸리티

Why: 테이블 관련 저수준 처리를 한 모듈에 집중시켜
     hybrid_extractor.py가 비즈니스 로직에만 집중할 수 있게 한다.

이식 원본: step1_extract_gemini_v33.py L232~291, L472~509
"""

import logging
from PIL import Image

from config import TABLE_MIN_HEIGHT_RATIO, TABLE_BOTTOM_EXTRA_PADDING

logger = logging.getLogger(__name__)


def detect_tables(page) -> list[tuple]:
    """
    pdfplumber 페이지에서 테이블 bbox 목록을 반환한다.

    Returns:
        [(x0, y0, x1, y1), ...] 형식의 bbox 리스트. 감지 실패 시 [].

    이식 원본: step1_extract_gemini_v33.py L232~239
    """
    try:
        tables = page.find_tables()
        return [table.bbox for table in tables]
    except Exception as e:
        logger.warning(f"테이블 감지 실패: {e}")
        return []


def validate_and_fix_table_bboxes(
    table_bboxes: list, page_height: float, page_width: float
) -> tuple[list, bool]:
    """
    테이블 bbox를 검증하고 비정상인 경우 보정한다.

    Why: pdfplumber가 헤더 행만 잡아 매우 좁은 bbox를 반환할 때가 있다.
         이 경우 크롭 이미지가 헤더만 담아 AI가 본문을 볼 수 없다.
         → 다음 테이블 직전 또는 페이지 하단까지 bbox를 강제 확장한다.
         확장해도 페이지 절반 이상이면 전체 페이지 폴백이 더 낫다고 판단한다.

    Args:
        table_bboxes: detect_tables()가 반환한 bbox 리스트
        page_height: pdfplumber 페이지 높이 (포인트)
        page_width : pdfplumber 페이지 너비 (포인트, 현재 미사용, 확장성 고려)

    Returns:
        (보정된 bboxes, 전체페이지 폴백 필요 여부)

    이식 원본: step1_extract_gemini_v33.py L242~291
    """
    if not table_bboxes:
        return table_bboxes, False

    fixed_bboxes = []
    needs_fullpage_fallback = False

    for i, bbox in enumerate(table_bboxes):
        x0, y0, x1, y1 = bbox
        table_height = y1 - y0
        height_ratio = table_height / page_height

        if height_ratio < TABLE_MIN_HEIGHT_RATIO:
            # 비정상: 헤더만 잡혔을 가능성
            logger.info(
                f"테이블 {i+1} bbox 높이 비정상 "
                f"({height_ratio:.1%}, {table_height:.0f}pt / {page_height:.0f}pt)"
            )

            # 다음 테이블 직전까지, 없으면 페이지 하단 85%까지 확장
            if i + 1 < len(table_bboxes):
                new_y1 = table_bboxes[i + 1][1] - 5
            else:
                new_y1 = min(page_height * 0.85, page_height - 30)

            new_height = new_y1 - y0
            new_ratio = new_height / page_height

            if new_ratio > 0.5:
                # 확장해도 절반 이상이면 전체 페이지 폴백이 정확도 더 높음
                logger.info(f"  → 확장 시 페이지 {new_ratio:.0%} 차지 → 전체 페이지 Gemini 처리")
                needs_fullpage_fallback = True
                break
            else:
                logger.info(f"  → bbox 아래로 확장: {table_height:.0f}pt → {new_height:.0f}pt")
                fixed_bboxes.append((x0, y0, x1, new_y1))
        else:
            fixed_bboxes.append(bbox)

    return fixed_bboxes, needs_fullpage_fallback


def crop_table_image(
    page_image: Image.Image,
    bbox: tuple,
    page_height: float,
    page_width: float,
    extended: bool = False,
) -> Image.Image:
    """
    pdfplumber bbox를 PIL 이미지 좌표로 변환하여 테이블 영역을 크롭한다.

    Why: pdfplumber는 포인트 단위, PIL 이미지는 픽셀 단위이다.
         pdf2image의 렌더링 해상도에 따라 스케일이 다르므로
         page_image.width / page_width 비율로 정확히 변환해야 한다.

    Args:
        page_image: pdf2image로 렌더링된 PIL 이미지
        bbox: (x0, y0, x1, y1) 포인트 단위
        page_height: pdfplumber 페이지 높이 (포인트)
        page_width : pdfplumber 페이지 너비 (포인트)
        extended: True이면 아래쪽 패딩을 TABLE_BOTTOM_EXTRA_PADDING만큼 추가
                  (잘린 테이블 하단 캡처를 위한 개선2 로직)

    Returns:
        크롭된 PIL Image

    이식 원본: step1_extract_gemini_v33.py L472~509
    """
    x0, y0, x1, y1 = bbox

    # 포인트 → 픽셀 스케일 변환
    scale_x = page_image.width / page_width
    scale_y = page_image.height / page_height

    img_x0 = int(x0 * scale_x)
    img_y0 = int(y0 * scale_y)
    img_x1 = int(x1 * scale_x)
    img_y1 = int(y1 * scale_y)

    # 기본 패딩 (10px)
    padding_x = 10
    padding_top = 10

    # [개선2] 아래쪽 패딩: 기본 10px → extended 시 TABLE_BOTTOM_EXTRA_PADDING 포인트 추가
    padding_bottom = int(TABLE_BOTTOM_EXTRA_PADDING * scale_y) if extended else 10

    # 이미지 경계 초과 방지
    img_x0 = max(0, img_x0 - padding_x)
    img_y0 = max(0, img_y0 - padding_top)
    img_x1 = min(page_image.width, img_x1 + padding_x)
    img_y1 = min(page_image.height, img_y1 + padding_bottom)

    return page_image.crop((img_x0, img_y0, img_x1, img_y1))


# ────────────────────────────────────────────────────────────────────────────
# Phase 4: K2 + K3 테이블 감지 개선
# 알고리즘 참조: kordoc (https://github.com/chrisryugj/kordoc)
# Copyright (c) chrisryugj, MIT License
# ────────────────────────────────────────────────────────────────────────────

VERTEX_MERGE_FACTOR = 4       # kordoc line-detector.ts
MIN_COORD_MERGE_TOL = 8       # kordoc line-detector.ts
DEFAULT_SNAP_TOLERANCE = 3    # pdfplumber 기본값


def calculate_dynamic_tolerance(page) -> dict:
    """
    페이지의 선 두께를 분석하여 동적 허용 오차를 계산한다 (K3).

    Why: pdfplumber의 snap_tolerance=3, join_tolerance=3은 고정 상수로,
         선이 두꺼운 문서(건설 도면 등)에서는 테이블 감지에 실패한다.
         kordoc의 line-detector.ts 알고리즘을 참조하여
         선 두께에 비례하는 동적 허용 오차를 계산한다.

    Args:
        page: pdfplumber.Page 객체

    Returns:
        dict: {"snap_tolerance": float, "join_tolerance": float, "intersection_tolerance": float}
    """
    lines = page.lines or []

    if not lines:
        return {
            "snap_tolerance": DEFAULT_SNAP_TOLERANCE,
            "join_tolerance": DEFAULT_SNAP_TOLERANCE,
            "intersection_tolerance": DEFAULT_SNAP_TOLERANCE,
        }

    # 수평/수직 선의 두께 수집
    h_widths = []
    v_widths = []

    for line in lines:
        lw = line.get("lineWidth", line.get("stroke_width", 1))
        if lw is None:
            lw = 1
        # 수평선: y0 ≈ y1
        if abs(line.get("y0", 0) - line.get("y1", 0)) < 2:
            h_widths.append(lw)
        else:
            v_widths.append(lw)

    max_h = max(h_widths) if h_widths else 1
    max_v = max(v_widths) if v_widths else 1

    # kordoc 공식: 선 두께 × 4, 최소 8
    vertex_radius = max(max_h, max_v) * VERTEX_MERGE_FACTOR
    coord_merge_tol = max(MIN_COORD_MERGE_TOL, vertex_radius)

    return {
        "snap_tolerance": coord_merge_tol / 2,
        "join_tolerance": coord_merge_tol,
        "intersection_tolerance": coord_merge_tol,
    }


def detect_tables_by_text_alignment(page) -> list[dict]:
    """
    선 없는 테이블을 텍스트 정렬 패턴으로 감지한다 (K2).

    Why: 일부 PDF(특히 OCR 재구성 문서)는 테이블에 선이 없다.
         pdfplumber는 선 기반 감지가 기본이므로 이런 테이블을 놓친다.
         kordoc의 cluster-detector.ts 알고리즘을 참조하여
         텍스트 아이템의 좌표 정렬 패턴으로 테이블을 감지한다.

    Args:
        page: pdfplumber.Page 객체

    Returns:
        list[dict]: 감지된 테이블 리스트
            각 dict: {"bbox": (x0,y0,x1,y1), "rows": [[str,...], ...]}
            빈 리스트 = 테이블 미감지
    """
    Y_TOL = 3.0                # Y좌표 행 그룹핑 허용 오차
    COL_CLUSTER_TOL = 15.0     # X좌표 열 클러스터링 허용 오차
    MIN_HEADER_ITEMS = 2       # 헤더 최소 아이템 수
    MAX_HEADER_ITEMS = 8       # 헤더 최대 아이템 수
    MIN_DATA_ROWS = 2          # 최소 데이터 행 수

    words = page.extract_words(
        keep_blank_chars=True,
        x_tolerance=3,
        y_tolerance=3,
    )

    if len(words) < 6:
        return []

    # Step 1: Y좌표 행 그룹핑
    sorted_words = sorted(words, key=lambda w: (w['top'], w['x0']))
    rows = []
    current_row = [sorted_words[0]]

    for w in sorted_words[1:]:
        if abs(w['top'] - current_row[0]['top']) <= Y_TOL:
            current_row.append(w)
        else:
            rows.append(current_row)
            current_row = [w]
    rows.append(current_row)

    if len(rows) < MIN_DATA_ROWS + 1:
        return []

    # Step 2: 헤더 행 후보 탐색
    header_idx = None
    for i, row in enumerate(rows):
        n_items = len(row)
        if MIN_HEADER_ITEMS <= n_items <= MAX_HEADER_ITEMS:
            avg_len = sum(len(w['text']) for w in row) / n_items
            x_range = max(w['x1'] for w in row) - min(w['x0'] for w in row)
            page_width = float(page.width)

            if avg_len < 15 and x_range > page_width * 0.3:
                header_idx = i
                break

    if header_idx is None:
        return []

    # Step 3: X좌표 열 클러스터링 (헤더 행 기준)
    header_row = rows[header_idx]
    col_centers = sorted([(w['x0'] + w['x1']) / 2 for w in header_row])

    # Step 4: 데이터 행 수집
    data_rows = rows[header_idx:]
    if len(data_rows) < MIN_DATA_ROWS + 1:
        return []

    # Step 5: 행을 열에 매핑하여 2D 배열 생성
    table_rows = []
    for row_words in data_rows:
        row_cells = [''] * len(col_centers)
        for w in row_words:
            center = (w['x0'] + w['x1']) / 2
            min_dist = float('inf')
            min_col = 0
            for ci, cc in enumerate(col_centers):
                dist = abs(center - cc)
                if dist < min_dist:
                    min_dist = dist
                    min_col = ci
            if min_dist < COL_CLUSTER_TOL:
                if row_cells[min_col]:
                    row_cells[min_col] += ' ' + w['text']
                else:
                    row_cells[min_col] = w['text']
        table_rows.append(row_cells)

    if len(table_rows) < MIN_DATA_ROWS:
        return []

    # bbox 계산
    all_words = [w for row in data_rows for w in row]
    x0 = min(w['x0'] for w in all_words)
    y0 = min(w['top'] for w in all_words)
    x1 = max(w['x1'] for w in all_words)
    y1 = max(w['bottom'] for w in all_words)

    return [{"bbox": (x0, y0, x1, y1), "rows": table_rows}]


def detect_tables(page) -> list[tuple]:
    """
    페이지에서 테이블 bbox 목록을 반환한다.

    [Phase 4 변경] K3 동적 허용 오차 + K2 텍스트 정렬 폴백 추가.

    감지 순서:
    1. K3: 선 두께 기반 동적 허용 오차 계산
    2. pdfplumber find_tables() (동적 허용 오차 적용)
    3. [폴백] K2: 텍스트 정렬 기반 감지 (find_tables 실패 시)

    Returns:
        [(x0, y0, x1, y1), ...] 형식의 bbox 리스트. 감지 실패 시 []
    """
    try:
        # K3: 동적 허용 오차 계산
        tolerance = calculate_dynamic_tolerance(page)
        table_settings = {
            "snap_tolerance": tolerance["snap_tolerance"],
            "join_tolerance": tolerance["join_tolerance"],
            "intersection_tolerance": tolerance["intersection_tolerance"],
        }

        # 1차: pdfplumber (K3 적용)
        tables = page.find_tables(table_settings=table_settings)
        if tables:
            return [t.bbox for t in tables]

        # 2차: K2 텍스트 정렬 폴백
        text_tables = detect_tables_by_text_alignment(page)
        if text_tables:
            return [t["bbox"] for t in text_tables]

        return []

    except Exception as e:
        logger.warning("테이블 감지 실패: %s", e)
        return []

