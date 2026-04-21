"""tests/unit/engines/test_local_engine.py — LocalEngine 검증."""

from __future__ import annotations

import pytest

from engines.local_engine import LocalEngine


class TestLocalEngine:
    def test_supports_image_is_false(self):
        engine = LocalEngine()
        assert engine.supports_image is False
        assert engine.supports_ocr is False

    def test_extract_table_raises_not_implemented(self):
        engine = LocalEngine()
        with pytest.raises(NotImplementedError, match="supports_image"):
            engine.extract_table(image=None, table_num=1)

    def test_extract_full_page_raises_not_implemented(self):
        engine = LocalEngine()
        with pytest.raises(NotImplementedError, match="이미지"):
            engine.extract_full_page(image=None, page_num=1)

    def test_extract_table_from_data_produces_html(self):
        engine = LocalEngine()
        data = [
            ["명 칭", "규 격", "수량"],
            ["파이프 서포트", "150A", "4"],
            ["앵커 볼트", "M16", "8"],
        ]
        html = engine.extract_table_from_data(data, table_num=1)
        assert "<table>" in html
        assert "<th>명 칭</th>" in html
        assert "<td>파이프 서포트</td>" in html
        assert "<td>8</td>" in html
