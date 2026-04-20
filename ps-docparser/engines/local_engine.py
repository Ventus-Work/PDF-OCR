"""
engines/local_engine.py — 로컬 전용 엔진 (AI 없음, 무료)

Why: API 키 없이도 pdfplumber 자체 테이블 파싱으로 결과를 얻을 수 있다.
     비용 0원이며, pdf2image/Poppler 설치도 불필요하다.
     테이블이 있는 페이지에서도 pdfplumber 데이터를 BaseEngine.extract_table_from_data()로
     처리하므로 이미지 변환 단계 자체가 건너뛰어진다.

한계:
    - 셀 병합(rowspan/colspan) 인식 불가
    - 테두리 없는 표는 인식률 낮음
    - 정확도 필요 시 Gemini 엔진으로 전환 권장
"""

import logging

from engines.base_engine import BaseEngine

logger = logging.getLogger(__name__)


class LocalEngine(BaseEngine):
    """
    AI 없는 로컬 전용 엔진.

    supports_image = False → hybrid_extractor.py가 pdf2image를 호출하지 않는다.
    테이블은 pdfplumber 데이터를 BaseEngine.extract_table_from_data()로 처리한다.
    """

    supports_image = False  # ← 핵심: 이 값으로 파이프라인이 Poppler 호출 여부를 결정

    def extract_table(self, image, table_num: int) -> tuple[str, int, int]:
        """
        사용되지 않는 메서드 — supports_image=False이므로 호출 안 됨.

        Why: hybrid_extractor.py는 supports_image 체크 후 분기하므로
             이 메서드는 정상 흐름에서 절대 호출되지 않는다.
             혹시 직접 호출 시 명확한 에러를 발생시킨다.
        """
        raise NotImplementedError(
            "LocalEngine은 이미지 처리를 지원하지 않습니다. "
            "engine.supports_image 값을 확인하고 extract_table_from_data()를 사용하세요."
        )

    def extract_full_page(self, image, page_num: int) -> tuple[str, int, int]:
        """
        사용되지 않는 메서드 — supports_image=False이므로 호출 안 됨.
        """
        raise NotImplementedError(
            "LocalEngine은 이미지 기반 전체 페이지 처리를 지원하지 않습니다."
        )

    # extract_table_from_data()는 BaseEngine의 기본 구현을 사용
    # (pdfplumber 2D 배열 → 단순 HTML 테이블 변환)
