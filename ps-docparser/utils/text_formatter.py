"""
utils/text_formatter.py — PDF 텍스트 줄바꿈 병합 및 정리 모듈

Why: PDF에서 추출된 텍스트는 페이지 폭에서 강제로 끊긴 줄바꿈이 포함된다.
     이를 자연스러운 문단으로 복원하되, 항목 번호/문장 종결은 줄바꿈을 유지해야 한다.
     범용 모드와 품셈 프리셋 모드를 division_names 파라미터로 분기한다.

이식 원본: step1_extract_gemini_v33.py L370~469
Phase 8: 정규식 모듈 레벨 캐싱 + lru_cache 품셈 패턴 캐싱
"""
import re
from functools import lru_cache


# ── Phase 8: 정규식 모듈 레벨 1회 컴파일 캐싱 ──────────────────────────────
# Why: format_text_with_linebreaks()는 100페이지 배치에서 1,300회+
#      정규식을 재컴파일했다. 모듈 레벨 상수화로 1회만 컴파일.

# 섹션 선처리 패턴
_RE_SECTION_NUM  = re.compile(r'(?<=[^\n])(\d+-\d+-\d+\s+)')
_RE_NUMBERED     = re.compile(r'(?<=[다\.\)\]]) (\d+\.\s+)')
_RE_KOREAN_ALPHA = re.compile(r'(?<=[다\.\)\]]) ([가나다라마바사아자차카타파하]\.\s+)')
_RE_NOTE         = re.compile(r'(?<=[^\n])(\[주\])')
_RE_CIRCLED      = re.compile(r'(?<=[다\.\)\]]) ([①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳])')

# 한글 줄바꿈 병합
_RE_KO_LINEBREAK     = re.compile(r'([가-힣])\n([가-힣]{0,2}다[\.\\, ])')
_RE_KO_LINEBREAK_END = re.compile(r'([가-힣])\n(다)$', re.MULTILINE)

# 문단 정리
_RE_TRIPLE_NEWLINE = re.compile(r'\n{3,}')
_RE_DOUBLE_SPACE   = re.compile(r' {2,}')

# 리스트 항목 시작 패턴 (기본 — 품셈 분기 없는 경우)
_RE_LIST_BASE = re.compile(
    r'^(\d+[-.]|[가-하]\.|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]|\[주\]|\d+-\d+-\d+)'
)


@lru_cache(maxsize=8)
def _get_pumsem_patterns(division_names: str):
    """
    division_names별 품셈 전용 정규식 쌍을 캐싱 반환.

    Why: division_names는 호출마다 동일한 문자열이 반복 전달된다.
         lru_cache로 최초 1회만 컴파일 → 이후 캐시 히트.
         maxsize=8: 품셈 프리셋 종류가 보통 1~3개이므로 충분.
    """
    pattern_split = re.compile(
        rf'(?<![-\d])(\d+\s*(?:{division_names}|적용기준|제\d+장))'
    )
    pattern_list = re.compile(
        rf'^(\d+[-.]|[가-하]\.|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]'
        rf'|\[주\]|\d+-\d+-\d+|\d+\s*(?:{division_names}|적용기준|제\d+장))'
    )
    return pattern_split, pattern_list


def _is_sentence_ending(line: str) -> bool:
    """
    한국어 문장 종결 패턴을 감지한다.

    Why: 종결 패턴이 확인되면 다음 줄을 이어붙이지 않아야 자연스러운 문단이 된다.
         패턴이 없으면 PDF 줄바꿈 아티팩트로 판단하여 병합한다.

    Returns:
        True → 종결 감지됨 (이어붙이기 금지)
        False → 종결 아님 (이어붙이기 가능)

    이식 원본: step1_extract_gemini_v33.py L370~404
    """
    line = line.rstrip()
    if not line:
        return False

    ending_patterns = [
        r"다\.$",            # ~다.
        r"다\)$",            # ~다)
        r'다"$',             # ~다"
        r"[요임음함됨]\.$",  # ~요. ~임. ~음. ~함. ~됨.
        r"것$",              # ~것
        r"[\.]$",            # . 으로 끝남
        r"\)$",              # ) 로 끝남
        r"\]$",              # ] 로 끝남
        r":$",               # : 로 끝남
    ]

    for pattern in ending_patterns:
        if re.search(pattern, line):
            return True
    return False


def format_text_with_linebreaks(text: str, division_names: str = None) -> str:
    """
    PDF 추출 텍스트의 줄바꿈 병합 및 정리.

    Args:
        text: pdfplumber로 추출한 원본 텍스트
        division_names: 품셈 프리셋 전용 부문명 OR 패턴 문자열
                        예) "공통부문|토목부문|건축부문|..."
                        None이면 범용 모드 — 품셈 전용 정규식 완전 비활성화

    Returns:
        정리된 텍스트 (마크다운 호환)

    이식 원본: step1_extract_gemini_v33.py L407~469
    변경점:
        - division_names 파라미터 추가 (원본에서는 전역 DIVISION_NAMES 상수 사용)
        - L426의 re.sub AND L443의 re.match 양쪽 모두 division_names 조건부 분기
          (1차 해결안에서 L443 누락 확인 → 2차에서 수정)
        - Phase 8: 모듈 레벨 _RE_* 상수 사용 + lru_cache 품셈 패턴 캐싱
    """
    if not text:
        return ""

    # ── 0단계: 섹션 제목 패턴 앞에 줄바꿈 삽입 (병합 전 선처리) ──
    text = _RE_SECTION_NUM.sub(r'\n\n\1', text)
    text = _RE_NUMBERED.sub(r'\n\1', text)
    text = _RE_KOREAN_ALPHA.sub(r'\n\1', text)
    text = _RE_NOTE.sub(r'\n\n\1', text)
    text = _RE_CIRCLED.sub(r'\n\1', text)

    # ── 품셈 전용 패턴 (프리셋 활성화 시에만) ──
    if division_names:
        pattern_split, _ = _get_pumsem_patterns(division_names)
        text = pattern_split.sub(r'\n\1', text)

    # ── 1단계: PDF 줄바꿈으로 끊긴 문장 병합 ──
    text = _RE_KO_LINEBREAK.sub(r'\1\2', text)
    text = _RE_KO_LINEBREAK_END.sub(r'\1\2', text)

    # ── 2단계: 단일 줄바꿈 → 공백 변환 (문장 종결/줄 길이 기반 분기) ──
    lines = text.split("\n")
    result = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            result.append("")
            continue

        if division_names:
            _, pattern_list = _get_pumsem_patterns(division_names)
            is_list_item = bool(pattern_list.match(stripped))
        else:
            is_list_item = bool(_RE_LIST_BASE.match(stripped))

        if is_list_item:
            result.append(stripped)
        elif result and result[-1]:
            prev_line = result[-1]
            if _is_sentence_ending(prev_line):
                result.append(stripped)
            elif len(prev_line) >= 80:
                result.append(stripped)
            else:
                result[-1] = prev_line + " " + stripped
        else:
            result.append(stripped)

    text = "\n".join(result)

    # ── 3단계: 연속 줄바꿈 정리 (3개 이상 → 2개) ──
    text = _RE_TRIPLE_NEWLINE.sub('\n\n', text)

    # ── 4단계: 연속 공백 정리 ──
    text = _RE_DOUBLE_SPACE.sub(' ', text)

    return text.strip()

