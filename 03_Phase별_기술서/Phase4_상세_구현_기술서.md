# Phase 4 상세 구현 기술서 — BOM 추출 엔진 신규 설계

> 작성일: 2026-04-15 | 최종 수정: 2026-04-15 (코드 리뷰 7건 + 구현 동기화 3건 반영)
> 선행: Phase 3-B (Exporter 아키텍처 완성, detector.py, estimate 프리셋 완료)
> 참조: `상세_구현_기술서_작성_계획.md` §5 / ocr.py 도메인 지식 / kordoc (MIT) K2,K3 알고리즘
> 원본 소스: `ocr.py` (2,309줄) — 코드 포팅 아닌 **도메인 지식 참조** 전용

---

## 1. 목적

Phase 3-B까지 완성된 범용 문서 파서 파이프라인(PDF→MD→JSON→Excel)에 **BOM(Bill of Materials) / LINE LIST 추출 전용 파이프라인**을 추가한다.

핵심 설계 원칙:
1. **신규 설계** — ocr.py 코드를 직접 포팅하지 않는다. 도메인 지식(키워드, 패턴, 알고리즘 아이디어)만 추출하여 ps-docparser 아키텍처 위에 새로 구현한다.
2. **기존 아키텍처 준수** — Strategy Pattern(engines), Preset 체계(presets), 모듈 분리(extractors/parsers/exporters) 구조를 그대로 활용한다.
3. **OCR 엔진 3종 플러그인** — Z.ai GLM-OCR, Mistral Pixtral, Tesseract를 `BaseEngine` 상속으로 통합한다.
4. **kordoc K2/K3** — 선 없는 테이블 감지(K2)와 동적 허용 오차(K3)로 테이블 감지 품질을 개선한다.
5. **Phase 2 JSON 호환** — BOM 추출 결과를 표준 섹션 JSON 형식으로 출력하여 기존 ExcelExporter를 그대로 사용한다.

완료 시점에 `python main.py "drawing.pdf" --engine zai --preset bom --output excel` 한 줄로 BOM Excel이 생성되어야 한다.

---

## 2. 설계 방향: 신규 설계 근거

### 2.1 ocr.py 코드 품질 분석 요약

`상세_구현_기술서_작성_계획.md` §5.1~5.2에서 수행한 정밀 코드 리뷰 결과:

| 분류 | 치명적 | 주의 | 경미 | 합계 |
|------|--------|------|------|------|
| 에러 처리 (bare except 11건) | 11건 | 1건 | - | 12건 |
| Dead Code (미호출 함수 4건) | 4건 | - | - | 4건 |
| God Object (1클래스 26메서드) | 1건 | - | - | 1건 |
| 중복 코드 (HTML 파싱 3중 등) | 2건 | 3건 | - | 5건 |
| 하드코딩 (매직넘버 7건) | 1건 | 7건 | - | 8건 |
| GUI-로직 결합 | 1건 | - | - | 1건 |
| 동작 의심 | - | 4건 | - | 4건 |
| 보안 | - | - | 2건 | 2건 |
| **합계** | **20건** | **15건** | **2건** | **37건** |

> **판정:** 직접 포팅 시 37건의 결함이 유입될 위험이 높아 **신규 설계**로 전환한다.

### 2.2 신규 설계 접근 방식

```
[기존 접근 — 폐기]
ocr.py 코드 복사 → 클래스 분리 → 에러 처리 추가 → 중복 제거
(문제: 37건의 결함이 포팅 과정에서 유입될 위험)

[신규 접근 — 확정]
ocr.py에서 도메인 지식 추출 (키워드, 패턴, 알고리즘 아이디어)
     ↓
ps-docparser 기존 아키텍처 활용 (Strategy Pattern, preset 체계, 모듈 분리)
     ↓
새 파일 작성 (engines/base_engine.py, presets/ 인터페이스 준수)
```

### 2.3 ocr.py 도메인 지식 재활용 범위

```
🟢 도메인 지식으로 참조 (~20%, 요구사항 문서로 활용)
├── BOM 식별 키워드 전략 (품명/규격/수량/단위/재질 키워드 3그룹 AND 조건)
├── 앵커-경계선 상태머신 "패턴" (IDLE→SCAN→DATA→IDLE 아이디어)
├── 3단계 OCR 폴백의 "아이디어" (Z.ai→Mistral→Tesseract 순서)
├── 거래명세표/세금계산서 키워드 패턴
├── 도면 좌측 제거 → 우측 55% 표 영역 크롭 아이디어
└── 하단 50% LINE LIST 영역 크롭 아이디어

🟡 참고만 (~30%, 정규식/알고리즘 일부 발췌 가능)
├── HTML 테이블 정규식 (3중 중복 중 가장 나은 것 1개)
├── 마크다운 파이프 테이블 파싱 정규식
├── 공백 2+ 구분 컬럼 감지 휴리스틱
├── 열 수 정규화 알고리즘 (인접 최소 셀 병합)
└── Excel 저장 시 열 너비 자동 계산

🔴 폐기 (~50%, 코드 자체를 사용하지 않음)
├── GUI 전체 (tkinter) → Phase 5에서 새로 설계
├── API 키 암호화 (platform 기반 = 보안성 0) → config.py .env 방식 사용
├── Dead code 4개 함수
├── 11건의 bare except + pass
├── 3중 중복 HTML 파싱 → 통합 1개로 새로 작성
├── 3중 중복 분기 → preset 키워드로 자동 라우팅
├── 4중 중복 키워드 리스트 → presets/bom.py 1곳으로 통합
└── process_batch 배치 오케스트레이션 → Phase 5에서 새로 설계
```

---

## 3. Phase 3-B 출력물 분석 (입력 스펙)

### 3.1 현재 파이프라인 아키텍처 (Phase 1~3)

```
PDF ─[Phase 1: extractors/ + engines/]──→ MD
     │                                    │
     │  hybrid_extractor.py               │
     │  ├─ pdfplumber (테이블 감지+bbox)    │
     │  ├─ pdf2image (페이지→이미지)         │
     │  └─ engine.extract_table(image)     │
     │     ├─ GeminiEngine (Vision API)    │
     │     └─ LocalEngine (pdfplumber)     │
     │                                    │
MD ──[Phase 2: parsers/ + presets/]──→ JSON
     │                                    │
     │  document_parser.py                │
     │  ├─ section_splitter.py (마커 파싱)  │
     │  ├─ table_parser.py (HTML→2D)       │
     │  └─ text_cleaner.py (정제+메타)      │
     │                                    │
JSON [Phase 3: exporters/]──→ Excel/JSON
     │
     ├─ ExcelExporter (_build_generic_sheet)
     └─ JsonExporter
```

### 3.2 BOM 파이프라인 설계 (Phase 4 신규)

```
PDF ─[Phase 1-BOM: OCR engines]──→ Raw Text
     │                                    │
     │  OCR 엔진 선택:                     │
     │  ├─ ZaiEngine (Z.ai GLM-OCR)       │
     │  ├─ MistralEngine (Pixtral OCR)    │
     │  └─ TesseractEngine (로컬 OCR)      │
     │                                    │
     │  이미지 전처리:                      │
     │  ├─ 전체 페이지 (400 DPI)            │
     │  ├─ 우측 55% 크롭 (BOM 영역)         │
     │  └─ 하단 50% 크롭 (LINE LIST, 600 DPI)│
     │                                    │
Raw Text ─[Phase 2-BOM: bom_extractor]──→ JSON (Phase 2 호환)
     │                                    │
     │  bom_extractor.py                  │
     │  ├─ 상태머신 (IDLE→SCAN→DATA→IDLE)   │
     │  ├─ bom_table_parser.py (HTML/MD/공백)│
     │  └─ to_sections() → 표준 JSON 변환   │
     │                                    │
JSON ─[Phase 3: 기존 exporters/]──→ Excel
     │
     └─ ExcelExporter (그대로 재사용)
```

**핵심:** BOM 추출 결과를 Phase 2 출력과 동일한 JSON 섹션 형식으로 변환하여, Phase 3 ExcelExporter를 **무수정 재사용**한다.

### 3.3 기존 자산 재활용

| 기존 자산 | 재활용 방식 |
|----------|-----------|
| `engines/base_engine.py` | OCR 메서드(`ocr_document`, `ocr_image`) 추가 확장 |
| `table_parser.py::expand_table()` | BOM HTML 테이블의 rowspan/colspan 전개에 재사용 |
| `excel_exporter.py::_build_generic_sheet()` | BOM 테이블 Excel 출력에 그대로 사용 |
| `excel_exporter.py::_try_parse_number()` | QTY, WEIGHT 숫자 포맷팅에 그대로 사용 |
| `presets/pumsem.py` 인터페이스 | `bom.py`가 동일 구조(`get_*()` 함수) 준수 |
| `config.py` `.env` 패턴 | OCR API 키, Tesseract 경로 등 통합 관리 |
| `detector.py` | "bom" 유형 감지 추가 |
| `pdf2image` + Poppler | PDF→이미지 변환 (기존 인프라 재사용) |

---

## 4. Phase 4 신규/변경 파일 목록

```
ps-docparser/
├── config.py                              [변경] OCR 엔진 설정 추가
├── detector.py                            [변경] BOM 키워드 감지 추가
├── main.py                                [변경] OCR 엔진 선택 + BOM 파이프라인
│
├── engines/
│   ├── base_engine.py                     [변경] OCR 인터페이스 추가 (~30줄)
│   ├── zai_engine.py                      [신규] Z.ai GLM-OCR 엔진 (~140줄)
│   ├── mistral_engine.py                  [신규] Mistral Pixtral OCR 엔진 (~120줄)
│   └── tesseract_engine.py                [신규] Tesseract 로컬 OCR 엔진 (~130줄)
│
├── extractors/
│   ├── bom_types.py                       [신규] BOM 데이터 클래스 분리 (~50줄) ← 리뷰 반영 🔴1
│   ├── bom_extractor.py                   [신규] BOM/LINE LIST 추출 상태머신 (~400줄)
│   └── table_utils.py                     [변경] K2 + K3 추가 (~240줄 추가)
│
├── parsers/
│   └── bom_table_parser.py                [신규] BOM 테이블 파싱 통합 (~280줄)
│
├── presets/
│   └── bom.py                             [신규] BOM 프리셋 (~130줄)
│
└── utils/
    └── ocr_utils.py                       [신규] OCR 공통 유틸리티 (~60줄) ← 리뷰 반영 🟡5,7
```

| 구분 | 파일 수 | 예상 줄 수 |
|------|--------|----------|
| 신규 | 8개 | ~1,310줄 |
| 변경 | 5개 | ~370줄 추가 |
| **합계** | **13개** | **~1,680줄** |

---

## 5. 파일별 상세 스펙

### 5.0-A `extractors/bom_types.py` — BOM 데이터 클래스 분리 (신규)

> ⚠️ 리뷰 반영 (🔴1): 순환 import 방지를 위해 데이터 클래스를 별도 모듈로 분리
> 예상 규모: ~50줄

**Why:** `bom_extractor.py`가 `bom_table_parser.py`를 lazy import하고, `bom_table_parser.py`가 `BomSection`/`BomExtractionResult`를 모듈 레벨 import하면 **import 순서에 따라 순환 참조가 발생할 수 있다.** 데이터 클래스를 제3의 모듈(`bom_types.py`)에 분리하면 양쪽 모두 안전하게 모듈 레벨 import 가능.

```python
"""
extractors/bom_types.py — BOM 데이터 클래스 정의

Why: bom_extractor.py ↔ bom_table_parser.py 간 순환 import 방지.
     양쪽 모두 이 파일에서 데이터 클래스를 import한다.
     제3의 모듈에 정의하므로 import 방향이 항상 단방향:
       bom_types.py ← bom_extractor.py
       bom_types.py ← bom_table_parser.py

Dependencies: 없음 (표준 라이브러리 dataclasses만 사용)
"""
from dataclasses import dataclass, field


@dataclass
class BomSection:
    """추출된 BOM 또는 LINE LIST 섹션 1개."""
    section_type: str                      # "bom" | "line_list"
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    source_page: int | None = None
    raw_row_count: int = 0                 # 필터 전 행 수

    @property
    def parsed_row_count(self) -> int:
        return len(self.rows)


@dataclass
class BomExtractionResult:
    """BOM 추출 전체 결과."""
    bom_sections: list[BomSection] = field(default_factory=list)
    line_list_sections: list[BomSection] = field(default_factory=list)
    raw_text: str = ""
    ocr_engine: str = ""                   # 사용된 엔진명 (로그용)

    @property
    def has_bom(self) -> bool:
        return any(s.rows for s in self.bom_sections)

    @property
    def has_line_list(self) -> bool:
        return any(s.rows for s in self.line_list_sections)

    @property
    def total_bom_rows(self) -> int:
        return sum(s.parsed_row_count for s in self.bom_sections)

    @property
    def total_ll_rows(self) -> int:
        return sum(s.parsed_row_count for s in self.line_list_sections)
```

**Import 관계 (순환 없음):**
```
extractors/bom_types.py  (데이터 클래스만, 외부 import 없음)
     ↑                ↑
     │                │
bom_extractor.py   bom_table_parser.py
     │                ↑
     └── lazy import ─┘  (함수 내부에서만)
```

---

### 5.0-B `utils/ocr_utils.py` — OCR 공통 유틸리티 (신규)

> ⚠️ 리뷰 반영 (🟡5, 🟡7): `_file_to_data_uri()`, `_pdf_page_to_image()` 중복 제거
> 예상 규모: ~60줄

**Why:** `ZaiEngine`과 `MistralEngine`에 동일한 `_file_to_data_uri()`, `_image_to_data_uri()` static method가 중복되고, `ZaiEngine._pdf_page_to_image()`와 `bom_extractor._get_page_image()`도 동일 로직이다. 공통 유틸리티로 추출한다.

```python
"""
utils/ocr_utils.py — OCR 엔진 공통 유틸리티

Why: ZaiEngine, MistralEngine, bom_extractor에서 중복되는
     base64 변환 및 PDF→이미지 변환 로직을 1곳으로 통합한다.

Dependencies: Pillow, pdf2image, config.POPPLER_PATH
"""
import base64
import io
from pathlib import Path

from PIL import Image


def file_to_data_uri(file_path: Path) -> str:
    """파일을 base64 data URI로 변환한다."""
    file_path = Path(file_path)
    with open(file_path, "rb") as f:
        content = base64.b64encode(f.read()).decode("utf-8")
    ext = file_path.suffix.lower().lstrip(".")
    if ext == "pdf":
        mime = "application/pdf"
    elif ext in ("png", "jpg", "jpeg"):
        mime = f"image/{ext}"
    else:
        mime = "application/octet-stream"
    return f"data:{mime};base64,{content}"


def image_to_data_uri(image: Image.Image) -> str:
    """PIL 이미지를 base64 PNG data URI로 변환한다."""
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    content = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{content}"


def pdf_page_to_image(
    file_path: Path, page_idx: int, dpi: int = 400
) -> Image.Image:
    """
    PDF 특정 페이지를 PIL 이미지로 변환한다.

    Args:
        file_path: PDF 파일 경로
        page_idx: 페이지 인덱스 (0-based)
        dpi: 해상도 (기본 400)

    Returns:
        PIL Image
    """
    from pdf2image import convert_from_path
    from config import POPPLER_PATH

    images = convert_from_path(
        str(file_path),
        first_page=page_idx + 1,
        last_page=page_idx + 1,
        dpi=dpi,
        poppler_path=POPPLER_PATH,
    )
    return images[0]
```

---

### 5.1 `engines/base_engine.py` — OCR 인터페이스 확장 (변경)

> 현재: 110줄 / 변경 후: ~140줄 (+30줄)

**Why:** 기존 `extract_table(image)` / `extract_full_page(image)` 인터페이스는 pdfplumber 테이블 감지 후 AI로 내용을 추출하는 패턴. OCR 엔진은 PDF 파일을 직접 텍스트로 변환하는 다른 패턴이므로, 별도 OCR 메서드가 필요하다.

**추가할 데이터 클래스:**

```python
from dataclasses import dataclass, field


@dataclass
class OcrPageResult:
    """OCR 엔진의 페이지별 결과."""
    page_num: int
    text: str
    layout_details: list[dict] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
```

**BaseEngine 클래스에 추가할 멤버:**

```python
class BaseEngine(ABC):
    supports_image: bool = True
    supports_ocr: bool = False          # ← 신규: OCR 지원 여부

    # ... 기존 extract_table, extract_full_page, extract_table_from_data ...

    def ocr_document(
        self,
        file_path: Path,
        page_indices: list[int] | None = None,
    ) -> list[OcrPageResult]:
        """
        PDF/이미지 파일을 직접 OCR 처리한다.

        Args:
            file_path: PDF 또는 이미지 파일 경로
            page_indices: 처리할 페이지 인덱스 (0-based). None이면 전체.

        Returns:
            페이지별 OCR 결과 리스트

        Why: Z.ai/Mistral은 PDF를 직접 받아 처리할 수 있어
             이미지 변환 없이 원본 파일을 전송하는 것이 효율적.
             Tesseract는 내부에서 이미지 변환 후 처리.
        """
        raise NotImplementedError(
            f"{type(self).__name__}은(는) OCR을 지원하지 않습니다. "
            "supports_ocr=True인 엔진을 사용하세요."
        )

    def ocr_image(self, image: "Image.Image") -> OcrPageResult:
        """
        단일 PIL 이미지를 OCR 처리한다.

        Why: BOM 파이프라인의 영역 크롭(우측 55%, 하단 50%) 후
             크롭된 이미지를 OCR할 때 사용.
        """
        raise NotImplementedError(
            f"{type(self).__name__}은(는) 이미지 OCR을 지원하지 않습니다."
        )
```

**설계 결정:**
- `ocr_document()`: PDF 파일 직접 전송 (Z.ai/Mistral은 base64 data URI로 전송, Tesseract는 내부에서 이미지 변환)
- `ocr_image()`: 크롭된 이미지 처리 (BOM 2차/3차 시도 시 사용)
- `supports_ocr` 플래그로 엔진 능력 표시
- 기존 `extract_table()`, `extract_full_page()` 메서드 유지 — OCR 엔진도 표준 파이프라인에서 사용 가능

**호환성:** 기존 GeminiEngine, LocalEngine은 `supports_ocr=False`(기본값)이므로 변경 없음.

---

### 5.2 `engines/zai_engine.py` — Z.ai GLM-OCR 엔진 (신규)

> 원본 참조: ocr.py L628~682 (API 호출), L871~941 (응답 파싱)
> 예상 규모: ~160줄

**Why:** Z.ai GLM-OCR은 `layout_parsing` API로 문서 구조(테이블, 제목, 본문)를 인식하여 Markdown + layout_details를 반환한다. BOM 도면에서 테이블 영역을 자동 분리하는 `layout_details` 기능이 핵심 가치.

**Dependencies:** `zai-sdk` (pip install zai-sdk)

> ⚠️ 구현 동기화 (S1): 기술서 초안은 `zhipuai` SDK를 명세했으나, 실제 검증 결과
> `zhipuai`는 `open.bigmodel.cn`(본토) 전용 엔드포인트만 지원하여 해외 사용자에게
> `"Service Not Available For Overseas Users"` 오류 발생. `ocr.py`가 실제 사용하던
> `zai-sdk` (ZaiClient, api.z.ai 국제판)로 교체.

```python
"""
engines/zai_engine.py — Z.ai GLM-OCR 엔진

Why zai-sdk (not zhipuai):
    ocr.py가 실제로 사용하던 SDK는 'zai-sdk' (pip install zai-sdk)이며
    ZaiClient.layout_parsing.create(model, file: str(data URI))를 지원한다.
    zhipuai SDK는 open.bigmodel.cn(본토) 전용이며 해외 차단됨.

Dependencies: zai-sdk (pip install zai-sdk)
"""
import logging
import re
from pathlib import Path

from PIL import Image

from engines.base_engine import BaseEngine, OcrPageResult
from utils.ocr_utils import file_to_data_uri, image_to_data_uri, pdf_page_to_image

logger = logging.getLogger(__name__)


class ZaiEngine(BaseEngine):
    """Z.ai GLM-OCR 엔진 (zai-sdk 기반)."""

    supports_image = True
    supports_ocr = True

    def __init__(self, api_key: str, *, tracker=None):
        """
        Args:
            api_key: Z.ai API 키 (.env ZAI_API_KEY)
            tracker: UsageTracker 인스턴스 (선택)

        Why ZaiClient: ocr.py에서 실제 사용하던 z.ai 공식 SDK.
            layout_parsing.create(file=data_uri_str) 를 그대로 지원한다.
        """
        from zai import ZaiClient
        self._client = ZaiClient(api_key=api_key)
        self._tracker = tracker
        self._last_layout_details: list[dict] = []

    # ── OCR 인터페이스 ──

    def ocr_document(
        self,
        file_path: Path,
        page_indices: list[int] | None = None,
    ) -> list[OcrPageResult]:
        """
        PDF/이미지 파일을 Z.ai layout_parsing으로 OCR 처리한다.

        page_indices 미지정 시 전체 파일을 한 번에 전송 (가장 효율적).
        page_indices 지정 시 해당 페이지를 이미지로 변환 후 개별 처리.
        """
        file_path = Path(file_path)

        if page_indices is None:
            # 전체 파일 직접 전송 (효율적)
            data_uri = file_to_data_uri(file_path)  # ← ocr_utils 사용
            response = self._call_api(data_uri)
            text, layout = self._parse_response(response)
            self._last_layout_details = layout
            return [OcrPageResult(
                page_num=0, text=text, layout_details=layout,
            )]
        else:
            # 페이지별 이미지 변환 후 개별 처리
            results = []
            for idx in page_indices:
                image = pdf_page_to_image(file_path, idx, dpi=400)  # ← ocr_utils 사용
                result = self.ocr_image(image)
                result.page_num = idx
                results.append(result)
            return results

    def ocr_image(self, image: Image.Image) -> OcrPageResult:
        """PIL 이미지를 Z.ai OCR로 처리한다."""
        data_uri = image_to_data_uri(image)  # ← ocr_utils 사용
        response = self._call_api(data_uri)
        text, layout = self._parse_response(response)
        self._last_layout_details = layout
        return OcrPageResult(page_num=0, text=text, layout_details=layout)

    # ── 표준 파이프라인 호환 ──

    def extract_full_page(
        self, image: Image.Image, page_num: int
    ) -> tuple[str, int, int]:
        """표준 파이프라인 호환: 이미지 → OCR → Markdown 텍스트."""
        result = self.ocr_image(image)
        return (result.text, result.input_tokens, result.output_tokens)

    def extract_table(
        self, image: Image.Image, table_num: int
    ) -> tuple[str, int, int]:
        """표준 파이프라인 호환: 테이블 이미지 → OCR → 텍스트."""
        return self.extract_full_page(image, table_num)

    # ── 내부 메서드 ──

    def _call_api(self, data_uri: str) -> dict:
        """
        Z.ai layout_parsing API 호출.

        zai-sdk의 ZaiClient.layout_parsing.create()는
        file 파라미터로 data URI 문자열을 직접 받는다.
        (zhipuai SDK와 달리 bytes 변환 불필요)
        """
        try:
            response = self._client.layout_parsing.create(
                model="glm-ocr",
                file=data_uri,
            )
            # LayoutParsingResp → dict 변환
            if hasattr(response, 'model_dump'):
                return response.model_dump()
            elif hasattr(response, '__dict__'):
                return vars(response)
            return response if isinstance(response, dict) else {"raw": str(response)}
        except Exception as e:
            logger.error("Z.ai API 호출 실패: %s", e)
            raise

    def _parse_response(self, response: dict) -> tuple[str, list[dict]]:
        """
        Z.ai layout_parsing 응답에서 텍스트와 layout_details를 추출한다.

        응답 구조 (우선순위):
        1. response['md_results']       — Markdown 텍스트 (주 필드)
        2. response['pages'][n]['markdown'] — 페이지별 Markdown
        3. response['content']          — 평문 텍스트
        4. response['text']             — 평문 텍스트
        5. str(response)                — 최종 폴백
        """
        text = ""
        layout = []

        # ZaiClient 응답은 output 래퍼 없이 바로 필드가 노출되는 경우도 있음
        data = response.get("output", response)

        # 1순위: md_results
        if data.get("md_results"):
            text = data["md_results"]
        # 2순위: pages[].markdown
        elif data.get("pages"):
            parts = []
            for page in data["pages"]:
                md = page.get("markdown", page.get("text", ""))
                parts.append(md)
            text = "\n\n".join(parts)
        # 3순위: content / text
        elif data.get("content"):
            text = data["content"]
        elif data.get("text"):
            text = data["text"]
        else:
            text = str(data)
            logger.warning("Z.ai 응답에서 텍스트 필드를 찾을 수 없음, 전체 문자열 사용")

        # 이미지 링크 제거: ![](page=0,bbox=...)
        text = re.sub(r'!\[.*?\]\(.*?\)', '', text)

        # layout_details 추출
        layout = data.get("layout_details", [])

        return text, layout

    @property
    def last_layout_details(self) -> list[dict]:
        """마지막 OCR 호출의 layout_details (2차 추출 시 참조)."""
        return self._last_layout_details
```

**핵심 설계 포인트:**
1. `ocr_document()` — PDF 원본을 base64로 직접 전송 (이미지 변환 불필요, 최고 효율)
2. `ocr_image()` — 영역 크롭 이미지를 base64 PNG로 전송 (2차/3차 시도용)
3. `_last_layout_details` — Z.ai의 테이블 영역 데이터를 캐싱하여 `bom_extractor.py`에서 2차 추출 시 참조
4. `extract_full_page()` — 표준 파이프라인에서도 사용 가능 (OCR 엔진으로 Gemini 대체)
5. `_parse_response()` — 5단계 폴백 체인으로 다양한 응답 구조에 대응
6. **중복 제거(리뷰 🟡5,7):** base64 변환, PDF→이미지 변환은 `utils/ocr_utils.py` 공통 함수 사용

---

### 5.3 `engines/mistral_engine.py` — Mistral Pixtral OCR 엔진 (신규)

> 원본 참조: ocr.py L1647~1690 (Mistral API 호출)
> 예상 규모: ~140줄

**Why:** Mistral Pixtral OCR은 페이지별 Markdown을 반환하며, 파이프(`|`) 기반 테이블 포맷이 BOM 데이터 추출에 적합하다. Z.ai 실패 시 2차 폴백 엔진으로 사용.

**Dependencies:** `mistralai` (pip install mistralai)

```python
"""
engines/mistral_engine.py — Mistral Pixtral OCR 엔진

Why: Mistral OCR은 페이지별 Markdown을 반환하며,
     파이프(|) 기반 테이블 포맷팅이 우수하여
     Z.ai 실패 시 2차 폴백 엔진으로 사용한다.

Dependencies: mistralai (pip install mistralai)
"""
import base64
import io
import logging
from pathlib import Path

from PIL import Image

from engines.base_engine import BaseEngine, OcrPageResult
from utils.ocr_utils import file_to_data_uri, image_to_data_uri  # ← 리뷰 반영 🟡5

logger = logging.getLogger(__name__)


class MistralEngine(BaseEngine):
    """Mistral Pixtral OCR 엔진."""

    supports_image = True
    supports_ocr = True

    def __init__(self, api_key: str, *, model: str = "mistral-ocr-latest", tracker=None):
        """
        Args:
            api_key: Mistral API 키 (.env MISTRAL_API_KEY)
            model: OCR 모델명 (기본: mistral-ocr-latest)
            tracker: UsageTracker 인스턴스 (선택)
        """
        from mistralai import Mistral
        self._client = Mistral(api_key=api_key)
        self._model = model
        self._tracker = tracker

    # ── OCR 인터페이스 ──

    def ocr_document(
        self,
        file_path: Path,
        page_indices: list[int] | None = None,
    ) -> list[OcrPageResult]:
        """
        PDF/이미지 파일을 Mistral OCR로 처리한다.

        Mistral은 전체 파일을 처리하고 페이지별 결과를 반환한다.
        page_indices 지정 시 해당 페이지 결과만 필터링.
        """
        file_path = Path(file_path)
        data_uri = file_to_data_uri(file_path)  # ← ocr_utils 사용

        try:
            response = self._client.ocr.process(
                model=self._model,
                document={"type": "document_url", "document_url": data_uri},
            )
        except Exception as e:
            logger.error("Mistral OCR API 호출 실패: %s", e)
            raise

        results = []
        for i, page in enumerate(response.pages):
            if page_indices is not None and i not in page_indices:
                continue
            results.append(OcrPageResult(
                page_num=i,
                text=page.markdown,
                layout_details=[],
            ))

        return results

    def ocr_image(self, image: Image.Image) -> OcrPageResult:
        """PIL 이미지를 Mistral OCR로 처리한다."""
        data_uri = image_to_data_uri(image)  # ← ocr_utils 사용

        try:
            response = self._client.ocr.process(
                model=self._model,
                document={"type": "document_url", "document_url": data_uri},
            )
        except Exception as e:
            logger.error("Mistral OCR 이미지 처리 실패: %s", e)
            raise

        text = "\n\n".join(p.markdown for p in response.pages)
        return OcrPageResult(page_num=0, text=text)

    # ── 표준 파이프라인 호환 ──

    def extract_full_page(
        self, image: Image.Image, page_num: int
    ) -> tuple[str, int, int]:
        result = self.ocr_image(image)
        return (result.text, result.input_tokens, result.output_tokens)

    def extract_table(
        self, image: Image.Image, table_num: int
    ) -> tuple[str, int, int]:
        return self.extract_full_page(image, table_num)

    # ⚠️ 리뷰 반영 (🟡5): _file_to_data_uri, _image_to_data_uri 제거
    # → utils/ocr_utils.py의 공통 함수 사용 (상단 import 참조)
```

**ZaiEngine과의 차이:**
- Mistral은 `layout_details`를 반환하지 않음 → 2차 추출 시 불리
- Mistral은 페이지별 `.markdown` 필드로 결과를 분리하여 반환 → 멀티페이지 처리 편리
- **중복 제거(리뷰 🟡5):** base64 변환은 `utils/ocr_utils.py` 공통 함수 사용

---

### 5.4 `engines/tesseract_engine.py` — Tesseract 로컬 OCR 엔진 (신규)

> 원본 참조: ocr.py L1771~1810 (Tesseract 폴백)
> 예상 규모: ~130줄

**Why:** 무료/오프라인 OCR. API 키 없이 작동하며, 한국어+영문 동시 인식 가능. Z.ai/Mistral 대비 품질은 낮지만, 네트워크 불가 환경이나 비용 제한 시 사용.

**Dependencies:** `pytesseract` (pip install pytesseract), Tesseract-OCR 실행 파일 (시스템 설치)

```python
"""
engines/tesseract_engine.py — Tesseract 로컬 OCR 엔진

Why: 무료/오프라인 OCR 엔진. API 키 없이 동작하며
     한국어(kor)+영문(eng) 동시 인식을 지원한다.
     네트워크 불가 환경이나 비용 제한 시 폴백 엔진.

Dependencies: pytesseract, Tesseract-OCR 실행 파일
"""
import logging
from pathlib import Path

from PIL import Image

from engines.base_engine import BaseEngine, OcrPageResult

logger = logging.getLogger(__name__)


class TesseractEngine(BaseEngine):
    """Tesseract 로컬 OCR 엔진."""

    supports_image = True
    supports_ocr = True

    def __init__(self, *, tesseract_path: str | None = None, lang: str = "kor+eng"):
        """
        Args:
            tesseract_path: Tesseract 실행 파일 경로 (.env TESSERACT_PATH)
                            None이면 시스템 PATH에서 탐색
            lang: OCR 언어 (기본: kor+eng)
        """
        import pytesseract

        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
        self._pytesseract = pytesseract
        self._lang = lang

    # ── OCR 인터페이스 ──

    def ocr_document(
        self,
        file_path: Path,
        page_indices: list[int] | None = None,
    ) -> list[OcrPageResult]:
        """
        PDF 파일을 페이지별로 이미지 변환 후 Tesseract OCR 처리한다.

        Why: Tesseract는 이미지만 처리 가능하므로
             PDF→이미지 변환이 반드시 필요하다.
        """
        from pdf2image import convert_from_path
        from config import POPPLER_PATH

        images = convert_from_path(
            str(file_path),
            dpi=400,
            poppler_path=POPPLER_PATH,
        )

        results = []
        for i, img in enumerate(images):
            if page_indices is not None and i not in page_indices:
                continue
            result = self.ocr_image(img)
            result.page_num = i
            results.append(result)

        return results

    def ocr_image(self, image: Image.Image) -> OcrPageResult:
        """PIL 이미지를 Tesseract OCR로 처리한다."""
        try:
            text = self._pytesseract.image_to_string(
                image, lang=self._lang
            )
        except Exception as e:
            logger.error("Tesseract OCR 실패: %s", e)
            raise

        return OcrPageResult(page_num=0, text=text)

    # ── 표준 파이프라인 호환 ──

    def extract_full_page(
        self, image: Image.Image, page_num: int
    ) -> tuple[str, int, int]:
        result = self.ocr_image(image)
        return (result.text, 0, 0)  # Tesseract: 토큰 카운트 없음

    def extract_table(
        self, image: Image.Image, table_num: int
    ) -> tuple[str, int, int]:
        return self.extract_full_page(image, table_num)
```

**설계 결정:**
- Tesseract는 토큰 카운트가 없으므로 `input_tokens=0, output_tokens=0` 반환
- `layout_details`도 없음 — Tesseract는 순수 텍스트만 반환
- PDF→이미지 변환은 `pdf2image` + Poppler 사용 (기존 인프라 재사용)
- `_lang` 파라미터로 언어 설정 가능 (기본: `kor+eng` 한영 동시)

**ocr.py 결함 대응:**
- 문제 G 해결: Tesseract 경로를 `.env`에서 설정 (하드코딩 제거)
- 문제 A 해결: `except Exception as e`로 구체적 예외 처리 + logging

---

### 5.5 `extractors/bom_extractor.py` — BOM/LINE LIST 추출 상태머신 (신규)

> 원본 참조: ocr.py L1400~1536 (앵커-경계선 상태머신), L1252~1398 (3단계 테이블 추출)
> 예상 규모: ~450줄

**Why:** BOM 추출의 핵심 모듈. OCR 엔진이 반환한 원시 텍스트에서 BOM/LINE LIST 섹션을 상태머신으로 분리하고, 3단계 폴백으로 테이블 데이터를 추출한다. 추출 결과를 Phase 2 호환 JSON 섹션 형식으로 변환한다.

**Dependencies:** `parsers.bom_table_parser`, `presets.bom`

**§5.5-1. 데이터 클래스**

```python
"""
extractors/bom_extractor.py — BOM/LINE LIST 추출 상태머신

Why: OCR 텍스트에서 BOM/LINE LIST 데이터를 추출하는 핵심 모듈.
     ocr.py의 도메인 지식(앵커-경계선 패턴, 키워드 그룹)을
     ps-docparser 아키텍처에 맞게 신규 구현한다.

     ocr.py 결함 대응:
     - 문제 C(God Object): 추출 로직만 분리, 단일 책임
     - 문제 D(3중 중복 파싱): bom_table_parser.py 1곳에 통합 위임
     - 문제 E(3중 중복 분기): preset 키워드로 자동 라우팅
     - 문제 F(4중 중복 키워드): presets/bom.py 1곳에서 관리

Dependencies: extractors.bom_types, parsers.bom_table_parser, presets.bom, utils.ocr_utils
"""
import logging
import re
from pathlib import Path

from PIL import Image

# ⚠️ 리뷰 반영 (🔴1): 데이터 클래스를 bom_types.py에서 import (순환 import 방지)
from extractors.bom_types import BomSection, BomExtractionResult
# ⚠️ 리뷰 반영 (🟡7): PDF→이미지 변환을 ocr_utils에서 import (중복 제거)
from utils.ocr_utils import pdf_page_to_image

logger = logging.getLogger(__name__)

# 데이터 클래스는 extractors/bom_types.py에 정의 (§5.0-A 참조)
# BomSection, BomExtractionResult를 상단에서 import
```

**§5.5-2. HTML 전처리 (상태머신 입력 준비)**

```python
def _sanitize_html(text: str) -> str:
    """
    OCR 응답의 HTML 잔여물을 상태머신 입력용 텍스트로 정리한다.

    Why: Z.ai/Mistral OCR 응답에 <table>, <tr>, <td> 태그가
         남아 있을 수 있다. 상태머신은 파이프(|) 구분 텍스트를
         기대하므로 HTML 구조를 파이프로 변환한다.

    원본 참조: ocr.py L1416~1436 (HTML 전처리 5단계)
    """
    # Step 1: </tr> → 줄바꿈 (행 구분)
    text = re.sub(r'</tr[^>]*>', '\n', text, flags=re.IGNORECASE)

    # Step 2: </td><td> 또는 </th><th> → 파이프 (열 구분)
    text = re.sub(
        r'</t[dh]>\s*<t[dh][^>]*>', ' | ', text, flags=re.IGNORECASE
    )

    # Step 3: 나머지 HTML 태그 제거
    text = re.sub(r'<[^>]+>', ' ', text)

    # Step 4: HTML 엔티티 치환
    text = text.replace('&amp;', '&').replace('&#x27;', "'")
    text = re.sub(r'&[a-zA-Z]+;', '', text)
    text = re.sub(r'&#x[0-9a-fA-F]+;', '', text)

    # Step 5: 연속 공백 압축
    text = re.sub(r'[ \t]+', ' ', text)

    return text
```

**§5.5-3. 상태머신 핵심 — `extract_bom()`**

```python
def extract_bom(text: str, keywords: dict) -> BomExtractionResult:
    """
    OCR 텍스트에서 BOM/LINE LIST 데이터를 상태머신으로 추출한다.

    Args:
        text: OCR 엔진이 반환한 원시 텍스트 (Markdown/HTML 혼재 가능)
        keywords: presets/bom.py의 get_bom_keywords() 반환값

    Returns:
        BomExtractionResult: BOM/LINE LIST 섹션 리스트

    상태머신:
        IDLE     + 앵커 키워드 감지 → BOM_SCAN 또는 LL_SCAN
        *_SCAN   + 헤더 행 감지     → *_DATA
        *_DATA   + 킬 키워드       → IDLE (섹션 종료)
        *_DATA   + 빈 행 2연속     → IDLE (섹션 종료)
    """
    from parsers.bom_table_parser import parse_bom_rows, filter_noise_rows

    # 키워드 로딩
    anchor_bom = keywords.get("anchor_bom", [])
    anchor_ll = keywords.get("anchor_ll", [])
    header_a = keywords.get("bom_header_a", [])
    header_b = keywords.get("bom_header_b", [])
    header_c = keywords.get("bom_header_c", [])
    ll_header_a = keywords.get("ll_header_a", [])
    ll_header_b = keywords.get("ll_header_b", [])
    ll_header_c = keywords.get("ll_header_c", [])
    kill_kw = keywords.get("kill", [])
    noise_kw = keywords.get("noise_row", [])
    rev_markers = keywords.get("rev_markers", [])

    # HTML 전처리
    clean_text = _sanitize_html(text)
    lines = clean_text.split('\n')

    # 상태 변수
    state = "IDLE"           # IDLE | BOM_SCAN | BOM_DATA | LL_SCAN | LL_DATA
    blank_count = 0
    header_found = False
    current_rows: list[list[str]] = []
    current_headers: list[str] = []

    # 결과 수집
    bom_sections: list[BomSection] = []
    ll_sections: list[BomSection] = []

    def _flush_section():
        """현재 섹션을 결과에 저장하고 상태를 초기화한다."""
        nonlocal state, blank_count, header_found, current_rows, current_headers

        if current_rows:
            filtered = filter_noise_rows(current_rows, noise_kw)
            section = BomSection(
                section_type="bom" if state.startswith("BOM") else "line_list",
                headers=current_headers,
                rows=filtered,
                raw_row_count=len(current_rows),
            )
            if state.startswith("BOM"):
                bom_sections.append(section)
            else:
                ll_sections.append(section)

        state = "IDLE"
        blank_count = 0
        header_found = False
        current_rows = []
        current_headers = []

    def _is_bom_header(cells_upper: list[str]) -> bool:
        """BOM 헤더 행 판정: A ∧ B ∧ C 그룹 키워드 동시 존재."""
        joined = ' '.join(cells_upper)
        has_a = any(kw in joined for kw in header_a)
        has_b = any(kw in joined for kw in header_b)
        has_c = any(kw in joined for kw in header_c)
        return has_a and has_b and has_c

    def _is_ll_header(cells_upper: list[str]) -> bool:
        """LINE LIST 헤더 행 판정."""
        joined = ' '.join(cells_upper)
        has_a = any(kw in joined for kw in ll_header_a)
        has_bc = any(kw in joined for kw in ll_header_b + ll_header_c)
        return has_a or has_bc

    def _is_rev_header(cells_upper: list[str]) -> bool:
        """REV 헤더 행 판정 (3개 이상 REV 마커)."""
        joined = ' '.join(cells_upper)
        return sum(1 for m in rev_markers if m in joined) >= 3

    def _parse_cells(line: str) -> list[str]:
        """행에서 셀을 추출한다 (파이프 구분 우선, 공백 2+ 폴백)."""
        stripped = line.strip()
        if '|' in stripped and stripped.count('|') >= 2:
            cells = [c.strip() for c in stripped.split('|')]
            cells = [c for c in cells if c]  # 빈 경계 제거
        else:
            cells = [stripped] if stripped else []
        return cells

    # ── 상태머신 루프 ──
    for line in lines:
        line_stripped = line.strip()
        line_upper = line_stripped.upper()

        # ── 앵커 감지 (IDLE 상태에서만) ──
        if state == "IDLE":
            if any(kw in line_upper for kw in anchor_bom):
                state = "BOM_SCAN"
                blank_count = 0
                header_found = False
                continue
            if any(kw in line_upper for kw in anchor_ll):
                state = "LL_SCAN"
                blank_count = 0
                header_found = False
                continue

            # 앵커 없이 헤더 키워드만으로도 BOM 감지 (앵커 텍스트 없는 도면 대응)
            cells = _parse_cells(line)
            if cells:
                cells_upper = [c.upper() for c in cells]
                if _is_bom_header(cells_upper):
                    state = "BOM_DATA"
                    header_found = True
                    current_headers = cells
                    blank_count = 0
                    continue

        # ── 킬 키워드 감지 (활성 상태에서) ──
        if state != "IDLE":
            if any(kw in line_upper for kw in kill_kw):
                _flush_section()
                continue

        # ── 빈 행 처리 ──
        cells = _parse_cells(line)

        if not cells or all(c.strip() == '' for c in cells):
            if header_found:
                blank_count += 1
                if blank_count >= 2:
                    _flush_section()
            continue
        else:
            blank_count = 0

        # ── SCAN 상태: 헤더 탐색 ──
        if state in ("BOM_SCAN", "LL_SCAN"):
            cells_upper = [c.upper() for c in cells]

            if state == "BOM_SCAN" and _is_bom_header(cells_upper):
                state = "BOM_DATA"
                header_found = True
                current_headers = cells
                continue
            elif state == "LL_SCAN" and _is_ll_header(cells_upper):
                state = "LL_DATA"
                header_found = True
                current_headers = cells
                continue

        # ── DATA 상태: 데이터 수집 ──
        if state in ("BOM_DATA", "LL_DATA"):
            cells_upper = [c.upper() for c in cells]

            # REV 헤더 감지 → 섹션 종료
            if _is_rev_header(cells_upper):
                _flush_section()
                continue

            # 반복 헤더 건너뛰기 (멀티페이지 BOM에서 헤더 반복)
            if header_found and _is_bom_header(cells_upper):
                continue

            # 구분선 건너뛰기 (---+--- 패턴)
            if all(re.match(r'^[-:= ]+$', c) for c in cells if c):
                continue

            current_rows.append(cells)

    # 루프 종료 후 잔여 섹션 플러시
    if state != "IDLE":
        _flush_section()

    return BomExtractionResult(
        bom_sections=bom_sections,
        line_list_sections=ll_sections,
        raw_text=text,
    )
```

**§5.5-4. 3단계 테이블 추출 폴백 — `extract_bom_tables()`**

```python
def extract_bom_tables(
    text: str,
    keywords: dict,
    layout_details: list[dict] | None = None,
) -> BomExtractionResult:
    """
    3단계 폴백으로 BOM 테이블을 추출한다.

    원본 참조: ocr.py L1252~1398 (3단계 폴백 전략)

    단계 1: HTML <table> 기반 추출
        → OCR 엔진이 구조화된 <table>을 반환한 경우
    단계 2: layout_details 기반 추출
        → Z.ai 엔진의 테이블 영역 데이터 활용
    단계 3: 상태머신 기반 추출 (extract_bom)
        → Markdown 파이프 + 공백 구분 텍스트

    Args:
        text: OCR 원시 텍스트
        keywords: presets/bom.py 키워드
        layout_details: Z.ai layout_details (선택)

    Returns:
        BomExtractionResult
    """
    from parsers.bom_table_parser import parse_html_bom_tables

    # 단계 1: HTML <table> 기반 추출
    html_result = parse_html_bom_tables(text, keywords)
    if html_result.has_bom:
        logger.info("BOM 추출: HTML <table> 기반 성공 (%d행)", html_result.total_bom_rows)
        return html_result

    # 단계 2: layout_details 기반 추출
    if layout_details:
        for item in layout_details:
            if item.get("label") == "table":
                content = item.get("content", "")
                ld_result = parse_html_bom_tables(content, keywords)
                if ld_result.has_bom:
                    logger.info("BOM 추출: layout_details 기반 성공 (%d행)", ld_result.total_bom_rows)
                    return ld_result

    # 단계 3: 상태머신 기반 추출 (Markdown 파이프 + 공백)
    sm_result = extract_bom(text, keywords)
    if sm_result.has_bom:
        logger.info("BOM 추출: 상태머신 기반 성공 (%d행)", sm_result.total_bom_rows)
    else:
        logger.warning("BOM 추출: 3단계 모두 실패")
    return sm_result
```

**§5.5-5. OCR 재시도 오케스트레이션 — `extract_bom_with_retry()`**

```python
def extract_bom_with_retry(
    engine: "BaseEngine",
    file_path: Path,
    keywords: dict,
    image_settings: dict,
    page_indices: list[int] | None = None,
) -> BomExtractionResult:
    """
    3단계 OCR 재시도로 BOM/LINE LIST를 추출한다.

    원본 참조: ocr.py L2034~2056 (2차 OCR 폴백)

    1차: 전체 페이지 OCR → extract_bom_tables()
    2차: 우측 55% 크롭 OCR → extract_bom() (BOM 복구)
    3차: 하단 50% 고해상도 OCR → extract_bom() (LINE LIST 복구)

    Args:
        engine: OCR 엔진 (supports_ocr=True 필수)
        file_path: PDF/이미지 파일 경로
        keywords: presets/bom.py 키워드
        image_settings: presets/bom.py 이미지 설정
        page_indices: 처리할 페이지 인덱스 (None=전체)

    Returns:
        BomExtractionResult (3차까지 누적)
    """
    default_dpi = image_settings.get("default_dpi", 400)
    retry_dpi = image_settings.get("retry_dpi", 600)
    bom_crop_left = image_settings.get("bom_crop_left_ratio", 0.45)
    ll_crop_top = image_settings.get("ll_crop_top_ratio", 0.50)

    # ── 1차: 전체 페이지 OCR ──
    print("   🔍 1차 OCR: 전체 페이지 처리 중...")
    ocr_results = engine.ocr_document(file_path, page_indices)
    full_text = "\n\n".join(r.text for r in ocr_results)
    layout = ocr_results[0].layout_details if ocr_results else []

    result = extract_bom_tables(full_text, keywords, layout_details=layout)
    result.raw_text = full_text
    result.ocr_engine = type(engine).__name__

    # ── 2차: 우측 55% 크롭 (BOM 복구) ──
    if not result.has_bom:
        print("   🔍 2차 OCR: 우측 55% 크롭 (BOM 영역)...")
        try:
            for ocr_r in ocr_results:
                page_img = pdf_page_to_image(file_path, ocr_r.page_num, default_dpi)  # ← ocr_utils 사용
                w, h = page_img.size
                cropped = page_img.crop((int(w * bom_crop_left), 0, w, h))
                crop_result = engine.ocr_image(cropped)
                bom2 = extract_bom(crop_result.text, keywords)
                result.bom_sections.extend(bom2.bom_sections)
        except Exception as e:
            logger.warning("2차 OCR 크롭 실패: %s", e)

    # ── 3차: 하단 50% 고해상도 (LINE LIST 복구) ──
    if not result.has_line_list:
        print("   🔍 3차 OCR: 하단 50% 고해상도 크롭 (LINE LIST 영역)...")
        try:
            for ocr_r in ocr_results:
                page_img = pdf_page_to_image(file_path, ocr_r.page_num, retry_dpi)  # ← ocr_utils 사용
                w, h = page_img.size
                cropped = page_img.crop((0, int(h * ll_crop_top), w, h))
                crop_result = engine.ocr_image(cropped)
                ll3 = extract_bom(crop_result.text, keywords)
                result.line_list_sections.extend(ll3.line_list_sections)
        except Exception as e:
            logger.warning("3차 OCR 크롭 실패: %s", e)

    # 결과 로깅
    print(f"   ✅ BOM: {result.total_bom_rows}행 / LINE LIST: {result.total_ll_rows}행")
    return result


    # ⚠️ 리뷰 반영 (🟡7): _get_page_image() 제거
    # → utils/ocr_utils.py의 pdf_page_to_image() 공통 함수 사용 (상단 import 참조)
```

**§5.5-6. Phase 2 JSON 호환 변환 — `to_sections()`**

```python
def to_sections(result: BomExtractionResult) -> list[dict]:
    """
    BomExtractionResult를 Phase 2 출력 호환 JSON 섹션 리스트로 변환한다.

    Why: 기존 ExcelExporter(_build_generic_sheet)를 무수정으로 재사용하기 위해
         Phase 2 parse_markdown() 출력과 동일한 구조를 생성한다.

    Phase 2 출력 JSON 구조:
    {
        "section_id": "BOM-1",
        "title": "BILL OF MATERIALS",
        "tables": [{
            "table_id": "T-BOM-1-01",
            "type": "BOM_자재",
            "headers": ["S/N", "SIZE", ...],
            "rows": [{"S/N": "1", "SIZE": "100A", ...}, ...],
        }]
    }
    """
    sections = []

    for i, bom in enumerate(result.bom_sections, 1):
        if not bom.rows:
            continue
        rows_as_dicts = []
        for row in bom.rows:
            row_dict = {}
            for j, cell in enumerate(row):
                key = bom.headers[j] if j < len(bom.headers) else f"열{j+1}"
                row_dict[key] = cell
            rows_as_dicts.append(row_dict)

        sections.append({
            "section_id": f"BOM-{i}",
            "title": f"BILL OF MATERIALS #{i}",
            "department": None,
            "chapter": None,
            "page": bom.source_page,
            "clean_text": "",
            "tables": [{
                "table_id": f"T-BOM-{i}-01",
                "type": "BOM_자재",
                "headers": bom.headers,
                "rows": rows_as_dicts,
                "notes_in_table": [],
                "raw_row_count": bom.raw_row_count,
                "parsed_row_count": bom.parsed_row_count,
            }],
            "notes": [],
            "conditions": [],
            "cross_references": [],
            "revision_year": None,
            "unit_basis": None,
        })

    for i, ll in enumerate(result.line_list_sections, 1):
        if not ll.rows:
            continue
        rows_as_dicts = []
        for row in ll.rows:
            row_dict = {}
            for j, cell in enumerate(row):
                key = ll.headers[j] if j < len(ll.headers) else f"열{j+1}"
                row_dict[key] = cell
            rows_as_dicts.append(row_dict)

        sections.append({
            "section_id": f"LL-{i}",
            "title": f"LINE LIST #{i}",
            "department": None,
            "chapter": None,
            "page": ll.source_page,
            "clean_text": "",
            "tables": [{
                "table_id": f"T-LL-{i}-01",
                "type": "BOM_LINE_LIST",
                "headers": ll.headers,
                "rows": rows_as_dicts,
                "notes_in_table": [],
                "raw_row_count": ll.raw_row_count,
                "parsed_row_count": ll.parsed_row_count,
            }],
            "notes": [],
            "conditions": [],
            "cross_references": [],
            "revision_year": None,
            "unit_basis": None,
        })

    return sections
```

---

### 5.6 `parsers/bom_table_parser.py` — BOM 테이블 파싱 통합 (신규)

> 원본 참조: ocr.py L692~709 (HTML 파싱), L1131~1166 (텍스트 파싱), L796~868 (한국어 테이블)
> 예상 규모: ~280줄

**Why:** ocr.py에서 3곳에 중복된 테이블 파싱 로직을 **1개 모듈**로 통합한다. HTML, Markdown 파이프, 공백 구분 3가지 형식을 자동 감지하여 2D 배열로 변환한다.

**ocr.py 결함 대응:**
- 문제 D 해결: HTML 파싱 3중 중복 → `parse_html_bom_tables()` 1개로 통합
- 문제 E 해결: 분기 3중 복붙 → `parse_bom_table()` 자동 형식 감지

```python
"""
parsers/bom_table_parser.py — BOM 테이블 파싱 (HTML/Markdown/공백 통합)

Why: ocr.py에서 3곳에 중복된 HTML 파싱, 2곳에 중복된 Markdown 파싱을
     1개 모듈로 통합한다. 3가지 형식을 자동 감지하여 2D 배열로 변환.

     ocr.py 결함 대응:
     - 문제 D: HTML <table> 파싱 3중 중복 → parse_html_bom_tables() 1개
     - 문제 E: 분기 3중 복붙 → parse_bom_table() 자동 형식 감지
"""
import re
import logging
from bs4 import BeautifulSoup

# ⚠️ 리뷰 반영 (🔴1): bom_extractor가 아닌 bom_types에서 import (순환 import 방지)
from extractors.bom_types import BomSection, BomExtractionResult

logger = logging.getLogger(__name__)
```

**§5.6-1. HTML <table> 기반 파싱**

```python
def parse_html_bom_tables(
    text: str,
    keywords: dict,
) -> BomExtractionResult:
    """
    텍스트에서 HTML <table> 블록을 추출하고 BOM 여부를 판정한다.

    원본 참조: ocr.py L1330~1350 (pd.read_html 기반)
    변경점: pandas 의존 제거 → BeautifulSoup + 기존 expand_table() 재사용

    Process:
    1. 정규식으로 <table>...</table> 블록 추출
    2. 각 블록에 대해 BOM 헤더 키워드 A∧B∧C 검증
    3. ⚠️ 구현 동기화 (S2): LINE LIST 전용 키워드 경로 추가
    4. 블랙리스트 키워드 체크
    5. expand_table() → 타이틀 행 스킵 → 실제 헤더/데이터 분리
    6. ⚠️ 구현 동기화 (S3): colspan 타이틀 행 자동 감지·스킵
    7. BOM/LINE LIST 분류 (타이틀 텍스트 + is_line_list 플래그 이중 판정)
    8. 행 필터링 (노이즈 제거)
    """
    from parsers.table_parser import expand_table  # 기존 rowspan/colspan 처리 재사용

    header_a  = keywords.get("bom_header_a", [])
    header_b  = keywords.get("bom_header_b", [])
    header_c  = keywords.get("bom_header_c", [])
    ll_hdr_a  = [kw.upper() for kw in keywords.get("ll_header_a", [])]
    ll_hdr_b  = [kw.upper() for kw in keywords.get("ll_header_b", [])]
    ll_hdr_c  = [kw.upper() for kw in keywords.get("ll_header_c", [])]
    blacklist = keywords.get("blacklist", [])
    noise_kw  = keywords.get("noise_row", [])

    # HTML <table> 블록 추출
    table_pattern = re.compile(
        r'<table[^>]*>.*?</table>', re.DOTALL | re.IGNORECASE
    )
    html_blocks = table_pattern.findall(text)

    bom_sections = []
    ll_sections  = []

    for html_block in html_blocks:
        block_upper = html_block.upper()

        # ── 블록 타입 판정 ────────────────────────────────────────
        # 경로 1: BOM 키워드 A∧B∧C
        is_bom = (
            any(kw.upper() in block_upper for kw in header_a)
            and any(kw.upper() in block_upper for kw in header_b)
            and any(kw.upper() in block_upper for kw in header_c)
        )
        # ⚠️ 구현 동기화 (S2): LINE LIST 전용 키워드 경로 추가
        # Why: LINE LIST 블록에는 WT/QTY 등 BOM 전용 키워드가 없으므로
        #      별도 경로가 없으면 항상 스킵됨 (구현 중 발견된 버그).
        is_line_list = (
            any(kw in block_upper for kw in ll_hdr_a)
            and any(kw in block_upper for kw in ll_hdr_b)
            and any(kw in block_upper for kw in ll_hdr_c)
        )

        if not (is_bom or is_line_list):
            continue

        # 블랙리스트 체크 (BOM/LINE LIST 공통)
        if any(kw.upper() in block_upper for kw in blacklist):
            continue

        # expand_table()로 2D 배열 변환
        try:
            soup = BeautifulSoup(html_block, "html.parser")
            table_tag = soup.find("table")
            if not table_tag:
                continue
            grid = expand_table(table_tag)
        except Exception as e:
            logger.warning("HTML 테이블 파싱 실패: %s", e)
            continue

        if len(grid) < 2:
            continue

        # ── ⚠️ 구현 동기화 (S3): 타이틀 행 스킵 로직 ──────────────────────
        # Z.ai는 BOM 제목(`BILL OF MATERIALS`, `LINE LIST`)을 colspan=N 단일 셀로 반환.
        # expand_table() 처리 후 해당 행의 모든 셀이 같은 값으로 채워진다.
        # → 이 행은 섹션 제목이므로 건너뛰고 다음 행을 실제 컬럼 헤더로 사용한다.
        #
        # 초기 구현은 이 행을 헤더로 오인하여 JSON의 headers 필드가
        # ["BILL OF MATERIALS", "BILL OF MATERIALS", ...] 로 오출력됨.
        section_title = None
        header_start = 0

        for i, row in enumerate(grid):
            non_empty = [str(c).strip() for c in row if str(c).strip()]
            unique_vals = set(non_empty)
            next_row_len = len(grid[i + 1]) if i + 1 < len(grid) else 0

            # 판정: unique 값이 1개(=colspan 복제) AND 다음 행이 더 많은 고유 열 보유
            is_title_row = (
                len(unique_vals) == 1
                and next_row_len > len(unique_vals)
            )
            if is_title_row:
                section_title = list(unique_vals)[0]
                header_start = i + 1
                logger.debug("타이틀 행 감지 및 스킵: '%s' (grid[%d])", section_title, i)
                break

        effective_grid = grid[header_start:]
        if len(effective_grid) < 2:
            continue

        headers = effective_grid[0]
        rows = effective_grid[1:]

        # 노이즈 행 필터링
        filtered = filter_noise_rows(rows, noise_kw)

        # ── LINE LIST vs BOM 분류 ──────────────────────────────────
        # 우선순위: ① 타이틀 행 텍스트 → ② 블록 키워드 판정(is_line_list)
        title_upper = (section_title or "").upper()
        classify_as_ll = (
            "LINE LIST" in title_upper
            or "LINELIST" in title_upper
            or is_line_list  # 타이틀 없을 때 키워드 경로 플래그 활용
        )
        if classify_as_ll:
            ll_sections.append(BomSection(
                section_type="line_list",
                headers=headers,
                rows=filtered,
                raw_row_count=len(rows),
            ))
            logger.info("LINE LIST 테이블 감지: %d행", len(filtered))
        else:
            bom_sections.append(BomSection(
                section_type="bom",
                headers=headers,
                rows=filtered,
                raw_row_count=len(rows),
            ))
            logger.info("BOM 테이블 감지: %d행", len(filtered))

    return BomExtractionResult(
        bom_sections=bom_sections,
        line_list_sections=ll_sections,
    )
```

**§5.6-2. Markdown 파이프 파싱**

```python
def parse_markdown_pipe_table(text: str) -> list[list[str]]:
    """
    Markdown 파이프(|) 형식 테이블을 2D 배열로 파싱한다.

    원본 참조: ocr.py L810~829 (파이프 기반 파싱)

    입력 예시:
        | S/N | SIZE | MAT'L | Q'TY |
        |-----|------|-------|------|
        | 1   | 100A | SS304 | 2    |

    Returns:
        2D 배열 (헤더 포함), 테이블이 없으면 빈 리스트
    """
    rows = []
    for line in text.split('\n'):
        line = line.strip()
        if '|' not in line or line.count('|') < 2:
            continue

        cells = [c.strip() for c in line.split('|')]
        # 양쪽 빈 경계 제거
        if cells and cells[0] == '':
            cells = cells[1:]
        if cells and cells[-1] == '':
            cells = cells[:-1]

        # 구분선 건너뛰기 (---|---)
        if all(re.match(r'^[-:= ]+$', c) for c in cells if c):
            continue

        if cells:
            rows.append(cells)

    return rows
```

**§5.6-3. 공백 구분 파싱**

```python
def parse_whitespace_table(text: str) -> list[list[str]]:
    """
    공백 2개 이상으로 구분된 테이블을 2D 배열로 파싱한다.

    원본 참조: ocr.py L831~852 (공백 기반 파싱 + 열 수 보정)

    입력 예시:
        S/N  SIZE   MAT'L    Q'TY
        1    100A   SS304    2
        2    80A    CS       4
    """
    rows = []
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue

        cells = re.split(r'\s{2,}', line)
        if len(cells) >= 3:
            rows.append(cells)

    return rows
```

**§5.6-4. 열 수 정규화**

```python
def normalize_columns(
    rows: list[list[str]],
    *,
    reference_col_count: int | None = None,
) -> list[list[str]]:
    """
    열 수를 정규화한다.

    원본 참조: ocr.py L854~868 (패딩) + L831~852 (인접 셀 병합)

    - 짧은 행: 빈 셀로 패딩
    - 긴 행: 인접 최소 길이 셀 병합 (OCR 과분할 보정)
    """
    if not rows:
        return rows

    target = reference_col_count or max(len(r) for r in rows)
    result = []

    for row in rows:
        if len(row) == target:
            result.append(row)
        elif len(row) < target:
            # 패딩
            result.append(row + [''] * (target - len(row)))
        else:
            # 인접 최소 셀 병합
            merged = list(row)
            while len(merged) > target:
                # 인접 두 셀 합산 길이가 가장 짧은 위치 찾기
                min_len = float('inf')
                min_idx = 0
                for i in range(len(merged) - 1):
                    combined = len(merged[i]) + len(merged[i + 1])
                    if combined < min_len:
                        min_len = combined
                        min_idx = i
                # 병합
                merged[min_idx] = merged[min_idx] + ' ' + merged[min_idx + 1]
                merged.pop(min_idx + 1)
            result.append(merged)

    return result
```

**§5.6-5. 노이즈 행 필터링**

```python
def filter_noise_rows(
    rows: list[list[str]],
    noise_keywords: list[str],
) -> list[list[str]]:
    """
    노이즈 행을 필터링한다.

    원본 참조: ocr.py L1924~1936 (row_noise_keywords)

    필터 기준:
    1. 킬/노이즈 키워드 포함 행 제거
    2. 완전 빈 행 제거
    3. 모든 셀이 동일한 행 제거 (OCR 아티팩트)
    """
    result = []
    for row in rows:
        joined_upper = ' '.join(str(c) for c in row).upper()

        # 노이즈 키워드 체크
        if any(kw.upper() in joined_upper for kw in noise_keywords):
            continue

        # 완전 빈 행 체크
        if all(not str(c).strip() for c in row):
            continue

        # 동일 셀 행 체크 (OCR 아티팩트)
        non_empty = [c for c in row if str(c).strip()]
        if len(non_empty) > 1 and len(set(str(c).strip() for c in non_empty)) == 1:
            continue

        result.append(row)
    return result
```

**§5.6-6. 통합 파싱 함수**

```python
def parse_bom_rows(text: str) -> list[list[str]]:
    """
    텍스트를 자동 감지하여 BOM 행으로 파싱한다.

    자동 감지 우선순위:
    1. Markdown 파이프 (|) 형식
    2. 공백 2+ 구분 형식
    """
    # 1차: Markdown 파이프
    rows = parse_markdown_pipe_table(text)
    if rows:
        return normalize_columns(rows)

    # 2차: 공백 구분
    rows = parse_whitespace_table(text)
    if rows:
        return normalize_columns(rows)

    return []
```

---

### 5.7 `presets/bom.py` — BOM 프리셋 (신규)

> 예상 규모: ~120줄

**Why:** ocr.py에 4곳에 산재한 키워드 리스트를 **1곳으로 통합**한다. `pumsem.py`, `estimate.py`와 동일한 인터페이스(`get_*()` 함수)를 제공한다.

**ocr.py 결함 대응:**
- 문제 F 해결: 4중 중복 키워드 → BOM_KEYWORDS 1곳에서 관리

```python
"""
presets/bom.py — BOM(Bill of Materials) 프리셋

Why: ocr.py에 4곳에 산재한 BOM 키워드를 1곳으로 통합한다.
     pumsem.py, estimate.py와 동일한 인터페이스(get_*() 함수)를 제공.

     키워드 출처:
     - ocr.py L1262~1264 (BOM_MUST_HAVE 그룹 A/B/C)
     - ocr.py L1267~1271 (blacklist_keywords)
     - ocr.py L1291~1300 (_clean_bom_dataframe 인라인)
     - ocr.py L1452~1458 (KILL_KEYWORDS)
     - ocr.py L1924~1936 (row_noise_keywords)
     → 4곳을 통합하여 동기화 문제를 원천 해결
"""

# ── Phase 1: 부문명 (BOM 문서에 부문 구분 없음) ──
DIVISION_NAMES = None


# ── BOM 키워드 체계 ──
BOM_KEYWORDS = {
    # BOM 헤더 감지 (3그룹 AND 조건: A ∧ B ∧ C 모두 충족 필수)
    # 원본: ocr.py L1262~1264
    "bom_header_a": ["S/N", "SN", "MARK", "NO", "NO."],
    "bom_header_b": ["SIZE", "SPEC", "SPECIFICATION"],
    "bom_header_c": ["Q'TY", "QTY", "QUANTITY", "WT", "WEIGHT", "WT(KG)"],

    # LINE LIST 헤더 감지
    # 원본: ocr.py L1557~1562
    "ll_header_a": ["LINE NO", "LINE NO."],
    "ll_header_b": ["SN", "S/N"],
    "ll_header_c": ["ITEM", "REMARKS"],

    # 앵커 키워드 (섹션 시작 감지)
    "anchor_bom": ["BILL OF MATERIALS", "BILL OF MATERIAL"],
    "anchor_ll": ["LINE LIST"],

    # 블랙리스트 (BOM이 아닌 테이블 제외)
    # 원본: ocr.py L1267~1271
    "blacklist": [
        "CLIENT:", "CLIENT：",
        "CONTRACTOR:", "CONTRACTOR：",
        "PROJECT:", "PROJECT：",
        "TITLE:", "TITLE：",
        "DRAWING NO", "SCALE", "SUPPORT DWG", "DWG LIST",
    ],

    # 킬 키워드 (활성 섹션 즉시 종료)
    # 원본: ocr.py L1452~1458 통합
    "kill": [
        "TOTAL WEIGHT", "TOTAL:",
        "CLIENT:", "CLIENT：", "CONTRACTOR:", "CONTRACTOR：",
        "PROJECT:", "PROJECT：", "TITLE:", "TITLE：",
        "DRAWING NO", "SCALE", "DESCRIPTION",
        "YOUNGPOONG", "YOUNG POONG", "KERYCO",
        "ALL IN ONE", "NICKEL REFINERY",
        "GE PROCESS", "PROCESS REVISION",
    ],

    # 노이즈 행 키워드 (행 레벨 필터)
    # 원본: ocr.py L1291~1300 + L1924~1936 통합
    "noise_row": [
        "DRW'D", "CHK'D", "APP'D",
        "DETAIL DRAWINGS", "PIPE SUPPORT",
        "SUPPORT DWG", "DWG LIST",
    ],

    # REV 헤더 감지 마커 (3개 이상이면 REV 행)
    # 원본: ocr.py L1307~1310
    "rev_markers": ["REV", "DATE", "DESCRIPTION", "DRW'D"],
}

# BOM 전용 키워드 (BOM vs LINE LIST 구분용)
BOM_ONLY_KEYWORDS = ["WT(KG)", "WT (KG)", "WEIGHT", "MAT'L", "MATERIAL"]


# ── 한국어 BOM 테이블 키워드 ──
# 원본: ocr.py L722~742
KOREAN_TABLE_HEADERS = [
    "품목", "품명", "규격", "치수", "수량", "단가",
    "공급가액", "재질", "중량", "단위",
]

KOREAN_ITEM_PATTERNS = [
    r'H\s*형\s*강', r'각\s*파\s*이\s*프', r'원\s*파\s*이\s*프',
    r'철\s*근', r'철\s*판', r'앵\s*글', r'채\s*널',
]


# ── 이미지 전처리 설정 ──
IMAGE_SETTINGS = {
    "default_dpi": 400,              # 1차 OCR 해상도
    "retry_dpi": 600,                # 재시도 해상도
    "bom_crop_left_ratio": 0.45,     # 우측 55% (좌 45% 제거)
    "ll_crop_top_ratio": 0.50,       # 하단 50% (상 50% 제거)
}


# ── 테이블 분류 키워드 (Phase 2 table_parser 호환) ──
TABLE_TYPE_KEYWORDS = {
    "BOM_자재": ["S/N", "SIZE", "QTY", "WEIGHT", "MAT'L"],
    "BOM_LINE_LIST": ["LINE NO", "ITEM", "REMARKS"],
}


# ── 공개 인터페이스 (pumsem.py, estimate.py와 동일 패턴) ──

def get_bom_keywords() -> dict:
    """BOM 추출 키워드 전체를 반환한다."""
    return BOM_KEYWORDS


def get_image_settings() -> dict:
    """이미지 전처리 설정을 반환한다."""
    return IMAGE_SETTINGS


def get_table_type_keywords() -> dict:
    """Phase 2 table_parser 호환 테이블 분류 키워드."""
    return TABLE_TYPE_KEYWORDS


def get_division_names() -> str | None:
    """Phase 1 부문명 (BOM은 부문 구분 없음)."""
    return DIVISION_NAMES


def get_excel_config() -> dict | None:
    """
    Excel 출력 커스텀 설정.

    ⚠️ 리뷰 반영 (🟡4): estimate.py에 get_excel_config()이 있으므로
       인터페이스 일관성을 위해 추가. BOM은 현재 커스텀 시트 레이아웃이
       불필요하므로 None 반환 → ExcelExporter._build_generic_sheet() 사용.

    향후 BOM 전용 시트 포맷(고정 열 너비, 색상 등)이 필요하면
    estimate.py처럼 dict 반환으로 확장한다.
    """
    return None
```

---

### 5.8 `extractors/table_utils.py` — K2 + K3 테이블 감지 개선 (변경)

> 참조: kordoc `cluster-detector.ts` (K2), `line-detector.ts` (K3), MIT License
> 현재: 149줄 / 변경 후: ~389줄 (+240줄)

**Why:** 현재 `detect_tables()`는 pdfplumber `find_tables()`에만 의존한다. 선이 없거나 얇은 테이블은 감지 실패한다. kordoc의 두 알고리즘으로 감지율을 개선한다:
- K2: 텍스트 정렬 패턴 기반 선 없는 테이블 감지 (폴백)
- K3: 선 두께 비례 동적 허용 오차 (기존 find_tables 개선)

**§5.8-1. K3: 동적 허용 오차 계산**

```python
# 알고리즘 참조: kordoc (https://github.com/chrisryugj/kordoc)
# Copyright (c) chrisryugj, MIT License

# ── 상수 ──
VERTEX_MERGE_FACTOR = 4       # kordoc line-detector.ts
MIN_COORD_MERGE_TOL = 8       # kordoc line-detector.ts
DEFAULT_SNAP_TOLERANCE = 3    # pdfplumber 기본값


def calculate_dynamic_tolerance(page) -> dict:
    """
    페이지의 선 두께를 분석하여 동적 허용 오차를 계산한다.

    Why: pdfplumber의 snap_tolerance=3, join_tolerance=3은 고정 상수로,
         선이 두꺼운 문서(건설 도면 등)에서는 테이블 감지에 실패한다.
         kordoc의 line-detector.ts 알고리즘을 참조하여
         선 두께에 비례하는 동적 허용 오차를 계산한다.

    Args:
        page: pdfplumber.Page 객체

    Returns:
        dict: {
            "snap_tolerance": float,
            "join_tolerance": float,
            "intersection_tolerance": float,
        }
    """
    lines = page.lines or []
    rects = page.rects or []

    if not lines and not rects:
        return {
            "snap_tolerance": DEFAULT_SNAP_TOLERANCE,
            "join_tolerance": DEFAULT_SNAP_TOLERANCE,
            "intersection_tolerance": DEFAULT_SNAP_TOLERANCE,
        }

    # 수평/수직 선의 두께 수집
    h_widths = []
    v_widths = []

    for line in lines:
        lw = line.get("lineWidth", line.get("stroke_width", 1))
        if lw is None:
            lw = 1
        # 수평선: y0 ≈ y1
        if abs(line.get("y0", 0) - line.get("y1", 0)) < 2:
            h_widths.append(lw)
        else:
            v_widths.append(lw)

    max_h = max(h_widths) if h_widths else 1
    max_v = max(v_widths) if v_widths else 1

    # kordoc 공식
    vertex_radius = max(max_h, max_v) * VERTEX_MERGE_FACTOR
    coord_merge_tol = max(MIN_COORD_MERGE_TOL, vertex_radius)

    return {
        "snap_tolerance": coord_merge_tol / 2,
        "join_tolerance": coord_merge_tol,
        "intersection_tolerance": coord_merge_tol,
    }
```

**§5.8-2. K2: 텍스트 정렬 기반 선 없는 테이블 감지**

```python
def detect_tables_by_text_alignment(page) -> list[dict]:
    """
    선 없는 테이블을 텍스트 정렬 패턴으로 감지한다.
    pdfplumber find_tables() 실패 시 폴백으로 사용.

    Why: 일부 PDF(특히 OCR 재구성 문서)는 테이블에 선이 없다.
         pdfplumber는 선 기반 감지가 기본이므로 이런 테이블을 놓친다.
         kordoc의 cluster-detector.ts 알고리즘을 참조하여
         텍스트 아이템의 좌표 정렬 패턴으로 테이블을 감지한다.

    Algorithm (kordoc cluster-detector 참조):
    1. page.extract_words() → 텍스트 아이템 리스트
    2. Y좌표 행 그룹핑 (Y_TOL = 3pt 허용)
    3. 헤더 행 감지: 2~6개 짧은 아이템 + 넓은 X 범위
    4. X좌표 열 클러스터링 (COL_CLUSTER_TOL = 15pt)
    5. 행별 적응형 갭 분석
    6. 다중행 셀 병합

    Args:
        page: pdfplumber.Page 객체

    Returns:
        list[dict]: 감지된 테이블 리스트
            각 dict: {"bbox": (x0,y0,x1,y1), "rows": [[str,...], ...]}
            빈 리스트 = 테이블 미감지
    """
    Y_TOL = 3.0                # Y좌표 행 그룹핑 허용 오차
    COL_CLUSTER_TOL = 15.0     # X좌표 열 클러스터링 허용 오차
    MIN_HEADER_ITEMS = 2       # 헤더 최소 아이템 수
    MAX_HEADER_ITEMS = 8       # 헤더 최대 아이템 수
    MIN_DATA_ROWS = 2          # 최소 데이터 행 수
    SPARSE_GAP_THRESHOLD = 12  # 희소 행 갭 임계값

    words = page.extract_words(
        keep_blank_chars=True,
        x_tolerance=3,
        y_tolerance=3,
    )

    if len(words) < 6:
        return []

    # Step 1: Y좌표 행 그룹핑
    sorted_words = sorted(words, key=lambda w: (w['top'], w['x0']))
    rows = []
    current_row = [sorted_words[0]]

    for w in sorted_words[1:]:
        if abs(w['top'] - current_row[0]['top']) <= Y_TOL:
            current_row.append(w)
        else:
            rows.append(current_row)
            current_row = [w]
    rows.append(current_row)

    if len(rows) < MIN_DATA_ROWS + 1:
        return []

    # Step 2: 헤더 행 후보 탐색
    header_idx = None
    for i, row in enumerate(rows):
        n_items = len(row)
        if MIN_HEADER_ITEMS <= n_items <= MAX_HEADER_ITEMS:
            # 아이템 평균 길이 짧은지 확인 (헤더는 보통 짧은 라벨)
            avg_len = sum(len(w['text']) for w in row) / n_items
            x_range = max(w['x1'] for w in row) - min(w['x0'] for w in row)
            page_width = float(page.width)

            if avg_len < 15 and x_range > page_width * 0.3:
                header_idx = i
                break

    if header_idx is None:
        return []

    # Step 3: X좌표 열 클러스터링 (헤더 행 기준)
    header_row = rows[header_idx]
    col_centers = sorted([(w['x0'] + w['x1']) / 2 for w in header_row])

    # Step 4: 데이터 행 수집 (헤더 다음부터)
    data_rows = rows[header_idx:]
    if len(data_rows) < MIN_DATA_ROWS + 1:
        return []

    # Step 5: 행을 열에 매핑하여 2D 배열 생성
    table_rows = []
    for row_words in data_rows:
        row_cells = [''] * len(col_centers)
        for w in row_words:
            center = (w['x0'] + w['x1']) / 2
            # 가장 가까운 열 찾기
            min_dist = float('inf')
            min_col = 0
            for ci, cc in enumerate(col_centers):
                dist = abs(center - cc)
                if dist < min_dist:
                    min_dist = dist
                    min_col = ci
            if min_dist < COL_CLUSTER_TOL:
                if row_cells[min_col]:
                    row_cells[min_col] += ' ' + w['text']
                else:
                    row_cells[min_col] = w['text']
        table_rows.append(row_cells)

    if len(table_rows) < MIN_DATA_ROWS:
        return []

    # bbox 계산
    all_words = [w for row in data_rows for w in row]
    x0 = min(w['x0'] for w in all_words)
    y0 = min(w['top'] for w in all_words)
    x1 = max(w['x1'] for w in all_words)
    y1 = max(w['bottom'] for w in all_words)

    return [{
        "bbox": (x0, y0, x1, y1),
        "rows": table_rows,
    }]
```

**§5.8-3. 기존 `detect_tables()` 수정**

```python
def detect_tables(page) -> list[tuple]:
    """
    페이지에서 테이블을 감지한다.

    [변경점] K3 동적 허용 오차 + K2 텍스트 정렬 폴백 추가

    감지 순서:
    1. K3: 선 두께 기반 동적 허용 오차 계산
    2. pdfplumber find_tables() (동적 허용 오차 적용)
    3. [폴백] K2: 텍스트 정렬 기반 감지 (find_tables 실패 시)
    """
    # K3: 동적 허용 오차 계산
    tolerance = calculate_dynamic_tolerance(page)

    table_settings = {
        "snap_tolerance": tolerance["snap_tolerance"],
        "join_tolerance": tolerance["join_tolerance"],
        "intersection_tolerance": tolerance["intersection_tolerance"],
    }

    # 1차: pdfplumber (K3 적용)
    tables = page.find_tables(table_settings=table_settings)
    if tables:
        return [t.bbox for t in tables]

    # 2차: K2 텍스트 정렬 폴백
    text_tables = detect_tables_by_text_alignment(page)
    if text_tables:
        return [t["bbox"] for t in text_tables]

    return []
```

---

### 5.9 `config.py` — OCR 엔진 설정 확장 (변경)

> 현재: 108줄 / 변경 후: ~140줄 (+32줄)

```python
# ── 기존 설정 아래에 추가 ──
# ⚠️ 리뷰 반영 (🔴2): 함수 정의를 변수 참조보다 먼저 배치 (기존 _detect_poppler_path 패턴 준수)
# ⚠️ 리뷰 반영 (🟡3): ZAI_API_KEY는 기존 config.py L43에 이미 존재 → 중복 추가 금지

# OCR 엔진 설정 (Phase 4)
# 참고: ZAI_API_KEY는 L43에서 이미 정의됨 (Phase 3 시점에 추가됨)
MISTRAL_API_KEY: str | None = os.getenv("MISTRAL_API_KEY")


def _detect_tesseract_path() -> str | None:
    """
    Tesseract 실행 파일 경로를 자동 탐지한다.

    Why: ocr.py는 r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"를
         하드코딩(문제 G)했다. 자동 탐지로 다양한 환경을 지원한다.

    Note: 이 함수는 TESSERACT_PATH 변수 참조보다 반드시 먼저 정의해야 한다.
          (기존 _detect_poppler_path → POPPLER_PATH 패턴과 동일, L56~L97 참조)
    """
    import shutil

    # 1순위: 시스템 PATH
    path = shutil.which("tesseract")
    if path:
        return path

    # 2순위: Windows 기본 설치 경로
    if sys.platform == "win32":
        candidates = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ]
        for p in candidates:
            if Path(p).exists():
                return p

    return None


# ⚠️ 반드시 _detect_tesseract_path() 정의 이후에 배치 (🔴2 NameError 방지)
TESSERACT_PATH: str | None = os.getenv("TESSERACT_PATH") or _detect_tesseract_path()

BOM_DEFAULT_ENGINE: str = os.getenv("BOM_DEFAULT_ENGINE", "zai")
```

**`.env` 파일에 추가할 키:**

```env
# Phase 4: OCR 엔진 (BOM 추출)
# 참고: ZAI_API_KEY는 Phase 3 시점에 이미 .env에 존재 (중복 추가 금지)
MISTRAL_API_KEY=your_mistral_api_key_here
TESSERACT_PATH=                              # 자동 탐지 또는 수동 경로
BOM_DEFAULT_ENGINE=zai                       # zai | mistral | tesseract
```

---

### 5.10 `main.py` — BOM 파이프라인 연결 (변경)

> 현재: 468줄 / 변경 후: ~540줄 (+72줄)

**§5.10-1. argparse 변경**

```python
# --engine choices 확장
parser.add_argument(
    "--engine",
    default=config.DEFAULT_ENGINE,
    choices=["gemini", "local", "zai", "mistral", "tesseract"],  # ← 3종 추가
    help="추출 엔진 (기본: %(default)s)",
)

# --preset choices 확장
parser.add_argument(
    "--preset",
    default=None,
    choices=["pumsem", "estimate", "bom"],  # ← bom 추가
    help="도메인 프리셋 (기본: 없음=범용)",
)
```

**§5.10-2. OCR 엔진 생성 함수**

```python
def _create_engine(engine_name: str, tracker=None):
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
            print("❌ .env에 ZAI_API_KEY가 설정되지 않았습니다.")
            sys.exit(1)
        return ZaiEngine(config.ZAI_API_KEY, tracker=tracker)
    elif engine_name == "mistral":
        from engines.mistral_engine import MistralEngine
        if not config.MISTRAL_API_KEY:
            print("❌ .env에 MISTRAL_API_KEY가 설정되지 않았습니다.")
            sys.exit(1)
        return MistralEngine(config.MISTRAL_API_KEY, tracker=tracker)
    elif engine_name == "tesseract":
        from engines.tesseract_engine import TesseractEngine
        return TesseractEngine(tesseract_path=config.TESSERACT_PATH)
    else:
        print(f"❌ 알 수 없는 엔진: {engine_name}")
        sys.exit(1)
```

**§5.10-3. BOM 파이프라인 분기**

```python
# main() 함수 내부, preset 로딩 후:

if preset == "bom":
    from presets.bom import get_bom_keywords, get_image_settings
    bom_keywords = get_bom_keywords()
    image_settings = get_image_settings()
    print(f"📋 프리셋 활성화: bom")

    # OCR 엔진 검증
    engine = _create_engine(engine_name, tracker)
    if not engine.supports_ocr:
        print(f"⚠️  BOM 프리셋은 OCR 엔진(zai/mistral/tesseract)이 필요합니다.")
        print(f"   현재 엔진: {engine_name} → --engine zai 로 변경하세요.")
        sys.exit(1)

    # Phase 1-BOM: OCR → 텍스트
    print(f"\n{'='*60}")
    print(f"Phase 1-BOM: OCR 추출 (엔진: {engine_name})")
    print(f"{'='*60}")

    from extractors.bom_extractor import extract_bom_with_retry, to_sections
    bom_result = extract_bom_with_retry(
        engine, input_path, bom_keywords, image_settings, page_indices
    )

    # 중간 결과: Raw Text 저장 (.md)
    md_path = output_base.with_suffix(".md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(bom_result.raw_text)
    print(f"   📝 OCR 원문 저장: {md_path}")

    # Phase 2-BOM: BOM → 표준 JSON 섹션
    print(f"\n{'='*60}")
    print(f"Phase 2-BOM: BOM 데이터 구조화")
    print(f"{'='*60}")

    sections = to_sections(bom_result)
    print(f"   📦 BOM 섹션: {len(bom_result.bom_sections)}개")
    print(f"   📦 LINE LIST 섹션: {len(bom_result.line_list_sections)}개")

    # JSON 저장
    from exporters.json_exporter import JsonExporter
    json_path = output_base.with_suffix(".json")
    JsonExporter().export(sections, json_path)
    print(f"   💾 JSON 저장: {json_path}")

    # Phase 3: Excel 출력 (기존 ExcelExporter 재사용)
    if output_format == "excel":
        print(f"\n{'='*60}")
        print(f"Phase 3: Excel 출력")
        print(f"{'='*60}")
        from exporters.excel_exporter import ExcelExporter
        xlsx_path = output_base.with_suffix(".xlsx")
        ExcelExporter().export(sections, xlsx_path)
        print(f"   📊 Excel 저장: {xlsx_path}")

    # BOM이 아닌 표준 파이프라인은 기존 코드 유지 (else 블록)
```

**§5.10-4. detector.py BOM 감지 추가**

```python
# detector.py에 추가

BOM_KEYWORDS = [
    "BILL OF MATERIALS", "BILL OF MATERIAL",
    "S/N", "MARK", "WT(KG)", "Q'TY", "MAT'L",
    "LINE LIST", "LINE NO",
]

THRESHOLD_BOM = 3  # BOM 키워드 매칭 임계값

def detect_document_type(text: str) -> str | None:
    # ... 기존 estimate/pumsem 판정 ...

    # BOM 판정 추가
    text_upper = text.upper()
    bom_score = sum(1 for kw in BOM_KEYWORDS if kw in text_upper)
    if bom_score >= THRESHOLD_BOM:
        return "bom"

    # 기존 반환
    return None
```

---

## 6. 잠재 위험 요소 검토

### 위험 1: OCR 엔진 API 응답 구조 변경

**문제:** Z.ai, Mistral OCR API의 응답 JSON 구조가 버전 업데이트로 변경될 수 있다. `_parse_response()` 함수가 새 구조를 처리하지 못하면 전체 파이프라인이 실패한다.

**해결:**
- `_parse_response()`에 5단계 폴백 체인을 구현 (§5.2 참조)
- 최종 폴백으로 `str(response)` 전체 문자열을 사용
- 각 폴백 단계에서 `logger.warning()` 으로 구조 변경 감지 로깅
- 테스트에서 실제 API 응답을 JSON fixture로 저장하여 회귀 테스트

### 위험 2: BOM 상태머신 오탐 — 앵커 없는 BOM

**문제:** 일부 도면은 "BILL OF MATERIALS" 텍스트 없이 바로 테이블이 시작된다. 앵커 의존 상태머신은 이런 BOM을 놓친다.

**해결:**
- IDLE 상태에서도 헤더 키워드(A∧B∧C) 감지 시 직접 BOM_DATA로 전이 (§5.5-3 구현됨)
- 3단계 폴백의 1단계(HTML `<table>` 기반)에서 앵커 없이 키워드만으로 감지
- 테스트: 앵커 있는 BOM / 앵커 없는 BOM 둘 다 검증

### 위험 3: K2 텍스트 정렬 감지의 오탐

**문제:** K2는 텍스트 좌표 정렬 패턴으로 테이블을 추정한다. 다단 레이아웃(제목+본문 2열) 문서를 테이블로 오인할 수 있다.

**해결:**
- `MIN_HEADER_ITEMS=2`, `MAX_HEADER_ITEMS=8` 범위로 헤더 행 후보 제한
- 헤더 행의 아이템 평균 길이 < 15 조건 (긴 문장은 헤더가 아님)
- X 범위가 페이지 폭의 30% 이상 조건 (좁은 영역은 테이블이 아님)
- K2는 **폴백 전용** — pdfplumber `find_tables()`가 성공하면 K2는 실행 안 됨

### 위험 4: pdf2image + Poppler 미설치 환경

**문제:** BOM 2차/3차 시도에서 PDF→이미지 변환이 필요한데, Poppler가 설치되지 않은 환경에서 `convert_from_path()`가 실패한다.

**해결:**
- `extract_bom_with_retry()`의 2차/3차 시도에서 `try/except`로 감싸서 변환 실패 시 건너뛰기 (§5.5-5 구현됨)
- 1차 시도(전체 파일 OCR)는 Z.ai/Mistral에서 PDF 직접 전송이므로 Poppler 불필요
- 향후: PyMuPDF(`fitz`) 폴백 추가 검토 (Phase 5)

### 위험 5: BOM 열 수 불일치 — OCR 과분할

**문제:** OCR이 하나의 셀을 여러 셀로 분할하여 열 수가 헤더보다 많아지는 경우. 예: `"SS 304"` → `["SS", "304"]`

**해결:**
- `normalize_columns()` 함수에서 인접 최소 길이 셀 자동 병합 (§5.6-4 구현됨)
- `reference_col_count`로 헤더 열 수를 기준값으로 전달
- 병합 기준: 인접 두 셀의 합산 길이가 가장 짧은 쌍부터 병합

### 위험 6: Tesseract 한국어 언어 데이터 미설치

**문제:** Tesseract에 `kor` 언어 데이터가 없으면 `lang='kor+eng'` 지정 시 에러 발생.

**해결:**
- `TesseractEngine.__init__()`에서 `lang` 파라미터로 언어 설정 가능
- Tesseract 설치 가이드를 README에 추가
- 에러 메시지에 한국어 데이터 설치 방법 포함:
  `"Tesseract 한국어 데이터가 필요합니다: sudo apt install tesseract-ocr-kor"`

### 위험 7: 순환 import — bom_extractor ↔ bom_table_parser (리뷰 🔴1 반영)

**문제:** `bom_extractor.py`가 `bom_table_parser.py`를 import하고, `bom_table_parser.py`가 `BomSection`/`BomExtractionResult` 데이터 클래스를 import하면 순환 발생.

**해결 (리뷰 🔴1 반영 — bom_types.py 분리):**
- `BomSection`, `BomExtractionResult` 데이터 클래스를 **제3의 모듈 `extractors/bom_types.py`에 분리** (§5.0-A)
- `bom_extractor.py`와 `bom_table_parser.py` 양쪽 모두 `from extractors.bom_types import ...`로 import
- import 방향이 항상 단방향: `bom_types ← bom_extractor`, `bom_types ← bom_table_parser`
- `bom_extractor.py`는 `bom_table_parser.py`를 **함수 내부 lazy import**로 호출 (§5.5-3, §5.5-4)
- 기존 "데이터 클래스를 bom_extractor에 두고 lazy import" 방식 대비, 모듈 레벨 import가 가능해져 **IDE 자동완성 및 타입 체크 완전 지원**

### 위험 8: Z.ai API 비용 — 크롭 재시도로 API 호출 3배 증가

**문제:** `extract_bom_with_retry()`가 3차까지 재시도하면 최대 3회 API 호출. 멀티페이지 PDF에서 페이지 수 × 3회로 비용 폭증.

**해결:**
- 1차(전체 파일)에서 BOM 감지 성공 시 2차/3차 건너뛰기 (§5.5-5 구현됨)
- LINE LIST도 1차에서 감지되면 3차 건너뛰기
- Phase 5 캐싱: 동일 파일+영역 해시로 중복 API 호출 방지
- `UsageTracker`로 API 비용 실시간 모니터링

### 위험 9: `zhipuai` SDK 해외 차단 (구현 동기화 S1)

> ⚠️ 구현 중 발견 — 기술서 초안에는 없었던 위험

**문제:** 기술서 초안은 `zhipuai` SDK (`pip install zhipuai`)를 명세했으나, 실제 테스트에서 `open.bigmodel.cn`(중국 본토) 엔드포인트만 지원하여 해외 사용자에게 `"Service Not Available For Overseas Users"` HTTP 오류 발생.

**해결:**
- 기존 `ocr.py` 분석 결과, 실제 사용하던 SDK는 `zai-sdk` (v0.2.2, ZaiClient)임을 확인
- `zai-sdk`는 `api.z.ai` (국제판 엔드포인트)를 사용하며 동일한 `layout_parsing.create(file=data_uri)` API 지원
- §5.2 ZaiEngine 코드에서 `from zhipuai import ZhipuAI` → `from zai import ZaiClient`로 교체
- §10 requirements.txt에서 `zhipuai` → `zai-sdk`로 교체

### 위험 10: LINE LIST 0행 — BOM 키워드 단일 경로 (구현 동기화 S2)

> ⚠️ 구현 중 발견 — 기술서 초안에는 없었던 위험

**문제:** `parse_html_bom_tables()`가 BOM 키워드(A∧B∧C: S/N, SIZE, Q'TY)만 검증하여 LINE LIST 블록이 항상 0행으로 처리됨. LINE LIST에는 `WT(KG)`, `Q'TY` 등 BOM 전용 키워드가 없어 A∧B∧C 조건을 충족하지 못함.

**해결:**
- `ll_header_a/b/c` LINE LIST 전용 키워드 경로를 추가 (`is_bom OR is_line_list` 이중 조건)
- 분류 시 타이틀 텍스트("LINE LIST") + `is_line_list` 플래그 이중 판정
- §5.6 `parse_html_bom_tables()` 코드에 반영

### 위험 11: colspan 타이틀 행 오인식 (구현 동기화 S3)

> ⚠️ 구현 중 발견 — 기술서 초안에는 없었던 위험

**문제:** Z.ai는 BOM 섹션 제목(`BILL OF MATERIALS`, `LINE LIST`)을 `colspan=N` 단일 셀로 반환. `expand_table()` 처리 후 해당 행의 모든 셀이 동일한 값으로 복제됨. 초기 구현은 이 행을 헤더로 오인하여 JSON의 `headers` 필드가 `["BILL OF MATERIALS", "BILL OF MATERIALS", ...]`로 오출력.

**해결:**
- unique 셀 값이 1개이고 다음 행이 더 많은 열을 보유한 경우 → 타이틀 행으로 판정
- `section_title`로 저장 후 스킵, 다음 행(S/N, SIZE, MAT'L, Q'TY, WT(kg), REMARKS)을 실제 컬럼 헤더로 사용
- §5.6 `parse_html_bom_tables()` 코드에 반영

---

## 7. 구현 순서 (의존성 기반)

```
1단계: 의존성 없는 모듈 (병렬 가능)
  ├── extractors/bom_types.py      (순수 데이터 클래스, 의존성 없음) ← 리뷰 반영 🔴1
  ├── utils/ocr_utils.py           (공통 유틸리티, Pillow/pdf2image 의존) ← 리뷰 반영 🟡5,7
  ├── presets/bom.py               (순수 상수/함수, 의존성 없음)
  ├── config.py 확장               (os.getenv, 의존성 없음)
  └── engines/base_engine.py 확장  (OcrPageResult 데이터 클래스 + 메서드 시그니처)

2단계: OCR 엔진 (1단계 의존)
  ├── engines/zai_engine.py        (BaseEngine 상속, ocr_utils, zai-sdk)
  ├── engines/mistral_engine.py    (BaseEngine 상속, ocr_utils, mistralai SDK)
  └── engines/tesseract_engine.py  (BaseEngine 상속, pytesseract)

3단계: 파서 + K2/K3 (1단계 의존)
  ├── parsers/bom_table_parser.py  (BomSection import ← bom_types.py) ← 리뷰 반영 🔴1
  └── extractors/table_utils.py    (K2 + K3 추가, 기존 detect_tables 수정)

4단계: BOM 추출기 (2+3단계 의존)
  └── extractors/bom_extractor.py  (bom_types + ocr_utils + bom_table_parser + bom preset 통합)

5단계: CLI 연결 (1~4단계 전체 의존)
  ├── main.py                      (BOM 파이프라인 분기 + OCR 엔진 선택)
  └── detector.py                  (BOM 키워드 감지 추가)
```

**의존 관계 DAG:**
```
extractors/bom_types.py ───────────────────────────┐
utils/ocr_utils.py ─────────────────────┐          │
presets/bom.py ─────────────────────────┤          │
config.py ──────────────────────────────┤          │
base_engine.py ─┬─ zai_engine.py ──────┤          │
                │     (+ ocr_utils)     │          │
                ├─ mistral_engine.py ───┤          │
                │     (+ ocr_utils)     │          │
                └─ tesseract_engine.py ─┤          │
                                        ├─ bom_extractor.py ─── main.py
bom_table_parser.py ────────────────────┤     (+ bom_types)
  (+ bom_types)                         │     (+ ocr_utils)
table_utils.py (K2+K3) ────────────────┘
```

---

## 8. 검증 계획

### 8.1 단위 테스트

| # | 검증 항목 | 입력 | 기대 결과 |
|---|---------|------|----------|
| 1 | `OcrPageResult` 데이터 클래스 | 생성자 호출 | 모든 필드 기본값 정상 |
| 2 | `ZaiEngine.supports_ocr` | 속성 접근 | `True` |
| 3 | `GeminiEngine.supports_ocr` | 속성 접근 | `False` (기본값) |
| 4 | `ocr_utils.image_to_data_uri()` | 100×100 PIL Image | `data:image/png;base64,...` 형식 |
| 5 | `ocr_utils.file_to_data_uri()` | 샘플 PDF | `data:application/pdf;base64,...` 형식 |
| 5-1 | `ocr_utils.pdf_page_to_image()` | 1페이지 PDF + dpi=400 | PIL Image (너비,높이 > 0) |
| 5-2 | `bom_types.BomSection` 독립 import | `from extractors.bom_types import BomSection` | import 성공, 순환 없음 |
| 6 | `TesseractEngine.ocr_image()` | 텍스트 포함 이미지 | 텍스트 추출 (비어있지 않음) |
| 7 | `_sanitize_html()` | `<tr><td>A</td><td>B</td></tr>` | `A \| B` |
| 8 | `extract_bom()` — 앵커 있는 BOM | "BILL OF MATERIALS\n\|S/N\|SIZE..." | BOM 섹션 1개, 데이터 행 존재 |
| 9 | `extract_bom()` — 앵커 없는 BOM | "\|S/N\|SIZE\|MAT'L\|Q'TY..." 직접 시작 | BOM 섹션 1개 (IDLE→BOM_DATA 직접 전이) |
| 10 | `extract_bom()` — 킬 키워드 종료 | BOM 데이터 후 "TOTAL WEIGHT" | 데이터 수집 종료, 킬 키워드 이후 행 미포함 |
| 11 | `extract_bom()` — 빈 행 2연속 종료 | BOM 데이터 후 빈 줄 2개 | 데이터 수집 종료 |
| 12 | `extract_bom()` — BOM + LINE LIST 혼재 | BOM 앵커 + LL 앵커 순서대로 | bom_sections 1개 + ll_sections 1개 |
| 13 | `parse_html_bom_tables()` | `<table>` with S/N+SIZE+QTY | BOM 섹션 1개, 헤더 매칭 |
| 14 | `parse_html_bom_tables()` 블랙리스트 | `<table>` with CLIENT: | 빈 결과 (제외됨) |
| 15 | `parse_markdown_pipe_table()` | 파이프 구분 3행 | 3행 2D 배열 |
| 16 | `parse_whitespace_table()` | 공백 구분 3행 | 3행 2D 배열 |
| 17 | `normalize_columns()` 패딩 | 열 수 불일치 행 | 최대 열 수로 패딩 |
| 18 | `normalize_columns()` 병합 | 과분할 행 (열 수 초과) | 기준 열 수로 병합 |
| 19 | `filter_noise_rows()` | 노이즈 키워드 포함 행 | 해당 행 제거, 정상 행 유지 |
| 20 | `to_sections()` | BomExtractionResult | Phase 2 JSON 호환 섹션 리스트 |
| 21 | `calculate_dynamic_tolerance()` | 선 두께 4pt 페이지 | snap ≈ 8, join ≈ 16 |
| 22 | `calculate_dynamic_tolerance()` | 선 없는 페이지 | 기본값 (snap=3, join=3) |
| 23 | `detect_tables_by_text_alignment()` | 3열 5행 정렬 텍스트 | 테이블 1개 감지 |
| 24 | `detect_tables_by_text_alignment()` | 일반 본문 텍스트 | 빈 리스트 (미감지) |
| 25 | `detect_tables()` K3 적용 | 두꺼운 선 페이지 | 동적 tolerance로 테이블 감지 성공 |
| 26 | BOM_KEYWORDS 완전성 | 키워드 딕셔너리 | 9개 키 모두 존재, 빈 리스트 없음 |

### 8.2 통합 테스트

| # | 검증 항목 | 명령어 | 기대 결과 |
|---|---------|--------|----------|
| 1 | BOM PDF→Excel (Z.ai) | `python main.py "drawing.pdf" --engine zai --preset bom --output excel` | BOM 시트 + LINE LIST 시트, 행 수 > 0 |
| 2 | BOM PDF→JSON (Mistral) | `python main.py "drawing.pdf" --engine mistral --preset bom --output json` | JSON에 BOM-1 섹션 존재 |
| 3 | BOM PDF→Excel (Tesseract) | `python main.py "drawing.pdf" --engine tesseract --preset bom --output excel` | 오프라인 OCR로 BOM 추출 |
| 4 | 잘못된 엔진 조합 | `python main.py "drawing.pdf" --engine gemini --preset bom` | `⚠️ BOM 프리셋은 OCR 엔진이 필요합니다` 에러 |
| 5 | OCR 엔진 + 표준 파이프라인 | `python main.py "견적서.pdf" --engine zai --output excel` | OCR 텍스트 → 표준 Phase 2 → Excel (BOM 아닌 일반 문서) |
| 6 | BOM 자동 감지 | `python main.py "drawing.pdf" --engine zai --output excel` | `💡 BOM 문서로 감지...` 프리셋 제안 출력 |
| 7 | 멀티페이지 BOM | `python main.py "multi_page.pdf" --engine zai --preset bom --output excel` | 전 페이지 BOM 행 누적 |
| 8 | 페이지 범위 지정 | `python main.py "drawing.pdf" --engine zai --preset bom --pages 1-3 --output excel` | 1~3페이지만 처리 |

### 8.3 출력물 비교 테스트

| # | 검증 항목 | 기대 결과 |
|---|---------|----------|
| 1 | BOM 열 수 일치 | Excel 헤더 열 수 == JSON headers 길이 == BOM 헤더 키워드 수 |
| 2 | BOM 행 수 일치 | Excel 데이터 행 수 == JSON rows 길이 == raw_row_count - 필터된 행 |
| 3 | 숫자 포맷 | QTY, WEIGHT 열이 Excel에서 숫자 타입 (문자열 "15.3" → 숫자 15.3) |
| 4 | 빈 셀 처리 | OCR이 놓친 셀은 빈 문자열, None 아님 |
| 5 | 한글 BOM | 한국어 헤더(품목/규격/수량)가 K1 균등배분 병합 후 정상 표시 |

### 8.4 회귀 테스트 (Phase 1/2/3 보존)

| # | 검증 항목 | 기대 결과 |
|---|---------|----------|
| 1 | `python main.py "견적서.pdf"` | Phase 1 MD 출력 변경 없음 |
| 2 | `python main.py "추출.md" --output json --preset pumsem` | Phase 2 JSON 변경 없음 |
| 3 | `python main.py "추출.md" --output excel` | Phase 3 Excel 변경 없음 |
| 4 | `python main.py "견적서.pdf" --output excel --preset estimate` | Phase 3-B 견적서 Excel 변경 없음 |
| 5 | `python _test_phase3.py` | 기존 테스트 ALL PASS |
| 6 | `--engine gemini` / `--engine local` | 기존 엔진 정상 동작 |
| 7 | K3 적용 후 기존 테이블 감지 | 기존 PDF에서 테이블 감지 결과 동일 또는 개선 (악화 없음) |

---

## 9. 완료 후 파이프라인 전체 흐름

```
📄 입력 파일
     │
     ├── .pdf ──────────────────────────────────────────────────
     │     │
     │     ├─ --preset bom ─────────────────────────────────────┐
     │     │    │                                               │
     │     │    │  [Phase 1-BOM: OCR 엔진]                      │
     │     │    │  ├─ --engine zai      → ZaiEngine            │
     │     │    │  ├─ --engine mistral  → MistralEngine        │
     │     │    │  └─ --engine tesseract → TesseractEngine     │
     │     │    │         │                                     │
     │     │    │         ├─ 1차: 전체 페이지 OCR               │
     │     │    │         ├─ 2차: 우측 55% 크롭 (BOM 복구)      │
     │     │    │         └─ 3차: 하단 50% 크롭 (LINE LIST)     │
     │     │    │                │                              │
     │     │    │  [Phase 2-BOM: bom_extractor]                │
     │     │    │  ├─ 상태머신 (IDLE→SCAN→DATA)                 │
     │     │    │  ├─ bom_table_parser (HTML/MD/공백 통합)      │
     │     │    │  └─ to_sections() → Phase 2 JSON 호환        │
     │     │    │                │                              │
     │     │    └────────────────┤                              │
     │     │                     │                              │
     │     ├─ --preset pumsem/estimate/없음 ─────────────────────┤
     │     │    │                                               │
     │     │    │  [Phase 1: extractors/ + engines/]            │
     │     │    │  ├─ K3 동적 허용 오차 (table_utils)  ← [4 신규] │
     │     │    │  └─ K2 텍스트 정렬 폴백 (table_utils) ← [4 신규] │
     │     │    │                │                              │
     │     │    │  [Phase 2: parsers/ + presets/]               │
     │     │    │                │                              │
     │     │    └────────────────┤                              │
     │     │                     │                              │
     ├── .md ────────────────────┤                              │
     ├── .json ──────────────────┤                              │
     │                           │                              │
     │              📦 JSON (Phase 2 표준 형식)                  │
     │                           │                              │
     │              [Phase 3: exporters/]                       │
     │              ├─ JsonExporter  → 📦 .json                │
     │              └─ ExcelExporter → 📊 .xlsx                │
     │                      │                                   │
     │                      ├─ preset=bom      → BOM/LL 시트    │  ← [4 신규]
     │                      ├─ preset=estimate → 갑지+내역서      │
     │                      ├─ preset=pumsem   → 견적서/내역서    │
     │                      └─ preset=없음     → 범용 Table_N    │
     │                                                          │
     └──────────────────────────────────────────────────────────
```

---

## 10. requirements.txt 추가 패키지

```
# Phase 4: OCR 엔진 (선택 설치)
zai-sdk          # Z.ai GLM-OCR (--engine zai 사용 시) ← S1: zhipuai→zai-sdk 교체
mistralai        # Mistral Pixtral OCR (--engine mistral 사용 시)
pytesseract      # Tesseract OCR (--engine tesseract 사용 시)
```

> **설치 전략:** OCR 패키지는 선택사항이므로 `requirements-ocr.txt`로 분리하거나, 엔진별 lazy import로 미설치 시 명확한 에러 메시지를 출력한다 (§5.2~5.4에서 함수 내부 import 사용).

---

## 11. ocr.py 결함 대응 매핑 (최종 요약)

| ocr.py 결함 | 해당 코드 | Phase 4 대응 | 대응 위치 |
|------------|----------|-------------|----------|
| 문제 A: bare except 11건 | L256,291,378... | 구체적 `except Exception as e` + logging | 전 모듈 |
| 문제 B: Dead Code 4건 | L26,56,86,1692 | 호출 관계 사전 설계 → 미연결 코드 원천 차단 | 설계 단계 |
| 문제 C: God Object 2,175줄 | L131~2306 | 파일별 단일 책임 분리 (engine/extractor/parser/preset) | 전 구조 |
| 문제 D: HTML 파싱 3중 중복 | L692,1131,1331 | `bom_table_parser.py` 1개 통합 함수 | §5.6 |
| 문제 E: 분기 3중 복붙 | L973,1189,1914 | preset 키워드로 자동 라우팅 | §5.7, §5.10 |
| 문제 F: 키워드 4중 중복 | L1267,1291,1452,1924 | `presets/bom.py` BOM_KEYWORDS 1곳 관리 | §5.7 |
| 문제 G: 하드코딩 | L1771,643,1716... | `.env` + `config.py` 설정 관리 | §5.9 |
| 문제 H: GUI-로직 결합 | L1662 | 순수 함수, GUI 의존 제로, headless 테스트 가능 | 전 모듈 |
| pdfplumber 고정 허용 오차 | 고정 snap=3 | kordoc K3: 동적 허용 오차 | §5.8-1 |
| pdfplumber 선 없는 테이블 미감지 | find_tables 의존 | kordoc K2: 텍스트 정렬 폴백 | §5.8-2 |

---

---

## 12. 리뷰 반영 이력

| 일자 | 구분 | 리뷰 항목 | 대응 내용 | 반영 위치 |
|------|------|----------|----------|----------|
| 2026-04-15 | 🔴 치명적 | **🔴1** 순환 import: `bom_table_parser` ↔ `bom_extractor` | `extractors/bom_types.py` 신규 추가, 데이터 클래스 분리 | §5.0-A 신규, §5.5 import 변경, §5.6 import 변경, §6 위험7 업데이트 |
| 2026-04-15 | 🔴 치명적 | **🔴2** `config.py` 함수 정의 순서: `_detect_tesseract_path()` 정의 전 호출 → NameError | 함수 정의를 변수 참조보다 먼저 배치 (기존 `_detect_poppler_path` 패턴 준수) | §5.9 코드 순서 수정 |
| 2026-04-15 | 🟡 주의 | **🟡3** `ZAI_API_KEY` 이미 config.py L43에 존재 | §5.9에서 중복 제거, 주석으로 기존 위치 명시 | §5.9 코드 수정, .env 가이드 수정 |
| 2026-04-15 | 🟡 주의 | **🟡4** `bom.py`에 `get_excel_config()` 없음 | `get_excel_config() → None` 추가, 인터페이스 일관성 확보 | §5.7 함수 추가 |
| 2026-04-15 | 🟡 주의 | **🟡5** `_file_to_data_uri` 2개 엔진에 중복 | `utils/ocr_utils.py` 신규 추가, 양쪽 엔진에서 공통 함수 import | §5.0-B 신규, §5.2 import 변경, §5.3 import 변경 + static method 제거 |
| 2026-04-15 | 🟡 주의 | **🟡6** `detector.py` BOM 판정에 `.upper()` 미적용 | `text_upper = text.upper()` 적용 후 키워드 매칭 | §5.10-4 코드 수정 |
| 2026-04-15 | 🟡 주의 | **🟡7** `_pdf_page_to_image` 2곳 중복 | `utils/ocr_utils.py`에 `pdf_page_to_image()` 통합, `bom_extractor._get_page_image()` 제거 | §5.0-B, §5.2 import 변경, §5.5 import 변경 + 함수 제거 |

| 2026-04-15 | ⚠️ 동기화 | **S1** `zhipuai` SDK 해외 차단 → `zai-sdk` 교체 | `from zai import ZaiClient` 사용, `zhipuai` 참조 전체 제거 | §5.2 코드 전체, §10 requirements.txt, §6 위험 9 추가 |
| 2026-04-15 | ⚠️ 동기화 | **S2** LINE LIST 0행 — BOM 키워드 단일 경로 | `ll_header_a/b/c` 전용 경로 추가, `is_bom OR is_line_list` 이중 판정 | §5.6-1 코드 전체, §6 위험 10 추가 |
| 2026-04-15 | ⚠️ 동기화 | **S3** colspan 타이틀 행 오인식 | unique 셀 1개 패턴 감지 → 타이틀 행 스킵, 다음 행을 헤더로 교정 | §5.6-1 코드 전체, §6 위험 11 추가 |

> 리뷰 결과: 7건 전체 타당성 확인 → 전건 반영 완료
> 구현 동기화: 3건 (S1~S3) — 구현 중 발견된 차이점을 기술서에 역반영 완료

---

> 작성일: 2026-04-15 | Phase 4 of 5 | 작성: Antigravity AI
> 라이선스 참조: K2, K3 알고리즘은 kordoc (MIT License, Copyright (c) chrisryugj) 참조
> 외부 SDK: zai-sdk (pip, Z.ai 공식), mistralai (Apache-2.0), pytesseract (Apache-2.0)

