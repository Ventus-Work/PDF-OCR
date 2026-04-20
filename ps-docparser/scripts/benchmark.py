"""
scripts/benchmark.py — Phase 8 성능 벤치마크 스크립트

사용:
    # 1단계: 베이스라인 측정
    python scripts/benchmark.py --pdf sample.pdf --iterations 3 --out baseline.json

    # 2단계: Phase 8 적용 후 측정
    python scripts/benchmark.py --pdf sample.pdf --iterations 3 --out after.json

    # 비교
    python scripts/benchmark.py --compare baseline.json after.json
"""
import argparse
import json
import sys
import time
import tracemalloc
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 (scripts/ 하위에서 실행 가능하도록)
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def measure(pdf_path: str, iterations: int = 3) -> dict:
    """
    PDF 처리 시간과 메모리 피크를 N회 반복 측정하여 통계를 반환한다.

    Why: 단일 측정은 JIT 워밍업 및 OS 캐시 효과로 왜곡됨.
         최소 3회 반복 → min/avg/max로 노이즈 분리.
    """
    from extractors.hybrid_extractor import process_pdf
    from engines.local_engine import LocalEngine

    times, peaks = [], []

    for n in range(iterations):
        tracemalloc.start()
        t0 = time.perf_counter()

        engine = LocalEngine()
        _ = process_pdf(pdf_path, engine)

        elapsed = time.perf_counter() - t0
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        times.append(elapsed)
        peaks.append(peak)
        print(f"  반복 {n+1}/{iterations}: {elapsed:.2f}s, 피크 {peak/1024/1024:.1f}MB")

    return {
        "pdf": str(pdf_path),
        "iterations": iterations,
        "avg_time_sec":    round(sum(times) / len(times), 3),
        "min_time_sec":    round(min(times), 3),
        "max_time_sec":    round(max(times), 3),
        "peak_memory_mb":  round(max(peaks) / (1024 * 1024), 2),
    }


def compare(baseline_path: str, after_path: str) -> None:
    """
    두 측정 결과를 비교하여 개선율을 출력한다.
    """
    base = json.loads(Path(baseline_path).read_text(encoding="utf-8"))
    aft  = json.loads(Path(after_path).read_text(encoding="utf-8"))

    t_base, t_aft = base["avg_time_sec"], aft["avg_time_sec"]
    m_base, m_aft = base["peak_memory_mb"], aft["peak_memory_mb"]

    t_delta = (t_base - t_aft) / t_base * 100 if t_base else 0
    m_delta = (m_base - m_aft) / m_base * 100 if m_base else 0

    print(f"\n{'='*50}")
    print(f"  Phase 8 성능 비교 리포트")
    print(f"{'='*50}")
    print(f"  PDF:       {base['pdf']}")
    print(f"  반복 횟수: baseline={base['iterations']}, after={aft['iterations']}")
    print(f"{'─'*50}")
    print(f"  ⏱  처리 시간: {t_base:.2f}s → {t_aft:.2f}s  ({t_delta:+.1f}%)")
    print(f"  💾 피크 메모리: {m_base:.1f}MB → {m_aft:.1f}MB  ({m_delta:+.1f}%)")
    print(f"{'='*50}\n")


def main():
    ap = argparse.ArgumentParser(description="Phase 8 성능 벤치마크")
    ap.add_argument("--pdf", help="처리할 PDF 파일 경로")
    ap.add_argument("--iterations", type=int, default=3, help="반복 횟수 (기본 3)")
    ap.add_argument("--out", help="결과 저장 경로 (JSON)")
    ap.add_argument(
        "--compare",
        nargs=2,
        metavar=("BASELINE", "AFTER"),
        help="두 측정 결과 비교",
    )
    args = ap.parse_args()

    if args.compare:
        compare(*args.compare)
    elif args.pdf:
        print(f"\n📊 벤치마크 시작: {args.pdf}  ({args.iterations}회 반복)")
        result = measure(args.pdf, args.iterations)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if args.out:
            Path(args.out).write_text(
                json.dumps(result, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"💾 결과 저장: {args.out}")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
