"""tests/unit/extractors/test_pdf_image_loader.py — PdfImageLoader LRU 캐시 검증."""

from __future__ import annotations

from unittest.mock import MagicMock

from extractors.pdf_image_loader import PdfImageLoader


class TestPdfImageLoaderCache:
    def test_same_page_twice_calls_convert_once(self, mocker):
        """
        동일 페이지를 2회 요청하면 pdf2image.convert_from_path 가 1회만 호출된다.

        Why: LRU 캐시의 핵심 계약.
        """
        mock_img = MagicMock(name="PIL.Image")
        mock_convert = mocker.patch(
            "extractors.pdf_image_loader.convert_from_path",
            return_value=[mock_img],
        )

        loader = PdfImageLoader("fake.pdf", dpi=200, cache_size=4)
        first = loader.get_page(3)
        second = loader.get_page(3)

        assert first is mock_img
        assert second is mock_img
        assert mock_convert.call_count == 1

    def test_lru_evicts_oldest_page_when_cache_full(self, mocker):
        """
        cache_size=2 일 때 3개 페이지를 차례로 요청하면
        가장 오래된 페이지는 evict 되어 재변환(총 4회 호출)되어야 한다.
        """
        mock_convert = mocker.patch(
            "extractors.pdf_image_loader.convert_from_path",
            side_effect=lambda **kw: [MagicMock(name=f"img-p{kw['first_page']}")],
        )

        loader = PdfImageLoader("fake.pdf", cache_size=2)
        loader.get_page(1)  # miss → convert
        loader.get_page(2)  # miss → convert
        loader.get_page(3)  # miss → convert, evict p1
        loader.get_page(1)  # evicted → re-convert

        assert mock_convert.call_count == 4

    def test_close_clears_cache(self, mocker):
        mock_convert = mocker.patch(
            "extractors.pdf_image_loader.convert_from_path",
            return_value=[MagicMock()],
        )
        loader = PdfImageLoader("fake.pdf", cache_size=4)
        loader.get_page(1)
        loader.close()
        loader.get_page(1)  # 캐시 비어있으므로 다시 호출

        assert mock_convert.call_count == 2
