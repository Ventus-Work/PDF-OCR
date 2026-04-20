import pytest
from extractors.toc_parser import _normalize_section_name


class TestNormalizeSectionName:
    def test_basic(self):
        assert _normalize_section_name("제1장 공 통") == "제1장 공통"

    def test_preserves_korean(self):
        res = _normalize_section_name("제2장 구조물")
        assert "제2장" in res
        assert "구조물" in res

    def test_strips_extra_whitespace(self):
        res = _normalize_section_name("  제3편   건축   ")
        assert res.strip() == res  # 앞뒤 공백 없음

    def test_empty_input(self):
        assert _normalize_section_name("") == ""
