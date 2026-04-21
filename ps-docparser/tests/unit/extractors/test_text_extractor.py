"""tests/unit/extractors/test_text_extractor.py — pdfplumber 기반 텍스트 추출기 검증."""

from __future__ import annotations

from unittest.mock import MagicMock

from extractors.text_extractor import (
    extract_text_outside_tables,
    extract_text_regions_with_positions,
    deduplicate_bold_fake,
)


class TestExtractTextOutsideTables:
    def test_no_table_bboxes_extracts_all_text(self):
        page = MagicMock()
        page.extract_text.return_value = "페이지 전문 텍스트"

        text = extract_text_outside_tables(page, table_bboxes=[])
        assert text == "페이지 전문 텍스트"

    def test_with_bboxes_uses_outside_bbox(self):
        filtered = MagicMock()
        filtered.extract_text.return_value = "table 제외 텍스트"
        filtered.outside_bbox.return_value = filtered  # chain

        page = MagicMock()
        page.outside_bbox.return_value = filtered

        result = extract_text_outside_tables(page, table_bboxes=[(0, 10, 100, 50)])

        page.outside_bbox.assert_called_once_with((0, 10, 100, 50))
        assert result == "table 제외 텍스트"

    def test_all_bboxes_fail_falls_back_to_full_text(self):
        """
        모든 outside_bbox 실패 시 page.extract_text() 로 폴백한다.
        """
        page = MagicMock()
        page.outside_bbox.side_effect = Exception("boom")
        page.extract_text.return_value = "폴백 텍스트"

        result = extract_text_outside_tables(page, table_bboxes=[(0, 0, 10, 10)])
        assert result == "폴백 텍스트"


class TestExtractTextRegionsWithPositions:
    def test_no_bboxes_returns_single_region_at_y0(self, mocker):
        mocker.patch(
            "extractors.text_extractor.format_text_with_linebreaks",
            side_effect=lambda t, division_names=None: t,
        )
        page = MagicMock()
        page.extract_text.return_value = "헤더 문단"

        regions = extract_text_regions_with_positions(page, table_bboxes=[])
        assert len(regions) == 1
        assert regions[0]["y"] == 0
        assert regions[0]["type"] == "text"
        assert "헤더 문단" in regions[0]["content"]

    def test_splits_text_around_table_bbox(self, mocker):
        mocker.patch(
            "extractors.text_extractor.format_text_with_linebreaks",
            side_effect=lambda t, division_names=None: t,
        )

        upper_crop = MagicMock()
        upper_crop.extract_text.return_value = "위쪽 텍스트"
        lower_crop = MagicMock()
        lower_crop.extract_text.return_value = "아래쪽 텍스트"

        page = MagicMock()
        page.width = 595.0
        page.height = 842.0
        # 0..100 = upper, 100..200 = table, 200..842 = lower
        page.within_bbox.side_effect = [upper_crop, lower_crop]

        regions = extract_text_regions_with_positions(
            page, table_bboxes=[(0, 100, 595, 200)]
        )

        assert len(regions) == 2
        assert regions[0]["y"] == 0
        assert "위쪽" in regions[0]["content"]
        assert regions[1]["y"] == 200
        assert "아래쪽" in regions[1]["content"]


class TestDeduplicateBoldFake:
    def test_removes_near_offset_duplicate(self):
        words = [
            {"text": "품명", "x0": 10.0, "top": 100.0},
            {"text": "품명", "x0": 12.0, "top": 100.5},  # 볼드 오프셋 — 제거 대상
            {"text": "규격", "x0": 50.0, "top": 100.0},
        ]
        result = deduplicate_bold_fake(words)
        assert len(result) == 2
        assert [w["text"] for w in result] == ["품명", "규격"]

    def test_keeps_same_text_on_different_lines(self):
        words = [
            {"text": "총계", "x0": 10.0, "top": 100.0},
            {"text": "총계", "x0": 10.0, "top": 200.0},  # 같은 텍스트 ≠ 같은 행
        ]
        result = deduplicate_bold_fake(words)
        assert len(result) == 2
