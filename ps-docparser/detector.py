"""
detector.py — 문서 유형 자동 감지기 (텍스트 기반)

Why: Phase 1 추출 완료 후의 MD 텍스트를 입력으로 받아
     키워드 매칭으로 문서 유형을 판별한다.
     --preset 미지정 시에만 동작하며, 확신도 낮으면 None 반환.

Dependencies: 없음 (순수 문자열 처리)
"""


# ── 키워드 정의 ──

ESTIMATE_KEYWORDS = [
    "見積", "견적", "견적금액", "내역서", "납품기일",
    "결제조건", "견적유효기간", "직접비", "간접비",
]

PUMSEM_KEYWORDS = [
    "품셈", "수량산출", "부문", "제6장", "단위당",
    "적용기준", "노무비", "참조", "보완",
]

# BOM 직접 감지 키워드 (영문 대우자 매칭, text_upper 사용)
# Why: BOM 도면은 영문이 대부분이므로 .upper()로 통일 및 estimate/pumsem 키워드와 충돌 없음
BOM_KEYWORDS = [
    "BILL OF MATERIALS", "BILL OF MATERIAL",
    "S/N", "MARK", "WT(KG)", "Q'TY", "MAT'L",
    "LINE LIST", "LINE NO",
]

# Why: 3→4 상향 — "견적", "노무비" 같은 단어가 아무 문서 도입부에도
#      등장할 수 있어 오탐 방지를 위해 임계값을 높임.
THRESHOLD = 4
THRESHOLD_BOM = 3  # BOM 키워드 매칭 임계값


def detect_document_type(text: str) -> str | None:
    """
    추출된 텍스트를 분석하여 문서 유형을 추정한다.

    Args:
        text: Phase 1 추출 결과 (MD 문자열)

    Returns:
        "estimate" | "pumsem" | "bom" | None (판별 불가 → 범용)
    """
    if not text or not text.strip():
        return None

    # 한염 키워드: 원문 사용
    estimate_score = sum(1 for kw in ESTIMATE_KEYWORDS if kw in text)
    pumsem_score = sum(1 for kw in PUMSEM_KEYWORDS if kw in text)

    if estimate_score >= THRESHOLD and estimate_score > pumsem_score:
        return "estimate"
    elif pumsem_score >= THRESHOLD and pumsem_score > estimate_score:
        return "pumsem"

    # BOM 키워드: 영문 대우자 통일어 매칭
    text_upper = text.upper()
    bom_score = sum(1 for kw in BOM_KEYWORDS if kw in text_upper)
    if bom_score >= THRESHOLD_BOM:
        return "bom"

    return None


def suggest_preset(text: str) -> str:
    """제안 메시지를 생성한다. 빈 문자열 = 제안 없음."""
    detected = detect_document_type(text)
    if detected == "estimate":
        return "💡 견적서로 감지되었습니다. --preset estimate 를 추가하면 견적서 양식으로 출력됩니다."
    elif detected == "pumsem":
        return "💡 품셈 문서로 감지되었습니다. --preset pumsem --toc <목차파일> 을 추가하면 품셈 양식으로 출력됩니다."
    elif detected == "bom":
        return "💡 BOM 도면으로 감지되었습니다. --preset bom --engine zai 를 추가하면 BOM Excel이 생성됩니다."
    return ""
