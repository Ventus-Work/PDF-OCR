"""
presets/estimate.py — 견적서(estimate) 전용 프리셋 설정

Why: 견적서 PDF는 품셈 문서와 다른 도메인 규칙:
     - 갑지(표지) + 내역서 2시트 구조가 표준
     - 표지에서 메타데이터(제출처, 금액, 공사명 등) 추출 필요
     - 합계/소계 행 시각적 강조
"""
import re
from pathlib import Path

# Why: config.py와 동일한 Path(__file__).resolve() 기반 경로 관리.
#      상대 경로는 실행 디렉터리에 따라 깨지므로 절대 경로 사용.
_PRESET_DIR = Path(__file__).resolve().parent          # presets/
_TEMPLATE_PATH = _PRESET_DIR.parent / "templates" / "견적서_양식.xlsx"


# ── 테이블 유형 분류 키워드 ──

TABLE_TYPE_KEYWORDS = {
    "E_견적요약": ["직접비", "간접비", "합계", "소계", "총 합 계"],
    "E_견적내역": ["재료비", "노무비", "경비", "합계", "단가", "금액"],
    "E_견적조건": ["일반사항", "특기사항", "납품", "결제조건"],
}


# ── 표지 메타데이터 정규식 ──

COVER_PATTERNS = {
    "client": re.compile(r'제\s*출\s*처\s*[:：]\s*(.+?)(?:\s*貴中|\s*$)', re.MULTILINE),
    "amount_text": re.compile(r'견적금액\s*[:：]\s*(.+?)(?:\s*원정|\s*$)', re.MULTILINE),
    "project": re.compile(r'현\s*장\s*명\s*[:：]\s*(.+?)$', re.MULTILINE),
    # Why: "경남"/"대표" 등 특정 지역명/단어 하드코딩 제거 → $ 범용 줄끝 앵커 사용
    "description": re.compile(r'공\s*사\s*명\s*[:：]\s*(.+?)$', re.MULTILINE),
    "item": re.compile(r'물\s*품\s*명\s*[:：]\s*(.+?)$', re.MULTILINE),
    "serial_no": re.compile(r'견적일련번호\s*[:：]\s*(\S+)', re.MULTILINE),
}


def extract_cover_metadata(clean_text: str) -> dict:
    """
    견적서 표지 텍스트에서 메타데이터를 추출한다.

    Args:
        clean_text: Phase 2 출력의 section["clean_text"]

    Returns:
        dict: client, amount_text, amount(int|None), project,
              description, item, serial_no
    """
    result = {}
    failed_keys = []
    for key, pattern in COVER_PATTERNS.items():
        match = pattern.search(clean_text)
        if match:
            result[key] = match.group(1).strip()
        else:
            result[key] = ""
            failed_keys.append(key)

    if failed_keys:
        print(f"   ⚠️ 표지 메타 추출 실패 필드: {', '.join(failed_keys)}")

    # 금액 문자열 → 정수 파싱
    amount_str = result.get("amount_text", "")
    amount_digits = re.sub(r'[^\d]', '', amount_str)
    result["amount"] = int(amount_digits) if amount_digits else None

    return result


# ── Excel 시트 구성 ──

EXCEL_SHEET_CONFIG = {
    "template_path": _TEMPLATE_PATH,   # 절대 경로 (없으면 key-value 폴백)
    "sheets": [
        {
            "name": "갑지",
            "type": "cover",
            "fields": {
                "title": "A1", "date": "I3", "client": "C4",
                "amount": "C5", "project": "C6", "description": "C7",
                "item": "C8", "serial_no": "C9",
            },
        },
        {
            "name": "내역서",
            "type": "detail",
            "source_table_type": "E_견적내역",
            "source_table_index": -1,
        },
        {
            "name": "요약",
            "type": "summary",
            "source_table_index": 0,
        },
    ],
}


# ── 합계/소계 행 판별 ──

SUMMARY_ROW_KEYWORDS = [
    "소 계", "소계", "합 계", "합계", "총 합 계", "총합계",
    "직접비", "간접비", "일반관리비",
]


def is_summary_row(row_data: dict) -> bool:
    """행이 합계/소계 행인지 판별한다."""
    for value in row_data.values():
        if isinstance(value, str):
            for keyword in SUMMARY_ROW_KEYWORDS:
                if keyword in value:
                    return True
    return False


# ── 공개 인터페이스 ──

def get_table_type_keywords() -> dict:
    return TABLE_TYPE_KEYWORDS


def get_excel_config() -> dict:
    return EXCEL_SHEET_CONFIG


def get_cover_patterns() -> dict:
    return COVER_PATTERNS
