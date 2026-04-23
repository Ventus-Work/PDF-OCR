"""tests/unit/extractors/test_hybrid_extractor.py — 하이브리드 파이프라인 분기 검증.

전략:
    pdfplumber.open, detect_tables, validate_and_fix_table_bboxes,
    crop_table_image, extract_text_regions_with_positions, PdfImageLoader 를
    모듈 레벨에서 mocker.patch 하여 실제 PDF/이미지/AI 호출을 완전히 우회.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from extractors.hybrid_extractor import _extract_local_table_from_bbox, process_pdf


def _patch_common(mocker, *, pages, table_bboxes_per_page, text_regions=None):
    """
    공통 mock 주입.

    Args:
        pages: [(width, height, extract_text_return, extract_tables_return)]
        table_bboxes_per_page: 각 페이지에 대해 detect_tables 가 반환할 bbox 리스트들
        text_regions: extract_text_regions_with_positions 가 반환할 리스트
    """
    mock_pages = []
    for w, h, text, ptables in pages:
        mp = MagicMock()
        mp.width = w
        mp.height = h
        mp.extract_text.return_value = text
        mp.extract_tables.return_value = ptables
        mock_pages.append(mp)

    mock_pdf_ctx = MagicMock()
    mock_pdf_ctx.__enter__.return_value.pages = mock_pages
    mock_pdf_ctx.__exit__.return_value = False
    mocker.patch(
        "extractors.hybrid_extractor.pdfplumber.open",
        return_value=mock_pdf_ctx,
    )

    mocker.patch(
        "extractors.hybrid_extractor.detect_tables",
        side_effect=list(table_bboxes_per_page),
    )
    mocker.patch(
        "extractors.hybrid_extractor.validate_and_fix_table_bboxes",
        side_effect=lambda bboxes, h, w: (bboxes, False),
    )
    mocker.patch(
        "extractors.hybrid_extractor.crop_table_image",
        return_value=MagicMock(name="table_img"),
    )
    mocker.patch(
        "extractors.hybrid_extractor.extract_text_regions_with_positions",
        return_value=(text_regions if text_regions is not None else []),
    )
    mocker.patch(
        "extractors.hybrid_extractor.merge_spaced_korean",
        side_effect=lambda t: t,
    )
    mocker.patch(
        "extractors.hybrid_extractor.format_text_with_linebreaks",
        side_effect=lambda t, division_names=None: t,
    )

    mock_loader = MagicMock()
    mock_loader.get_page.return_value = MagicMock(name="page_image")
    mocker.patch(
        "extractors.hybrid_extractor.PdfImageLoader",
        return_value=mock_loader,
    )
    return mock_pages, mock_loader


class TestProcessPdfBranches:
    def test_no_tables_text_only_skips_ai_and_loader(self, mocker):
        """
        분기 1: 테이블 0개 → plumber 텍스트 + AI 미호출 + pdf2image 미호출.
        """
        engine = MagicMock()
        engine.supports_image = True

        mock_pages, loader = _patch_common(
            mocker,
            pages=[(595, 842, "본문 텍스트", [])],
            table_bboxes_per_page=[[]],
        )

        md = process_pdf("fake.pdf", engine=engine)

        assert "본문 텍스트" in md
        engine.extract_table.assert_not_called()
        engine.extract_full_page.assert_not_called()
        loader.get_page.assert_not_called()

    def test_image_engine_with_tables_calls_extract_table(self, mocker):
        """
        분기 2: supports_image=True + 테이블 있음 → crop → engine.extract_table.
        """
        engine = MagicMock()
        engine.supports_image = True
        engine.extract_table.return_value = ("<table>x</table>", 10, 20)

        bbox = (0, 100, 595, 300)
        _patch_common(
            mocker,
            pages=[(595, 842, "some text", [])],
            table_bboxes_per_page=[[bbox]],
            text_regions=[{"y": 0, "type": "text", "content": "상단"}],
        )

        md = process_pdf("fake.pdf", engine=engine)

        engine.extract_table.assert_called_once()
        assert "<table>x</table>" in md
        assert "상단" in md

    def test_local_engine_falls_back_to_pdfplumber_tables(self, mocker):
        """
        분기 3: supports_image=False → pdfplumber.extract_tables + extract_table_from_data.
        """
        engine = MagicMock()
        engine.supports_image = False
        engine.extract_table_from_data.return_value = "<table>local</table>"

        bbox = (0, 100, 595, 300)
        plumber_tables = [[["헤더1", "헤더2"], ["값1", "값2"]]]
        _patch_common(
            mocker,
            pages=[(595, 842, "body", plumber_tables)],
            table_bboxes_per_page=[[bbox]],
            text_regions=[],
        )

        md = process_pdf("fake.pdf", engine=engine)

        engine.extract_table_from_data.assert_called_once()
        engine.extract_table.assert_not_called()
        assert "<table>local</table>" in md

    def test_elements_sorted_by_y_coordinate(self, mocker):
        """
        분기 4: y좌표 기준 정렬 — 낮은 y(상단)가 먼저 출력된다.
        """
        engine = MagicMock()
        engine.supports_image = True
        engine.extract_table.return_value = ("<table>T</table>", 0, 0)

        bbox = (0, 500, 595, 700)  # 테이블은 페이지 중하단
        _patch_common(
            mocker,
            pages=[(595, 842, "top txt", [])],
            table_bboxes_per_page=[[bbox]],
            text_regions=[
                {"y": 50, "type": "text", "content": "<p>TOP</p>"},
                {"y": 750, "type": "text", "content": "<p>BOTTOM</p>"},
            ],
        )

        md = process_pdf("fake.pdf", engine=engine)

        idx_top = md.find("TOP")
        idx_table = md.find("<table>T</table>")
        idx_bottom = md.find("BOTTOM")
        assert 0 <= idx_top < idx_table < idx_bottom

    def test_full_page_fallback_when_validator_signals(self, mocker):
        """
        분기 5: validate_and_fix_table_bboxes 가 needs_fallback=True 반환 시
                engine.extract_full_page 로 전환.
        """
        engine = MagicMock()
        engine.supports_image = True
        engine.extract_full_page.return_value = ("FULL PAGE MD", 10, 20)

        mock_pdf_ctx = MagicMock()
        mp = MagicMock()
        mp.width, mp.height = 595, 842
        mp.extract_text.return_value = "ignored"
        mock_pdf_ctx.__enter__.return_value.pages = [mp]
        mocker.patch(
            "extractors.hybrid_extractor.pdfplumber.open", return_value=mock_pdf_ctx
        )
        mocker.patch(
            "extractors.hybrid_extractor.detect_tables",
            return_value=[(0, 100, 595, 200)],
        )
        mocker.patch(
            "extractors.hybrid_extractor.validate_and_fix_table_bboxes",
            return_value=([], True),  # needs_fallback=True
        )
        mocker.patch(
            "extractors.hybrid_extractor.extract_text_regions_with_positions",
            return_value=[],
        )
        mocker.patch(
            "extractors.hybrid_extractor.PdfImageLoader",
            return_value=MagicMock(get_page=lambda n: MagicMock()),
        )

        md = process_pdf("fake.pdf", engine=engine)

        engine.extract_full_page.assert_called_once()
        engine.extract_table.assert_not_called()
        assert "FULL PAGE MD" in md

    def test_page_marker_emitted_for_each_processed_page(self, mocker):
        """
        분기 6: 모든 페이지는 build_page_marker 로 헤더가 삽입된다 (페이지 번호 포함).
        """
        engine = MagicMock()
        engine.supports_image = True

        _patch_common(
            mocker,
            pages=[
                (595, 842, "page1 txt", []),
                (595, 842, "page2 txt", []),
            ],
            table_bboxes_per_page=[[], []],
        )

        md = process_pdf("fake.pdf", engine=engine)

        # build_page_marker 는 페이지 번호를 포함한 헤더를 반환한다.
        assert "1" in md and "2" in md
        assert "page1 txt" in md and "page2 txt" in md


def _make_word(text: str, x0: float, x1: float, top: float) -> dict:
    return {"text": text, "x0": x0, "x1": x1, "top": top}


class TestExtractLocalTableFromBbox:
    def test_keeps_single_cell_rows_in_two_column_tables(self):
        cropped_page = MagicMock()
        cropped_page.extract_table.return_value = [
            ["*. general", "*. notes"],
            ["1. due date", "-vat"],
        ]
        cropped_page.extract_words.return_value = [
            _make_word("*.", 0, 8, 0),
            _make_word("general", 10, 60, 0),
            _make_word("*.", 180, 188, 0),
            _make_word("notes", 190, 230, 0),
            _make_word("1.", 0, 8, 20),
            _make_word("due", 10, 30, 20),
            _make_word("date", 32, 56, 20),
            _make_word("-vat", 190, 220, 20),
            _make_word("4.", 0, 8, 40),
            _make_word("validity", 10, 52, 40),
            _make_word("one", 54, 74, 40),
            _make_word("month", 76, 112, 40),
            _make_word("5.", 0, 8, 60),
            _make_word("owner", 10, 42, 60),
            _make_word("kim", 44, 64, 60),
        ]

        plumber_page = MagicMock()
        plumber_page.crop.return_value = cropped_page

        table = _extract_local_table_from_bbox(plumber_page, (0, 0, 240, 80))

        assert table == [
            ["*. general", "*. notes"],
            ["1. due date", "-vat"],
            ["4. validity one month", ""],
            ["5. owner kim", ""],
        ]

    def test_clamps_bbox_to_page_bounds_before_crop(self):
        cropped_page = MagicMock()
        cropped_page.extract_table.return_value = [
            ["A", "B"],
            ["1", "2"],
        ]
        cropped_page.extract_words.return_value = []

        plumber_page = MagicMock()
        plumber_page.bbox = (0, 0, 612, 859)
        plumber_page.crop.return_value = cropped_page

        table = _extract_local_table_from_bbox(
            plumber_page,
            (-4.678, 792.943, 612.0, 809.9840000000002),
        )

        plumber_page.crop.assert_called_once_with((0, 792.943, 612, 809.9840000000002))
        assert table == [["A", "B"], ["1", "2"]]
