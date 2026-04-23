"""
Manual smoke runner for the current BOM OCR pipeline.

Usage:
    python scripts/manual_ocr_smoke.py path/to/sample.pdf
    python scripts/manual_ocr_smoke.py path/to/sample.pdf --engine gemini
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def run_smoke(pdf_path: Path, engine_name: str = "zai") -> list[dict]:
    from engines.factory import create_engine
    from extractors.bom_converter import to_sections
    from extractors.bom_ocr_retry import extract_bom_with_retry
    from presets.bom import get_bom_keywords, get_image_settings
    from utils.usage_tracker import UsageTracker

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    tracker = UsageTracker()
    engine = create_engine(engine_name, tracker)
    keywords = get_bom_keywords()
    image_settings = get_image_settings()

    result = extract_bom_with_retry(
        engine,
        pdf_path,
        keywords,
        image_settings,
    )
    sections = to_sections(result)

    bom_rows = sum(len(section.rows) for section in result.bom_sections)
    ll_rows = sum(len(section.rows) for section in result.line_list_sections)

    print("\n" + "=" * 60)
    print("  OCR Smoke Test")
    print(f"  PDF      : {pdf_path.name}")
    print(f"  Engine   : {engine_name}")
    print(f"  BOM rows : {bom_rows}")
    print(f"  LL rows  : {ll_rows}")
    print(f"  Sections : {len(sections)}")
    print("=" * 60 + "\n")
    print(json.dumps(sections, ensure_ascii=False, indent=2)[:2000])

    if tracker.call_count > 0:
        print()
        print(tracker.summary())

    return sections


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a manual BOM OCR smoke test.")
    parser.add_argument("pdf", type=Path, help="Path to a sample PDF file.")
    parser.add_argument(
        "--engine",
        default="zai",
        choices=["zai", "gemini", "mistral", "tesseract", "local"],
        help="OCR engine to use.",
    )
    args = parser.parse_args()

    try:
        run_smoke(args.pdf, args.engine)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
