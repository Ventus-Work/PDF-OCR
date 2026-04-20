"""
utils/usage_tracker.py — AI API 사용량 추적 모듈

Why: API 호출 횟수와 토큰 수를 누적하여 예상 비용을 계산한다.
     전역 변수 대신 인스턴스로 생성하여 main.py에서 엔진에 주입하는 방식으로 사용한다.
     (전역 공유 시 모듈 분리 후 참조 불가 문제 발생 → 해결: 의존성 주입)

이식 원본: step1_extract_gemini_v33.py L106~134, L196~203
Phase 8: Gemini 가격을 config.py 환경변수에서 로드 + 생성자 주입 허용
"""

from config import (
    GEMINI_INPUT_PRICE_PER_M,
    GEMINI_OUTPUT_PRICE_PER_M,
    GEMINI_PRICING_MODEL,
)


class UsageTracker:
    """
    AI API 사용량(토큰/비용) 추적 클래스.

    사용 패턴:
        tracker = UsageTracker()
        engine = GeminiEngine(api_key=..., tracker=tracker)
        # 처리 완료 후
        print(tracker.summary())

    Phase 8: input_price/output_price를 생성자에서 주입 가능.
             未지정 시 config.py의 환경변수 값 사용.
             멀티모델(Gemini+Mistral 혼용) 시 모델별로 다른 가격 주입 가능.
    """

    def __init__(self, input_price: float = None, output_price: float = None):
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.call_count: int = 0
        # config에서 로드하되, 생성자 주입 허용 (테스트/멀티모델 대응)
        # Why: 테스트에서 monkeypatch 없이 임의 가격 주입 가능하도록
        self.input_price: float = input_price if input_price is not None else GEMINI_INPUT_PRICE_PER_M
        self.output_price: float = output_price if output_price is not None else GEMINI_OUTPUT_PRICE_PER_M

    def add(self, input_tokens: int, output_tokens: int) -> None:
        """호출 1회의 토큰 수를 누적한다."""
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.call_count += 1

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    @property
    def total_cost_usd(self) -> float:
        """예상 총 비용(USD) — 프로퍼티로 접근 가능."""
        return (
            (self.total_input_tokens  / 1_000_000 * self.input_price)
            + (self.total_output_tokens / 1_000_000 * self.output_price)
        )

    def summary(self) -> str:
        """누적 사용량과 예상 비용을 포맷팅하여 반환한다."""
        if self.call_count == 0:
            return "AI 엔진 호출 없음 (비용 $0)"

        est_cost = self.total_cost_usd
        return (
            f"📈 AI 사용량 요약 ({GEMINI_PRICING_MODEL}):\n"
            f"   - API 호출: {self.call_count}회\n"
            f"   - 입력 토큰: {self.total_input_tokens:,} @ ${self.input_price}/M\n"
            f"   - 출력 토큰: {self.total_output_tokens:,} @ ${self.output_price}/M\n"
            f"   - 총 토큰: {self.total_tokens:,}\n"
            f"   - 예상 비용: ${est_cost:.4f} (약 {int(est_cost * 1_400)}원)"
        )


def parse_usage_metadata(response) -> tuple[int, int]:
    """
    Gemini API 응답 객체에서 토큰 사용량을 추출한다.

    Why: usage_metadata 필드가 없거나 None인 경우(무료 티어, 오류 응답 등)에도
         안전하게 (0, 0)을 반환하도록 방어 코드를 추가한다.

    Returns:
        (input_tokens, output_tokens)

    이식 원본: step1_extract_gemini_v33.py L196~203
    """
    input_tokens = 0
    output_tokens = 0
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        input_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
        output_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) or 0
    return input_tokens, output_tokens
