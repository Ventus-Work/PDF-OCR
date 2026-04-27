"""Helpers for output naming and compare directory layout."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def get_output_base_name(
    input_path: Path | str,
    page_indices: list[int] | None = None,
) -> str:
    """Return the shared base name used for output bundles."""

    pdf_stem = Path(input_path).stem
    date_str = datetime.now().strftime("%Y%m%d")

    page_range_str = ""
    if page_indices:
        page_range_str = f"_p{min(page_indices) + 1}-{max(page_indices) + 1}"

    return f"{date_str}_{pdf_stem}{page_range_str}"


def get_output_path(
    output_dir: Path,
    pdf_path: str,
    page_indices: list[int] | None = None,
) -> Path:
    """Create a unique markdown output path for the main output bundle."""

    output_dir.mkdir(parents=True, exist_ok=True)
    base_name = get_output_base_name(pdf_path, page_indices)
    output_path = output_dir / f"{base_name}.md"

    counter = 1
    while output_path.exists():
        output_path = output_dir / f"{base_name}_{counter}.md"
        counter += 1

    return output_path


def get_compare_dir(
    output_dir: Path,
    input_path: Path | str,
    page_indices: list[int] | None = None,
) -> Path:
    """Return a unique compare directory for generic baseline outputs."""

    compare_root = Path(output_dir) / "_compare"
    compare_root.mkdir(parents=True, exist_ok=True)

    base_name = get_output_base_name(input_path, page_indices)
    compare_dir = compare_root / base_name

    counter = 1
    while compare_dir.exists():
        compare_dir = compare_root / f"{base_name}_{counter}"
        counter += 1

    return compare_dir
