"""tests/unit/exporters/test_json_exporter.py"""

import json
from pathlib import Path
import pytest
from exporters.json_exporter import JsonExporter


class TestJsonExporter:
    def test_file_extension(self):
        assert JsonExporter.file_extension == ".json"

    def test_export_sections_only(self, tmp_path: Path):
        sections = [{"section_id": "S-1", "tables": []}]
        out = tmp_path / "out.json"
        JsonExporter().export(sections, out)
        data = json.loads(out.read_text(encoding="utf-8-sig"))
        assert isinstance(data, list)
        assert data[0]["section_id"] == "S-1"

    def test_export_with_metadata(self, tmp_path: Path):
        sections = [{"section_id": "S-1"}]
        meta = {"description": "테스트 문서"}
        out = tmp_path / "out.json"
        JsonExporter().export(sections, out, metadata=meta)
        data = json.loads(out.read_text(encoding="utf-8-sig"))
        assert "metadata" in data
        assert data["metadata"]["description"] == "테스트 문서"
        assert data["sections"][0]["section_id"] == "S-1"

    def test_export_returns_path(self, tmp_path: Path):
        out = tmp_path / "out.json"
        result = JsonExporter().export([], out)
        assert result == out
