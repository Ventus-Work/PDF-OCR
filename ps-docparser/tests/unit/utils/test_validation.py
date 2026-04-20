import pytest
from pathlib import Path
from utils.validation import (
    ValidationError,
    validate_pdf_path,
    validate_page_count,
    validate_text_length,
    validate_output_dir,
)


class TestValidatePdfPath:
    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(ValidationError, match="찾을 수 없습니다"):
            validate_pdf_path(tmp_path / "missing.pdf")

    def test_non_pdf_raises(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("x")
        with pytest.raises(ValidationError, match="PDF 파일이 아닙니다"):
            validate_pdf_path(f)

    def test_size_limit_raises(self, tmp_path):
        f = tmp_path / "big.pdf"
        f.write_bytes(b"x" * 1024)
        with pytest.raises(ValidationError, match="크기 초과"):
            validate_pdf_path(f, max_size_mb=0)

    def test_valid_pdf_returns_path(self, tmp_path):
        f = tmp_path / "ok.pdf"
        f.write_bytes(b"%PDF-1.4")
        result = validate_pdf_path(f)
        assert result == f


class TestValidatePageCount:
    def test_over_limit_raises(self):
        with pytest.raises(ValidationError, match="페이지 수 초과"):
            validate_page_count(2001, max_pages=2000)

    def test_at_limit_ok(self):
        validate_page_count(2000, max_pages=2000)


class TestValidateTextLength:
    def test_over_limit_raises(self):
        with pytest.raises(ValidationError, match="텍스트 길이 초과"):
            validate_text_length("x" * 101, max_length=100)

    def test_at_limit_ok(self):
        validate_text_length("x" * 100, max_length=100)


class TestValidateOutputDir:
    def test_creates_dir(self, tmp_path):
        new_dir = tmp_path / "new"
        result = validate_output_dir(new_dir)
        assert result.exists()

    @pytest.mark.skipif(
        __import__("sys").platform == "win32",
        reason="Windows admin은 읽기전용 디렉토리도 쓰기 가능",
    )
    def test_readonly_dir_raises(self, tmp_path):
        import stat
        d = tmp_path / "ro"
        d.mkdir()
        d.chmod(stat.S_IREAD | stat.S_IEXEC)
        try:
            with pytest.raises(ValidationError, match="쓰기 불가"):
                validate_output_dir(d)
        finally:
            d.chmod(stat.S_IRWXU)
