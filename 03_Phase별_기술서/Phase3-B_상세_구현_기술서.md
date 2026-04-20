# Phase 3-B 상세 구현 기술서 — Exporter 아키텍처 완성 + 견적서 프리셋 + 한글 처리

> 작성일: 2026-04-14
> 선행: Phase 3-A (excel_exporter.py 수정 A~H 완료, 653줄)
> 참조: `Phase3_상세_구현_기술서.md` §2,§4,§5,§6,§7 / kordoc (MIT) K1,K4 알고리즘

---

## 목적

Phase 3-A에서 `excel_exporter.py`의 핵심 기능과 8건의 버그 수정(A~H)을 완료했다. Phase 3-B에서는:

1. **Exporter 아키텍처 정립** — `BaseExporter` ABC 도입, 기존 함수 기반 `export()`를 클래스 기반으로 전환
2. **JSON Exporter 분리** — `main.py`에 인라인된 `json.dump()` 로직을 독립 모듈로 추출
3. **견적서 프리셋** — `estimate` 프리셋 추가 (표지 메타 추출, 시트 구성, 테이블 분류)
4. **문서 유형 감지** — `detector.py`로 프리셋 미지정 시 자동 제안
5. **한글 처리 개선** — kordoc 알고리즘 차용 (K1: 균등배분 병합, K4: Bold-fake 제거)

완료 시점에 `python main.py "견적서.pdf" --output excel --preset estimate` 한 줄로 견적서 Excel이 생성되어야 한다.

---

## Phase 3-A 현재 코드 분석 (Phase 3-B 입력)

### 현재 excel_exporter.py 공개 API

```python
# exporters/excel_exporter.py (653줄) — 함수 기반
def export(sections: list[dict], output_path, *, title=None) -> Path
```

**문제:** `BaseExporter` ABC가 없으므로 함수 기반이다. Phase3 기술서의 클래스 설계와 불일치.

### 현재 main.py JSON 저장 (인라인)

```python
# main.py L392-394 — json.dump 직접 호출
with open(json_path, "w", encoding="utf-8-sig") as f:
    json.dump(sections, f, ensure_ascii=False, indent=2)
```

**문제:** Exporter 인터페이스 없이 main.py에 직접 작성되어 있다.

### 현재 main.py Excel 호출

```python
# main.py L404 — 함수 직접 import
from exporters.excel_exporter import export as excel_export
excel_export(sections, xlsx_path)
```

**문제:** 클래스가 아닌 함수를 직접 호출. `metadata`, `preset_config` 파라미터 없음.

---

## Phase 3-B 신규/변경 파일 목록

```
ps-docparser/
├── main.py                          [변경] .json 입력 + detector + estimate + Exporter 클래스 연결
├── detector.py                      [신규] 문서 유형 자동 감지
│
├── exporters/
│   ├── __init__.py                  [변경] JsonExporter 등록
│   ├── base_exporter.py             [신규] ABC 인터페이스
│   ├── excel_exporter.py            [변경] BaseExporter 상속 래퍼 추가 (기존 export() 보존)
│   └── json_exporter.py             [신규] JSON 저장 분리
│
├── presets/
│   └── estimate.py                  [신규] 견적서 프리셋
│
├── templates/
│   └── 견적서_양식.xlsx              [신규] 갑지 표지 양식 (수동 생성)
│
├── extractors/
│   ├── hybrid_extractor.py          [변경] K1 호출 삽입 (Phase 1 PDF 추출 직후, format 전)
│   └── text_extractor.py            [변경] K1 호출 삽입 + K4 deduplicate_bold_fake() 함수 정의
│
├── parsers/
│   └── text_cleaner.py              [변경] K1 merge_spaced_korean() 함수 정의 + clean_text() 보조 호출
│
└── utils/
    └── (text_formatter.py 변경 없음 — K4는 extractors/text_extractor.py로 이동)
```

---

## 파일별 상세 스펙

### 1. `exporters/base_exporter.py` — 내보내기 ABC (신규)

> 원본 설계: Phase3_상세_구현_기술서.md §2 (L114~160)
> 변경점: 없음 (원본 설계 그대로 구현)

```python
"""
내보내기 공통 인터페이스 (Abstract Base Class).

Why: engines/base_engine.py와 동일한 Strategy Pattern.
     새 출력 형식 추가 시 이 클래스를 상속하면 main.py가 자동 인식.
"""
from abc import ABC, abstractmethod
from pathlib import Path


class BaseExporter(ABC):
    """출력 파일 생성기의 공통 인터페이스."""

    @abstractmethod
    def export(
        self,
        sections: list[dict],
        output_path: Path,
        *,
        metadata: dict | None = None,
        preset_config: dict | None = None,
    ) -> Path:
        """
        JSON 섹션 리스트를 출력 파일로 변환한다.

        Args:
            sections: Phase 2 출력 JSON 배열
            output_path: 출력 파일 경로
            metadata: 문서 메타데이터 (표지 정보 등)
            preset_config: 프리셋별 출력 설정 (시트 구성, 열 매핑 등)

        Returns:
            실제로 저장된 파일 경로
        """
        ...

    @property
    @abstractmethod
    def file_extension(self) -> str:
        """이 Exporter가 생성하는 파일 확장자 (예: '.xlsx')."""
        ...
```

**예상 규모:** ~30줄

---

### 2. `exporters/excel_exporter.py` — BaseExporter 래퍼 추가 (변경)

> 원본 설계: Phase3_상세_구현_기술서.md §3 (L164~628)
> 변경점: **기존 653줄 코드를 보존**하면서 클래스 래퍼만 추가

**전략:** 기존 `export()` 함수(수정 A~H 적용 완료, 실전 검증됨)를 파괴하지 않는다. `ExcelExporter` 클래스를 추가하고, 내부에서 `_export_impl()` 을 호출하는 위임(delegation) 패턴을 사용한다.

**⚠️ 리뷰 반영 (오류 3):** `export_func = export` 별칭 대신 `_export_impl` 내부 rename 방식으로 변경. 기존 함수명 `export`와 클래스 메서드명 `export`의 혼동을 원천 차단하고, 기존 `from exporters.excel_exporter import export` 임포트 호환성도 유지.

```python
# ── 변경 1: 기존 export() 함수를 _export_impl()로 rename ──
# 파일 L548: def export(...) → def _export_impl(...)

def _export_impl(                          # ← 기존 export에서 rename
    sections: list[dict[str, Any]],
    output_path: str | Path,
    *,
    title: str | None = None,
) -> Path:
    """(기존 export() 함수 본문 그대로)"""
    ...  # 기존 L565~652 코드 변경 없음

# ── 변경 2: 하위 호환용 공개 API 별칭 ──
# Why: 기존 _test_phase3.py L17, main.py L404에서
#      from exporters.excel_exporter import export as excel_export 사용 중.
#      이 별칭이 있으면 기존 코드 무수정으로 동작.
export = _export_impl


# ── 변경 3: 파일 최하단에 추가 ──

from exporters.base_exporter import BaseExporter


class ExcelExporter(BaseExporter):
    """JSON 섹션 리스트를 Excel 워크북으로 변환한다."""

    file_extension = ".xlsx"

    def export(
        self,
        sections: list[dict],
        output_path: Path,
        *,
        metadata: dict | None = None,
        preset_config: dict | None = None,
    ) -> Path:
        """
        BaseExporter 인터페이스 구현.

        현재는 내부 _export_impl()에 위임한다.
        preset_config가 있으면 향후 _write_preset_sheets()로 분기.

        Why: _export_impl()은 수정 A~H로 실전 검증되었다.
             전면 리팩터 대신 위임 패턴으로 안전하게 클래스 인터페이스를 제공.
             Phase 4 이후 점진적으로 로직을 클래스 내부로 이전한다.
        """
        # preset_config 지원: 향후 estimate 프리셋 연동 시 분기 예정
        title = metadata.get("description") if metadata else None
        return _export_impl(sections, output_path, title=title)
```

**핵심 결정:**
- 기존 `export()` 함수 → `_export_impl()`로 rename (내부 구현)
- `export = _export_impl` 별칭으로 기존 import 하위 호환 유지
- `ExcelExporter.export()` → `_export_impl()` 직접 호출 (별칭 없는 명시적 위임)
- `main.py`에서 신규 호출: `ExcelExporter().export(...)`, 기존 호출: `export(...)` 둘 다 동작

**예상 추가 규모:** ~35줄 (기존 653줄 + 35줄 = ~688줄)

---

### 3. `exporters/json_exporter.py` — JSON 저장 분리 (신규)

> 원본 설계: Phase3_상세_구현_기술서.md §4 (L629~683)
> 변경점: 없음 (원본 설계 그대로 구현)

```python
"""
JSON 파일 저장 Exporter.

Why: 현재 main.py L392-394에 인라인된 json.dump() 호출을
     BaseExporter 인터페이스에 맞춰 분리한다.
"""
import json
from pathlib import Path
from exporters.base_exporter import BaseExporter


class JsonExporter(BaseExporter):
    """JSON 섹션 리스트를 파일로 저장한다."""

    file_extension = ".json"

    def export(
        self,
        sections: list[dict],
        output_path: Path,
        *,
        metadata: dict | None = None,
        preset_config: dict | None = None,
    ) -> Path:
        """
        JSON 파일로 저장한다.

        metadata가 있으면 최상위에 문서 메타데이터를 병합:
            {"metadata": {...}, "sections": [...]}
        metadata가 없으면 기존 동작 유지 (섹션 배열만 저장):
            [...]
        """
        if metadata:
            output_data = {"metadata": metadata, "sections": sections}
        else:
            output_data = sections

        with open(output_path, "w", encoding="utf-8-sig") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        return output_path
```

**예상 규모:** ~40줄

---

### 4. `presets/estimate.py` — 견적서 프리셋 (신규)

> 원본 설계: Phase3_상세_구현_기술서.md §5 (L687~886)
> 변경점: 없음 (원본 설계 그대로 구현)

**구조:** `pumsem.py`와 동일한 인터페이스 패턴

```python
"""
presets/estimate.py — 견적서(estimate) 전용 프리셋 설정

Why: 견적서 PDF는 품셈 문서와 다른 도메인 규칙:
     - 갑지(표지) + 내역서 2시트 구조가 표준
     - 표지에서 메타데이터(제출처, 금액, 공사명 등) 추출 필요
     - 합계/소계 행 시각적 강조
"""
import re
from pathlib import Path

# ⚠️ 리뷰 반영 (오류 4): 상대 경로 → 절대 경로
# config.py와 동일한 Path(__file__).resolve() 기반 경로 관리
_PRESET_DIR = Path(__file__).resolve().parent          # presets/
_TEMPLATE_PATH = _PRESET_DIR.parent / "templates" / "견적서_양식.xlsx"
```

**§4-1. TABLE_TYPE_KEYWORDS**

```python
TABLE_TYPE_KEYWORDS = {
    "E_견적요약": ["직접비", "간접비", "합계", "소계", "총 합 계"],
    "E_견적내역": ["재료비", "노무비", "경비", "합계", "단가", "금액"],
    "E_견적조건": ["일반사항", "특기사항", "납품", "결제조건"],
}
```

**§4-2. COVER_PATTERNS** — 표지 메타데이터 추출 정규식

```python
COVER_PATTERNS = {
    "client": re.compile(r'제\s*출\s*처\s*[:：]\s*(.+?)(?:\s*貴中|\s*$)', re.MULTILINE),
    "amount_text": re.compile(r'견적금액\s*[:：]\s*(.+?)(?:\s*원정|\s*$)', re.MULTILINE),
    "project": re.compile(r'현\s*장\s*명\s*[:：]\s*(.+?)$', re.MULTILINE),
    # ⚠️ 리뷰 반영 (🟡): "경남"/"대표" 특정 종결자 제거 → $ (줄끝) 범용 종결
    "description": re.compile(r'공\s*사\s*명\s*[:：]\s*(.+?)$', re.MULTILINE),
    "item": re.compile(r'물\s*품\s*명\s*[:：]\s*(.+?)$', re.MULTILINE),
    "serial_no": re.compile(r'견적일련번호\s*[:：]\s*(\S+)', re.MULTILINE),
}
```

**§4-3. extract_cover_metadata()**

```python
def extract_cover_metadata(clean_text: str) -> dict:
    """
    견적서 표지 텍스트에서 메타데이터를 추출한다.

    Args:
        clean_text: Phase 2 출력의 section["clean_text"]

    Returns:
        dict: client, amount_text, amount(int), project, description, item, serial_no
    """
    result = {}
    failed_keys = []
    for key, pattern in COVER_PATTERNS.items():
        match = pattern.search(clean_text)
        if match:
            result[key] = match.group(1).strip()
        else:
            result[key] = ""
            failed_keys.append(key)

    if failed_keys:
        print(f"   ⚠️ 표지 메타 추출 실패 필드: {', '.join(failed_keys)}")

    # 금액 숫자 파싱
    amount_str = result.get("amount_text", "")
    amount_digits = re.sub(r'[^\d]', '', amount_str)
    result["amount"] = int(amount_digits) if amount_digits else None

    return result
```

**§4-4. EXCEL_SHEET_CONFIG**

```python
EXCEL_SHEET_CONFIG = {
    "template_path": _TEMPLATE_PATH,  # ⚠️ 리뷰 반영 (오류 4): 절대 경로 사용
    "sheets": [
        {
            "name": "갑지",
            "type": "cover",
            "fields": {
                "title": "A1", "date": "I3", "client": "C4",
                "amount": "C5", "project": "C6", "description": "C7",
                "item": "C8", "serial_no": "C9",
            },
        },
        {
            "name": "내역서",
            "type": "detail",
            "source_table_type": "E_견적내역",
            "source_table_index": -1,
        },
        {
            "name": "요약",
            "type": "summary",
            "source_table_index": 0,
        },
    ],
}
```

**§4-5. SUMMARY_ROW_KEYWORDS + is_summary_row()**

```python
SUMMARY_ROW_KEYWORDS = [
    "소 계", "소계", "합 계", "합계", "총 합 계", "총합계",
    "직접비", "간접비", "일반관리비",
]

def is_summary_row(row_data: dict) -> bool:
    """행이 합계/소계 행인지 판별한다."""
    for value in row_data.values():
        if isinstance(value, str):
            for keyword in SUMMARY_ROW_KEYWORDS:
                if keyword in value:
                    return True
    return False
```

**§4-6. 공개 인터페이스**

```python
def get_table_type_keywords() -> dict:
    return TABLE_TYPE_KEYWORDS

def get_excel_config() -> dict:
    return EXCEL_SHEET_CONFIG

def get_cover_patterns() -> dict:
    return COVER_PATTERNS
```

**예상 규모:** ~180줄

---

### 5. `detector.py` — 문서 유형 자동 감지 (신규)

> 원본 설계: Phase3_상세_구현_기술서.md §6 (L890~976)
> 변경점: 없음 (원본 설계 그대로 구현)

```python
"""
detector.py — 문서 유형 자동 감지기 (텍스트 기반)

Why: Phase 1 추출 완료 후의 MD 텍스트를 입력으로 받아
     키워드 매칭으로 문서 유형을 판별한다.
     --preset 미지정 시에만 동작하며, 확신도 낮으면 None 반환.

Dependencies: 없음 (순수 문자열 처리)
"""


# ── 키워드 정의 ──

ESTIMATE_KEYWORDS = [
    "見積", "견적", "견적금액", "내역서", "납품기일",
    "결제조건", "견적유효기간", "직접비", "간접비",
]

PUMSEM_KEYWORDS = [
    "품셈", "수량산출", "부문", "제6장", "단위당",
    "적용기준", "노무비", "참조", "보완",
]

THRESHOLD = 4  # ⚠️ 리뷰 반영 (🟡): 3→4 상향 (오탐 방지)


def detect_document_type(text: str) -> str | None:
    """
    추출된 텍스트를 분석하여 문서 유형을 추정한다.

    Args:
        text: Phase 1 추출 결과 (MD 문자열)

    Returns:
        "estimate" | "pumsem" | None (판별 불가 → 범용)
    """
    if not text or not text.strip():
        return None

    estimate_score = sum(1 for kw in ESTIMATE_KEYWORDS if kw in text)
    pumsem_score = sum(1 for kw in PUMSEM_KEYWORDS if kw in text)

    if estimate_score >= THRESHOLD and estimate_score > pumsem_score:
        return "estimate"
    elif pumsem_score >= THRESHOLD and pumsem_score > estimate_score:
        return "pumsem"

    return None


def suggest_preset(text: str) -> str:
    """프리셋 제안 메시지를 생성한다. 빈 문자열 = 제안 없음."""
    detected = detect_document_type(text)
    if detected == "estimate":
        return "💡 견적서로 감지되었습니다. --preset estimate 를 추가하면 견적서 양식으로 출력됩니다."
    elif detected == "pumsem":
        return "💡 품셈 문서로 감지되었습니다. --preset pumsem --toc <목차파일> 을 추가하면 품셈 양식으로 출력됩니다."
    return ""
```

**예상 규모:** ~55줄

---

### 6. K1 한글 균등배분 병합 — 함수 정의 + 다중 호출 지점 (변경)

> 참조: kordoc `cluster-detector.ts` 균등배분 처리 로직 (MIT)
> ⚠️ 리뷰 반영 (오류 1): 삽입 위치를 clean_text() 단독 → hybrid_extractor.py/text_extractor.py(주) + clean_text()(보조)로 변경

**§6-1. 함수 정의 — `parsers/text_cleaner.py`**

함수 정의는 `text_cleaner.py`에 유지한다 (표준 라이브러리 `re`만 의존, 아키텍처 깔끔).

```python
# 알고리즘 참조: kordoc (https://github.com/chrisryugj/kordoc)
# Copyright (c) chrisryugj, MIT License

# ⚠️ 리뷰 반영 (🟡): \d 제거 — 숫자 1글자 토큰은 균등배분 판정 대상이 아님
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
        "현 장 명"   → "현장명"
        "SUS 304"    → "SUS 304" (변환 안 함: 한글 토큰 0%)
        "배관 Support" → "배관 Support" (변환 안 함: 비율 미달)

    Args:
        text: 원본 텍스트

    Returns:
        균등배분이 병합된 텍스트
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
```

**§6-2. 주 호출 — `extractors/hybrid_extractor.py` (Phase 1 PDF 추출)**

> Why: K1이 가장 효과적인 구간은 PDF에서 텍스트가 처음 뽑혀나올 때다.
> `format_text_with_linebreaks()` 전에 K1을 적용해야 "제 출 처" 같은 텍스트가
> 줄바꿈 병합 로직에 의해 오판되지 않는다.

```python
# hybrid_extractor.py 상단 import 추가
from parsers.text_cleaner import merge_spaced_korean

# L137 부근 (테이블 없는 페이지 텍스트 추출):
text = plumber_page.extract_text()
if text:
    text = merge_spaced_korean(text)           # ← K1 삽입
    formatted = format_text_with_linebreaks(
        text, division_names=division_names
    )
    markdown_output += formatted + "\n\n"

# L162 부근 (이미지 변환 실패 폴백):
text = plumber_page.extract_text()
if text:
    text = merge_spaced_korean(text)           # ← K1 삽입
    formatted = format_text_with_linebreaks(
        text, division_names=division_names
    )
    markdown_output += formatted + "\n\n"
```

**§6-3. 주 호출 — `extractors/text_extractor.py` (Phase 1 텍스트 전용)**

```python
# text_extractor.py 상단 import 추가
from parsers.text_cleaner import merge_spaced_korean

# extract_text_regions_with_positions() L80 부근:
text = page.extract_text()
if text and text.strip():
    return [{
        "y": 0, "type": "text",
        "content": format_text_with_linebreaks(
            merge_spaced_korean(text.strip()),  # ← K1 삽입
            division_names=division_names
        ),
    }]

# L117 부근 (영역별 추출):
text = cropped.extract_text()
if text and text.strip():
    formatted = format_text_with_linebreaks(
        merge_spaced_korean(text.strip()),      # ← K1 삽입
        division_names=division_names
    )

# process_pdf_text_only() L208 부근:
if text:
    formatted_text = format_text_with_linebreaks(
        merge_spaced_korean(text),              # ← K1 삽입
        division_names=division_names
    )
```

**§6-4. 보조 호출 — `parsers/text_cleaner.py` clean_text() (Phase 2 안전망)**

> Why: MD 파일 직접 입력 시 Phase 1을 거치지 않으므로,
> clean_text()에서도 K1을 실행하여 MD→JSON 파이프라인을 커버한다.

```python
def clean_text(text: str, ...) -> str:
    # ── 범용: 항상 수행 ──
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    text = merge_spaced_korean(text)  # ← K1 보조 호출 (Phase 2 안전망)
    # ... 기존 줄바꿈 정리 ...
```

**예상 추가 규모:** text_cleaner.py ~35줄 (함수 정의), hybrid_extractor.py ~6줄, text_extractor.py ~9줄

---

### 7. `extractors/text_extractor.py` — K4 Bold-fake 글리프 중복 제거 (변경)

> 참조: kordoc `parser.ts` Bold-fake 처리 로직 (MIT)
> ⚠️ 리뷰 반영 (오류 2): `utils/text_formatter.py` → `extractors/text_extractor.py`로 위치 변경.
> Why: K4는 pdfplumber `page.extract_words()` 결과(좌표 포함 dict)를 입력으로 받는다.
> `text_formatter.py`는 순수 문자열(str) 처리 모듈이므로 아키텍처적으로 잘못된 위치.
> `text_extractor.py`는 이미 pdfplumber를 import하고 page 객체를 직접 다루므로 적합.

**추가 함수:**

```python
# extractors/text_extractor.py 내 추가

# 알고리즘 참조: kordoc (https://github.com/chrisryugj/kordoc)
# Copyright (c) chrisryugj, MIT License


def deduplicate_bold_fake(words: list[dict]) -> list[dict]:
    """
    Bold-fake 글리프 중복을 제거한다.

    Why: 일부 PDF는 볼드를 폰트 가중치 대신 동일 텍스트를
         ±3px 오프셋으로 중복 렌더링하여 구현한다.
         pdfplumber extract_words() 결과에서 이를 제거하지 않으면
         "품명품명" 같은 중복이 발생한다.

    Args:
        words: pdfplumber page.extract_words() 결과
               각 원소: dict {'x0': float, 'top': float, 'text': str, ...}

    Returns:
        중복 제거된 words 리스트

    판정 기준 (kordoc 참조):
        - 동일 텍스트
        - Y좌표 차이 ≤ 1pt (같은 행)
        - X좌표 차이 ≤ 3pt (오프셋 볼드)
        → 세 조건 모두 충족 시 중복 판정, 첫 번째만 유지
    """
    if not words:
        return words

    result = []
    for word in words:
        text = word['text']
        x0 = word['x0']
        y0 = word['top']

        is_dup = False
        for existing in result:
            if (text == existing['text']
                    and abs(y0 - existing['top']) <= 1.0
                    and abs(x0 - existing['x0']) <= 3.0):
                is_dup = True
                break

        if not is_dup:
            result.append(word)

    return result
```

**적용 위치:** `text_extractor.py` 내의 `extract_text_regions_with_positions()` 또는 `hybrid_extractor.py`에서 `page.extract_words()` 호출 직후에 필터링. Phase 3-B에서는 함수만 추가하고, 실제 호출 연결은 Phase 4 BOM 엔진에서 수행.

**향후 연결 예시 (Phase 4):**
```python
# hybrid_extractor.py 내 테이블 영역 텍스트 추출 시
words = plumber_page.extract_words()
words = deduplicate_bold_fake(words)  # K4
text = " ".join(w['text'] for w in words)
```

**예상 추가 규모:** ~45줄

---

### 8. `main.py` — 확장 (변경)

> 원본 설계: Phase3_상세_구현_기술서.md §7 (L980~1115)
> 변경점: 현재 코드 (435줄) 기준으로 4곳 변경

**§8-1. argparse 변경**

```python
# 현재: choices=["md", "json", "excel"] — 이미 구현됨
# 변경: --preset에 "estimate" 추가
parser.add_argument(
    "--preset",
    default=None,
    choices=["pumsem", "estimate"],  # ← estimate 추가
    help="도메인 프리셋 (기본: 없음=범용)",
)
```

**§8-2. .json 입력 지원 (신규)**

```python
# input_path 판정부에 추가
is_json_input = input_path.lower().endswith(".json")

if is_json_input:
    if args.output_format != "excel":
        print("⚠️  .json 파일 입력 시 --output excel 을 사용하세요.")
        sys.exit(1)

    import json as json_lib
    with open(input_path, "r", encoding="utf-8-sig") as f:
        sections = json_lib.load(f)
    if isinstance(sections, dict):
        cover_metadata = sections.get("metadata")
        sections = sections.get("sections", [])
```

**§8-3. estimate 프리셋 로딩**

```python
# 기존 pumsem 프리셋 로딩 블록 아래에 추가
excel_config = None
cover_metadata = None

if preset == "estimate":
    from presets.estimate import (
        get_table_type_keywords as get_est_keywords,
        get_excel_config,
        extract_cover_metadata,
    )
    type_keywords = get_est_keywords()
    excel_config = get_excel_config()
    print(f"📋 프리셋 활성화: {preset}")
```

**§8-4. detector 연동 (Phase 1 완료 후)**

```python
# Phase 1 완료 후, --preset 미지정 시
if preset is None and md:
    from detector import suggest_preset
    suggestion = suggest_preset(md)
    if suggestion:
        print(suggestion)
```

**§8-5. Phase 3 Excel 호출을 ExcelExporter 클래스로 전환**

```python
# 현재 (함수 기반):
from exporters.excel_exporter import export as excel_export
excel_export(sections, xlsx_path)

# 변경 (클래스 기반):
from exporters.excel_exporter import ExcelExporter
exporter = ExcelExporter()

# 견적서 프리셋: 표지 메타 추출
if preset == "estimate" and sections:
    cover_metadata = extract_cover_metadata(
        sections[0].get("clean_text", "")
    )
    print(f"   📋 표지 메타 추출: {cover_metadata.get('serial_no', '(없음)')}")

exporter.export(
    sections, xlsx_path,
    metadata=cover_metadata,
    preset_config=excel_config,
)
```

**§8-6. JSON 저장을 JsonExporter 클래스로 전환**

```python
# 현재 (인라인):
with open(json_path, "w", encoding="utf-8-sig") as f:
    json.dump(sections, f, ensure_ascii=False, indent=2)

# 변경 (클래스 기반):
from exporters.json_exporter import JsonExporter
json_exporter = JsonExporter()
json_exporter.export(sections, json_path)
```

**예상 변경 규모:** ~50줄 변경/추가

---

### 9. `exporters/__init__.py` — 패키지 초기화 (변경)

```python
"""
exporters/ — Phase 3: JSON → 출력 변환 엔진

구현:
    base_exporter.py    ABC 인터페이스
    excel_exporter.py   JSON sections → Excel (.xlsx)
    json_exporter.py    JSON sections → JSON 파일

향후:
    db_exporter.py      Supabase 업로드
"""
```

**예상 규모:** ~10줄

---

### 10. `templates/견적서_양식.xlsx` — 갑지 표지 양식 (신규)

> 이 파일은 **코드 생성이 아닌 수동 생성**이다.

Excel에서 갑지 양식(로고, 결재선, 셀 병합 등)을 직접 디자인하여 저장.
`estimate.py`의 `EXCEL_SHEET_CONFIG.template_path`가 이 파일을 참조.

**시트 구조:**
- "갑지" 시트: 견적서 표지 (A1: 제목, C4: 제출처, C5: 금액 등 셀 위치 고정)
- 나머지 시트: 코드에서 동적 생성

**주의:** 템플릿이 없는 경우 `ExcelExporter`는 빈 워크북에서 key-value 형태로 폴백한다.

---

## 기구현 항목 (Phase 3-A에서 완료, 재구현 불필요)

| 항목 | 위치 | 상태 |
|------|------|------|
| `_try_parse_number()` | `excel_exporter.py` L126-160 | ✅ 수정 D |
| `_build_generic_sheet()` | `excel_exporter.py` L482-541 | ✅ 수정 C |
| `_classify_table()` → generic 반환 | `excel_exporter.py` L109-110 | ✅ 수정 A |
| `_row_style()` all([]) 수정 | `excel_exporter.py` L189 | ✅ 수정 F |
| `_build_condition_sheet()` dedup 수정 | `excel_exporter.py` L463-475 | ✅ 수정 E |
| `wb.save()` PermissionError | `excel_exporter.py` L644-650 | ✅ 수정 G |
| 헤더 없는 테이블 폴백 | `excel_exporter.py` L497-504 | ✅ 수정 H |
| openpyxl requirements.txt 추가 | `requirements.txt` | ✅ |

---

## 잠재 위험 요소 검토

### 위험 1: ExcelExporter 위임 패턴의 시그니처 불일치

**문제:** 기존 `export(sections, output_path, *, title=None)`과 `BaseExporter.export(sections, output_path, *, metadata=None, preset_config=None)`의 시그니처가 다르다.

**해결:** `ExcelExporter.export()` 내부에서 `metadata`에서 `title`을 추출하여 기존 함수에 전달:
```python
title = metadata.get("description") if metadata else None
return export_func(sections, output_path, title=title)
```

### 위험 2: K1 균등배분 오탐 — 영문+숫자 토큰

**문제:** `"A B C D E"` 같은 영문 알파벳 나열도 1글자 토큰이므로 균등배분으로 오판될 수 있다.

**해결:** `_RE_SINGLE_HANGUL = re.compile(r'^[가-힣]$')` — **한글만** 판정 대상. 영문/숫자 1글자 토큰은 비율 계산에서 제외. (리뷰 반영으로 `\d` 제거 완료)

### 위험 3: estimate 프리셋 COVER_PATTERNS의 정규식 범위

**문제:** `"공 사 명"` 처럼 균등배분된 라벨은 `r'공\s*사\s*명'` 패턴으로 잡히지만, 실제 견적서마다 라벨 표기가 다를 수 있다.

**해결:** K1 균등배분 병합이 **Phase 1 추출 직후 + Phase 2 clean_text() 이중으로 실행**되므로, extract_cover_metadata()에 도달하는 시점에는 이미 `"공사명"` 형태로 정제되어 있다. 패턴의 `\s*`는 K1이 놓치는 엣지 케이스 방어용.

### 위험 4: templates/ 폴더 미생성 시

**문제:** `templates/견적서_양식.xlsx`이 없으면 `estimate` 프리셋의 갑지 시트가 빈 폴백으로 생성된다.

**해결:** 의도된 동작. `ExcelExporter`의 `_write_cover_sheet()`가 템플릿 없을 시 key-value 방식으로 폴백. 기능은 정상 작동하되 시각적 양식이 없는 상태.

### 위험 5: main.py JSON 인라인 코드와 JsonExporter 이중 경로

**문제:** 기존 `json.dump()` 인라인 코드를 `JsonExporter`로 교체할 때, 기존 json 출력 경로가 깨지지 않아야 한다.

**해결:** `JsonExporter.export()`의 동작이 기존 `json.dump()`와 **바이트 단위로 동일한 출력**을 생성하는지 검증 필수. 인코딩(`utf-8-sig`), indent(2), `ensure_ascii=False` 모두 일치시킨다.

---

## 구현 순서 (의존성 기반)

```
1단계: 의존성 없는 모듈 (병렬 가능)
  ├── exporters/base_exporter.py       (ABC, 의존성 없음)
  ├── presets/estimate.py              (re + Path만 사용, 의존성 없음)
  ├── detector.py                      (순수 문자열, 의존성 없음)
  ├── parsers/text_cleaner.py K1 정의  (re만 사용, merge_spaced_korean 함수 추가)
  └── extractors/text_extractor.py K4  (pdfplumber 이미 import됨, 함수만 추가)

2단계: Exporter + Extractor 연결 (1단계 의존)
  ├── exporters/excel_exporter.py      (_export_impl rename + ExcelExporter 래퍼)
  ├── exporters/json_exporter.py       (BaseExporter 상속)
  ├── exporters/__init__.py            (docstring 업데이트)
  ├── extractors/hybrid_extractor.py   (K1 호출 삽입 — text_cleaner import)
  └── extractors/text_extractor.py     (K1 호출 삽입 — text_cleaner import)

3단계: CLI 연결 (1+2단계 전체 의존)
  └── main.py                          (4곳 변경)

4단계: 템플릿 (코드 무관, 언제든 생성 가능)
  └── templates/견적서_양식.xlsx        (수동 디자인)
```

---

## 검증 계획

### 단위 테스트

| # | 검증 항목 | 입력 | 기대 결과 |
|---|---------|------|----------|
| 1 | `BaseExporter` ABC 강제 | `BaseExporter()` 직접 인스턴스화 | `TypeError` (추상 클래스) |
| 2 | `ExcelExporter.file_extension` | 속성 접근 | `".xlsx"` |
| 3 | `JsonExporter.file_extension` | 속성 접근 | `".json"` |
| 4 | `ExcelExporter.export()` 위임 | 기존 테스트 JSON 입력 | 기존 `export()` 함수와 동일한 Excel 출력 |
| 5 | `JsonExporter.export()` | sections + metadata | `{"metadata": ..., "sections": [...]}` 구조 |
| 6 | `JsonExporter.export()` | sections only (metadata=None) | `[...]` 배열 구조 (기존 동일) |
| 7 | `extract_cover_metadata()` | 견적서 clean_text | 6개 필드 추출, `amount=16700000` |
| 8 | `extract_cover_metadata()` | 빈 문자열 | 모든 필드 빈 값, amount=None |
| 9 | `detect_document_type()` | 견적서 텍스트 | `"estimate"` |
| 10 | `detect_document_type()` | 품셈 텍스트 | `"pumsem"` |
| 11 | `detect_document_type()` | 일반 텍스트 | `None` |
| 12 | `merge_spaced_korean()` | `"제 출 처"` | `"제출처"` |
| 13 | `merge_spaced_korean()` | `"SUS 304"` | `"SUS 304"` (변환 안 함) |
| 14 | `merge_spaced_korean()` | `"배관 Support 제작"` | `"배관 Support 제작"` (비율 미달) |
| 15 | `deduplicate_bold_fake()` | 중복 word 2개 (x 차이 2px) | 1개만 유지 |
| 16 | `deduplicate_bold_fake()` | 비중복 word 2개 (x 차이 50px) | 2개 모두 유지 |
| 17 | `is_summary_row()` | `{"명 칭": "합 계", "금 액": "15,000,000"}` | `True` |

### 통합 테스트

| # | 검증 항목 | 명령어 | 기대 결과 |
|---|---------|--------|----------|
| 1 | PDF→Excel (견적서) | `python main.py "견적서.pdf" --output excel --preset estimate` | 갑지+내역서+요약 시트, 금액 숫자 포맷 |
| 2 | PDF→Excel (범용) | `python main.py "견적서.pdf" --output excel` | 테이블별 시트 (기존 동작 유지) |
| 3 | MD→Excel | `python main.py "추출.md" --output excel` | JSON 거쳐 Excel 출력 |
| 4 | JSON→Excel | `python main.py "결과.json" --output excel` | JSON 직접 로드 → Excel |
| 5 | 문서 감지 | `python main.py "견적서.pdf" --output excel` (preset 미지정) | `💡 견적서로 감지...` 출력 |
| 6 | JSON 저장 호환 | `python main.py "추출.md" --output json` | 기존과 바이트 단위 동일한 JSON |

### 회귀 테스트 (Phase 1/2/3-A 보존)

| # | 검증 항목 | 기대 결과 |
|---|---------|----------|
| 1 | `python main.py "견적서.pdf"` (기본) | Phase 1 MD 출력 변경 없음 |
| 2 | `python main.py "추출.md" --output json --preset pumsem` | Phase 2 JSON 변경 없음 |
| 3 | `python main.py "추출.md" --output excel` | Phase 3-A Excel 변경 없음 |
| 4 | `python _test_phase3.py` | 기존 테스트 ALL PASS |

---

## 완료 후 파이프라인 전체 흐름

```
📄 입력 파일
     │
     ├── .pdf ──[Phase 1: extractors/ + engines/]──→ 📝 MD
     │                                                │
     │                                                ├─ detector.suggest_preset() ← [3-B 신규]
     │                                                │
     ├── .md ──────────────────────────────────────────┤
     │                                                │
     │          ┌─ merge_spaced_korean() (K1) ← [3-B 신규]
     │          │
     │    [Phase 2: parsers/ + presets/]───────────→ 📦 JSON
     │                                                │
     ├── .json ← [3-B 신규 입력] ──────────────────────┤
     │                                                │
     │    [Phase 3: exporters/]                       │
     │          │                                     │
     │          ├── JsonExporter  → 📦 JSON 파일      ← [3-B 신규]
     │          └── ExcelExporter → 📊 Excel (.xlsx)  ← [3-B 클래스화]
     │                    │
     │                    ├── preset=None     → 범용 (Table_N 시트)
     │                    ├── preset=pumsem   → 품셈 (견적서/내역서/조건)
     │                    └── preset=estimate → 견적서 (갑지+내역서+요약) ← [3-B 신규]
     │
     └────────────────────────────────────────────────
```

---

---

## 리뷰 반영 이력

> **리뷰어:** 수석 엔지니어 (2026-04-14)
> **반영일:** 2026-04-14

| # | 구분 | 항목 | 원본 | 수정 |
|---|------|------|------|------|
| 🔴1 | K1 삽입 위치 | §6 | `clean_text()` 단독 | hybrid_extractor.py + text_extractor.py(주) + clean_text()(보조) |
| 🔴2 | K4 파일 위치 | §7 | `utils/text_formatter.py` | `extractors/text_extractor.py` |
| 🔴3 | export 이름 충돌 | §2 | `export_func = export` 별칭 | `_export_impl` rename + `export = _export_impl` 호환 |
| 🔴4 | template_path | §4-4 | 상대 경로 `"templates/..."` | `Path(__file__).resolve()` 기반 절대 경로 |
| 🟡5 | _RE_SINGLE_HANGUL | §6 | `r'^[가-힣\d]$'` | `r'^[가-힣]$'` (\d 제거) |
| 🟡6 | COVER_PATTERNS | §4-2 | `(?:\s*경남\|\s*$)` 종결 | `$` 범용 종결 |
| 🟡7 | THRESHOLD | §5 | 3 | 4 (오탐 방지) |

---

> 작성일: 2026-04-14 | Phase 3-B of 5 | 작성: Antigravity AI
> 리뷰 반영: 2026-04-14 | 수석 엔지니어 핀셋 리뷰 7건
> 라이선스 참조: K1, K4 알고리즘은 kordoc (MIT License, Copyright (c) chrisryugj) 참조
