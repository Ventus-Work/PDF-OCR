"""
parsers/text_normalizer.py — 텍스트 정규화 및 한글 균등배분 병합

Why: Phase 12 Step 12-4 분해 결과물.
     text_cleaner.py의 텍스트 정규화 로직(clean_text, merge_spaced_korean)을
     분리한 순수 정규화 모듈.
     외부 의존성 없음 (re만 사용). K1 한글 균등배분 알고리즘 포함.

원본: parsers/text_cleaner.py L165~206 (clean_text)
              + L342~394 (merge_spaced_korean + _RE_SINGLE_HANGUL)
"""

import re


# ── K1: 한글 균등배분 병합 (kordoc 알고리즘 참조, MIT License) ──────────────
# 알고리즘 참조: kordoc (https://github.com/chrisryugj/kordoc)
# Copyright (c) chrisryugj, MIT License

# Why: \d 제외 — 숫자 1글자 토큰은 균등배분 판정 대상이 아님 (오탐 방지)
_RE_SINGLE_HANGUL = re.compile(r'^[가-힣]$')


def merge_spaced_korean(text: str) -> str:
    """
    한글 균등배분 텍스트를 병합한다.

    Why: 한국 공문서/견적서에서 "제 출 처", "품   명" 등
         글자 사이에 공백을 넣는 균등배분 배치가 빈번하다.
         PDF 추출 시 공백이 그대로 남아 데이터 품질을 저하시킨다.
         kordoc의 cluster-detector.ts 알고리즘을 참조하여
         한글 1글자 토큰 비율 70%+ 이면 공백을 제거한다.

    예시:
        "제 출 처"   → "제출처"
        "품   명"    → "품명"
        "SUS 304"    → "SUS 304"  (변환 안 함: 한글 토큰 0%)
        "배관 Support" → "배관 Support" (변환 안 함: 비율 미달)

    Args:
        text: 원본 텍스트

    Returns:
        균등배분이 병합된 텍스트

    원본: text_cleaner.py L350~394
    """
    if not text or len(text) < 3:
        return text

    lines = text.split('\n')
    result_lines = []

    for line in lines:
        tokens = line.split()
        if len(tokens) < 2:
            result_lines.append(line)
            continue

        # 한글 1글자 토큰 비율 계산
        single_hangul_count = sum(1 for t in tokens if _RE_SINGLE_HANGUL.match(t))
        ratio = single_hangul_count / len(tokens)

        if ratio >= 0.7:
            # 균등배분으로 판정 → 공백 제거
            result_lines.append(''.join(tokens))
        else:
            result_lines.append(line)

    return '\n'.join(result_lines)


def clean_text(
    text: str,
    patterns: dict = None,
) -> str:
    """
    텍스트를 정제한다. 범용 정제는 항상, 도메인 정제는 patterns 있을 때만.

    범용 (항상 수행):
        - HTML 주석 (<!-- ... -->) 제거
        - 연속 줄바꿈(3개 이상) → 2개로 정리
        - 한글 균등배분 병합 (merge_spaced_korean)

    도메인 (patterns["chapter_title"] 있을 때):
        - 장 제목 행 ("제6장 철근콘크리트공사" 등) 제거
          Why: 품셈 문서에서 장 제목은 구조 마커 역할이지 내용이 아님.
               일반 문서에서는 제목을 제거하면 안 되므로 조건부 적용.

    Args:
        text: 정제 대상 텍스트
        patterns: 도메인 패턴 딕셔너리.
                  필요 키: "chapter_title" (있으면 장 제목 행 제거)

    Returns:
        str: 정제된 텍스트

    원본: text_cleaner.py L165~206
    """
    # ── 범용: 항상 수행 ──
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    # K1 보조 호출: MD 파일 직접 입력 시 Phase 1을 거치지 않으므로
    # clean_text() 단계에서 한 번 더 균등배분 병합을 수행하여 커버.
    text = merge_spaced_korean(text)

    # ── 도메인: 장 제목 행 제거 (품셈 프리셋 시) ──
    if patterns and "chapter_title" in patterns:
        text = patterns["chapter_title"].sub('', text)

    # ── 범용: 항상 수행 ──
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()
