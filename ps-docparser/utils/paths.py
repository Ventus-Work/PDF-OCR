"""출력 경로 생성 유틸리티. (main.py _get_output_path 추출)"""

from datetime import datetime
from pathlib import Path


def get_output_path(
    output_dir: Path,
    pdf_path: str,
    page_indices: list | None = None,
) -> Path:
    """중복 없는 출력 파일 경로를 생성한다."""
    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_stem = Path(pdf_path).stem
    date_str = datetime.now().strftime("%Y%m%d")

    page_range_str = ""
    if page_indices:
        page_range_str = f"_p{min(page_indices)+1}-{max(page_indices)+1}"

    base_name = f"{date_str}_{pdf_stem}{page_range_str}"
    output_path = output_dir / f"{base_name}.md"

    counter = 1
    while output_path.exists():
        output_path = output_dir / f"{base_name}_{counter}.md"
        counter += 1

    return output_path
