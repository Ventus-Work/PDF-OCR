"""
scripts/preflight.py — 프로덕션 배치 전 사전 점검 (Dry-Run)

실행: python scripts/preflight.py
목적:
    실제 PDF에 대한 배치 실행 전에 환경, 설정, 파일 접근성을 점검하여
    본 배치 실행 중 예상 가능한 오류를 사전 차단한다.

점검 항목:
    ENV-1  .env 파일 존재 및 ZAI_API_KEY 설정 확인
    ENV-2  CACHE_ENABLED / CACHE_TTL_DAYS 설정 확인
    ENV-3  출력 디렉토리 쓰기 권한 확인
    FILE-1 PDF 소스 디렉토리 존재 확인
    FILE-2 BOM 대상 PDF 필터(표지·목록 제외) 결과 확인
    FILE-3 전체 파일 읽기 가능 여부 확인
    MOD-1  bom_extractor 모듈 임포트 가능 확인
    MOD-2  ZaiEngine 초기화 가능 확인 (API 미호출)
    MOD-3  bom_aggregator 임포트 가능 확인
    MOD-4  ExcelExporter 임포트 가능 확인
    DRY-1  배치 명령어 미리보기 출력
"""

import sys
import os
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent  # ps-docparser root
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

results = []

_PDF_BASE = _HERE.parent / "5-2) 450line, Filter press  (FRP DUCT)"

_EXCLUDE_KEYWORDS = [
    "COVER", "DWG LIST", "물량", "SUPPORT_물량"
]

_OUTPUT_DIR = _HERE / "output" / "preflight"


def check(name: str, ok: bool, detail: str = ""):
    status = "PASS" if ok else "FAIL"
    results.append((name, status, detail))
    mark = "[OK]" if ok else "[XX]"
    print(f"  {mark} {name}" + (f"\n       {detail}" if detail else ""))
    return ok


def _is_bom_target(path: Path) -> bool:
    name_upper = path.name.upper()
    return not any(kw.upper() in name_upper for kw in _EXCLUDE_KEYWORDS)


def run_preflight():
    print("\n" + "=" * 62)
    print("  프로덕션 배치 사전 점검 (Dry-Run)")
    print("=" * 62 + "\n")

    print("[ENV-1] .env 및 API 키 설정")
    env_path = _HERE / ".env"
    env_exists = env_path.exists()
    check(".env 파일 존재", env_exists, str(env_path) if not env_exists else "")

    import config
    zai_key_ok = bool(config.ZAI_API_KEY)
    check(
        "ZAI_API_KEY 설정됨",
        zai_key_ok,
        "ZAI_API_KEY 미설정 — .env 파일에 ZAI_API_KEY=... 추가 필요" if not zai_key_ok else
        f"ZAI_API_KEY: ...{config.ZAI_API_KEY[-6:]} (마지막 6자)"
    )

    print("\n[ENV-2] 캐시 설정")
    check("CACHE_ENABLED=True", config.CACHE_ENABLED is True)
    check(f"CACHE_TTL_DAYS={config.CACHE_TTL_DAYS}", config.CACHE_TTL_DAYS > 0)
    check(f"CACHE_DIR 경로: {config.CACHE_DIR.name}", True, str(config.CACHE_DIR))

    print("\n[ENV-3] 출력 디렉토리 쓰기 권한")
    try:
        import tempfile
        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=_OUTPUT_DIR):
            pass
        check("출력 디렉토리 쓰기 가능", True, str(_OUTPUT_DIR))
    except Exception as e:
        check("출력 디렉토리 쓰기 가능", False, str(e))

    print("\n[FILE-1] PDF 소스 디렉토리")
    base_exists = _PDF_BASE.exists()
    check("소스 디렉토리 존재", base_exists, str(_PDF_BASE))

    all_pdfs: list[Path] = []
    bom_pdfs: list[Path] = []
    excluded: list[Path] = []

    if base_exists:
        all_pdfs = sorted(_PDF_BASE.rglob("*.pdf"))
        bom_pdfs = [p for p in all_pdfs if _is_bom_target(p)]
        excluded = [p for p in all_pdfs if not _is_bom_target(p)]
        check(f"전체 PDF 수: {len(all_pdfs)}개", len(all_pdfs) > 0)

        print("\n[FILE-2] BOM 대상 필터링 (표지/목록 제외)")
        check(
            f"BOM 도면 대상: {len(bom_pdfs)}개 (제외: {len(excluded)}개)",
            len(bom_pdfs) > 0,
        )
        if excluded:
            print("       [제외 파일 목록]")
            for p in excluded:
                print(f"         - {p.name}")

        print("\n[FILE-3] 전체 파일 읽기 가능 여부")
        unreadable = []
        for p in bom_pdfs:
            try:
                with open(p, "rb") as f:
                    f.read(512)
            except Exception as e:
                unreadable.append((p.name, str(e)))
        check(
            f"읽기 가능: {len(bom_pdfs) - len(unreadable)}/{len(bom_pdfs)}개",
            len(unreadable) == 0,
            "\n       ".join(f"{n}: {e}" for n, e in unreadable) if unreadable else ""
        )

    print("\n[MOD-1] bom_extractor 모듈")
    try:
        from extractors.bom_extractor import extract_bom_with_retry, to_sections
        check("extractors.bom_extractor 임포트", True)
    except ImportError as e:
        check("extractors.bom_extractor 임포트", False, str(e))

    print("\n[MOD-2] ZaiEngine 초기화 (API 미호출)")
    try:
        from engines.zai_engine import ZaiEngine
        if config.ZAI_API_KEY:
            engine = ZaiEngine(config.ZAI_API_KEY)
            check("ZaiEngine 인스턴스 생성", True)
            check("ZaiEngine.supports_ocr == True", engine.supports_ocr is True)
        else:
            check("ZaiEngine 초기화 (API 키 없음)", False, "ZAI_API_KEY 미설정")
    except Exception as e:
        check("ZaiEngine 초기화", False, str(e))

    print("\n[MOD-3] bom_aggregator")
    try:
        from exporters.bom_aggregator import aggregate_boms, export_aggregated_excel
        check("exporters.bom_aggregator 임포트", True)
        check("aggregate_boms 함수 존재", callable(aggregate_boms))
        check("export_aggregated_excel 함수 존재", callable(export_aggregated_excel))
    except ImportError as e:
        check("exporters.bom_aggregator 임포트", False, str(e))

    print("\n[MOD-4] ExcelExporter")
    try:
        from exporters.excel_exporter import ExcelExporter
        check("exporters.excel_exporter 임포트", True)
    except ImportError as e:
        check("exporters.excel_exporter 임포트", False, str(e))

    print("\n[DRY-1] 권장 배치 실행 명령어")
    print()
    fp_dir = _PDF_BASE / "1. Filter press" / "PDF"
    print(f'  python main.py "{fp_dir}" --preset bom --output excel --engine zai')
    pl_dir = _PDF_BASE / "2. 450 line" / "PDF"
    print(f'  python main.py "{pl_dir}" --preset bom --output excel --engine zai')
    bm_dir = _PDF_BASE / "3. Black Mass" / "2) SUPPORT DETAIL DWG" / "PDF"
    print(f'  python main.py "{bm_dir}" --preset bom --output excel --engine zai')
    print()

    total = len(results)
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = total - passed

    print("=" * 62)
    print(f"  사전 점검 결과: {passed}/{total} 통과 / {failed}건 실패")
    if bom_pdfs:
        print(f"  BOM 배치 대상: {len(bom_pdfs)}개 도면 / 제외: {len(excluded)}개")
    print("=" * 62)

    if failed:
        print("\n[실패 항목 — 배치 실행 전 해결 필요]")
        for name, status, detail in results:
            if status == "FAIL":
                print(f"  ✗ {name}" + (f"\n    {detail}" if detail else ""))
        sys.exit(1)
    else:
        print("\n✅ 모든 사전 점검 통과 — 배치 실행 준비 완료")
        sys.exit(0)


if __name__ == "__main__":
    run_preflight()
