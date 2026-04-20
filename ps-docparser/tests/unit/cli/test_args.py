import pytest
from cli.args import build_argument_parser


class TestBuildParser:
    def test_build_parser_all_options_present(self):
        parser = build_argument_parser()
        actions = {a.dest for a in parser._actions}
        assert "input" in actions
        assert "engine" in actions
        assert "text_only" in actions
        assert "toc" in actions
        assert "pages" in actions
        assert "output_dir" in actions
        assert "preset" in actions
        assert "output_format" in actions
        assert "force" in actions
        assert "no_cache" in actions

    def test_no_cache_flag_default_false(self):
        parser = build_argument_parser()
        args = parser.parse_args(["dummy.pdf"])
        assert args.no_cache is False

    def test_no_cache_flag_enabled_when_passed(self):
        parser = build_argument_parser()
        args = parser.parse_args(["dummy.pdf", "--no-cache"])
        assert args.no_cache is True
