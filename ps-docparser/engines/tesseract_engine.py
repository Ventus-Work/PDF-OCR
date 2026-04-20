"""
engines/tesseract_engine.py — Tesseract 로컬 OCR 엔진

Why: 무료/오프라인 OCR 엔진. API 키 없이 동작하며
     한국어(kor)+영문(eng) 동시 인식을 지원한다.
     네트워크 불가 환경이나 비용 제한 시 폴백 엔진.

Dependencies: pytesseract (pip install pytesseract), Tesseract-OCR 실행 파일
"""
import logging
from pathlib import Path

from PIL import Image

from engines.base_engine import BaseEngine, OcrPageResult

logger = logging.getLogger(__name__)


class TesseractEngine(BaseEngine):
    """Tesseract 로컬 OCR 엔진."""

    supports_image = True
    supports_ocr = True

    def __init__(self, *, tesseract_path: str | None = None, lang: str = "kor+eng"):
        """
        Args:
            tesseract_path: Tesseract 실행 파일 경로 (.env TESSERACT_PATH)
                            None이면 시스템 PATH에서 탐색
            lang: OCR 언어 (기본: kor+eng)
        """
        import pytesseract

        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
        self._pytesseract = pytesseract
        self._lang = lang

    # ── OCR 인터페이스 ──

    def ocr_document(
        self,
        file_path: Path,
        page_indices: list[int] | None = None,
    ) -> list[OcrPageResult]:
        """
        PDF 파일을 페이지별로 이미지 변환 후 Tesseract OCR 처리한다.

        Why: Tesseract는 이미지만 처리 가능하므로
             PDF→이미지 변환이 반드시 필요하다.
             전체 변환 1회가 페이지별 N회보다 효율적.
        """
        from pdf2image import convert_from_path
        from config import POPPLER_PATH

        images = convert_from_path(
            str(file_path),
            dpi=400,
            poppler_path=POPPLER_PATH,
        )

        results = []
        for i, img in enumerate(images):
            if page_indices is not None and i not in page_indices:
                continue
            result = self.ocr_image(img)
            result.page_num = i
            results.append(result)

        return results

    def ocr_image(self, image: Image.Image) -> OcrPageResult:
        """PIL 이미지를 Tesseract OCR로 처리한다."""
        try:
            text = self._pytesseract.image_to_string(
                image, lang=self._lang
            )
        except Exception as e:
            logger.error("Tesseract OCR 실패: %s", e)
            raise

        return OcrPageResult(page_num=0, text=text)

    # ── 표준 파이프라인 호환 ──

    def extract_full_page(
        self, image: Image.Image, page_num: int
    ) -> tuple[str, int, int]:
        result = self.ocr_image(image)
        return (result.text, 0, 0)  # Tesseract: 토큰 카운트 없음

    def extract_table(
        self, image: Image.Image, table_num: int
    ) -> tuple[str, int, int]:
        return self.extract_full_page(image, table_num)
