"""parsers/types.py — TypedDict 구조 검증."""

from parsers.types import TableCell, ParsedTable, ParsedSection, TocEntry


class TestTableCell:
    def test_required_text_field(self):
        cell: TableCell = {"text": "A"}
        assert cell["text"] == "A"

    def test_optional_rowspan_colspan(self):
        cell: TableCell = {"text": "B", "rowspan": 2, "colspan": 3}
        assert cell["rowspan"] == 2
        assert cell["colspan"] == 3


class TestParsedTable:
    def test_minimal_structure(self):
        table: ParsedTable = {
            "type": "general",
            "headers": ["항목", "수량"],
            "rows": [[{"text": "A"}, {"text": "1"}]],
        }
        assert table["type"] == "general"
        assert len(table["headers"]) == 2

    def test_all_type_literals(self):
        for t in ("general", "bom", "line_list", "material", "cost"):
            table: ParsedTable = {"type": t, "headers": [], "rows": []}
            assert table["type"] == t


class TestParsedSection:
    def test_required_fields(self):
        section: ParsedSection = {
            "section_id": "1",
            "title": "서론",
            "text": "내용",
            "tables": [],
        }
        assert section["section_id"] == "1"
        assert section["tables"] == []

    def test_optional_division_chapter(self):
        section: ParsedSection = {
            "section_id": "2",
            "title": "본론",
            "text": "본론 내용",
            "tables": [],
            "division": "A부문",
            "chapter": "제1장",
        }
        assert section["division"] == "A부문"


class TestTocEntry:
    def test_required_fields(self):
        entry: TocEntry = {"page": 1, "section_id": "1.1", "title": "개요"}
        assert entry["page"] == 1

    def test_optional_division_chapter(self):
        entry: TocEntry = {
            "page": 5,
            "section_id": "2.1",
            "title": "세부항목",
            "division": "B부문",
            "chapter": "제2장",
        }
        assert entry["division"] == "B부문"
