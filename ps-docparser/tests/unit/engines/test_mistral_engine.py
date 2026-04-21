"""tests/unit/engines/test_mistral_engine.py — MistralEngine 검증 (Mock client)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from engines.mistral_engine import MistralEngine


def _make_engine():
    engine = MistralEngine(api_key="fake")
    engine._client = MagicMock()
    return engine


def _make_ocr_response(texts: list[str]) -> MagicMock:
    resp = MagicMock()
    resp.pages = [MagicMock(markdown=t) for t in texts]
    return resp


class TestMistralEngineInit:
    def test_supports_flags(self):
        engine = _make_engine()
        assert engine.supports_image is True
        assert engine.supports_ocr is True


class TestMistralEngineOcrDocument:
    def test_success_returns_all_pages(self, tmp_path: Path):
        engine = _make_engine()
        pdf = tmp_path / "fake.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        engine._client.ocr.process.return_value = _make_ocr_response(
            ["page 0 BOM", "page 1 조건"]
        )

        results = engine.ocr_document(pdf)

        assert len(results) == 2
        assert results[0].page_num == 0
        assert "BOM" in results[0].text
        assert results[1].page_num == 1
        engine._client.ocr.process.assert_called_once()

    def test_page_indices_filters_pages(self, tmp_path: Path):
        engine = _make_engine()
        pdf = tmp_path / "multi.pdf"
        pdf.write_bytes(b"%PDF-1.4")

        engine._client.ocr.process.return_value = _make_ocr_response(
            ["p0", "p1", "p2"]
        )

        results = engine.ocr_document(pdf, page_indices=[1])
        assert len(results) == 1
        assert results[0].page_num == 1

    def test_cache_hit_skips_api_call(self, tmp_path: Path):
        engine = _make_engine()
        pdf = tmp_path / "cached.pdf"
        pdf.write_bytes(b"%PDF-1.4 data")

        cache_mock = MagicMock()
        cache_mock.make_key_from_file.return_value = "mkey"
        cache_mock.get.return_value = [
            {"page_num": 0, "text": "cached page 0"},
            {"page_num": 1, "text": "cached page 1"},
        ]
        engine.cache = cache_mock

        results = engine.ocr_document(pdf)

        assert len(results) == 2
        assert "cached page 0" in results[0].text
        engine._client.ocr.process.assert_not_called()


class TestMistralEngineOcrImage:
    def test_concatenates_pages(self):
        engine = _make_engine()
        engine._client.ocr.process.return_value = _make_ocr_response(["a", "b"])

        result = engine.ocr_image(Image.new("RGB", (10, 10)))
        assert "a" in result.text and "b" in result.text
