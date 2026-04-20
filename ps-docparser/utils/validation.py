"""입력 검증 유틸리티. (spec §3.4)"""

from pathlib import Path

MAX_PDF_SIZE_MB = 500
MAX_PAGES = 2000
MAX_TEXT_LENGTH = 10_000_000


class ValidationError(ValueError):
    """입력 검증 실패 (ParserError와 별도 — 재시도 불가)."""


def validate_pdf_path(path, max_size_mb: int = MAX_PDF_SIZE_MB) -> Path:
    p = Path(path)
    if not p.exists():
        raise ValidationError(f"파일을 찾을 수 없습니다: {path}")
    if not p.is_file():
        raise ValidationError(f"파일이 아닙니다: {path}")
    if p.suffix.lower() != ".pdf":
        raise ValidationError(f"PDF 파일이 아닙니다: {path}")
    size_mb = p.stat().st_size / (1024 * 1024)
    if size_mb > max_size_mb:
        raise ValidationError(
            f"PDF 크기 초과: {size_mb:.1f}MB > {max_size_mb}MB "
            f"(--max-size 옵션으로 상향 가능)"
        )
    return p


def validate_page_count(total_pages: int, max_pages: int = MAX_PAGES) -> None:
    if total_pages > max_pages:
        raise ValidationError(
            f"페이지 수 초과: {total_pages} > {max_pages} "
            f"(--pages 옵션으로 부분 처리 권장)"
        )


def validate_text_length(text: str, max_length: int = MAX_TEXT_LENGTH) -> None:
    if len(text) > max_length:
        raise ValidationError(f"텍스트 길이 초과: {len(text):,} > {max_length:,}")


def validate_output_dir(path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    test_file = p / ".write_check"
    try:
        test_file.touch()
        test_file.unlink()
    except (PermissionError, OSError) as e:
        raise ValidationError(f"출력 디렉토리 쓰기 불가: {path} ({e})")
    return p
