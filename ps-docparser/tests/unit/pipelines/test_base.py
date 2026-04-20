import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from pipelines.base import BasePipeline, PipelineContext


def _make_ctx(tmp_path, pages=None):
    args = MagicMock()
    args.pages = pages
    return PipelineContext(
        input_path=tmp_path / "test.pdf",
        output_dir=tmp_path / "output",
        args=args,
    )


class TestPipelineContext:
    def test_fields_set_correctly(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        assert ctx.input_path == tmp_path / "test.pdf"
        assert ctx.cache is None
        assert ctx.tracker is None

    def test_optional_cache_and_tracker(self, tmp_path):
        args = MagicMock()
        args.pages = None
        cache = object()
        tracker = object()
        ctx = PipelineContext(
            input_path=tmp_path / "f.pdf",
            output_dir=tmp_path,
            args=args,
            cache=cache,
            tracker=tracker,
        )
        assert ctx.cache is cache
        assert ctx.tracker is tracker


class TestBasePipeline:
    def test_cannot_instantiate_abc(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        with pytest.raises(TypeError):
            BasePipeline(ctx)

    def test_get_output_base(self, tmp_path):
        class ConcretePipeline(BasePipeline):
            def run(self): pass

        ctx = _make_ctx(tmp_path)
        p = ConcretePipeline(ctx)
        result = p._get_output_base("_bom")
        # 날짜(8자리) + 줄기 이름 + 접미사 형식 검증
        assert result.parent == tmp_path / "output"
        assert result.name.endswith("_test_bom")
        assert len(result.name.split("_")[0]) == 8  # YYYYMMDD

    def test_resolve_pages_none_when_no_pages(self, tmp_path):
        class ConcretePipeline(BasePipeline):
            def run(self): pass

        ctx = _make_ctx(tmp_path, pages=None)
        p = ConcretePipeline(ctx)
        assert p._resolve_pages() is None
