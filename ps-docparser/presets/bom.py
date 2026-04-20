"""
presets/bom.py — BOM(Bill of Materials) 프리셋

Why: ocr.py에 4곳에 산재한 BOM 키워드를 1곳으로 통합한다.
     pumsem.py, estimate.py와 동일한 인터페이스(get_*() 함수)를 제공.

     키워드 출처:
     - ocr.py L1262~1264 (BOM_MUST_HAVE 그룹 A/B/C)
     - ocr.py L1267~1271 (blacklist_keywords)
     - ocr.py L1291~1300 (_clean_bom_dataframe 인라인)
     - ocr.py L1452~1458 (KILL_KEYWORDS)
     - ocr.py L1924~1936 (row_noise_keywords)
     → 4곳을 통합하여 동기화 문제를 원천 해결
"""

# ── Phase 1: 부문명 (BOM 문서에 부문 구분 없음) ──
DIVISION_NAMES = None


# ── BOM 키워드 체계 ──
BOM_KEYWORDS = {
    # BOM 헤더 감지 (3그룹 AND 조건: A ∧ B ∧ C 모두 충족 필수)
    # 원본: ocr.py L1262~1264
    "bom_header_a": ["S/N", "SN", "MARK", "NO", "NO."],
    "bom_header_b": ["SIZE", "SPEC", "SPECIFICATION"],
    "bom_header_c": ["Q'TY", "QTY", "QUANTITY", "WT", "WEIGHT", "WT(KG)"],

    # LINE LIST 헤더 감지
    # 원본: ocr.py L1557~1562
    "ll_header_a": ["LINE NO", "LINE NO."],
    "ll_header_b": ["SN", "S/N"],
    "ll_header_c": ["ITEM", "REMARKS"],

    # 앵커 키워드 (섹션 시작 감지)
    "anchor_bom": ["BILL OF MATERIALS", "BILL OF MATERIAL"],
    "anchor_ll": ["LINE LIST"],

    # 블랙리스트 (BOM이 아닌 테이블 제외)
    # 원본: ocr.py L1267~1271
    "blacklist": [
        "CLIENT:", "CLIENT：",
        "CONTRACTOR:", "CONTRACTOR：",
        "PROJECT:", "PROJECT：",
        "TITLE:", "TITLE：",
        "DRAWING NO", "SCALE", "SUPPORT DWG", "DWG LIST",
    ],

    # 킬 키워드 (활성 섹션 즉시 종료)
    # 원본: ocr.py L1452~1458 통합
    "kill": [
        "TOTAL WEIGHT", "TOTAL:",
        "CLIENT:", "CLIENT：", "CONTRACTOR:", "CONTRACTOR：",
        "PROJECT:", "PROJECT：", "TITLE:", "TITLE：",
        "DRAWING NO", "SCALE", "DESCRIPTION",
        "YOUNGPOONG", "YOUNG POONG", "KERYCO",
        "ALL IN ONE", "NICKEL REFINERY",
        "GE PROCESS", "PROCESS REVISION",
    ],

    # 노이즈 행 키워드 (행 레벨 필터)
    # 원본: ocr.py L1291~1300 + L1924~1936 통합
    "noise_row": [
        "DRW'D", "CHK'D", "APP'D",
        "DETAIL DRAWINGS", "PIPE SUPPORT",
        "SUPPORT DWG", "DWG LIST",
    ],

    # REV 헤더 감지 마커 (3개 이상이면 REV 행)
    # 원본: ocr.py L1307~1310
    "rev_markers": ["REV", "DATE", "DESCRIPTION", "DRW'D"],
}

# BOM 전용 키워드 (BOM vs LINE LIST 구분용)
BOM_ONLY_KEYWORDS = ["WT(KG)", "WT (KG)", "WEIGHT", "MAT'L", "MATERIAL"]


# ── 한국어 BOM 테이블 키워드 ──
# 원본: ocr.py L722~742
KOREAN_TABLE_HEADERS = [
    "품목", "품명", "규격", "치수", "수량", "단가",
    "공급가액", "재질", "중량", "단위",
]

KOREAN_ITEM_PATTERNS = [
    r'H\s*형\s*강', r'각\s*파\s*이\s*프', r'원\s*파\s*이\s*프',
    r'철\s*근', r'철\s*판', r'앵\s*글', r'채\s*널',
]


# ── 이미지 전처리 설정 ──
IMAGE_SETTINGS = {
    "default_dpi": 400,              # 1차 OCR 해상도
    "retry_dpi": 600,                # 재시도 해상도
    "bom_crop_left_ratio": 0.45,     # 우측 55% (좌 45% 제거)
    "ll_crop_top_ratio": 0.50,       # 하단 50% (상 50% 제거)
}


# ── 테이블 분류 키워드 (Phase 2 table_parser 호환) ──
TABLE_TYPE_KEYWORDS = {
    "BOM_자재": ["S/N", "SIZE", "QTY", "WEIGHT", "MAT'L"],
    "BOM_LINE_LIST": ["LINE NO", "ITEM", "REMARKS"],
}


# ── 공개 인터페이스 (pumsem.py, estimate.py와 동일 패턴) ──

def get_bom_keywords() -> dict:
    """BOM 추출 키워드 전체를 반환한다."""
    return BOM_KEYWORDS


def get_image_settings() -> dict:
    """이미지 전처리 설정을 반환한다."""
    return IMAGE_SETTINGS


def get_table_type_keywords() -> dict:
    """Phase 2 table_parser 호환 테이블 분류 키워드."""
    return TABLE_TYPE_KEYWORDS


def get_division_names() -> str | None:
    """Phase 1 부문명 (BOM은 부문 구분 없음)."""
    return DIVISION_NAMES


def get_excel_config() -> dict | None:
    """
    Excel 출력 커스텀 설정.

    BOM은 현재 커스텀 시트 레이아웃이 불필요하므로 None 반환
    → ExcelExporter._build_generic_sheet() 사용.

    향후 BOM 전용 시트 포맷(고정 열 너비, 색상 등)이 필요하면
    estimate.py처럼 dict 반환으로 확장한다.
    """
    return None
