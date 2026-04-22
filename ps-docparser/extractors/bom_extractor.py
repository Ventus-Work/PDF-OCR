"""
extractors/bom_extractor.py — BOM 추출 공개 API shim

Why: Phase 12 Step 12-3 분해 결과물.
     기존 import 경로를 100% 유지하는 순수 re-export shim.
     신규 로직 없음 — 모든 구현은 하위 모듈에 있다.

     분해 구조:
         bom_sanitizer.py    → HTML 전처리 (_sanitize_html + 정규식 캐시)
         bom_state_machine.py → 상태머신 추출 (extract_bom, extract_bom_tables)
         bom_ocr_retry.py    → OCR 재시도 (_get_table_bbox_scaled, extract_bom_with_retry)
         bom_converter.py    → JSON 변환 (to_sections)

     외부 코드(pipelines/bom_pipeline.py, 테스트)는 이 파일을 통해
     모든 심볼에 동일 경로로 접근 가능하다.

원본: extractors/bom_extractor.py L1~592 (Phase 11 완료 기준)
"""

# ── Import shim: 하위 모듈에서 전체 공개/반공개 API re-export ──
from extractors.bom_sanitizer import (
    _sanitize_html,
    _RE_TR_CLOSE,
    _RE_TD_SPLIT,
    _RE_TAG,
    _RE_ENTITY_NAMED,
    _RE_ENTITY_HEX,
    _RE_WHITESPACE,
)
from extractors.bom_state_machine import (
    extract_bom,
    extract_bom_tables,
)
from extractors.bom_ocr_retry import (
    _get_table_bbox_scaled,
    extract_bom_with_retry,
)
from extractors.bom_converter import to_sections

__all__ = [
    # bom_sanitizer
    "_sanitize_html",
    "_RE_TR_CLOSE", "_RE_TD_SPLIT", "_RE_TAG",
    "_RE_ENTITY_NAMED", "_RE_ENTITY_HEX", "_RE_WHITESPACE",
    # bom_state_machine
    "extract_bom",
    "extract_bom_tables",
    # bom_ocr_retry
    "_get_table_bbox_scaled",
    "extract_bom_with_retry",
    # bom_converter
    "to_sections",
]
