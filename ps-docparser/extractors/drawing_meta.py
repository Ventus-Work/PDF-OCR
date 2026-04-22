"""
extractors/drawing_meta.py — BOM 도면 타이틀 블록 메타데이터 추출기

Why: BOM 파이프라인의 OCR raw_text에는 도면 번호·제목 등의 타이틀 블록 정보가
     포함되어 있으나, 기존 bom_extractor/bom_state_machine은 BOM 표에만 집중해
     이 정보를 무시했다. Phase 14에서 해당 정보를 JSON + Excel로 내보내기 위해
     전용 추출 모듈을 분리한다.

처리 흐름:
    raw_text → HTML 정규화 → 줄 분리 → 줄 단위 line scan (first-match-wins) → dict 반환

제약:
    - OCR 결과물이므로 오타 허용 → 정규식 패턴을 느슨하게 작성
    - v1: 영문 키워드 기반. 한글 혼합은 Phase 14 이후 확장
    - 외부 의존성 없음 (표준 라이브러리 re만 사용)
"""

from __future__ import annotations

import html
import re
from typing import TypeAlias

DrawingMeta: TypeAlias = dict[str, str | None]

# ──────────────────────────────────────────────────────────
# 출력 필드 정의 (순서 고정 — Excel 시트 행 순서와 일치)
# ──────────────────────────────────────────────────────────
_FIELD_KEYS: tuple[str, ...] = (
    "dwg_no",
    "rev",
    "title",
    "date",
    "project",
    "client",
    "drawn_by",
    "checked_by",
    "approved_by",
    "scale",
    "sheet",
)

# ──────────────────────────────────────────────────────────
# 필드별 정규식 카탈로그
# 포맷: (field_key, compiled_pattern)
# 우선순위: 리스트 순서 = 매칭 우선순위 (앞에 있는 것이 먼저 시도됨)
# ──────────────────────────────────────────────────────────
_FIELD_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        # Why: 구분자([:.] 또는 공백) 뒤에 반드시 비공백 문자가 있어야 매칭.
        #      "DWG NO." 처럼 값 없는 줄이 잘못 캡처되는 것을 방지.
        "dwg_no",
        re.compile(
            r"^(?:DWG\s*NO\.?|DRAWING\s*NO\.?)\s*(?:[:.]\s*|\s+)(?P<value>\S.*?)\s*$",
            re.IGNORECASE,
        ),
    ),
    (
        "rev",
        re.compile(
            r"^(?:REV(?:ISION)?)\.?\s*(?:[:.]\s*|\s+)(?P<value>\S.*?)\s*$",
            re.IGNORECASE,
        ),
    ),
    (
        "title",
        re.compile(
            r"^TITLE\.?\s*(?:[:.]\s*|\s+)(?P<value>\S.*?)\s*$",
            re.IGNORECASE,
        ),
    ),
    (
        "date",
        re.compile(
            r"^(?:DATE|ISSUED)\s*(?:[:.]\s*|\s+)(?P<value>\S.*?)\s*$",
            re.IGNORECASE,
        ),
    ),
    (
        "project",
        re.compile(
            r"^(?:PROJECT|JOB\s*NO\.?)\s*(?:[:.]\s*|\s+)(?P<value>\S.*?)\s*$",
            re.IGNORECASE,
        ),
    ),
    (
        "client",
        re.compile(
            r"^(?:CLIENT|OWNER|CONTRACTOR)\s*(?:[:.]\s*|\s+)(?P<value>\S.*?)\s*$",
            re.IGNORECASE,
        ),
    ),
    (
        "drawn_by",
        re.compile(
            r"^(?:DRAWN\s*BY|DRAWN|DRW'?D)\s*(?:[:.]\s*|\s+)(?P<value>\S.*?)\s*$",
            re.IGNORECASE,
        ),
    ),
    (
        "checked_by",
        re.compile(
            r"^(?:CHECKED\s*BY|CHECKED|CHK'?D)\s*(?:[:.]\s*|\s+)(?P<value>\S.*?)\s*$",
            re.IGNORECASE,
        ),
    ),
    (
        "approved_by",
        re.compile(
            r"^(?:APPROVED\s*BY|APPROVED|APP'?D)\s*(?:[:.]\s*|\s+)(?P<value>\S.*?)\s*$",
            re.IGNORECASE,
        ),
    ),
    (
        "scale",
        re.compile(
            r"^SCALE\s*(?:[:.]\s*|\s+)(?P<value>\S.*?)\s*$",
            re.IGNORECASE,
        ),
    ),
    (
        "sheet",
        re.compile(
            r"^SHEET\s*(?:[:.]\s*|\s+)(?P<value>\S.*?)\s*$",
            re.IGNORECASE,
        ),
    ),
]

# 파이프 구분 인라인 매칭용 — "DWG NO. KO-001 | REV. 0 | TITLE: PIPE DETAIL" 형태
_PIPE_SEGMENT_PATTERN = re.compile(r"[|]")

# 마크다운 구분선 — 이 줄은 건너뜀
_MD_SEPARATOR_RE = re.compile(r"^[-|:]{3,}\s*$")

# 빈 테이블 행 — "|  |  |" 형태로 내용이 없는 줄 건너뜀
_EMPTY_TABLE_ROW_RE = re.compile(r"^[|\s]+$")


# ──────────────────────────────────────────────────────────
# 내부 헬퍼
# ──────────────────────────────────────────────────────────

def _normalize_html(text: str) -> str:
    """
    OCR 결과에 섞인 HTML 아티팩트 제거.
    Why: ZAI/Mistral OCR은 <br>, &nbsp; 등을 그대로 토해내는 경우가 있음.
    """
    # <br>, <br/>, <br /> → 줄바꿈
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    # 나머지 HTML 태그 제거
    text = re.sub(r"<[^>]+>", "", text)
    # HTML 엔티티 디코드 (&nbsp; → 공백 등)
    text = html.unescape(text)
    return text


def _normalize_value(value: str) -> str | None:
    """
    추출한 값의 후처리.
    - 앞뒤 공백 제거
    - 연속 공백 1칸으로
    - 빈 문자열 → None
    """
    value = value.strip()
    value = re.sub(r"\s{2,}", " ", value)
    return value if value else None


def _match_segments(segments: list[str], result: DrawingMeta) -> None:
    """
    세그먼트 리스트(파이프 분리 또는 단일 줄)에서 각 필드 패턴 매칭.
    first-match-wins: 이미 채워진 필드는 덮어쓰지 않음.
    """
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        for field_key, pattern in _FIELD_PATTERNS:
            if result.get(field_key) is not None:
                # 이미 값이 있으면 skip
                continue
            m = pattern.match(seg)
            if m:
                result[field_key] = _normalize_value(m.group("value"))
                break  # 한 세그먼트는 하나의 필드에만 매칭


# ──────────────────────────────────────────────────────────
# 공개 API
# ──────────────────────────────────────────────────────────

def extract_drawing_meta(raw_text: str) -> DrawingMeta:
    """
    OCR 결과(raw_text)에서 도면 타이틀 블록 메타데이터를 추출한다.

    처리 전략:
        1. HTML 정규화 (<br> → \n, 엔티티 디코드)
        2. 줄 단위 split 후 각 줄을 처리
        3. 파이프(|)가 있는 줄은 segment로 분리해 다중 필드 인라인 매칭
        4. 마크다운 구분선(---) 및 빈 테이블 행은 건너뜀
        5. first-match-wins: 먼저 채워진 필드는 덮어쓰지 않음

    Args:
        raw_text: OCR 엔진이 반환한 원본 텍스트 (마크다운 포함 가능)

    Returns:
        DrawingMeta: 11개 키를 가진 dict. 미추출 필드는 None.
        {
            "dwg_no": str | None,
            "rev": str | None,
            "title": str | None,
            "date": str | None,
            "project": str | None,
            "client": str | None,
            "drawn_by": str | None,
            "checked_by": str | None,
            "approved_by": str | None,
            "scale": str | None,
            "sheet": str | None,
        }
    """
    # 결과 dict 초기화 (모든 필드 None)
    result: DrawingMeta = {k: None for k in _FIELD_KEYS}

    if not raw_text or not raw_text.strip():
        return result

    text = _normalize_html(raw_text)

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # 마크다운 구분선 / 빈 테이블 행 건너뜀
        if _MD_SEPARATOR_RE.match(line) or _EMPTY_TABLE_ROW_RE.match(line):
            continue

        if _PIPE_SEGMENT_PATTERN.search(line):
            # 파이프 구분 줄: 각 segment를 개별 시도
            segments = _PIPE_SEGMENT_PATTERN.split(line)
            _match_segments(segments, result)
        else:
            _match_segments([line], result)

        # 모든 필드가 채워지면 조기 종료 (성능 최적화)
        if all(v is not None for v in result.values()):
            break

    return result
