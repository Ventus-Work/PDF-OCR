"""
engines/base_engine.py — AI 엔진 공통 인터페이스 (Abstract Base Class)

Why: 엔진 교체를 플러그인처럼 하려면 공통 계약(인터페이스)이 필요하다.
     GeminiEngine, LocalEngine, ZaiEngine 등 새 엔진 추가 시 이 클래스를 상속하면
     hybrid_extractor.py 파이프라인이 수정 없이 자동으로 인식한다.
     (OCP - 개방폐쇄원칙: 확장에 열려있고, 수정에 닫혀있다)

인터페이스 계약:
    - extract_table(): 테이블 이미지 크롭 → HTML (이미지 지원 엔진)
    - extract_full_page(): 전체 페이지 이미지 → MD+HTML (이미지 지원 엔진)
    - extract_table_from_data(): pdfplumber 2D 배열 → HTML (이미지 미지원 엔진 폴백)
    - supports_image: 이미지 처리 가능 여부 (이 값으로 파이프라인이 분기)
    - ocr_document(): PDF 파일 직접 OCR 처리 (Phase 4 BOM 파이프라인)
    - ocr_image(): 단일 PIL 이미지 OCR 처리 (크롭 영역 처리)
    - supports_ocr: OCR 지원 여부 (이 값으로 BOM 파이프라인 분기)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from PIL import Image

if TYPE_CHECKING:
    # 실행 시 임포트하지 않고 타입 체커(mypy 등)용으로만 참조
    # Why: cache.table_cache → engines.base_engine 순환 임포트 방지
    from cache.table_cache import TableCache



@dataclass
class OcrPageResult:
    """OCR 엔진의 페이지별 결과."""
    page_num: int
    text: str
    layout_details: list[dict] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


class BaseEngine(ABC):
    """
    모든 AI 추출 엔진의 공통 기반 클래스.

    Attributes:
        supports_image (bool):
            True  → 이미지 기반 처리 가능 (pdf2image + Poppler 필요)
            False → 텍스트/데이터 기반만 처리 (pdf2image + Poppler 불필요)
            hybrid_extractor.py가 이 값을 보고 pdf2image 호출 여부를 결정한다.
    """

    supports_image: bool = True
    supports_ocr: bool = False          # OCR 지원 여부 (ZaiEngine, MistralEngine, TesseractEngine만 True)
    cache: "TableCache | None" = None   # Phase 5: 캐시 레이어 (main.py에서 외부 주입)


    @abstractmethod
    def extract_table(
        self, image: "Image.Image", table_num: int
    ) -> tuple[str, int, int]:
        """
        테이블 이미지 크롭을 받아 HTML 문자열로 변환한다.

        Args:
            image: PIL Image (테이블 영역 크롭된 이미지)
            table_num: 페이지 내 테이블 번호 (로그 출력용)

        Returns:
            (html_str, input_tokens, output_tokens)
            실패 시 (<!-- 에러 주석 -->, 0, 0)
        """
        ...

    @abstractmethod
    def extract_full_page(
        self, image: "Image.Image", page_num: int
    ) -> tuple[str, int, int]:
        """
        전체 페이지 이미지를 MD+HTML 혼합 형식으로 변환한다.

        Why: bbox 검증 실패 등 비정상 테이블이 감지되면
             페이지 전체를 한 번에 AI에게 전달하는 폴백으로 사용된다.

        Args:
            image: PIL Image (전체 페이지)
            page_num: 1-indexed 페이지 번호 (로그 출력용)

        Returns:
            (content_str, input_tokens, output_tokens)
        """
        ...

    def extract_table_from_data(
        self, table_data: list[list], table_num: int
    ) -> str:
        """
        pdfplumber가 추출한 2D 배열을 HTML 테이블로 변환한다.

        Why: supports_image=False인 엔진(LocalEngine 등)에서 this method가
             pdf2image/Poppler 없이 테이블 처리를 가능하게 하는 유일한 경로다.
             기본 구현은 단순 <table> 태그 생성이며, 서브클래스에서 오버라이드 가능.

        Args:
            table_data: pdfplumber page.extract_tables()가 반환한 2D 리스트
            table_num: 페이지 내 테이블 번호 (로그 출력용)

        Returns:
            HTML 문자열 (<table>...</table>)
        """
        if not table_data:
            return f"<!-- 테이블 {table_num}: 데이터 없음 -->"

        html = "<table>\n"

        # 첫 행을 헤더로 처리
        if table_data:
            html += "<thead>\n<tr>"
            for cell in table_data[0]:
                html += f"<th>{cell or ''}</th>"
            html += "</tr>\n</thead>\n"

        # 나머지 행을 tbody로 처리
        if len(table_data) > 1:
            html += "<tbody>\n"
            for row in table_data[1:]:
                html += "<tr>"
                for cell in row:
                    html += f"<td>{cell or ''}</td>"
                html += "</tr>\n"
            html += "</tbody>\n"

        html += "</table>"
        return html

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
