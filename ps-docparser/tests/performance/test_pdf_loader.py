"""
tests/performance/test_pdf_loader.py — PdfImageLoader LRU 캐시 회귀 테스트

Why: PdfImageLoader가 실수로 일반 함수 호출로 교체되면
     동일 페이지를 N회 재변환하여 메모리 폭증이 재발한다.
     이 테스트가 통과하면 캐시가 정상 동작함을 보장한다.
"""
from unittest.mock import patch, MagicMock

import pytest


class TestPdfImageLoader:
    @patch("extractors.pdf_image_loader.convert_from_path")
    def test_lru_cache_avoids_reconversion(self, mock_convert):
        """
        같은 페이지 번호를 여러 번 get_page() 해도
        convert_from_path는 고유 페이지 수만큼만 호출되어야 한다.
        """
        from extractors.pdf_image_loader import PdfImageLoader

        mock_convert.return_value = [MagicMock()]
        loader = PdfImageLoader("dummy.pdf", cache_size=4)

        loader.get_page(1)   # 미스 → 변환 1회
        loader.get_page(1)   # 히트 → 변환 없음
        loader.get_page(2)   # 미스 → 변환 1회
        loader.get_page(1)   # 히트 → 변환 없음
        loader.get_page(2)   # 히트 → 변환 없음

        # 고유 페이지 2개(1, 2)만 변환 호출
        assert mock_convert.call_count == 2, (
            f"예상 2회, 실제 {mock_convert.call_count}회 — LRU 캐시 미동작"
        )
        loader.close()

    @patch("extractors.pdf_image_loader.convert_from_path")
    def test_cache_cleared_after_close(self, mock_convert):
        """
        close() 후에는 캐시가 비워지므로 이후 get_page()는 재변환해야 한다.
        """
        from extractors.pdf_image_loader import PdfImageLoader

        mock_convert.return_value = [MagicMock()]
        loader = PdfImageLoader("dummy.pdf", cache_size=2)

        loader.get_page(1)          # 변환 1회
        loader.close()              # 캐시 초기화
        loader.get_page(1)          # 캐시 비워졌으므로 재변환

        assert mock_convert.call_count == 2, (
            "close() 후 재변환이 발생해야 하는데 캐시가 남아 있음"
        )

    def test_close_no_exception(self):
        """close()는 예외 없이 수행되어야 한다."""
        from extractors.pdf_image_loader import PdfImageLoader
        loader = PdfImageLoader("dummy.pdf")
        loader.close()  # 예외 없이 수행

    def test_context_manager(self):
        """with 문으로 사용 시 __exit__에서 close()가 호출되어야 한다."""
        from extractors.pdf_image_loader import PdfImageLoader
        with patch.object(PdfImageLoader, "close") as mock_close:
            with PdfImageLoader("dummy.pdf"):
                pass
        mock_close.assert_called_once()
