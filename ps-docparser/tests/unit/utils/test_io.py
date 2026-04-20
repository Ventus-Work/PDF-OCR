"""
utils/io.py 단위 테스트.

Phase 6에서 도입된 _safe_write_text는 다음을 보장:
- PermissionError → ParserError
- OSError → ParserError
- 부모 디렉토리 자동 생성
"""
import pytest
from pathlib import Path
from unittest.mock import patch, mock_open

from utils.io import _safe_write_text, ParserError


class TestSafeWriteText:

    def test_write_success(self, tmp_path: Path):
        target = tmp_path / "test.md"
        _safe_write_text(target, "hello world")
        assert target.read_text(encoding="utf-8-sig") == "hello world"

    def test_creates_parent_directories(self, tmp_path: Path):
        target = tmp_path / "deep" / "nested" / "dir" / "file.md"
        _safe_write_text(target, "content")
        assert target.exists()

    def test_permission_error_converted(self, tmp_path: Path):
        target = tmp_path / "test.md"
        with patch("builtins.open", side_effect=PermissionError("Access denied")):
            with pytest.raises(ParserError) as exc_info:
                _safe_write_text(target, "content")
            assert "권한 거부" in str(exc_info.value)
            assert "Excel" in str(exc_info.value)  # 힌트 메시지

    def test_os_error_converted(self, tmp_path: Path):
        target = tmp_path / "test.md"
        with patch("builtins.open", side_effect=OSError("Disk full")):
            with pytest.raises(ParserError) as exc_info:
                _safe_write_text(target, "content")
            assert "I/O 오류" in str(exc_info.value)

    @pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "cp949"])
    def test_encodings(self, tmp_path: Path, encoding: str):
        target = tmp_path / f"test_{encoding}.md"
        text = "한글 테스트"
        _safe_write_text(target, text, encoding=encoding)
        assert target.read_text(encoding=encoding) == text

    def test_overwrite_existing(self, tmp_path: Path):
        target = tmp_path / "test.md"
        target.write_text("old", encoding="utf-8-sig")
        _safe_write_text(target, "new")
        assert target.read_text(encoding="utf-8-sig") == "new"
