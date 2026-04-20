"""
bom_table_parser 단위 테스트
"""
import pytest
from parsers.bom_table_parser import parse_markdown_pipe_table, filter_noise_rows

class TestBomTableParser:
    def test_parse_markdown_pipe_table(self):
        text = "| PIPE | 10 |\n| BALL VALVE | 5 |"
        rows = parse_markdown_pipe_table(text)
        assert len(rows) == 2
        assert rows[0][0].strip() == "PIPE"
        assert rows[1][1].strip() == "5"

    def test_filter_noise_rows(self):
        rows = [
            ["PIPE", "10"],
            ["소계", "10"],
            ["합계", "10"]
        ]
        noise_kw = ["소계", "합계"]
        filtered = filter_noise_rows(rows, noise_kw)
        assert len(filtered) == 1
        assert filtered[0][0] == "PIPE"
