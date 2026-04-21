"""
tests/integration/test_io_conflicts.py — 파일 I/O 충돌 처리 통합 테스트

대상: utils.io._safe_write_text, exporters.excel_exporter.ExcelExporter
검증: PermissionError / OSError 발생 시 ParserError로 표준화되는지 확인

모든 케이스는 tmp_path(OS 중립)로 격리되어 실제 I/O를 사용한다.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from utils.io import _safe_write_text, ParserError
from exporters.excel_exporter import ExcelExporter


# ─────────────────────────────────────────────────────────────
# _safe_write_text 충돌 처리
# ─────────────────────────────────────────────────────────────

class TestSafeWriteTextConflicts:
    def test_permission_error_raises_parser_error(self, tmp_path: Path):
        target = tmp_path / "out.md"
        with patch("builtins.open", side_effect=PermissionError("access denied")):
            with pytest.raises(ParserError, match="권한 거부"):
                _safe_write_text(target, "content")

    def test_os_error_raises_parser_error(self, tmp_path: Path):
        target = tmp_path / "out.md"
        with patch("builtins.open", side_effect=OSError("disk full")):
            with pytest.raises(ParserError, match="I/O"):
                _safe_write_text(target, "content")

    def test_directory_collision_raises_parser_error(self, tmp_path: Path):
        # 파일 경로에 디렉터리가 이미 존재하는 경우
        collision = tmp_path / "collision.md"
        collision.mkdir()
        with pytest.raises(ParserError):
            _safe_write_text(collision, "content")

    def test_readonly_parent_dir_raises_parser_error(self, tmp_path: Path):
        # Windows에서는 os.chmod 로 디렉터리 쓰기를 막을 수 없으므로 mock으로 시뮬레이션
        target = tmp_path / "readonly" / "out.md"
        with patch("builtins.open", side_effect=PermissionError("read-only")):
            with pytest.raises(ParserError, match="권한 거부"):
                _safe_write_text(target, "content")

    def test_normal_write_succeeds(self, tmp_path: Path):
        target = tmp_path / "out.md"
        _safe_write_text(target, "hello world")
        assert target.read_text(encoding="utf-8-sig") == "hello world"


# ─────────────────────────────────────────────────────────────
# ExcelExporter 충돌 처리
# ─────────────────────────────────────────────────────────────

class TestExcelExporterConflicts:
    def test_permission_error_raises_parser_error(self, tmp_path: Path):
        out = tmp_path / "out.xlsx"
        exporter = ExcelExporter()
        with patch("openpyxl.Workbook.save", side_effect=PermissionError("locked")):
            with pytest.raises(ParserError, match="권한 거부"):
                exporter.export([], out)

    def test_readonly_file_raises_parser_error(self, tmp_path: Path):
        out = tmp_path / "readonly.xlsx"
        out.write_bytes(b"")
        os.chmod(out, stat.S_IREAD)
        try:
            exporter = ExcelExporter()
            with pytest.raises(ParserError):
                exporter.export([], out)
        finally:
            os.chmod(out, stat.S_IWRITE | stat.S_IREAD)
