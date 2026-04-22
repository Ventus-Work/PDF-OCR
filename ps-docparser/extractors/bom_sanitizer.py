"""
extractors/bom_sanitizer.py — OCR HTML 잔여물 전처리 유틸리티

Why: Phase 12 Step 12-3 분해 결과물.
     bom_extractor.py의 HTML→파이프 변환 로직을 분리한 순수 전처리 모듈.
     상태머신(bom_state_machine.py)이 파이프 텍스트를 기대하므로
     이 모듈이 HTML 구조를 파이프로 변환하는 전처리를 단독 담당한다.
     외부 의존성 없음 (re만 사용).

원본: extractors/bom_extractor.py L29~72 (정규식 캐시 6개 + _sanitize_html)
"""

import re

# ── Phase 8: 정규식 모듈 레벨 1회 컴파일 캐싱 ──────────────────────────────
# Why: _sanitize_html()은 100페이지 배치에서 수백 회 호출된다.
#      re.sub(r'...') 형태는 매 호출마다 정규식을 재컴파일한다.
#      모듈 로드 시 1회 컴파일 → 이후 N회 호출은 캐시 히트 → CPU 절약.
_RE_TR_CLOSE     = re.compile(r'</tr[^>]*>',          re.IGNORECASE)
_RE_TD_SPLIT     = re.compile(r'</t[dh]>\s*<t[dh][^>]*>', re.IGNORECASE)
_RE_TAG          = re.compile(r'<[^>]+>')
_RE_ENTITY_NAMED = re.compile(r'&[a-zA-Z]+;')
_RE_ENTITY_HEX   = re.compile(r'&#x[0-9a-fA-F]+;')
_RE_WHITESPACE   = re.compile(r'[ \t]+')


def _sanitize_html(text: str) -> str:
    """
    OCR 응답의 HTML 잔여물을 상태머신 입력용 텍스트로 정리한다.

    Why: Z.ai/Mistral OCR 응답에 <table>, <tr>, <td> 태그가
         남아 있을 수 있다. 상태머신은 파이프(|) 구분 텍스트를
         기대하므로 HTML 구조를 파이프로 변환한다.

    원본 참조: ocr.py L1416~1436 (HTML 전처리 5단계)
    Phase 8: 모듈 레벨 _RE_* 상수 사용으로 재컴파일 제거.
    원본: bom_extractor.py L41~72
    """
    if not text:
        return text

    # Step 1: </tr> → 줄바꿈 (행 구분)
    text = _RE_TR_CLOSE.sub('\n', text)

    # Step 2: </td><td> 또는 </th><th> → 파이프 (열 구분)
    text = _RE_TD_SPLIT.sub(' | ', text)

    # Step 3: 나머지 HTML 태그 제거
    text = _RE_TAG.sub(' ', text)

    # Step 4: HTML 엔티티 치환 (명시적 치환 우선, 나머지는 정규식)
    text = text.replace('&amp;', '&').replace('&#x27;', "'")
    text = _RE_ENTITY_NAMED.sub('', text)
    text = _RE_ENTITY_HEX.sub('', text)

    # Step 5: 연속 공백 압축
    text = _RE_WHITESPACE.sub(' ', text)

    return text
