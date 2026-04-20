import pytest
from pathlib import Path
from parsers.document_parser import parse_markdown


FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "sample_markdowns"


class TestParseMarkdown:
    def test_empty_returns_empty_list(self):
        res = parse_markdown("")
        assert isinstance(res, list)
        assert res == []

    def test_returns_list_for_valid_input(self):
        md = "# 제목\n\n본문 내용입니다." * 20  # 길이 충족
        res = parse_markdown(md)
        assert isinstance(res, list)

    def test_with_simple_estimate_fixture(self):
        path = FIXTURES / "simple_estimate.md"
        if not path.exists():
            pytest.skip("fixture not yet populated")
        content = path.read_text(encoding="utf-8")
        res = parse_markdown(content)
        assert isinstance(res, list)
        # 목차/제편/제장 분기가 최소 하나는 잡혀야 함
        assert len(res) > 0

    def test_short_input_no_crash(self):
        # 너무 짧은 입력도 크래시 없이 리스트 반환
        for s in ["a", "짧음", "# H"]:
            res = parse_markdown(s)
            assert isinstance(res, list)
