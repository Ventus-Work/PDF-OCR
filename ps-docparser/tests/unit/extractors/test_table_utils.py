from extractors import table_utils
from extractors.table_utils import detect_tables, detect_tables_by_text_alignment
from PIL import Image


class DummyTable:
    def __init__(self, bbox):
        self.bbox = bbox


class DummyPage:
    def __init__(self, lines=None, tables=None, words=None, width=612, height=792):
        self.width = width
        self.height = height
        self.lines = lines or []
        self._tables = tables or []
        self._words = words or []

    def find_tables(self, table_settings=None):
        return self._tables

    def extract_words(self, **kwargs):
        return self._words


class TestDetectTables:
    def test_no_tables(self):
        page = DummyPage()
        assert detect_tables(page) == []

    def test_single_table(self):
        page = DummyPage(tables=[DummyTable(bbox=(0, 0, 100, 50))])
        assert detect_tables(page) == [(0, 0, 100, 50)]

    def test_multiple_tables(self):
        page = DummyPage(
            tables=[
                DummyTable(bbox=(0, 0, 100, 50)),
                DummyTable(bbox=(0, 100, 100, 150)),
            ]
        )
        assert len(detect_tables(page)) == 2

    def test_merges_pdf_and_text_detected_bboxes(self, monkeypatch):
        page = DummyPage(tables=[DummyTable(bbox=(0, 0, 100, 50))])
        monkeypatch.setattr(
            table_utils,
            "detect_tables_by_text_alignment",
            lambda _page: [
                {"bbox": (0, 0, 100, 50), "rows": []},
                {"bbox": (120, 10, 220, 90), "rows": []},
            ],
        )
        assert detect_tables(page) == [(0, 0, 100, 50), (120, 10, 220, 90)]

    def test_keeps_nested_small_text_table_when_area_is_distinct(self, monkeypatch):
        page = DummyPage(tables=[DummyTable(bbox=(0, 0, 300, 300))])
        monkeypatch.setattr(
            table_utils,
            "detect_tables_by_text_alignment",
            lambda _page: [{"bbox": (10, 220, 160, 290), "rows": []}],
        )
        assert detect_tables(page) == [(0, 0, 300, 300), (10, 220, 160, 290)]


class TestDetectTablesByTextAlignment:
    def test_detects_keyword_condition_table(self):
        words = [
            {"text": "\uc77c\ubc18\uc0ac\ud56d", "x0": 10, "x1": 70, "top": 10, "bottom": 20},
            {"text": "\ud2b9\uae30\uc0ac\ud56d", "x0": 120, "x1": 180, "top": 10, "bottom": 20},
            {"text": "SS400", "x0": 10, "x1": 60, "top": 30, "bottom": 40},
            {"text": "\uc6a9\uc811", "x0": 120, "x1": 160, "top": 30, "bottom": 40},
        ]
        page = DummyPage(words=words)

        tables = detect_tables_by_text_alignment(page)
        assert len(tables) == 1
        assert tables[0]["bbox"] == (10, 10, 180, 40)

    def test_returns_keyword_table_even_with_few_words(self):
        words = [
            {"text": "\uc77c\ubc18\uc0ac\ud56d", "x0": 10, "x1": 70, "top": 10, "bottom": 20},
            {"text": "\ud2b9\uae30\uc0ac\ud56d", "x0": 120, "x1": 180, "top": 10, "bottom": 20},
            {"text": "A", "x0": 10, "x1": 20, "top": 30, "bottom": 40},
            {"text": "B", "x0": 120, "x1": 130, "top": 30, "bottom": 40},
        ]
        page = DummyPage(words=words)

        tables = detect_tables_by_text_alignment(page)
        assert len(tables) == 1

    def test_condition_table_bbox_keeps_multiple_rows_with_looser_gap(self):
        words = [
            {"text": "\uc77c\ubc18\uc0ac\ud56d", "x0": 10, "x1": 70, "top": 10, "bottom": 20},
            {"text": "\ud2b9\uae30\uc0ac\ud56d", "x0": 120, "x1": 180, "top": 10, "bottom": 20},
            {"text": "1.", "x0": 10, "x1": 20, "top": 30, "bottom": 40},
            {"text": "A", "x0": 40, "x1": 60, "top": 30, "bottom": 40},
            {"text": "B", "x0": 120, "x1": 130, "top": 30, "bottom": 40},
            {"text": "2.", "x0": 10, "x1": 20, "top": 50, "bottom": 60},
            {"text": "C", "x0": 40, "x1": 60, "top": 50, "bottom": 60},
            {"text": "D", "x0": 120, "x1": 130, "top": 50, "bottom": 60},
            {"text": "3.", "x0": 10, "x1": 20, "top": 72, "bottom": 82},
            {"text": "E", "x0": 40, "x1": 60, "top": 72, "bottom": 82},
            {"text": "F", "x0": 120, "x1": 130, "top": 72, "bottom": 82},
        ]
        page = DummyPage(words=words)

        tables = detect_tables_by_text_alignment(page)
        assert len(tables) == 1
        assert tables[0]["bbox"] == (10, 10, 180, 82)


class TestCropTableImage:
    def test_clamps_and_sorts_invalid_bbox(self):
        image = Image.new("RGB", (100, 200), "white")

        cropped = table_utils.crop_table_image(
            image,
            bbox=(110, 180, -10, 20),
            page_height=200,
            page_width=100,
            extended=False,
        )

        assert cropped.size[0] >= 1
        assert cropped.size[1] >= 1
