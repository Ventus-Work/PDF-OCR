"""
detector.py 단위 테스트.
"""
import pytest
from detector import detect_document_type


class TestDetectDocumentType:
    """문서 유형 자동 감지 로직 검증."""

    # ── 정상 케이스 ──
    def test_estimate_by_keyword(self):
        # THRESHOLD = 4
        text = "견적금액: 1,000,000원\n내역서 제공\n납품기일 협의\n결제조건 완료"
        assert detect_document_type(text) == "estimate"

    def test_bom_by_bill_of_materials(self):
        # THRESHOLD_BOM = 3
        text = "BILL OF MATERIALS\nS/N | SPEC | Q'TY"
        assert detect_document_type(text) == "bom"

    def test_bom_by_line_list(self):
        # THRESHOLD_BOM = 3
        text = "LINE LIST\nLINE NO | MARK | ..."
        assert detect_document_type(text) == "bom"

    def test_pumsem_by_division(self):
        # THRESHOLD = 4
        text = "제1편 단가계산 / 품셈 적용기준 참조\n제6장 보완 노무비 내역."
        assert detect_document_type(text) == "pumsem"

    # ── 엣지 케이스 ──
    @pytest.mark.parametrize("text,expected", [
        ("", None),
        ("   \n\n  ", None),
        ("알 수 없는 문서 내용", None),
    ])
    def test_unknown_or_empty(self, text, expected):
        assert detect_document_type(text) == expected

    def test_priority_bom_over_estimate(self):
        """BOM 키워드가 더 강력한 신호"""
        # BOM = 3, Estimate = 1 (Estimate < 4 이고, BOM >= 3 이므로 BOM)
        text = "BILL OF MATERIALS\nS/N | Q'TY\n견적금액도 포함"
        assert detect_document_type(text) == "bom"

    def test_case_insensitive(self):
        text = "bill of materials\ns/n | q'ty"
        assert detect_document_type(text) == "bom"
