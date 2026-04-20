"""
table_parser.py 단위 테스트 (P1)
"""
import pytest
from parsers.table_parser import clean_cell_text, is_note_row, try_numeric

class TestTableParser:
    def test_clean_cell_text(self):
        assert clean_cell_text("  셀   내용  ") == "셀 내용"
        assert clean_cell_text("줄바꿈\n내용") == "줄바꿈 내용"

    def test_is_note_row(self):
        # 첫 번째 항목이 주석 기호로 시작하면 True 반환
        assert is_note_row(["[주] 참고사항", ""]) is True
        assert is_note_row(["일반 데이터", "값"]) is False

    def test_try_numeric(self):
        assert bool(try_numeric("1"))
