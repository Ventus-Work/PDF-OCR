"""tests/unit/exporters/test_base_exporter.py"""

from pathlib import Path
import pytest
from exporters.base_exporter import BaseExporter


class _ConcreteExporter(BaseExporter):
    file_extension = ".txt"

    def export(self, sections, output_path, *, metadata=None, preset_config=None):
        Path(output_path).write_text("ok")
        return Path(output_path)


class TestBaseExporter:
    def test_concrete_subclass_instantiates(self):
        exp = _ConcreteExporter()
        assert exp.file_extension == ".txt"

    def test_abstract_cannot_instantiate(self):
        with pytest.raises(TypeError):
            BaseExporter()

    def test_export_returns_path(self, tmp_path):
        out = tmp_path / "out.txt"
        exp = _ConcreteExporter()
        result = exp.export([], out)
        assert result == out
        assert out.exists()
