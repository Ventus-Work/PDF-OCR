import pytest
from unittest.mock import patch, MagicMock
from engines.factory import create_engine
from utils.io import ParserError


class TestCreateEngine:
    def test_unknown_engine_raises(self):
        with pytest.raises(ParserError, match="알 수 없는 엔진"):
            create_engine("invalid_engine")

    def test_local_engine_created(self, mocker):
        mock_cls = MagicMock()
        mocker.patch("engines.local_engine.LocalEngine", mock_cls)
        create_engine("local")
        mock_cls.assert_called_once()

    def test_zai_missing_key_raises(self, mocker):
        mocker.patch.object(__import__("config"), "ZAI_API_KEY", "")
        with pytest.raises(ParserError, match="ZAI_API_KEY"):
            create_engine("zai")

    def test_mistral_missing_key_raises(self, mocker):
        mocker.patch.object(__import__("config"), "MISTRAL_API_KEY", "")
        with pytest.raises(ParserError, match="MISTRAL_API_KEY"):
            create_engine("mistral")

    def test_gemini_engine_created(self, mocker):
        mock_cls = MagicMock()
        mocker.patch("engines.gemini_engine.GeminiEngine", mock_cls)
        mocker.patch.object(__import__("config"), "GEMINI_API_KEY", "fake-key")
        mocker.patch.object(__import__("config"), "GEMINI_API_KEYS", ("fake-key", "fake-key-2"))
        mocker.patch.object(__import__("config"), "GEMINI_KEY_MAX_CALLS", 20)
        mocker.patch.object(__import__("config"), "GEMINI_MODEL", "gemini-pro")
        mocker.patch("engines.factory._get_gemini_key_rotator", return_value="rotator")
        create_engine("gemini")
        mock_cls.assert_called_once_with(
            api_key="fake-key",
            model="gemini-pro",
            tracker=None,
            key_rotator="rotator",
        )
