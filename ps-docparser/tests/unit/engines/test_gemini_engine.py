"""tests/unit/engines/test_gemini_engine.py — GeminiEngine 검증 (Mock client)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PIL import Image

from engines.gemini_engine import GeminiEngine


def _make_engine(mocker, tracker=None):
    """
    GeminiEngine 인스턴스를 Mock client 주입 상태로 생성.

    Why:
        __init__ 에서 `import google.genai as genai` 로 지연 import 후
        self._client = genai.Client(api_key=...) 로 보관한다.
        생성 후 self._client 를 Mock 으로 재주입하면
        이후의 모든 API 호출이 Mock 경로를 탄다.
        추가로 FREE_TIER_DELAY time.sleep 을 0 으로 패치하여 테스트 지연 제거.
    """
    mocker.patch("engines.gemini_engine.time.sleep", return_value=None)
    engine = GeminiEngine(api_key="fake", model="gemini-2.0-flash", tracker=tracker or MagicMock())
    mock_client = MagicMock()
    engine._clients = {"fake": mock_client}
    return engine, mock_client


class TestGeminiEngineInit:
    def test_supports_flags(self, mocker):
        engine, _ = _make_engine(mocker)
        assert engine.supports_image is True
        assert engine.supports_ocr is False

    def test_missing_api_key_raises_value_error(self):
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            GeminiEngine(api_key="", model="gemini-2.0-flash", tracker=MagicMock())


class TestGeminiEngineExtractTable:
    def test_success_returns_html_and_tokens(self, mocker, load_mock):
        tracker = MagicMock()
        engine, mock_client = _make_engine(mocker, tracker=tracker)

        mock_response = MagicMock()
        mock_response.text = load_mock("gemini/extract_table_success.html")
        mock_response.usage_metadata = MagicMock(
            prompt_token_count=100, candidates_token_count=200
        )
        mock_client.models.generate_content.return_value = mock_response

        img = Image.new("RGB", (100, 100))
        html, in_tok, out_tok = engine.extract_table(img, table_num=1)

        assert "<table" in html
        assert in_tok == 100 and out_tok == 200
        tracker.add.assert_called_once_with(100, 200)

    def test_strips_markdown_code_fence(self, mocker):
        engine, mock_client = _make_engine(mocker)

        mock_response = MagicMock()
        mock_response.text = "```html\n<table><tr><td>x</td></tr></table>\n```"
        mock_response.usage_metadata = MagicMock(
            prompt_token_count=10, candidates_token_count=20
        )
        mock_client.models.generate_content.return_value = mock_response

        html, _, _ = engine.extract_table(Image.new("RGB", (10, 10)), table_num=1)
        assert not html.startswith("```")
        assert "<table>" in html

    def test_api_error_returns_safe_fallback(self, mocker):
        engine, mock_client = _make_engine(mocker)
        mock_client.models.generate_content.side_effect = Exception("quota exceeded")

        html, in_tok, out_tok = engine.extract_table(
            Image.new("RGB", (10, 10)), table_num=3
        )
        assert "<!--" in html
        assert "3" in html
        assert in_tok == 0 and out_tok == 0

    def test_rotates_api_keys_after_max_calls(self, mocker):
        tracker = MagicMock()
        mocker.patch("engines.gemini_engine.time.sleep", return_value=None)

        client_a = MagicMock()
        client_b = MagicMock()
        for client in (client_a, client_b):
            response = MagicMock()
            response.text = "<table><tr><td>x</td></tr></table>"
            response.usage_metadata = MagicMock(
                prompt_token_count=1,
                candidates_token_count=1,
            )
            client.models.generate_content.return_value = response

        engine = GeminiEngine(
            api_keys=["key-a", "key-b"],
            model="gemini-2.0-flash",
            tracker=tracker,
            max_calls_per_key=2,
        )
        make_client = mocker.patch.object(
            engine,
            "_make_client",
            side_effect=lambda api_key: client_a if api_key == "key-a" else client_b,
        )

        img = Image.new("RGB", (10, 10))
        for table_num in range(1, 6):
            html, _, _ = engine.extract_table(img, table_num=table_num)
            assert "<table>" in html

        assert make_client.call_count == 2
        assert client_a.models.generate_content.call_count == 3
        assert client_b.models.generate_content.call_count == 2


class TestGeminiEngineExtractFullPage:
    def test_full_page_error_returns_empty(self, mocker):
        engine, mock_client = _make_engine(mocker)
        mock_client.models.generate_content.side_effect = Exception("boom")

        text, in_tok, out_tok = engine.extract_full_page(
            Image.new("RGB", (10, 10)), page_num=1
        )
        assert text == ""
        assert in_tok == 0 and out_tok == 0
