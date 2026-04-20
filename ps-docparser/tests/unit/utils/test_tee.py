import io
import pytest
from utils.tee import Tee


class TestTee:
    def test_writes_to_all_files(self):
        a, b = io.StringIO(), io.StringIO()
        tee = Tee(a, b)
        tee.write("hello")
        assert a.getvalue() == "hello"
        assert b.getvalue() == "hello"

    def test_flush_calls_all(self):
        flushed = []

        class FakeFile:
            def write(self, obj): pass
            def flush(self): flushed.append(True)

        tee = Tee(FakeFile(), FakeFile())
        tee.flush()
        assert len(flushed) == 2
