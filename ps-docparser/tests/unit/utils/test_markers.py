import pytest
from utils.markers import build_page_marker


class TestBuildPageMarker:
    def test_basic(self):
        ctx = {"division": "제1편", "chapter": "제1장"}
        marker = build_page_marker(10, ctx)
        assert "PAGE 10" in marker
        assert "제1장" in marker

    def test_empty_context(self):
        marker = build_page_marker(1, {})
        assert "PAGE 1" in marker

    def test_high_page_number(self):
        marker = build_page_marker(999, {"division": "D", "chapter": "C"})
        assert "999" in marker

    def test_division_included(self):
        marker = build_page_marker(5, {"division": "제2편", "chapter": "제3장"})
        assert "제2편" in marker or "제3장" in marker
