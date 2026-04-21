"""tests/unit/engines/test_tesseract_engine.py — TesseractEngine 검증 (Mock pytesseract)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PIL import Image

from engines.tesseract_engine import TesseractEngine


def _make_engine(tesseract_path=None):
    engine = TesseractEngine(tesseract_path=tesseract_path)
    engine._pytesseract = MagicMock()
    return engine


class TestTesseractEngineInit:
    def test_supports_flags(self):
        engine = _make_engine()
        assert engine.supports_image is True
        assert engine.supports_ocr is True

    def test_no_api_key_required(self):
        engine = TesseractEngine()
        assert engine is not None


class TestTesseractEngineOcrImage:
    def test_calls_image_to_string(self):
        engine = _make_engine()
        engine._pytesseract.image_to_string.return_value = "OCR 결과"

        result = engine.ocr_image(Image.new("RGB", (50, 50)))

        assert result.text == "OCR 결과"
        assert result.page_num == 0
        engine._pytesseract.image_to_string.assert_called_once()

    def test_extract_full_page_returns_zero_tokens(self):
        engine = _make_engine()
        engine._pytesseract.image_to_string.return_value = "page text"

        text, in_tok, out_tok = engine.extract_full_page(
            Image.new("RGB", (10, 10)), page_num=1
        )
        assert text == "page text"
        assert in_tok == 0 and out_tok == 0


class TestTesseractEngineOcrDocument:
    def test_ocr_document_iterates_pages(self, mocker, tmp_path):
        engine = _make_engine()
        engine._pytesseract.image_to_string.return_value = "page text"

        mock_images = [Image.new("RGB", (10, 10)) for _ in range(3)]
        mocker.patch(
            "pdf2image.convert_from_path",
            return_value=mock_images,
        )

        pdf = tmp_path / "x.pdf"
        pdf.write_bytes(b"%PDF-1.4")

        results = engine.ocr_document(pdf)

        assert len(results) == 3
        assert [r.page_num for r in results] == [0, 1, 2]
