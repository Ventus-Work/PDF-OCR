"""
tests/performance/test_regex_caching.py — Phase 8 정규식 캐싱 회귀 테스트

Why: 모듈 레벨 _RE_* 상수와 lru_cache 패턴이 실수로 제거되면
     100페이지 배치에서 1,300회+ 재컴파일이 재발한다.
     이 테스트가 통과하면 캐싱 구조가 살아 있음을 보장한다.
"""
import pytest
from extractors import bom_extractor
from utils import text_formatter


class TestRegexCaching:
    def test_bom_extractor_has_module_level_patterns(self):
        """bom_extractor.py에 모듈 레벨 정규식 상수가 존재해야 한다."""
        assert hasattr(bom_extractor, "_RE_TR_CLOSE"),     "_RE_TR_CLOSE 없음"
        assert hasattr(bom_extractor, "_RE_TD_SPLIT"),     "_RE_TD_SPLIT 없음"
        assert hasattr(bom_extractor, "_RE_TAG"),          "_RE_TAG 없음"
        assert hasattr(bom_extractor, "_RE_ENTITY_NAMED"), "_RE_ENTITY_NAMED 없음"
        assert hasattr(bom_extractor, "_RE_ENTITY_HEX"),   "_RE_ENTITY_HEX 없음"
        assert hasattr(bom_extractor, "_RE_WHITESPACE"),   "_RE_WHITESPACE 없음"

    def test_text_formatter_has_module_level_patterns(self):
        """text_formatter.py에 모듈 레벨 정규식 상수가 존재해야 한다."""
        assert hasattr(text_formatter, "_RE_SECTION_NUM"),    "_RE_SECTION_NUM 없음"
        assert hasattr(text_formatter, "_RE_TRIPLE_NEWLINE"), "_RE_TRIPLE_NEWLINE 없음"
        assert hasattr(text_formatter, "_RE_DOUBLE_SPACE"),   "_RE_DOUBLE_SPACE 없음"
        assert hasattr(text_formatter, "_RE_LIST_BASE"),      "_RE_LIST_BASE 없음"

    def test_bom_extractor_patterns_are_compiled(self):
        """상수가 실제 컴파일된 Pattern 객체인지 확인."""
        import re
        assert isinstance(bom_extractor._RE_TR_CLOSE, type(re.compile("")))
        assert isinstance(bom_extractor._RE_TAG,      type(re.compile("")))

    def test_text_formatter_patterns_are_compiled(self):
        import re
        assert isinstance(text_formatter._RE_TRIPLE_NEWLINE, type(re.compile("")))
        assert isinstance(text_formatter._RE_DOUBLE_SPACE,   type(re.compile("")))

    def test_pumsem_patterns_cached(self):
        """동일 division_names 두 번 호출 시 같은 객체를 반환해야 한다 (lru_cache)."""
        from utils.text_formatter import _get_pumsem_patterns
        p1 = _get_pumsem_patterns("공통부문|토목부문")
        p2 = _get_pumsem_patterns("공통부문|토목부문")
        assert p1 is p2, "lru_cache 미적용 — 동일 키에 대해 새 객체 반환됨"

    def test_pumsem_patterns_different_keys(self):
        """다른 division_names는 다른 객체를 반환해야 한다."""
        from utils.text_formatter import _get_pumsem_patterns
        p1 = _get_pumsem_patterns("공통부문")
        p2 = _get_pumsem_patterns("건축부문")
        assert p1 is not p2, "서로 다른 키가 같은 캐시를 반환함"
