import pytest
from pathlib import Path
from unittest.mock import patch
from utils.paths import get_output_path


class TestGetOutputPath:
    def test_returns_dated_path(self, tmp_path):
        with patch("utils.paths.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260420"
            result = get_output_path(tmp_path, "sample.pdf")
        assert result == tmp_path / "20260420_sample.md"

    def test_page_indices_appended(self, tmp_path):
        with patch("utils.paths.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260420"
            result = get_output_path(tmp_path, "sample.pdf", page_indices=[0, 1, 2])
        assert result == tmp_path / "20260420_sample_p1-3.md"

    def test_no_collision_when_file_exists(self, tmp_path):
        with patch("utils.paths.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260420"
            (tmp_path / "20260420_sample.md").touch()
            result = get_output_path(tmp_path, "sample.pdf")
        assert result == tmp_path / "20260420_sample_1.md"

    def test_creates_output_dir(self, tmp_path):
        new_dir = tmp_path / "nested" / "dir"
        with patch("utils.paths.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "20260420"
            get_output_path(new_dir, "sample.pdf")
        assert new_dir.exists()
