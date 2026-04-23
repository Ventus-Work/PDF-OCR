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

    def test_isatty_returns_true_when_any_file_isatty(self):
        class FakeFile:
            def __init__(self, is_tty):
                self._is_tty = is_tty

            def write(self, obj):
                pass

            def flush(self):
                pass

            def isatty(self):
                return self._is_tty

        tee = Tee(FakeFile(False), FakeFile(True))
        assert tee.isatty() is True
