"""
utils/page_spec.py — 페이지 범위 지정 문자열 파서

Why: CLI에서 "1-15", "20-", "1,3,5-10" 같은 다양한 페이지 지정 형식을
     0-indexed 정수 리스트로 변환한다.
     PDF 처리 로직과 파싱 로직을 분리하여 단독 테스트가 가능하다.

이식 원본: step1_extract_gemini_v33.py L137~178
"""


def parse_page_spec(spec: str, total_pages: int) -> list[int]:
    """
    페이지 지정 문자열을 파싱하여 0-indexed 페이지 인덱스 리스트를 반환한다.

    Args:
        spec: 페이지 지정 문자열
        total_pages: PDF 전체 페이지 수 (범위 검증용)

    Returns:
        0-indexed 정수 리스트 (정렬됨)

    지원 형식:
        "10"        → 1~10페이지  (단일 숫자는 1부터 해당 페이지까지)
        "5-15"      → 5~15페이지
        "20-"       → 20~끝
        "-10"       → 1~10페이지
        "1,3,5-10"  → 1, 3, 5~10페이지 (쉼표 포함 시 단일 숫자는 해당 페이지만)

    이식 원본: step1_extract_gemini_v33.py L137~178
    """
    spec = spec.strip()
    if not spec:
        raise ValueError("Empty page specification")
        
    indices: set[int] = set()

    parts = [p.strip() for p in spec.split(",") if p.strip()]
    has_comma = "," in spec

    for part in parts:
        if "-" in part:
            if part.startswith("-"):
                # "-10" → 1~10
                end = int(part[1:])
                start = 1
            elif part.endswith("-"):
                # "20-" → 20~끝
                start = int(part[:-1])
                end = total_pages
            else:
                # "5-15" → 5~15
                start_str, end_str = part.split("-", 1)
                start = int(start_str)
                end = int(end_str)
                if start > end:
                    raise ValueError(f"Reverse range not supported: {part}")

            for p in range(start, end + 1):
                if 1 <= p <= total_pages:
                    indices.add(p - 1)
        else:
            p = int(part)
            if not has_comma and len(parts) == 1:
                # Why: 단일 숫자이고 쉼표가 없으면 "처음 N페이지" 의미로 해석
                #      (기존 동작 호환: "--pages 15" → 1~15페이지)
                for i in range(min(p, total_pages)):
                    indices.add(i)
            else:
                # 쉼표로 구분된 경우 해당 페이지 1개만
                if 1 <= p <= total_pages:
                    indices.add(p - 1)

    return sorted(indices)
