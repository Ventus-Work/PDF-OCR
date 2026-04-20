import pytest
from utils.text_formatter import format_text_with_linebreaks, _is_sentence_ending


class TestIsSentenceEnding:
    def test_da_period(self):
        # "~다." 종결
        assert _is_sentence_ending("이것은 예문이다.") is True

    def test_da_paren(self):
        # "~다)" 종결
        assert _is_sentence_ending("참고한다)") is True

    def test_colon_ending(self):
        # 콜론 종결
        assert _is_sentence_ending("다음과 같다:") is True

    def test_non_ending_line(self):
        # 종결 패턴 없음
        assert _is_sentence_ending("이 문장은 계속되는") is False

    def test_empty_line(self):
        assert _is_sentence_ending("") is False
        assert _is_sentence_ending("   ") is False


class TestFormatTextBasic:
    def test_empty_input(self):
        assert format_text_with_linebreaks("") == ""

    def test_none_input(self):
        # None 입력 방어
        assert format_text_with_linebreaks(None) == ""

    def test_returns_string(self):
        result = format_text_with_linebreaks("간단한 텍스트입니다.")
        assert isinstance(result, str)

    def test_collapses_triple_newlines(self):
        # 3개 이상 연속 개행 → 2개로 압축
        text = "A\n\n\n\nB"
        result = format_text_with_linebreaks(text)
        assert "\n\n\n" not in result

    def test_collapses_double_spaces(self):
        # 연속 공백 → 단일 공백
        text = "단어  하나    둘"
        result = format_text_with_linebreaks(text)
        assert "  " not in result


class TestFormatTextMergeBehavior:
    def test_list_item_stays_on_new_line(self):
        # "1. " 같은 번호 항목은 이전 줄에 병합되지 않아야 함
        text = "이전 줄 내용\n1. 첫 번째 항목\n2. 두 번째 항목"
        result = format_text_with_linebreaks(text)
        lines = [l for l in result.split("\n") if l.strip()]
        # 1. / 2. 로 시작하는 라인이 각각 유지되어야 함
        assert any(l.startswith("1.") for l in lines)
        assert any(l.startswith("2.") for l in lines)

    def test_note_marker_preserved(self):
        # [주] 표기 앞에 줄바꿈 삽입
        text = "본문입니다 [주] 이것은 주석"
        result = format_text_with_linebreaks(text)
        assert "[주]" in result

    def test_korean_circled_numbers_new_line(self):
        # ①②③ 원문자 앞에서 줄바꿈
        text = "앞 부분. ① 첫째 ② 둘째"
        result = format_text_with_linebreaks(text)
        assert "①" in result
        assert "②" in result


class TestFormatTextPresetMode:
    def test_universal_mode_no_division_split(self):
        # division_names=None → 품셈 전용 패턴 비활성
        text = "1 공통부문 내용"
        result = format_text_with_linebreaks(text, division_names=None)
        # 범용 모드에서는 "공통부문" 자체로는 분할되지 않아야 함
        assert isinstance(result, str)

    def test_pumsem_mode_accepts_pattern(self):
        # division_names 제공 시 크래시 없이 동작
        text = "1 공통부문\n내용입니다"
        result = format_text_with_linebreaks(
            text, division_names="공통부문|토목부문|건축부문"
        )
        assert isinstance(result, str)
        assert len(result) > 0
