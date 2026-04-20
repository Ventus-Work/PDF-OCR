"""파서 공통 TypedDict 정의. (spec §5.1)"""

from typing import TypedDict, Literal, NotRequired


class TableCell(TypedDict):
    text: str
    rowspan: NotRequired[int]
    colspan: NotRequired[int]


class ParsedTable(TypedDict):
    type: Literal["general", "bom", "line_list", "material", "cost"]
    headers: list[str]
    rows: list[list[TableCell]]
    page: NotRequired[int]


class ParsedSection(TypedDict):
    section_id: str
    title: str
    division: NotRequired[str]
    chapter: NotRequired[str]
    text: str
    tables: list[ParsedTable]
    metadata: NotRequired[dict]


class TocEntry(TypedDict):
    page: int
    section_id: str
    title: str
    division: NotRequired[str]
    chapter: NotRequired[str]
