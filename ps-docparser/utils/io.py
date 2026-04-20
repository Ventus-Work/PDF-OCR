"""
utils/io.py — 파일 I/O 및 파서 기본 예외 클래스 모듈
"""

from pathlib import Path

class ParserError(Exception):
    """
    단일 파일 처리 중 발생한 복구 불가능한 오류.

    배치 루프에서 sys.exit() 대신 예외로 처리하면
    해당 파일만 스킵하고 전체 진행을 계속할 수 있다.
    """
    pass

def _safe_write_text(path: Path, content: str, encoding: str = "utf-8-sig") -> None:
    """
    안전한 파일 쓰기. I/O 예외를 ParserError로 표준화한다.

    Raises:
        ParserError: 파일 쓰기 실패 시 (배치 처리가 해당 파일만 스킵)
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding=encoding) as f:
            f.write(content)
    except PermissionError as e:
        raise ParserError(
            f"파일 쓰기 권한 거부: {path.name}\n"
            f"  → 파일이 다른 프로그램(Excel 등)에서 열려있는지 확인하세요.\n"
            f"  상세: {e}"
        )
    except OSError as e:
        raise ParserError(
            f"파일 I/O 오류: {path.name}\n"
            f"  → 디스크 공간/경로 길이/파일명 문자를 확인하세요.\n"
            f"  상세: {e}"
        )
