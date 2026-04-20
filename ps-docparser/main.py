"""
main.py — ps-docparser CLI 진입점 (Phase 9 Step 4: 슬림화 완료)

Why: 이 파일은 비즈니스 로직을 포함하지 않는다.
     각 모듈을 import하여 파이프라인을 조립하는 컨트롤러 역할만 한다.
     모든 설계 결정(엔진 선택, 프리셋, 출력 경로 등)을 CLI 인수로 받아
     아래 계층에 전달한다.

흐름:
    1. CLI 인수 파싱 (cli/args.py)
    2. 입력 경로 수집 (단일 파일 / 디렉토리)
    3. 캐시·트래커 초기화
    4. 파일별 PipelineContext 생성 → create_pipeline().run()
    5. BOM 배치 집계 (--preset bom --output excel 시)
    6. 캐시 통계 출력
"""

import sys
import platform
import logging
from datetime import datetime
from pathlib import Path

# ── 프로젝트 루트를 sys.path에 추가 ──
_project_root = Path(__file__).resolve().parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import config
from config import OUTPUT_DIR, POPPLER_PATH, validate_config
from cli.args import build_argument_parser
from pipelines.base import PipelineContext
from pipelines.factory import create_pipeline
from utils.io import ParserError
from utils.tee import Tee
from utils.usage_tracker import UsageTracker
from utils.logging_utils import install_masking_filter


# ────────────────────────────────────────────────────────────
# 내부 헬퍼
# ────────────────────────────────────────────────────────────

def _collect_inputs(args) -> list[Path]:
    """args.input을 파일 목록으로 변환한다 (단일 파일 / 디렉토리)."""
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"오류: 경로를 찾을 수 없습니다: {input_path}")
        sys.exit(1)
    if input_path.is_dir():
        pdf_files = sorted(input_path.glob("*.pdf"))
        if not pdf_files:
            print(f"오류: 디렉토리에 PDF 파일이 없습니다: {input_path}")
            sys.exit(1)
        print(f"\n[배치 모드] {len(pdf_files)}개 PDF 파일 발견 -- {input_path}")
        return pdf_files
    return [input_path]


def _init_cache(args):
    """CACHE_ENABLED 설정 및 --no-cache 플래그에 따라 캐시를 초기화한다."""
    no_cache = getattr(args, "no_cache", False)
    if config.CACHE_ENABLED and not no_cache:
        from cache.table_cache import TableCache
        db_path = config.CACHE_DIR / "table_cache.db"
        cache = TableCache(db_path, ttl_days=config.CACHE_TTL_DAYS)
        cache.clear_expired()
        print(f"[캐시] 활성화 (DB: {db_path.name}, TTL: {config.CACHE_TTL_DAYS}일)")
        return cache
    print("[캐시] 비활성화")
    return None


def _process_single(args, input_path: Path, out_dir: Path, cache, tracker) -> None:
    """단일 파일 파이프라인 실행 — pipelines/ 패키지에 위임한다."""
    ctx = PipelineContext(
        input_path=Path(input_path),
        output_dir=out_dir,
        args=args,
        cache=cache,
        tracker=tracker,
    )
    create_pipeline(ctx).run()


def _run_bom_aggregation(args, out_dir: Path, succeeded: list[str]) -> None:
    """배치 BOM 집계 xlsx 자동 생성 (--preset bom --output excel 시)."""
    print("\n-- BOM 배치 집계 --")
    try:
        from exporters.bom_aggregator import export_aggregated_excel
        date_str = datetime.now().strftime("%Y%m%d")
        json_files: list[Path] = []
        for pdf_name in succeeded:
            stem = Path(pdf_name).stem
            candidates = list(out_dir.glob(f"*_{stem}_bom.json"))
            if candidates:
                json_files.append(sorted(candidates)[-1])

        if json_files:
            agg_path = out_dir / f"{date_str}_BOM집계.xlsx"
            _c = 1
            while agg_path.exists():
                agg_path = out_dir / f"{date_str}_BOM집계_{_c}.xlsx"
                _c += 1
            result = export_aggregated_excel(json_files, agg_path)
            print(f"  집계 파일 생성 완료: {result.name} ({len(json_files)}개 JSON)")
        else:
            print("  집계할 JSON 파일을 찾지 못했습니다. (출력 폴더 확인 필요)")
    except Exception as e:
        import traceback
        print(f"  BOM 집계 중 오류 (배치 결과는 보존됨): {e}")
        traceback.print_exc()
    print("=" * 55)


# ────────────────────────────────────────────────────────────
# 진입점
# ────────────────────────────────────────────────────────────

def main():
    install_masking_filter()

    parser = build_argument_parser()
    args = parser.parse_args()

    # ── 설정 검증 ──
    validation = validate_config(verbose=True)
    if validation["errors"] and not args.force:
        print("설정 오류로 중단합니다. --force 옵션으로 강제 실행 가능.")
        sys.exit(1)

    out_dir = Path(args.output_dir) if args.output_dir else OUTPUT_DIR
    cache = _init_cache(args)
    inputs = _collect_inputs(args)
    is_batch = len(inputs) > 1

    log_file = _project_root / "ps-docparser.log"
    succeeded: list[str] = []
    failed: list[tuple[str, str]] = []

    with open(log_file, "w", encoding="utf-8") as log:
        original_stdout = sys.stdout
        sys.stdout = Tee(sys.stdout, log)

        try:
            if is_batch:
                print(f"\n{'='*55}")
                print(f"ps-docparser 배치 시작 ({len(inputs)}건)")
                print(f"{'='*55}")
                print(f"  출력 폴더: {out_dir}")
                print(f"  플랫폼: {platform.system()}")
                if args.preset:
                    print(f"  프리셋: {args.preset}")
                print()

                for idx, pdf_path in enumerate(inputs, start=1):
                    print(f"[{idx:02d}/{len(inputs):02d}] {pdf_path.name}")
                    tracker = UsageTracker()
                    try:
                        _process_single(args, pdf_path, out_dir, cache, tracker)
                        succeeded.append(pdf_path.name)
                        print("  → 성공\n")
                    except ParserError as e:
                        failed.append((pdf_path.name, str(e)))
                        logging.getLogger(__name__).error("FAIL %s: %s", pdf_path.name, e)
                        print(f"  → 건너뜀: {e}\n")
                    except KeyboardInterrupt:
                        print("\n사용자 중단.")
                        break
                    except Exception as e:
                        import traceback
                        failed.append((pdf_path.name, f"{type(e).__name__}: {e}"))
                        logging.getLogger(__name__).exception("ERROR %s", pdf_path.name)
                        print(f"  → 오류: {e}")
                        traceback.print_exc()
                        print()

                print("=" * 55)
                print(f"배치 완료: 성공 {len(succeeded)}건 / 실패 {len(failed)}건 / 전체 {len(inputs)}건")
                if failed:
                    print("\n[실패 목록]")
                    for fname, reason in failed:
                        print(f"  - {fname}: {reason}")
                print("=" * 55)

                if args.preset == "bom" and args.output_format == "excel" and succeeded:
                    _run_bom_aggregation(args, out_dir, succeeded)

            else:
                input_path = inputs[0]
                print("=" * 55)
                print("ps-docparser 시작")
                print("=" * 55)
                print(f"  입력: {input_path}")
                print(f"  출력 형식: {args.output_format}")
                print(f"  플랫폼: {platform.system()}")
                if input_path.suffix.lower() != ".md":
                    print(f"  Poppler: {POPPLER_PATH or '시스템 PATH 사용'}")
                if args.preset:
                    print(f"  프리셋: {args.preset}")
                print()

                tracker = UsageTracker()
                try:
                    _process_single(args, input_path, out_dir, cache, tracker)
                    print()
                    print("=" * 55)
                    print("완료!")
                    print("=" * 55)
                except ParserError as e:
                    print(f"\n오류: {e}")
                    sys.exit(1)
                except KeyboardInterrupt:
                    print("\n사용자에 의해 중단됨")
                except Exception as e:
                    import traceback
                    logging.getLogger(__name__).error("오류 발생: %s", e)
                    traceback.print_exc()

        except KeyboardInterrupt:
            print("\n\n사용자에 의해 배치가 중단되었습니다.")
            if succeeded:
                print(f"  처리 완료: {len(succeeded)}건 -- {', '.join(succeeded)}")
        finally:
            sys.stdout = original_stdout

    # ── 캐시 통계 출력 ──
    if cache is not None:
        stats = cache.stats()
        print(
            f"[캐시 통계] 적중 {stats['hits']}회 / 미스 {stats['misses']}회 "
            f"/ 적중률 {stats['hit_rate_pct']}% / 저장 {stats['size']}건"
        )
        cache.close()


if __name__ == "__main__":
    main()
