import pytest
from extractors.table_utils import detect_tables


class DummyLine:
    def __init__(self, x0, y0, x1, y1):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1


class DummyTable:
    def __init__(self, bbox):
        self.bbox = bbox
    def extract(self):
        return [["A", "B"], ["1", "2"]]


class DummyPage:
    def __init__(self, lines=None, tables=None, width=612, height=792):
        self.width = width
        self.height = height
        self.lines = lines or []
        self._tables = tables or []
    def find_tables(self, table_settings=None):
        return self._tables


class TestDetectTables:
    def test_no_tables(self):
        page = DummyPage()
        assert detect_tables(page) == []

    def test_single_table(self):
        page = DummyPage(tables=[DummyTable(bbox=(0, 0, 100, 50))])
        res = detect_tables(page)
        assert len(res) == 1

    def test_multiple_tables(self):
        page = DummyPage(tables=[
            DummyTable(bbox=(0, 0, 100, 50)),
            DummyTable(bbox=(0, 100, 100, 150)),
        ])
        res = detect_tables(page)
        assert len(res) == 2

    def test_empty_page_with_lines_only(self):
        # 라인만 있고 실제 테이블은 없는 경우
        page = DummyPage(
            lines=[DummyLine(0, 0, 100, 0)],
            tables=[],
        )
        assert detect_tables(page) == []
