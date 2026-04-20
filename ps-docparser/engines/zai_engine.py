"""
engines/zai_engine.py — Z.ai GLM-OCR 엔진

Why zai-sdk (not zhipuai):
    ocr.py가 실제로 사용하던 SDK는 'zai-sdk' (pip install zai-sdk)이며
    ZaiClient.layout_parsing.create(model, file: str(data URI))를 지원한다.
    zhipuai SDK는 open.bigmodel.cn(본토) 전용이며 해외 차단됨.

Dependencies: zai-sdk (pip install zai-sdk)
"""
import logging
import re
from pathlib import Path

from PIL import Image

from engines.base_engine import BaseEngine, OcrPageResult
from utils.ocr_utils import file_to_data_uri, image_to_data_uri, pdf_page_to_image

logger = logging.getLogger(__name__)


class ZaiEngine(BaseEngine):
    """Z.ai GLM-OCR 엔진 (zai-sdk 기반)."""

    supports_image = True
    supports_ocr = True

    def __init__(self, api_key: str, *, tracker=None):
        """
        Args:
            api_key: Z.ai API 키 (.env ZAI_API_KEY)
            tracker: UsageTracker 인스턴스 (선택)

        Why ZaiClient: ocr.py에서 실제 사용하던 z.ai 공식 SDK.
            layout_parsing.create(file=data_uri_str) 를 그대로 지원한다.
        """
        from zai import ZaiClient
        self._client = ZaiClient(api_key=api_key)
        self._tracker = tracker
        self._last_layout_details: list[dict] = []

    # ── OCR 인터페이스 ──

    def ocr_document(
        self,
        file_path: Path,
        page_indices: list[int] | None = None,
    ) -> list[OcrPageResult]:
        """
        PDF/이미지 파일을 Z.ai layout_parsing으로 OCR 처리한다.

        page_indices 미지정 시 전체 파일을 data URI로 한 번에 전송.
        page_indices 지정 시 해당 페이지를 이미지로 변환 후 개별 처리.

        Phase 5: 파일 단위 캐시 적용 (page_indices=None 경우만 캐시 대상).
            - 캐시 키: sha256(파일 바이트) + 'zai' → 파일 내용이 바뀌면 새 키
            - 캐시 적중 시 API 호출 없이 즉시 반환
        """
        file_path = Path(file_path)

        if page_indices is None:
            # ── 파일 단위 캐시 조회 ──
            cache_key = None
            if self.cache:
                cache_key = self.cache.make_key_from_file(file_path, "zai")
                cached = self.cache.get(cache_key)
                if cached is not None:
                    logger.info("[Cache HIT] %s", file_path.name)
                    text = cached.get("text", "")
                    layout = cached.get("layout", [])
                    self._last_layout_details = layout
                    return [OcrPageResult(page_num=0, text=text, layout_details=layout)]

            # 캐시 미스 → API 호출
            data_uri = file_to_data_uri(file_path)
            response = self._call_api(data_uri)
            text, layout = self._parse_response(response)
            self._last_layout_details = layout

            # ── 파일 단위 캐시 저장 ──
            if self.cache and cache_key:
                self.cache.put(cache_key, {"text": text, "layout": layout}, engine="zai")

            return [OcrPageResult(page_num=0, text=text, layout_details=layout)]

        else:
            # 페이지별 이미지 변환 후 개별 처리 (이미지 단위 캐시는 ocr_image 내부)
            results = []
            for idx in page_indices:
                image = pdf_page_to_image(file_path, idx, dpi=400)
                result = self.ocr_image(image)
                result.page_num = idx
                results.append(result)
            return results

    def ocr_image(self, image: Image.Image) -> OcrPageResult:
        """
        PIL 이미지를 Z.ai OCR로 처리한다.

        Phase 5: 이미지 단위 캐시 적용.
            - 캐시 키: sha256(이미지 PNG 바이트) + 'zai'
        """
        import io
        # 이미지 → PNG 바이트 (캐시 키 생성용 + data_uri 생성)
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        img_bytes = buf.getvalue()

        # ── 이미지 단위 캐시 조회 ──
        cache_key = None
        if self.cache:
            cache_key = self.cache.make_key_from_data(img_bytes, "zai")
            cached = self.cache.get(cache_key)
            if cached is not None:
                logger.info("[Cache HIT] 이미지 OCR (zai)")
                text = cached.get("text", "")
                layout = cached.get("layout", [])
                self._last_layout_details = layout
                return OcrPageResult(page_num=0, text=text, layout_details=layout)

        # 캐시 미스 → API 호출
        data_uri = image_to_data_uri(image)
        response = self._call_api(data_uri)
        text, layout = self._parse_response(response)
        self._last_layout_details = layout

        # ── 이미지 단위 캐시 저장 ──
        if self.cache and cache_key:
            self.cache.put(cache_key, {"text": text, "layout": layout}, engine="zai")

        return OcrPageResult(page_num=0, text=text, layout_details=layout)

    # ── 표준 파이프라인 호환 ──

    def extract_full_page(
        self, image: Image.Image, page_num: int
    ) -> tuple[str, int, int]:
        """표준 파이프라인 호환: 이미지 → OCR → Markdown 텍스트."""
        result = self.ocr_image(image)
        return (result.text, result.input_tokens, result.output_tokens)

    def extract_table(
        self, image: Image.Image, table_num: int
    ) -> tuple[str, int, int]:
        """표준 파이프라인 호환: 테이블 이미지 → OCR → 텍스트."""
        return self.extract_full_page(image, table_num)

    # ── 내부 메서드 ──

    def _call_api(self, data_uri: str) -> dict:
        """
        Z.ai layout_parsing API 호출.

        zai-sdk의 ZaiClient.layout_parsing.create()는
        file 파라미터로 data URI 문자열을 직접 받는다.
        (zhipuai SDK와 달리 bytes 변환 불필요)
        """
        try:
            response = self._client.layout_parsing.create(
                model="glm-ocr",
                file=data_uri,
            )
            # LayoutParsingResp → dict 변환
            if hasattr(response, 'model_dump'):
                return response.model_dump()
            elif hasattr(response, '__dict__'):
                return vars(response)
            return response if isinstance(response, dict) else {"raw": str(response)}
        except Exception as e:
            logger.error("Z.ai API 호출 실패: %s", e)
            raise

    def _parse_response(self, response: dict) -> tuple[str, list[dict]]:
        """
        Z.ai layout_parsing 응답에서 텍스트와 layout_details를 추출한다.

        응답 구조 (우선순위):
        1. response['md_results']       — Markdown 텍스트 (주 필드)
        2. response['pages'][n]['markdown'] — 페이지별 Markdown
        3. response['content']          — 평문 텍스트
        4. response['text']             — 평문 텍스트
        5. str(response)                — 최종 폴백
        """
        text = ""
        layout = []

        # ZaiClient 응답은 output 래퍼 없이 바로 필드가 노출되는 경우도 있음
        data = response.get("output", response)

        # 1순위: md_results
        if data.get("md_results"):
            text = data["md_results"]
        # 2순위: pages[].markdown
        elif data.get("pages"):
            parts = []
            for page in data["pages"]:
                md = page.get("markdown", page.get("text", ""))
                parts.append(md)
            text = "\n\n".join(parts)
        # 3순위: content
        elif data.get("content"):
            text = data["content"]
        # 4순위: text
        elif data.get("text"):
            text = data["text"]
        else:
            text = str(data)
            logger.warning("Z.ai 응답에서 텍스트 필드를 찾을 수 없음, 전체 문자열 사용")

        # 이미지 링크 제거: ![](page=0,bbox=...)
        text = re.sub(r'!\[.*?\]\(.*?\)', '', text)

        # layout_details 추출
        layout = data.get("layout_details", [])

        return text, layout

    @property
    def last_layout_details(self) -> list[dict]:
        """마지막 OCR 호출의 layout_details (2차 추출 시 참조)."""
        return self._last_layout_details
