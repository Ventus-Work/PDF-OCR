"""
batch_test.py — PIPE-BM-PS-*.pdf 배치 OCR 테스트

사용법:
    python batch_test.py [--limit N] [--engine zai]

결과: output/batch_result.tsv, output/batch_summary.txt
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime


PDF_ROOT = Path(r"G:\My Drive\엑셀\00. 회사업무\피에스산업\견적자료\02. 이전견적서\00. 창녕공장\고려아연 배관 Support 제작_추가 2차_ 견적서")
OUTPUT_DIR = Path("output")
SCRIPT = Path(__file__).parent / "main.py"


def find_bom_pdfs(root: Path, limit: int) -> list[Path]:
    pdfs = sorted(root.rglob("PIPE-BM-PS-*.pdf"))
    return pdfs[:limit]


def run_one(pdf: Path, engine: str, output_dir: Path) -> dict:
    """단일 PDF 처리. 결과 dict 반환."""
    cmd = [
        sys.executable, str(SCRIPT),
        str(pdf),
        "--preset", "bom",
        "--engine", engine,
        "--output", "json",
        "--output-dir", str(output_dir),
    ]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=180, env=env,
        )
        elapsed = time.time() - t0
        combined = proc.stdout + proc.stderr

        # 결과 파싱
        bom_rows = ll_rows = 0
        bom_tables = ll_tables = 0
        status = "OK"

        for line in combined.splitlines():
            if "BOM:" in line and "LINE LIST:" in line:
                # "✅ BOM: 6행 / LINE LIST: 2행"
                import re
                m = re.search(r"BOM:\s*(\d+)행\s*/\s*LINE LIST:\s*(\d+)행", line)
                if m:
                    bom_rows, ll_rows = int(m.group(1)), int(m.group(2))
            if "BOM" in line and "개" in line and "LINE LIST" in line:
                # "📦 BOM 1개 / LINE LIST 1개"
                import re
                m = re.search(r"BOM\s*(\d+)개\s*/\s*LINE LIST\s*(\d+)개", line)
                if m:
                    bom_tables, ll_tables = int(m.group(1)), int(m.group(2))

        if proc.returncode != 0 and bom_rows == 0:
            # stderr에 실제 에러가 있는지 확인
            real_errors = [l for l in combined.splitlines()
                           if "Error" in l or "error" in l or "Exception" in l
                           and "UserWarning" not in l
                           and "Pydantic" not in l]
            if real_errors:
                status = "FAIL: " + real_errors[0][:80]

        return {
            "file": pdf.name,
            "status": status,
            "bom_tables": bom_tables,
            "ll_tables": ll_tables,
            "bom_rows": bom_rows,
            "ll_rows": ll_rows,
            "elapsed_s": round(elapsed, 1),
        }

    except subprocess.TimeoutExpired:
        return {
            "file": pdf.name,
            "status": "TIMEOUT (180s)",
            "bom_tables": 0, "ll_tables": 0,
            "bom_rows": 0, "ll_rows": 0,
            "elapsed_s": 180,
        }
    except Exception as e:
        return {
            "file": pdf.name,
            "status": f"ERROR: {e}",
            "bom_tables": 0, "ll_tables": 0,
            "bom_rows": 0, "ll_rows": 0,
            "elapsed_s": round(time.time() - t0, 1),
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5, help="테스트할 PDF 수 (기본 5)")
    parser.add_argument("--engine", default="zai", help="OCR 엔진 (기본 zai)")
    args = parser.parse_args()

    pdfs = find_bom_pdfs(PDF_ROOT, args.limit)
    if not pdfs:
        print("PDF 파일을 찾을 수 없습니다.")
        return

    OUTPUT_DIR.mkdir(exist_ok=True)
    tsv_path = OUTPUT_DIR / "batch_result.tsv"
    summary_path = OUTPUT_DIR / "batch_summary.txt"

    print(f"\n{'='*60}")
    print(f"배치 테스트: {len(pdfs)}개 파일 / 엔진: {args.engine}")
    print(f"{'='*60}\n")

    results = []
    for i, pdf in enumerate(pdfs, 1):
        print(f"[{i}/{len(pdfs)}] {pdf.name} ...", end=" ", flush=True)
        r = run_one(pdf, args.engine, OUTPUT_DIR)
        results.append(r)
        print(f"{r['status']} | BOM {r['bom_rows']}행 / LL {r['ll_rows']}행 | {r['elapsed_s']}s")

    # TSV 저장
    with open(tsv_path, "w", encoding="utf-8") as f:
        f.write("파일명\t상태\tBOM테이블\tLL테이블\tBOM행\tLL행\t소요시간(s)\n")
        for r in results:
            f.write(f"{r['file']}\t{r['status']}\t{r['bom_tables']}\t{r['ll_tables']}\t{r['bom_rows']}\t{r['ll_rows']}\t{r['elapsed_s']}\n")

    # 요약
    ok      = [r for r in results if r["status"] == "OK"]
    fail    = [r for r in results if r["status"] != "OK"]
    tot_bom = sum(r["bom_rows"] for r in ok)
    tot_ll  = sum(r["ll_rows"] for r in ok)
    avg_t   = sum(r["elapsed_s"] for r in results) / len(results)
    zero_bom = [r for r in ok if r["bom_rows"] == 0]

    summary = [
        f"배치 테스트 결과 — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"엔진: {args.engine}",
        f"총 파일: {len(results)}개",
        f"성공: {len(ok)}개 / 실패: {len(fail)}개",
        f"BOM 합계: {tot_bom}행 / LINE LIST 합계: {tot_ll}행",
        f"평균 소요시간: {avg_t:.1f}s / 파일",
        "",
    ]
    if zero_bom:
        summary.append(f"⚠️ BOM 0행 파일 ({len(zero_bom)}개):")
        for r in zero_bom:
            summary.append(f"  - {r['file']}")
    if fail:
        summary.append(f"\n❌ 실패 파일 ({len(fail)}개):")
        for r in fail:
            summary.append(f"  - {r['file']}: {r['status']}")

    summary_text = "\n".join(summary)
    print(f"\n{'='*60}")
    print(summary_text)
    print(f"{'='*60}")
    print(f"\n📄 TSV: {tsv_path}")
    print(f"📄 요약: {summary_path}")

    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary_text)


if __name__ == "__main__":
    main()
