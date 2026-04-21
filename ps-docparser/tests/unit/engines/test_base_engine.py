"""tests/unit/engines/test_base_engine.py — OcrPageResult + BaseEngine 계약 검증."""

from __future__ import annotations

from pathlib import Path
import pytest

from engines.base_engine import BaseEngine, OcrPageResult


class TestOcrPageResult:
    def test_default_values(self):
        r = OcrPageResult(page_num=0, text="hello")
        assert r.page_num == 0
        assert r.text == "hello"
        assert r.layout_details == []
        assert r.input_tokens == 0
        assert r.output_tokens == 0

    def test_with_full_fields(self):
        r = OcrPageResult(
            page_num=3,
            text="body",
            layout_details=[{"type": "table", "bbox": [0, 0, 100, 100]}],
            input_tokens=500,
            output_tokens=150,
        )
        assert r.page_num == 3
        assert r.layout_details[0]["type"] == "table"
        assert r.input_tokens == 500
        assert r.output_tokens == 150


class _StubEngine(BaseEngine):
    def extract_table(self, image, table_num):
        return ("<table></table>", 0, 0)

    def extract_full_page(self, image, page_num):
        return ("", 0, 0)


class TestBaseEngineContract:
    def test_abstract_cannot_instantiate(self):
        with pytest.raises(TypeError):
            BaseEngine()

    def test_default_flags(self):
        e = _StubEngine()
        assert e.supports_image is True
        assert e.supports_ocr is False
        assert e.cache is None

    def test_extract_table_from_data_produces_html(self):
        e = _StubEngine()
        data = [["Header1", "Header2"], ["a", "b"], ["c", "d"]]
        html = e.extract_table_from_data(data, table_num=1)
        assert "<table>" in html and "</table>" in html
        assert "<th>Header1</th>" in html
        assert "<td>a</td>" in html
        assert "<td>d</td>" in html

    def test_extract_table_from_data_empty_returns_comment(self):
        e = _StubEngine()
        assert "데이터 없음" in e.extract_table_from_data([], table_num=1)

    def test_ocr_document_default_raises(self, tmp_path: Path):
        e = _StubEngine()
        with pytest.raises(NotImplementedError, match="OCR"):
            e.ocr_document(tmp_path / "fake.pdf")

    def test_ocr_image_default_raises(self):
        from PIL import Image
        e = _StubEngine()
        with pytest.raises(NotImplementedError, match="이미지 OCR"):
            e.ocr_image(Image.new("RGB", (10, 10)))
