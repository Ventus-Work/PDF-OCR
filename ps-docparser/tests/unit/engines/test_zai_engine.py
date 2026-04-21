"""tests/unit/engines/test_zai_engine.py — ZaiEngine 검증 (Mock ZaiClient)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from engines.zai_engine import ZaiEngine


def _make_engine(tracker=None):
    """
    ZaiEngine 인스턴스를 Mock client 주입 상태로 생성.

    Why:
        __init__ 에서 `from zai import ZaiClient; self._client = ZaiClient(api_key=...)`.
        생성 후 self._client 을 Mock 으로 재주입하면 이후 모든 API 호출이 Mock 경로.
    """
    engine = ZaiEngine(api_key="fake", tracker=tracker)
    engine._client = MagicMock()
    return engine


def _make_layout_response(md_text: str) -> MagicMock:
    resp = MagicMock()
    resp.model_dump.return_value = {
        "md_results": md_text,
        "layout_details": [{"type": "table", "bbox": [0, 0, 100, 100]}],
    }
    return resp


class TestZaiEngineInit:
    def test_supports_flags(self):
        engine = _make_engine()
        assert engine.supports_image is True
        assert engine.supports_ocr is True


class TestZaiEngineOcrDocument:
    def test_success_returns_page_result(self, tmp_path: Path, load_mock):
        engine = _make_engine()
        pdf = tmp_path / "fake.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        mock_pages = json.loads(load_mock("zai/ocr_document_success.json"))
        md_text = mock_pages[0]["text"]
        engine._client.layout_parsing.create.return_value = _make_layout_response(md_text)

        results = engine.ocr_document(pdf)

        assert len(results) == 1
        assert "BILL OF MATERIALS" in results[0].text
        engine._client.layout_parsing.create.assert_called_once()

    def test_cache_hit_skips_api_call(self, tmp_path: Path):
        engine = _make_engine()
        pdf = tmp_path / "cached.pdf"
        pdf.write_bytes(b"%PDF-1.4 data")

        cache_mock = MagicMock()
        cache_mock.make_key_from_file.return_value = "key-123"
        cache_mock.get.return_value = {"text": "cached BOM text", "layout": []}
        engine.cache = cache_mock

        results = engine.ocr_document(pdf)

        assert len(results) == 1
        assert "cached BOM text" in results[0].text
        engine._client.layout_parsing.create.assert_not_called()


class TestZaiEngineOcrImage:
    def test_calls_layout_parsing(self):
        engine = _make_engine()
        engine._client.layout_parsing.create.return_value = _make_layout_response(
            "OCR 결과 텍스트"
        )

        result = engine.ocr_image(Image.new("RGB", (50, 50)))

        assert "OCR 결과" in result.text
        engine._client.layout_parsing.create.assert_called_once()


class TestZaiEngineParseResponse:
    @pytest.mark.parametrize("data,expected_in_text", [
        ({"md_results": "md text"}, "md text"),
        ({"pages": [{"markdown": "p1"}, {"markdown": "p2"}]}, "p1"),
        ({"content": "content text"}, "content text"),
        ({"text": "plain text"}, "plain text"),
    ])
    def test_parses_various_response_shapes(self, data, expected_in_text):
        engine = _make_engine()
        text, _ = engine._parse_response(data)
        assert expected_in_text in text

    def test_strips_image_markdown_links(self):
        engine = _make_engine()
        data = {"md_results": "before ![alt](page=0,bbox=1,2,3,4) after"}
        text, _ = engine._parse_response(data)
        assert "![" not in text
        assert "before" in text and "after" in text
