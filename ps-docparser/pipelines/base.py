"""파이프라인 기반 클래스. (spec §4.2)"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PipelineContext:
    """파이프라인 실행 컨텍스트 — 공유 상태 집중."""
    input_path: Path
    output_dir: Path
    args: object          # argparse.Namespace
    cache: object = None  # TableCache | None
    tracker: object = None


class BasePipeline(ABC):
    def __init__(self, context: PipelineContext):
        self.ctx = context

    @abstractmethod
    def run(self) -> None:
        """파이프라인 실행 (검증 → 추출 → 파싱 → 출력)."""

    def _get_output_base(self, suffix: str = "") -> Path:
        from datetime import datetime
        date_str = datetime.now().strftime("%Y%m%d")
        return self.ctx.output_dir / f"{date_str}_{self.ctx.input_path.stem}{suffix}"

    def _resolve_pages(self) -> list[int] | None:
        if not self.ctx.args.pages:
            return None
        import pdfplumber
        from utils.page_spec import parse_page_spec
        with pdfplumber.open(str(self.ctx.input_path)) as pdf:
            total = len(pdf.pages)
        return parse_page_spec(self.ctx.args.pages, total)
