from pathlib import Path

from engines.base_engine import BaseEngine, OcrPageResult
from extractors.ocr_document_extractor import process_pdf_ocr_document


class ZaiEngine(BaseEngine):
    supports_image = True
    supports_ocr = True

    def __init__(self, results):
        self._results = results

    def extract_table(self, image, table_num):
        raise NotImplementedError

    def extract_full_page(self, image, page_num):
        raise NotImplementedError

    def ocr_document(self, file_path: Path, page_indices=None):
        return self._results


class MistralEngine(ZaiEngine):
    pass


class TesseractEngine(ZaiEngine):
    pass


def test_process_pdf_ocr_document_preserves_zai_layout_order():
    engine = ZaiEngine(
        [
            OcrPageResult(
                page_num=0,
                text="",
                layout_details=[
                    {"label": "text", "text": "머리글"},
                    {"label": "table", "content": "<table><tr><td>A</td></tr></table>"},
                    {"label": "text", "text": "본문"},
                ],
            )
        ]
    )

    output = process_pdf_ocr_document("sample.pdf", engine)

    assert output.index("머리글") < output.index("<table>") < output.index("본문")


def test_process_pdf_ocr_document_converts_mistral_pipe_tables():
    engine = MistralEngine(
        [
            OcrPageResult(
                page_num=0,
                text="| 품목 | 수량 |\n| --- | --- |\n| 아연도금강판 | 10 |\n",
            )
        ]
    )

    output = process_pdf_ocr_document("sample.pdf", engine)

    assert "<table>" in output
    assert "<th>품목</th>" in output
    assert "<td>아연도금강판</td>" in output


def test_process_pdf_ocr_document_keeps_tesseract_plain_text():
    engine = TesseractEngine([OcrPageResult(page_num=0, text="스캔 텍스트")])

    output = process_pdf_ocr_document("sample.pdf", engine)

    assert "<!-- PAGE 1" in output
    assert "스캔 텍스트" in output


def test_process_pdf_ocr_document_inserts_toc_section_markers(mocker):
    engine = TesseractEngine([OcrPageResult(page_num=0, text="본문")])

    mocker.patch(
        "extractors.ocr_document_extractor.process_toc_context",
        return_value=(
            {"chapter": "제1장", "section": "1-1", "sections": []},
            [
                {
                    "id": "1-1",
                    "title": "토공사",
                    "chapter": "제1장",
                    "section": "1-1",
                }
            ],
            1,
        ),
    )

    class FakeTocParser:
        @staticmethod
        def build_page_to_sections_map(section_map):
            return {1: section_map}

        @staticmethod
        def get_active_section(pdf_page_num, section_map):
            return None

    output = process_pdf_ocr_document(
        "sample.pdf",
        engine,
        section_map={"1": "dummy"},
        toc_parser_module=FakeTocParser,
        preset="pumsem",
        division_names=["토공사"],
    )

    assert "<!-- SECTION: 1-1 | 토공사" in output
