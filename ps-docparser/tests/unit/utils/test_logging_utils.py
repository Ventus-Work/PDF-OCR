import logging
import pytest
from utils.logging_utils import mask_secrets, MaskingFilter, install_masking_filter


class TestMaskSecrets:
    def test_masks_openai_key(self):
        text = "key=sk-abcdefghijklmnopqrstu"
        assert "sk-***MASKED***" in mask_secrets(text)

    def test_masks_gemini_key(self):
        text = "GEMINI_API_KEY=AIzaSyabcdefghijklmnopqrstuvwxyz12345"
        result = mask_secrets(text)
        assert "AIza***MASKED***" in result or "***MASKED***" in result

    def test_masks_named_key_assignment(self):
        result = mask_secrets("api_key=supersecret123")
        assert "supersecret123" not in result
        assert "***MASKED***" in result

    def test_empty_string_unchanged(self):
        assert mask_secrets("") == ""

    def test_no_secret_unchanged(self):
        text = "hello world"
        assert mask_secrets(text) == text


class TestMaskingFilter:
    def test_masks_record_msg(self):
        f = MaskingFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="sk-abcdefghijklmnopqrstu leaked", args=(), exc_info=None,
        )
        f.filter(record)
        assert "sk-***MASKED***" in record.msg

    def test_filter_returns_true(self):
        f = MaskingFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="safe message", args=(), exc_info=None,
        )
        assert f.filter(record) is True


class TestInstallMaskingFilter:
    def test_installs_once(self):
        logger = logging.getLogger("test_install_once")
        logger.filters.clear()
        install_masking_filter(logger)
        install_masking_filter(logger)
        assert sum(isinstance(f, MaskingFilter) for f in logger.filters) == 1
