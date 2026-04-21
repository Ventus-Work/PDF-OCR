"""scripts/create_minimal_pdf.py — 테스트용 minimal.pdf 생성.

실행: python scripts/create_minimal_pdf.py
출력: tests/fixtures/sample_pdfs/minimal.pdf (텍스트 전용, ≤10KB)
"""

from pathlib import Path
from fpdf import FPDF

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "sample_pdfs" / "minimal.pdf"


def main():
    pdf = FPDF()
    pdf.set_margins(20, 20, 20)
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)

    lines = [
        "Test Document - ps-docparser smoke test",
        "",
        "Item A  100",
        "Item B  200",
        "Item C  300",
        "",
        "Total  600",
    ]
    for line in lines:
        pdf.cell(0, 8, line, new_x="LMARGIN", new_y="NEXT")

    pdf.add_page()
    pdf.cell(0, 8, "Page 2 content only", new_x="LMARGIN", new_y="NEXT")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUT))
    size_kb = OUT.stat().st_size / 1024
    print(f"created: {OUT}  ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
