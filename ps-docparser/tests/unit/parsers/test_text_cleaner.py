"""
text_cleaner.py 단위 테스트 (P1)
"""
import pytest
from parsers.text_cleaner import merge_spaced_korean, clean_text

class TestTextCleaner:
    def test_merge_spaced_korean(self):
        # 균등배분 패턴(글자 사이에 공백) 병합
        assert merge_spaced_korean("제 출 처") == "제출처"
        assert merge_spaced_korean("품   명") == "품명"
        # 정상 텍스트는 그대로 유지해야 함
        assert merge_spaced_korean("배관 Support") == "배관 Support"
        
    def test_clean_text_basic(self):
        # 주석 제거 및 다중 줄바꿈 처리
        text = "안녕하세요<!-- 주석 -->\n\n\n반갑습니다."
        assert clean_text(text) == "안녕하세요\n\n반갑습니다."

    def test_clean_text_with_domain_patterns(self):
        import re
        patterns = {"chapter_title": re.compile(r'제\s*\d+\s*장.*?장\s*')}
        text = "제 6 장 배관공사 장\n내용"
        assert clean_text(text, patterns=patterns) == "내용"
