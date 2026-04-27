"""Unit tests for detector.py."""

from detector import (
    analyze_document_type,
    detect_document_type,
    detect_material_quote,
    suggest_preset,
)


class TestAnalyzeDocumentType:
    def test_estimate_high_confidence(self):
        text = "견적 견적금액 내역서 납품기일 결제조건 견적유효기간 직접비"

        result = analyze_document_type(text)

        assert result.label == "estimate"
        assert result.confidence == "high"
        assert detect_document_type(text) == "estimate"

    def test_estimate_medium_confidence(self):
        text = "견적 견적금액 내역서 납품기일"

        result = analyze_document_type(text)

        assert result.label == "estimate"
        assert result.confidence == "medium"

    def test_pumsem_high_confidence(self):
        text = "품셈 수량산출 부문 공종 단위 적용기준 노무비 참조"

        result = analyze_document_type(text)

        assert result.label == "pumsem"
        assert result.confidence == "high"

    def test_bom_high_confidence(self):
        text = "BILL OF MATERIALS S/N MARK WT(KG) Q'TY MAT'L"

        result = analyze_document_type(text)

        assert result.label == "bom"
        assert result.confidence == "high"

    def test_bom_medium_confidence(self):
        text = "LINE LIST\nLINE NO\nMARK"

        result = analyze_document_type(text)

        assert result.label == "bom"
        assert result.confidence == "medium"

    def test_material_quote_is_forced_to_generic(self):
        text = (
            "견적서\n건명\n결정금액\n거래처\n"
            "항목 사양 치수 수량 단가 공급가액 메모"
        )

        result = analyze_document_type(text)

        assert detect_material_quote(text) is True
        assert result.label == "estimate"
        assert result.confidence == "high"
        assert result.material_quote is True
        assert "--preset estimate" in result.suggestion
        assert suggest_preset(text) == result.suggestion

    def test_estimate_item_table_keywords_route_to_estimate(self):
        text = "견적서\n품목 재질 치수 수량 중량 단가 단위 공급가액 메모\n결제조건"

        result = analyze_document_type(text)

        assert result.label == "estimate"
        assert result.confidence == "high"

    def test_ambiguous_mixed_document_stays_generic(self):
        text = "견적 견적금액 내역서 납품기일 품셈 수량산출 부문 공종"

        result = analyze_document_type(text)

        assert result.label is None
        assert result.confidence == "low"

    def test_empty_text_returns_generic_low_confidence(self):
        result = analyze_document_type("")

        assert result.label is None
        assert result.confidence == "low"
        assert result.scores == {"estimate": 0, "pumsem": 0, "bom": 0}
