"""
engines/gemini_engine.py — Google Gemini Vision 엔진

Why: 테이블 구조(셀 병합, 테두리 없는 표)를 정확히 파싱하려면 Vision AI가 필요하다.
     Gemini는 한국어 건설 문서에 대한 이해도와 비용 대비 품질이 최적이다.

변경점 (원본 대비):
    - supports_image = True (기본값)
    - google.genai를 __init__ 내부에서 지연 import
      (Why: local 엔진 사용 시 이 패키지 미설치여도 에러가 나지 않아야 한다)
    - tracker 전역 → self.tracker 인스턴스 변수
    - SAFETY_SETTING_DEFS → 클래스 상수로 이동
    - google.genai.Client(api_key=...) → __init__ 에서만 호출 (전역 X)

이식 원본: step1_extract_gemini_v33.py L512~606
마이그레이션: google.generativeai (지원 종료) → google.genai 1.x
"""

import time
import logging

from engines.base_engine import BaseEngine
from utils.usage_tracker import UsageTracker, parse_usage_metadata
from config import FREE_TIER_DELAY

logger = logging.getLogger(__name__)


class GeminiEngine(BaseEngine):
    """
    Google Gemini Vision API를 사용하는 AI 추출 엔진.

    사용 예:
        tracker = UsageTracker()
        engine = GeminiEngine(api_key="...", model="gemini-2.0-flash", tracker=tracker)
        html, in_tok, out_tok = engine.extract_table(image, table_num=1)
    """

    supports_image = True  # pdf2image + Poppler 필요

    # 안전 필터 설정: 건설/기술 문서는 콘텐츠 필터링 완전 해제
    # Why: 기술적 수치("폭발물 압력" 등)나 전문 용어가 안전 필터에 걸려
    #      빈 응답이 반환되는 것을 방지한다.
    SAFETY_SETTING_DEFS = [
        ("HARM_CATEGORY_HARASSMENT",        "BLOCK_NONE"),
        ("HARM_CATEGORY_HATE_SPEECH",       "BLOCK_NONE"),
        ("HARM_CATEGORY_SEXUALLY_EXPLICIT", "BLOCK_NONE"),
        ("HARM_CATEGORY_DANGEROUS_CONTENT", "BLOCK_NONE"),
    ]

    # 테이블 이미지 → HTML 변환 프롬프트
    PROMPT_TABLE = """이 건설 관련 테이블 이미지를 HTML 형식으로 정확히 변환해주세요.

규칙:
1. 반드시 <table>, <thead>, <tbody> 태그를 모두 사용
2. 병합된 셀은 rowspan/colspan 정확히 표현
3. 헤더가 여러 줄이면 <thead>에 모두 포함
4. <tbody>에 모든 데이터 행을 빠짐없이 포함 — 본문 행을 절대 생략하지 마세요
5. 숫자, 단위, 규격은 원본 그대로 정확히 추출
6. 이미지 하단이 잘려 보여도, 보이는 모든 행을 끝까지 추출
7. 설명이나 코드블록 없이 <table>...</table> HTML만 출력
"""

    # 전체 페이지 이미지 → MD+HTML 변환 프롬프트
    PROMPT_FULL_PAGE = """이 건설 관련 문서 이미지를 분석하여 마크다운 + HTML 형식으로 변환해주세요.

규칙:
1. 테이블은 반드시 HTML <table> 형식으로 변환
   - <thead>와 <tbody>를 반드시 구분
   - 모든 데이터 행을 빠짐없이 <tbody>에 포함
   - 병합 셀은 rowspan/colspan 사용
2. 일반 텍스트는 마크다운 형식
3. 숫자, 단위, 규격은 원본 그대로 정확히 추출
4. 테이블 앞뒤 텍스트도 모두 포함
5. 설명 없이 변환 결과만 출력
"""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash",
        tracker: UsageTracker = None,
    ):
        """
        Args:
            api_key: Gemini API 키 (필수)
            model: 사용할 모델명
            tracker: 사용량 추적기 (None이면 내부 생성)

        Raises:
            ImportError: google-genai 패키지 미설치 시
            ValueError: api_key 미제공 시
        """
        # 지연 import: local 엔진 사용 시 패키지 미설치여도 에러 없음
        try:
            import google.genai as genai
            from google.genai import types as genai_types
        except ImportError:
            raise ImportError(
                "Gemini 엔진을 사용하려면 google-genai 패키지가 필요합니다.\n"
                "설치: pip install google-genai"
            )

        if not api_key:
            raise ValueError(
                "Gemini 엔진에 GEMINI_API_KEY가 필요합니다.\n"
                ".env 파일에 GEMINI_API_KEY=your_key 를 추가하세요."
            )

        self._client = genai.Client(api_key=api_key)
        self._types = genai_types
        self.model_name = model
        self.tracker = tracker or UsageTracker()
        self._safety_settings = [
            genai_types.SafetySetting(category=cat, threshold=thr)
            for cat, thr in self.SAFETY_SETTING_DEFS
        ]

    def extract_table(self, image, table_num: int) -> tuple[str, int, int]:
        """
        테이블 이미지 크롭을 Gemini Vision으로 HTML 변환.

        재시도 로직: 429(할당량 초과) 발생 시 60초 대기 후 1회 재시도.

        이식 원본: step1_extract_gemini_v33.py L512~567
        """
        time.sleep(FREE_TIER_DELAY)  # 무료 티어 RPM 제한 준수

        config = self._types.GenerateContentConfig(
            safety_settings=self._safety_settings
        )
        max_retries = 2
        for attempt in range(max_retries):
            try:
                response = self._client.models.generate_content(
                    model=self.model_name,
                    contents=[self.PROMPT_TABLE, image],
                    config=config,
                )

                input_tokens, output_tokens = parse_usage_metadata(response)
                self.tracker.add(input_tokens, output_tokens)

                result = response.text.strip()

                # 코드 블록 래퍼 제거: ```html ... ``` → 내부 HTML만 추출
                if result.startswith("```"):
                    lines = result.split("\n")
                    result = "\n".join(
                        lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
                    )

                print(f"      ✅ 테이블 {table_num} 완료 (토큰: {input_tokens}+{output_tokens})")
                return result, input_tokens, output_tokens

            except Exception as e:
                error_str = str(e)
                if "429" in error_str and attempt < max_retries - 1:
                    print(f"      ⚠️ 할당량 초과! 60초 대기 후 재시도 ({attempt + 1}/{max_retries})...")
                    time.sleep(60)
                    continue
                logger.error(f"테이블 {table_num} 추출 실패 (시도 {attempt + 1}): {e}")
                return f"<!-- 테이블 {table_num} 추출 실패: {error_str[:100]} -->", 0, 0

        return f"<!-- 테이블 {table_num} 추출 실패 -->", 0, 0

    def extract_full_page(self, image, page_num: int) -> tuple[str, int, int]:
        """
        전체 페이지 이미지를 Gemini Vision으로 MD+HTML 변환.

        Why: bbox 검증 실패(비정상 테이블) 감지 시 전체 페이지를 한 번에
             AI에게 전달하는 폴백으로 사용한다.

        이식 원본: step1_extract_gemini_v33.py L570~606
        """
        time.sleep(FREE_TIER_DELAY)

        config = self._types.GenerateContentConfig(
            safety_settings=self._safety_settings
        )
        try:
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=[self.PROMPT_FULL_PAGE, image],
                config=config,
            )

            input_tokens, output_tokens = parse_usage_metadata(response)
            self.tracker.add(input_tokens, output_tokens)

            print(f"    ✅ 전체 페이지 {page_num} Gemini 완료 (토큰: {input_tokens}+{output_tokens})")
            return response.text.strip(), input_tokens, output_tokens

        except Exception as e:
            logger.error(f"전체 페이지 {page_num} 오류: {e}")
            return "", 0, 0
