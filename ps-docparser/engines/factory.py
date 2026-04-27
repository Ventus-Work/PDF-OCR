"""엔진 팩토리. (main.py _create_engine 추출)"""

import config
from utils.io import ParserError

_GEMINI_KEY_ROTATOR = None
_GEMINI_ROTATOR_SIGNATURE = None


def _get_gemini_key_rotator():
    """Return a process-wide Gemini key rotator."""

    global _GEMINI_KEY_ROTATOR, _GEMINI_ROTATOR_SIGNATURE
    if not config.GEMINI_API_KEYS:
        raise ParserError(".env에 GEMINI_API_KEY 또는 GEMINI_API_KEYS가 설정되지 않았습니다.")

    signature = (tuple(config.GEMINI_API_KEYS), config.GEMINI_KEY_MAX_CALLS)
    if _GEMINI_KEY_ROTATOR is None or _GEMINI_ROTATOR_SIGNATURE != signature:
        from utils.gemini_key_rotator import GeminiKeyRotator

        _GEMINI_KEY_ROTATOR = GeminiKeyRotator(
            config.GEMINI_API_KEYS,
            max_calls_per_key=config.GEMINI_KEY_MAX_CALLS,
        )
        _GEMINI_ROTATOR_SIGNATURE = signature
    return _GEMINI_KEY_ROTATOR


def create_engine(engine_name: str, tracker=None):
    """엔진명으로 엔진 인스턴스를 생성한다."""
    if tracker and hasattr(tracker, "set_context"):
        model = {
            "gemini": config.GEMINI_MODEL,
            "zai": "glm-ocr",
            "mistral": "mistral-ocr-latest",
            "local": "local",
            "tesseract": "tesseract",
        }.get(engine_name, engine_name)
        tracker.set_context(provider=engine_name, model=model)
    if engine_name == "gemini":
        from engines.gemini_engine import GeminiEngine
        return GeminiEngine(
            api_key=config.GEMINI_API_KEY,
            model=config.GEMINI_MODEL,
            tracker=tracker,
            key_rotator=_get_gemini_key_rotator(),
        )
    elif engine_name == "local":
        from engines.local_engine import LocalEngine
        return LocalEngine()
    elif engine_name == "zai":
        from engines.zai_engine import ZaiEngine
        if not config.ZAI_API_KEY:
            raise ParserError(".env에 ZAI_API_KEY가 설정되지 않았습니다.")
        return ZaiEngine(config.ZAI_API_KEY, tracker=tracker)
    elif engine_name == "mistral":
        from engines.mistral_engine import MistralEngine
        if not config.MISTRAL_API_KEY:
            raise ParserError(".env에 MISTRAL_API_KEY가 설정되지 않았습니다.")
        return MistralEngine(config.MISTRAL_API_KEY, tracker=tracker)
    elif engine_name == "tesseract":
        from engines.tesseract_engine import TesseractEngine
        return TesseractEngine(tesseract_path=config.TESSERACT_PATH)
    else:
        raise ParserError(f"알 수 없는 엔진: {engine_name}")
