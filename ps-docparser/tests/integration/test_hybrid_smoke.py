"""tests/integration/test_hybrid_smoke.py — hybrid_extractor 실 PDF 통합 스모크.

Why: test_hybrid_extractor.py 는 pdfplumber 를 전부 Mock 처리하여
     실제 PDF 파싱 경로가 검증되지 않는다.
     minimal.pdf(텍스트 전용, 테이블 없음)로 LocalEngine 과 함께
     process_pdf 의 실 경로를 종단간 검증한다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engines.local_engine import LocalEngine
from extractors.hybrid_extractor import process_pdf


@pytest.fixture(scope="module")
def minimal_pdf(sample_pdf_dir: Path) -> Path:
    p = sample_pdf_dir / "minimal.pdf"
    if not p.exists():
        pytest.skip("minimal.pdf 미생성 — python scripts/create_minimal_pdf.py 실행 필요")
    return p


class TestHybridSmokeLocalEngine:
    def test_text_only_pdf_returns_nonempty_markdown(self, minimal_pdf):
        """텍스트 전용 PDF + LocalEngine → AI 미호출로 비어있지 않은 마크다운 반환."""
        engine = LocalEngine()
        md = process_pdf(str(minimal_pdf), engine=engine)
        assert isinstance(md, str)
        assert len(md) > 0

    def test_contains_expected_text(self, minimal_pdf):
        """PDF 에 삽입한 텍스트가 추출 결과에 포함되어야 한다."""
        engine = LocalEngine()
        md = process_pdf(str(minimal_pdf), engine=engine)
        assert "Test Document" in md

    def test_multipage_pdf_contains_both_pages(self, minimal_pdf):
        """2페이지 PDF 처리 시 양 페이지 내용이 모두 포함된다."""
        engine = LocalEngine()
        md = process_pdf(str(minimal_pdf), engine=engine)
        assert "Item" in md
        assert "Page 2" in md

    def test_page_indices_filters_to_single_page(self, minimal_pdf):
        """page_indices=[0] 으로 1페이지만 처리하면 Page 2 내용은 없다."""
        engine = LocalEngine()
        md = process_pdf(str(minimal_pdf), engine=engine, page_indices=[0])
        assert "Test Document" in md
        assert "Page 2" not in md
