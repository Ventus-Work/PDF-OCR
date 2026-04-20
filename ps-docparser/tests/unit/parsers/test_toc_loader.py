import json
import pytest
from parsers.toc_loader import load_toc
from utils.io import ParserError


class TestLoadToc:
    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(ParserError, match="찾을 수 없습니다"):
            load_toc(str(tmp_path / "missing.txt"))

    def test_loads_json_section_map(self, tmp_path):
        toc = tmp_path / "toc.json"
        toc.write_text(
            json.dumps({"section_map": {"1": "서론", "2": "본론"}}),
            encoding="utf-8",
        )
        result = load_toc(str(toc))
        assert result == {"1": "서론", "2": "본론"}

    def test_json_without_section_map_returns_empty(self, tmp_path):
        toc = tmp_path / "toc.json"
        toc.write_text(json.dumps({}), encoding="utf-8")
        result = load_toc(str(toc))
        assert result == {}

    def test_non_json_calls_toc_parser(self, tmp_path, mocker):
        toc = tmp_path / "toc.txt"
        toc.write_text("1 서론\n2 본론", encoding="utf-8")
        mock_parse = mocker.patch(
            "parsers.toc_loader.toc_parser_module.parse_toc_file",
            return_value={"1": "서론"},
        )
        result = load_toc(str(toc))
        mock_parse.assert_called_once_with(str(toc))
        assert result == {"1": "서론"}
