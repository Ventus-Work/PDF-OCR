"""API 키 마스킹 필터. (spec §3.3)"""

import logging
import re

_SECRET_PATTERNS = [
    (re.compile(r'(sk-[a-zA-Z0-9_\-]{20,})'), 'sk-***MASKED***'),
    (re.compile(r'(AIza[a-zA-Z0-9_\-]{35})'), 'AIza***MASKED***'),
    (re.compile(
        r'(["\']?(api_key|API_KEY|GEMINI_API_KEY|ZAI_API_KEY|MISTRAL_API_KEY)["\']?\s*[:=]\s*["\']?)([^"\'\s]{8,})'
    ), r'\1***MASKED***'),
]


def mask_secrets(text: str) -> str:
    if not text:
        return text
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class MaskingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = mask_secrets(record.msg)
        if record.args:
            record.args = tuple(
                mask_secrets(str(a)) if isinstance(a, str) else a
                for a in record.args
            )
        return True


def install_masking_filter(logger: logging.Logger = None):
    target = logger or logging.getLogger()
    if not any(isinstance(f, MaskingFilter) for f in target.filters):
        target.addFilter(MaskingFilter())
