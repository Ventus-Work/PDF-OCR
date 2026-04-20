"""엔진 팩토리. (main.py _create_engine 추출)"""

import config
from utils.io import ParserError


def create_engine(engine_name: str, tracker=None):
    """엔진명으로 엔진 인스턴스를 생성한다."""
    if engine_name == "gemini":
        from engines.gemini_engine import GeminiEngine
        return GeminiEngine(config.GEMINI_API_KEY, config.GEMINI_MODEL, tracker)
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
