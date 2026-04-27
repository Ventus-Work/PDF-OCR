"""Keyword-based document detection for generic and specialized routing."""

from __future__ import annotations

from dataclasses import dataclass


ESTIMATE_KEYWORDS = [
    "견적",
    "견적서",
    "견적금액",
    "내역서",
    "납품기일",
    "결제조건",
    "견적유효기간",
    "직접비",
    "간접비",
    "품목",
    "수량",
    "단가",
    "공급가액",
]

PUMSEM_KEYWORDS = [
    "품셈",
    "수량산출",
    "부문",
    "공종",
    "단위",
    "적용기준",
    "노무비",
    "참조",
    "보완",
]

BOM_KEYWORDS = [
    "BILL OF MATERIALS",
    "BILL OF MATERIAL",
    "S/N",
    "MARK",
    "WT(KG)",
    "Q'TY",
    "MAT'L",
    "LINE LIST",
    "LINE NO",
    "DESCRIPTION",
    "DWG NO",
    "UNIT",
    "WEIGHT",
    "LOSS",
]

BOM_STRUCTURE_KEYWORDS = [
    "S/N",
    "MARK",
    "WT(KG)",
    "Q'TY",
    "MAT'L",
    "DESCRIPTION",
    "DWG NO",
    "UNIT",
    "WEIGHT",
]

MATERIAL_QUOTE_KEYWORDS = [
    "견적서",
    "건명",
    "결정금액",
    "거래처",
    "공급가액",
    "항목",
    "품목",
    "사양",
    "치수",
    "수량",
    "단가",
    "중량",
    "메모",
]

THRESHOLD = 4
THRESHOLD_BOM = 3
THRESHOLD_MATERIAL_QUOTE = 5


@dataclass(frozen=True)
class DetectionResult:
    """Structured detector output used by auto-routing."""

    label: str | None
    confidence: str
    scores: dict[str, int]
    reason_hits: list[str]
    material_quote: bool
    suggestion: str


def _count_hits(text: str, keywords: list[str]) -> tuple[int, list[str]]:
    hits = [keyword for keyword in keywords if keyword in text]
    return len(hits), hits


def _material_quote_features(text: str) -> tuple[int, bool]:
    if not text or not text.strip():
        return 0, False

    compact = text.replace(" ", "").replace("\n", "")
    hits = [
        keyword
        for keyword in MATERIAL_QUOTE_KEYWORDS
        if keyword.replace(" ", "") in compact
    ]
    has_material_header = all(
        keyword in compact for keyword in ("항목", "치수", "수량", "단가", "공급가액")
    ) or all(
        keyword in compact for keyword in ("품목", "치수", "수량", "단가", "공급가액")
    )
    return len(hits), has_material_header


def _top_score(scores: dict[str, int], label: str) -> tuple[int, int]:
    selected = scores[label]
    others = [value for key, value in scores.items() if key != label]
    runner_up = max(others) if others else 0
    return selected, runner_up


def _resolve_confidence(
    *,
    label: str,
    scores: dict[str, int],
    bom_structure_hits: int,
) -> str:
    score, runner_up = _top_score(scores, label)

    if label in {"estimate", "pumsem"}:
        if score >= 6 and (score - runner_up) >= 2:
            return "high"
        if score >= 4 and (score - runner_up) >= 2:
            return "medium"
        return "low"

    if label == "bom":
        if score >= 5 and bom_structure_hits >= 2 and (score - runner_up) >= 2:
            return "high"
        if score >= THRESHOLD_BOM and score >= runner_up:
            return "medium"
        return "low"

    return "low"


def _build_suggestion(result: DetectionResult) -> str:
    if result.material_quote:
        return (
            "이 문서는 자재 견적서로 보입니다. --preset estimate 를 지정하면 견적서 경로로 처리합니다."
        )
    if result.label == "estimate":
        if result.confidence == "high":
            return (
                "이 문서는 estimate 성격이 강합니다. "
                "--preset estimate 를 지정하면 정식 견적서 경로로 처리합니다."
            )
        return "이 문서는 estimate 후보입니다. 필요하면 --preset estimate 를 시도해보세요."
    if result.label == "pumsem":
        if result.confidence == "high":
            return (
                "이 문서는 pumsem 성격이 강합니다. "
                "--preset pumsem 을 지정하면 품셈 경로로 처리합니다."
            )
        return "이 문서는 pumsem 후보입니다. 필요하면 --preset pumsem 을 시도해보세요."
    if result.label == "bom":
        if result.confidence == "high":
            return (
                "이 문서는 BOM 성격이 강합니다. "
                "--preset bom --engine zai 를 지정하면 BOM 전용 경로로 처리합니다."
            )
        return "이 문서는 BOM 후보입니다. 필요하면 --preset bom 을 시도해보세요."
    return ""


def detect_material_quote(text: str) -> bool:
    """Return True when the text looks like a material quotation document."""

    hits, has_material_header = _material_quote_features(text)
    return hits >= THRESHOLD_MATERIAL_QUOTE or has_material_header


def analyze_document_type(text: str) -> DetectionResult:
    """Analyze document text and return a structured routing hint."""

    empty_result = DetectionResult(
        label=None,
        confidence="low",
        scores={"estimate": 0, "pumsem": 0, "bom": 0},
        reason_hits=[],
        material_quote=False,
        suggestion="",
    )
    if not text or not text.strip():
        return empty_result

    estimate_score, estimate_hits = _count_hits(text, ESTIMATE_KEYWORDS)
    pumsem_score, pumsem_hits = _count_hits(text, PUMSEM_KEYWORDS)

    text_upper = text.upper()
    bom_score, bom_hits = _count_hits(text_upper, BOM_KEYWORDS)
    bom_structure_score, bom_structure_hits = _count_hits(text_upper, BOM_STRUCTURE_KEYWORDS)

    material_quote = detect_material_quote(text)
    scores = {
        "estimate": estimate_score,
        "pumsem": pumsem_score,
        "bom": bom_score,
    }
    if material_quote:
        scores["estimate"] = max(scores["estimate"], 6)
    reason_hits = (
        [f"estimate:{keyword}" for keyword in estimate_hits]
        + [f"pumsem:{keyword}" for keyword in pumsem_hits]
        + [f"bom:{keyword}" for keyword in bom_hits]
    )
    if material_quote:
        reason_hits.append("material_quote")

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_label, best_score = ranked[0]
    if best_score <= 0:
        return empty_result

    confidence = _resolve_confidence(
        label=best_label,
        scores=scores,
        bom_structure_hits=bom_structure_score,
    )
    if confidence == "low":
        result = DetectionResult(
            label=None,
            confidence="low",
            scores=scores,
            reason_hits=reason_hits,
            material_quote=False,
            suggestion="",
        )
        return DetectionResult(
            label=result.label,
            confidence=result.confidence,
            scores=result.scores,
            reason_hits=result.reason_hits,
            material_quote=result.material_quote,
            suggestion=_build_suggestion(result),
        )

    reason_hits.extend(
        f"bom_structure:{keyword}" for keyword in bom_structure_hits
    )
    result = DetectionResult(
        label=best_label,
        confidence=confidence,
        scores=scores,
        reason_hits=reason_hits,
        material_quote=material_quote,
        suggestion="",
    )
    return DetectionResult(
        label=result.label,
        confidence=result.confidence,
        scores=result.scores,
        reason_hits=result.reason_hits,
        material_quote=result.material_quote,
        suggestion=_build_suggestion(result),
    )


def detect_document_type(text: str) -> str | None:
    """Backward-compatible wrapper that returns only the label."""

    return analyze_document_type(text).label


def suggest_preset(text: str) -> str:
    """Backward-compatible wrapper that returns only the suggestion text."""

    return analyze_document_type(text).suggestion
