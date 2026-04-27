"""Google Gemini Vision engine with process-wide key rotation support."""

from __future__ import annotations

import logging
import time

from config import FREE_TIER_DELAY
from engines.base_engine import BaseEngine
from utils.gemini_key_rotator import GeminiKeyLease, GeminiKeyRotator
from utils.usage_tracker import UsageTracker, parse_usage_metadata

logger = logging.getLogger(__name__)


class GeminiEngine(BaseEngine):
    """Gemini Vision engine for table and full-page extraction."""

    supports_image = True

    SAFETY_SETTING_DEFS = [
        ("HARM_CATEGORY_HARASSMENT", "BLOCK_NONE"),
        ("HARM_CATEGORY_HATE_SPEECH", "BLOCK_NONE"),
        ("HARM_CATEGORY_SEXUALLY_EXPLICIT", "BLOCK_NONE"),
        ("HARM_CATEGORY_DANGEROUS_CONTENT", "BLOCK_NONE"),
    ]

    PROMPT_TABLE = """Convert this construction-related table image into accurate HTML.

Rules:
1. Always include <table>, <thead>, and <tbody>.
2. Preserve merged headers with correct rowspan and colspan.
3. If headers span multiple rows, include every header row in <thead>.
4. Include every visible body cell in <tbody> without dropping sparse rows.
5. Keep numbers, units, and dimensions exactly as shown.
6. Extract all visible rows down to the bottom of the image.
7. Return only HTML <table>...</table> with no explanation or code fence.
"""

    PROMPT_FULL_PAGE = """Analyze this construction document page and convert it to markdown plus HTML tables.

Rules:
1. Convert tables to HTML using <table>, <thead>, and <tbody>.
2. Preserve merged headers with correct rowspan and colspan.
3. Keep surrounding non-table text in markdown.
4. Preserve numbers, units, dimensions, and visible notes exactly.
5. Return only the converted document content with no explanation.
"""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-2.0-flash",
        tracker: UsageTracker | None = None,
        *,
        api_keys: list[str] | tuple[str, ...] | None = None,
        max_calls_per_key: int = 20,
        key_rotator: GeminiKeyRotator | None = None,
    ):
        try:
            import google.genai as genai
            from google.genai import types as genai_types
        except ImportError as exc:
            raise ImportError(
                "Gemini 엔진을 사용하려면 google-genai 패키지가 필요합니다.\n"
                "설치: pip install google-genai"
            ) from exc

        resolved_keys = tuple(key.strip() for key in (api_keys or ()) if key and key.strip())
        if key_rotator is None:
            if not resolved_keys and api_key:
                resolved_keys = (api_key,)
            if not resolved_keys:
                raise ValueError(
                    "Gemini 엔진은 GEMINI_API_KEY 또는 GEMINI_API_KEYS가 필요합니다.\n"
                    ".env 파일에 키를 설정해 주세요."
                )
            key_rotator = GeminiKeyRotator(
                resolved_keys,
                max_calls_per_key=max_calls_per_key,
            )

        self._genai = genai
        self._types = genai_types
        self._key_rotator = key_rotator
        self._clients: dict[str, object] = {}
        self.model_name = model
        self.tracker = tracker or UsageTracker()
        self._last_key_index: int | None = None
        self._safety_settings = [
            genai_types.SafetySetting(category=category, threshold=threshold)
            for category, threshold in self.SAFETY_SETTING_DEFS
        ]

    def _make_client(self, api_key: str):
        return self._genai.Client(api_key=api_key)

    def _get_client(self, api_key: str):
        client = self._clients.get(api_key)
        if client is None:
            client = self._make_client(api_key)
            self._clients[api_key] = client
        return client

    @staticmethod
    def _is_rate_limit_error(error_text: str) -> bool:
        lowered = error_text.lower()
        return "429" in error_text or "quota" in lowered or "rate limit" in lowered

    def _lease_key(self) -> GeminiKeyLease:
        lease = self._key_rotator.lease()
        if lease.index != self._last_key_index:
            print(
                f"      Gemini key slot {lease.index + 1}/{self._key_rotator.key_count} "
                f"(call {lease.call_number}/{lease.max_calls}, cycle {lease.cycle})"
            )
            self._last_key_index = lease.index
        return lease

    def _generate_content(self, *, contents) -> tuple[str, int, int]:
        config = self._types.GenerateContentConfig(
            safety_settings=self._safety_settings
        )
        max_retries = max(2, self._key_rotator.key_count)
        last_error = ""

        for attempt in range(max_retries):
            time.sleep(FREE_TIER_DELAY)
            lease = self._lease_key()
            client = self._get_client(lease.api_key)

            try:
                response = client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=config,
                )
                input_tokens, output_tokens = parse_usage_metadata(response)
                self.tracker.add(input_tokens, output_tokens)
                return response.text.strip(), input_tokens, output_tokens
            except Exception as exc:
                last_error = str(exc)
                if self._is_rate_limit_error(last_error) and attempt < max_retries - 1:
                    self._key_rotator.exhaust_key(lease.index)
                    print(
                        f"      Gemini quota hit on key slot {lease.index + 1}/"
                        f"{self._key_rotator.key_count}; switching key..."
                    )
                    continue
                raise RuntimeError(last_error) from exc

        raise RuntimeError(last_error or "Gemini request failed")

    @staticmethod
    def _strip_code_fence(result: str) -> str:
        if result.startswith("```"):
            lines = result.split("\n")
            return "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return result

    def extract_table(self, image, table_num: int) -> tuple[str, int, int]:
        try:
            result, input_tokens, output_tokens = self._generate_content(
                contents=[self.PROMPT_TABLE, image]
            )
            result = self._strip_code_fence(result)
            print(f"      테이블 {table_num} 완료 (토큰: {input_tokens}+{output_tokens})")
            return result, input_tokens, output_tokens
        except Exception as exc:
            logger.error("테이블 %s 추출 실패: %s", table_num, exc)
            return f"<!-- 테이블 {table_num} 추출 실패: {str(exc)[:100]} -->", 0, 0

    def extract_full_page(self, image, page_num: int) -> tuple[str, int, int]:
        try:
            result, input_tokens, output_tokens = self._generate_content(
                contents=[self.PROMPT_FULL_PAGE, image]
            )
            print(f"    전체 페이지 {page_num} Gemini 완료 (토큰: {input_tokens}+{output_tokens})")
            return result, input_tokens, output_tokens
        except Exception as exc:
            logger.error("전체 페이지 %s 오류: %s", page_num, exc)
            return "", 0, 0
