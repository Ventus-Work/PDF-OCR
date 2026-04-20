"""
config.py 단위 테스트.

Phase 6에서 도입된 validate_config와 경로 감지 함수 검증.
"""
import pytest
import platform
from unittest.mock import patch

import importlib
import sys 


class TestDetectPopplerPath:

    def test_env_var_priority(self, monkeypatch, tmp_path):
        import config
        existing = tmp_path / "poppler_bin"
        existing.mkdir()
        monkeypatch.setenv("POPPLER_PATH", str(existing))
        assert config._detect_poppler_path() == str(existing)

    def test_env_var_invalid_falls_through(self, monkeypatch):
        import config
        monkeypatch.setenv("POPPLER_PATH", "/nonexistent/path")
        # which과 OS 경로 모두 없다고 가정
        with patch("shutil.which", return_value=None):
            with patch("os.path.exists", return_value=False):
                result = config._detect_poppler_path()
                assert result is None

    def test_shutil_which_fallback(self, monkeypatch):
        import config
        monkeypatch.delenv("POPPLER_PATH", raising=False)
        with patch("shutil.which", return_value="/usr/bin/pdftotext"):
            assert config._detect_poppler_path() == "/usr/bin"

    def test_windows_glob_selects_latest(self, monkeypatch):
        import config
        monkeypatch.delenv("POPPLER_PATH", raising=False)
        fake_paths = [
            r"C:\poppler\poppler-23.05.0\Library\bin",
            r"C:\poppler\poppler-25.01.0\Library\bin",
            r"C:\poppler\poppler-24.08.0\Library\bin",
        ]
        with patch("shutil.which", return_value=None):
            with patch("glob.glob", return_value=fake_paths):
                # mock os.path.exists specifically for these paths to be True if it contains 25.01.0
                def mock_exists(p): return True
                with patch("os.path.exists", side_effect=mock_exists):
                    with patch("platform.system", return_value="Windows"):
                        result = config._detect_poppler_path()
                        # 최신 25.01.0 선택
                        assert "25.01.0" in result


class TestValidateConfig:

    def test_missing_gemini_key_errors(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "GEMINI_API_KEY", None)
        monkeypatch.setattr(config, "DEFAULT_ENGINE", "gemini")
        result = config.validate_config(verbose=False)
        assert any("GEMINI_API_KEY" in e for e in result["errors"])

    def test_valid_gemini_setup(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "GEMINI_API_KEY", "fake_key_123")
        monkeypatch.setattr(config, "DEFAULT_ENGINE", "gemini")
        monkeypatch.setattr(config, "POPPLER_PATH", "/fake/poppler")
        result = config.validate_config(verbose=False)
        assert result["errors"] == []

    def test_missing_poppler_is_warning_not_error(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "POPPLER_PATH", None)
        monkeypatch.setattr(config, "DEFAULT_ENGINE", "local")  # local은 poppler 불필요
        result = config.validate_config(verbose=False)
        assert result["errors"] == []
        assert any("Poppler" in w for w in result["warnings"])

    def test_tesseract_engine_without_binary_errors(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "TESSERACT_PATH", None)
        monkeypatch.setattr(config, "DEFAULT_ENGINE", "tesseract")
        result = config.validate_config(verbose=False)
        assert any("tesseract" in e.lower() for e in result["errors"])
