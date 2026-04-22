"""
extractors/bom_ocr_retry.py — Phase 14 Step 14-2 연동 테스트

검증 범위:
    - extract_bom_with_retry() 반환 결과에 drawing_metadata가 포함되는지
    - raw_text에 타이틀 블록 정보가 있을 때 정상 추출되는지
    - raw_text가 비어있어도 result.drawing_metadata가 dict인지 (안전성)
    - 기존 bom_sections / line_list_sections 동작이 회귀되지 않는지

설계 원칙:
    - 실제 OCR 엔진 / PDF 파일 불필요 — 모두 MagicMock으로 대체
    - extract_bom_tables / extract_bom 은 mock 반환값을 주입해 경량화
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from extractors.bom_types import BomExtractionResult, BomSection


# ──────────────────────────────────────────────────────────
# 픽스처
# ──────────────────────────────────────────────────────────

@pytest.fixture
def mock_engine():
    """OCR 엔진 목 — 1차 OCR 결과를 raw_text로 반환."""
    engine = MagicMock()
    ocr_result = MagicMock()
    ocr_result.text = (
        "TITLE: PIPE SUPPORT DETAIL\n"
        "DWG NO. KO-D-010-14-16N\n"
        "REV. 0\n"
        "DATE: 2024-03-15\n"
    )
    ocr_result.layout_details = []
    ocr_result.page_num = 1
    engine.ocr_document.return_value = [ocr_result]
    return engine


@pytest.fixture
def mock_engine_empty_text():
    """OCR 결과가 빈 텍스트인 엔진."""
    engine = MagicMock()
    ocr_result = MagicMock()
    ocr_result.text = ""
    ocr_result.layout_details = []
    ocr_result.page_num = 1
    engine.ocr_document.return_value = [ocr_result]
    return engine


@pytest.fixture
def minimal_keywords():
    return {
        "anchor_bom": ["BOM"],
        "anchor_ll": ["LINE LIST"],
        "bom_header_a": ["ITEM"],
        "bom_header_b": ["SIZE"],
        "bom_header_c": ["QTY"],
        "ll_header_a": ["LINE NO"],
        "ll_header_b": ["FROM"],
        "ll_header_c": ["TO"],
        "kill": ["NOTES"],
        "noise_row": [],
        "rev_markers": ["REV"],
        "blacklist": [],
    }


@pytest.fixture
def image_settings():
    return {
        "default_dpi": 400,
        "retry_dpi": 600,
        "bom_crop_left_ratio": 0.45,
        "ll_crop_top_ratio": 0.50,
        "ll_within_bbox_top_ratio": 0.25,
        "ll_within_bbox_bottom_ratio": 0.72,
    }


def _make_bom_result_with_data():
    """BOM 1개 + 데이터 있는 BomExtractionResult."""
    bom = BomSection(
        "bom",
        headers=["ITEM", "SIZE", "QTY"],
        rows=[["1", "100A", "5"]],
        raw_row_count=1,
    )
    return BomExtractionResult(bom_sections=[bom])


# ──────────────────────────────────────────────────────────
# drawing_metadata 채움 확인
# ──────────────────────────────────────────────────────────

class TestDrawingMetaIntegration:

    def test_drawing_metadata_present_in_result(
        self, mock_engine, minimal_keywords, image_settings
    ):
        """extract_bom_with_retry() 반환값에 drawing_metadata가 있어야 함."""
        from extractors.bom_ocr_retry import extract_bom_with_retry

        with patch(
            "extractors.bom_state_machine.extract_bom_tables",
            return_value=_make_bom_result_with_data(),
        ):
            result = extract_bom_with_retry(
                mock_engine, Path("fake.pdf"), minimal_keywords, image_settings
            )

        assert hasattr(result, "drawing_metadata")
        assert isinstance(result.drawing_metadata, dict)

    def test_drawing_metadata_extracted_from_raw_text(
        self, mock_engine, minimal_keywords, image_settings
    ):
        """raw_text에 타이틀 블록이 있으면 필드가 채워져야 함."""
        from extractors.bom_ocr_retry import extract_bom_with_retry

        with patch(
            "extractors.bom_state_machine.extract_bom_tables",
            return_value=_make_bom_result_with_data(),
        ):
            result = extract_bom_with_retry(
                mock_engine, Path("fake.pdf"), minimal_keywords, image_settings
            )

        assert result.drawing_metadata.get("title") == "PIPE SUPPORT DETAIL"
        assert result.drawing_metadata.get("dwg_no") == "KO-D-010-14-16N"
        assert result.drawing_metadata.get("rev") == "0"
        assert result.drawing_metadata.get("date") == "2024-03-15"

    def test_drawing_metadata_is_dict_when_empty_text(
        self, mock_engine_empty_text, minimal_keywords, image_settings
    ):
        """raw_text가 비어있어도 drawing_metadata는 dict여야 함 (안전성)."""
        from extractors.bom_ocr_retry import extract_bom_with_retry

        with patch(
            "extractors.bom_state_machine.extract_bom_tables",
            return_value=BomExtractionResult(),
        ):
            result = extract_bom_with_retry(
                mock_engine_empty_text,
                Path("fake.pdf"),
                minimal_keywords,
                image_settings,
            )

        assert isinstance(result.drawing_metadata, dict)
        # 빈 텍스트 → 모든 값이 None
        assert all(v is None for v in result.drawing_metadata.values())

    def test_unmatched_raw_text_all_none(
        self, minimal_keywords, image_settings
    ):
        """타이틀 블록 없는 raw_text → 모든 필드 None."""
        from extractors.bom_ocr_retry import extract_bom_with_retry

        engine = MagicMock()
        ocr_result = MagicMock()
        ocr_result.text = "ITEM | SIZE | QTY\n1 | 100A | 5\n"  # BOM 데이터만
        ocr_result.layout_details = []
        ocr_result.page_num = 1
        engine.ocr_document.return_value = [ocr_result]

        with patch(
            "extractors.bom_state_machine.extract_bom_tables",
            return_value=_make_bom_result_with_data(),
        ):
            result = extract_bom_with_retry(
                engine, Path("fake.pdf"), minimal_keywords, image_settings
            )

        assert result.drawing_metadata.get("title") is None
        assert result.drawing_metadata.get("dwg_no") is None


# ──────────────────────────────────────────────────────────
# 기존 동작 회귀 확인
# ──────────────────────────────────────────────────────────

class TestExistingBehaviorRegression:

    def test_raw_text_set_from_ocr(
        self, mock_engine, minimal_keywords, image_settings
    ):
        """raw_text가 OCR 결과로 세팅되는 기존 동작 유지."""
        from extractors.bom_ocr_retry import extract_bom_with_retry

        with patch(
            "extractors.bom_state_machine.extract_bom_tables",
            return_value=_make_bom_result_with_data(),
        ):
            result = extract_bom_with_retry(
                mock_engine, Path("fake.pdf"), minimal_keywords, image_settings
            )

        assert "PIPE SUPPORT DETAIL" in result.raw_text

    def test_ocr_engine_name_set(
        self, mock_engine, minimal_keywords, image_settings
    ):
        """ocr_engine 필드가 엔진 클래스명으로 세팅되는 기존 동작 유지."""
        from extractors.bom_ocr_retry import extract_bom_with_retry

        with patch(
            "extractors.bom_state_machine.extract_bom_tables",
            return_value=_make_bom_result_with_data(),
        ):
            result = extract_bom_with_retry(
                mock_engine, Path("fake.pdf"), minimal_keywords, image_settings
            )

        assert result.ocr_engine == "MagicMock"

    def test_bom_sections_preserved(
        self, mock_engine, minimal_keywords, image_settings
    ):
        """bom_sections가 extract_bom_tables 반환값 그대로 보존됨."""
        from extractors.bom_ocr_retry import extract_bom_with_retry

        with patch(
            "extractors.bom_state_machine.extract_bom_tables",
            return_value=_make_bom_result_with_data(),
        ):
            result = extract_bom_with_retry(
                mock_engine, Path("fake.pdf"), minimal_keywords, image_settings
            )

        assert result.has_bom
        assert result.total_bom_rows == 1

    def test_returns_bom_extraction_result(
        self, mock_engine, minimal_keywords, image_settings
    ):
        """반환 타입이 BomExtractionResult임을 확인."""
        from extractors.bom_ocr_retry import extract_bom_with_retry

        with patch(
            "extractors.bom_state_machine.extract_bom_tables",
            return_value=BomExtractionResult(),
        ):
            result = extract_bom_with_retry(
                mock_engine, Path("fake.pdf"), minimal_keywords, image_settings
            )

        assert isinstance(result, BomExtractionResult)
