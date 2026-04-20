"""
engines/mistral_engine.py — Mistral Pixtral OCR 엔진

Why: Mistral OCR은 페이지별 Markdown을 반환하며,
     파이프(|) 기반 테이블 포맷팅이 우수하여
     Z.ai 실패 시 2차 폴백 엔진으로 사용한다.

Dependencies: mistralai (pip install mistralai)
"""
import logging
from pathlib import Path

from PIL import Image

from engines.base_engine import BaseEngine, OcrPageResult
from utils.ocr_utils import file_to_data_uri, image_to_data_uri

logger = logging.getLogger(__name__)


class MistralEngine(BaseEngine):
    """Mistral Pixtral OCR 엔진."""

    supports_image = True
    supports_ocr = True

    def __init__(self, api_key: str, *, model: str = "mistral-ocr-latest", tracker=None):
        """
        Args:
            api_key: Mistral API 키 (.env MISTRAL_API_KEY)
            model: OCR 모델명 (기본: mistral-ocr-latest)
            tracker: UsageTracker 인스턴스 (선택)
        """
        from mistralai import Mistral
        self._client = Mistral(api_key=api_key)
        self._model = model
        self._tracker = tracker

    # ── OCR 인터페이스 ──

    def ocr_document(
        self,
        file_path: Path,
        page_indices: list[int] | None = None,
    ) -> list[OcrPageResult]:
        """
        PDF/이미지 파일을 Mistral OCR로 처리한다.

        Mistral은 전체 파일을 처리하고 페이지별 결과를 반환한다.
        page_indices 지정 시 해당 페이지 결과만 필터링.

        Phase 5: 파일 단위 캐시 적용.
            - 캐시 키: sha256(파일 바이트) + 'mistral'
            - 캐시 저장 형식: [{"page_num": int, "text": str}, ...]
        """
        file_path = Path(file_path)

        # ── 파일 단위 캐시 조회 ──
        cache_key = None
        if self.cache:
            cache_key = self.cache.make_key_from_file(file_path, "mistral")
            cached = self.cache.get(cache_key)
            if cached is not None:
                logger.info("[Cache HIT] %s", file_path.name)
                all_results = [
                    OcrPageResult(page_num=p["page_num"], text=p["text"])
                    for p in cached
                ]
                if page_indices is not None:
                    all_results = [r for r in all_results if r.page_num in page_indices]
                return all_results

        # 캐시 미스 → API 호출
        data_uri = file_to_data_uri(file_path)
        try:
            response = self._client.ocr.process(
                model=self._model,
                document={"type": "document_url", "document_url": data_uri},
            )
        except Exception as e:
            logger.error("Mistral OCR API 호출 실패: %s", e)
            raise

        results = []
        for i, page in enumerate(response.pages):
            if page_indices is not None and i not in page_indices:
                continue
            results.append(OcrPageResult(
                page_num=i,
                text=page.markdown,
                layout_details=[],
            ))

        # ── 파일 단위 캐시 저장 (전체 페이지 반환 후 저장) ──
        if self.cache and cache_key:
            # 필터링 전 전체 페이지를 저장으로 사용: 이후 다른 page_indices로 재호출 시도 적중
            all_pages_data = [
                {"page_num": i, "text": p.markdown}
                for i, p in enumerate(response.pages)
            ]
            self.cache.put(cache_key, all_pages_data, engine="mistral")

        return results

    def ocr_image(self, image: Image.Image) -> OcrPageResult:
        """PIL 이미지를 Mistral OCR로 처리한다."""
        data_uri = image_to_data_uri(image)

        try:
            response = self._client.ocr.process(
                model=self._model,
                document={"type": "document_url", "document_url": data_uri},
            )
        except Exception as e:
            logger.error("Mistral OCR 이미지 처리 실패: %s", e)
            raise

        text = "\n\n".join(p.markdown for p in response.pages)
        return OcrPageResult(page_num=0, text=text)

    # ── 표준 파이프라인 호환 ──

    def extract_full_page(
        self, image: Image.Image, page_num: int
    ) -> tuple[str, int, int]:
        result = self.ocr_image(image)
        return (result.text, result.input_tokens, result.output_tokens)

    def extract_table(
        self, image: Image.Image, table_num: int
    ) -> tuple[str, int, int]:
        return self.extract_full_page(image, table_num)
