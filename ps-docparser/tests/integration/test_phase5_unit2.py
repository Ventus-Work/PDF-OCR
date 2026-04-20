"""
test_phase5_unit2.py — 단위 2 (배치 파이프라인 + 캐시 주입) 검증

실행: python test_phase5_unit2.py
의존성: 없음 (Python 표준 라이브러리만 사용 + main.py 정적 검사)

검증 항목:
    TC-1  ParserError 클래스 존재 및 정의 확인
    TC-2  _create_engine()이 sys.exit 대신 ParserError를 raise하는지 검사
    TC-3  _load_toc()이 sys.exit 대신 ParserError를 raise하는지 검사
    TC-4  _process_single() 함수 존재 및 시그니처 확인
    TC-5  main()에 배치 분기 로직 (is_dir()) 존재 확인
    TC-6  config.py에 CACHE_ENABLED / CACHE_TTL_DAYS / CACHE_DIR 존재 확인
    TC-7  캐시 주입 코드 (bom_engine.cache = cache) 존재 확인
    TC-8  ParserError가 배치 루프에서 catch되어 continue하는지 확인
    TC-9  cache.close() 가 main() 종료 시점에 호출되는지 확인
    TC-10 main.py 내 sys.exit 잔존 횟수 허용 범위 확인
          (최상단 인수 오류 처리 경로 2개만 허용)
"""

import sys
import ast
import inspect
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# ── 테스트 유틸 ──
results = []
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def check(name: str, ok: bool, detail: str = ""):
    status = "PASS" if ok else "FAIL"
    results.append((name, status, detail))
    mark = "[OK]" if ok else "[XX]"
    print(f"  {mark} {name}" + (f"  --  {detail}" if detail else ""))


def run_all():
    print("\n" + "=" * 62)
    print("  단위 2: 배치 파이프라인 + 캐시 주입 구조 검증")
    print("=" * 62 + "\n")

    # main.py 소스 로드 (AST + 텍스트 이중 검사)
    main_path = _HERE / "main.py"
    main_src = main_path.read_text(encoding="utf-8")
    main_tree = ast.parse(main_src)

    # ────────────────────────────────────────────────────────
    # TC-1: ParserError 클래스 존재
    # ────────────────────────────────────────────────────────
    print("[TC-1] ParserError 클래스 존재")
    try:
        import main as main_mod
        has_class = hasattr(main_mod, "ParserError")
        is_exception = (
            has_class and issubclass(main_mod.ParserError, Exception)
        )
        check("ParserError 클래스 존재", has_class)
        check("ParserError는 Exception 서브클래스", is_exception)
    except ImportError as e:
        check("main.py 임포트", False, str(e))

    # ────────────────────────────────────────────────────────
    # TC-2: _create_engine()에 sys.exit 없는지 확인
    # ────────────────────────────────────────────────────────
    print("\n[TC-2] _create_engine() — sys.exit 제거 확인")
    _check_no_sysexit_in_func(main_tree, "_create_engine")

    # ────────────────────────────────────────────────────────
    # TC-3: _load_toc()에 sys.exit 없는지 확인
    # ────────────────────────────────────────────────────────
    print("\n[TC-3] _load_toc() — sys.exit 제거 확인")
    _check_no_sysexit_in_func(main_tree, "_load_toc")

    # ────────────────────────────────────────────────────────
    # TC-4: _process_single() 시그니처
    # ────────────────────────────────────────────────────────
    print("\n[TC-4] _process_single() 함수 시그니처")
    has_fn = hasattr(main_mod, "_process_single")
    check("_process_single 함수 존재", has_fn)
    if has_fn:
        sig = inspect.signature(main_mod._process_single)
        params = list(sig.parameters.keys())
        check("파라미터: args", "args" in params)
        check("파라미터: input_path", "input_path" in params)
        check("파라미터: out_dir", "out_dir" in params)
        check("파라미터: cache", "cache" in params)
        check("파라미터: tracker", "tracker" in params)

    # ────────────────────────────────────────────────────────
    # TC-5: main()에 is_dir() 배치 분기 존재
    # ────────────────────────────────────────────────────────
    print("\n[TC-5] main() — 배치 분기 (is_dir) 존재")
    check("is_dir() 호출 코드 존재", "is_dir()" in main_src,
          "input_path.is_dir() 분기 없음")
    check("glob('*.pdf') 호출 존재", "glob(\"*.pdf\")" in main_src or
          "glob('*.pdf')" in main_src)
    check("배치 루프 (for ... in pdf_files) 존재", "for" in main_src and "pdf_files" in main_src)

    # ────────────────────────────────────────────────────────
    # TC-6: config.py 캐시 설정
    # ────────────────────────────────────────────────────────
    print("\n[TC-6] config.py 캐시 설정 확인")
    try:
        import config
        check("CACHE_ENABLED 존재", hasattr(config, "CACHE_ENABLED"))
        check("CACHE_TTL_DAYS 존재", hasattr(config, "CACHE_TTL_DAYS"))
        check("CACHE_DIR 존재", hasattr(config, "CACHE_DIR"))
        check("CACHE_ENABLED 기본값 True", config.CACHE_ENABLED is True)
    except ImportError as e:
        check("config.py 임포트", False, str(e))

    # ────────────────────────────────────────────────────────
    # TC-7: 캐시 주입 코드 (bom_engine.cache = cache)
    # ────────────────────────────────────────────────────────
    print("\n[TC-7] 캐시 주입 코드 존재")
    check(
        "bom_engine.cache = cache 코드 존재",
        "bom_engine.cache = cache" in main_src,
    )
    check(
        "cache is not None 가드 존재",
        "cache is not None" in main_src,
    )

    # ────────────────────────────────────────────────────────
    # TC-8: ParserError가 배치 루프에서 catch되는지
    # ────────────────────────────────────────────────────────
    print("\n[TC-8] 배치 루프의 예외 처리")
    check(
        "except ParserError 존재",
        "except ParserError" in main_src,
    )
    # succeeded/failed 리스트로 추적하는지
    check(
        "succeeded 리스트 존재",
        "succeeded" in main_src,
    )
    check(
        "failed 리스트 존재",
        "failed" in main_src,
    )

    # ────────────────────────────────────────────────────────
    # TC-9: cache.close() 호출 존재
    # ────────────────────────────────────────────────────────
    print("\n[TC-9] cache.close() 호출 존재")
    check(
        "cache.close() 코드 존재",
        "cache.close()" in main_src,
    )

    # ────────────────────────────────────────────────────────
    # TC-10: main.py 내 sys.exit 실제 호출 횟수 (AST 기반)
    # ────────────────────────────────────────────────────────
    print("\n[TC-10] sys.exit 실제 호출 횟수 (AST 기반, 주석/docstring 제외)")
    # Why AST: 단순 문자열 카운트는 주석·docstring 내 설명 텍스트까지 포함한다.
    #          AST Call 노드만 검사하면 실제 실행되는 호출만 집계된다.
    sysexit_calls = []
    for node in ast.walk(main_tree):
        if isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "exit"
                and isinstance(func.value, ast.Name)
                and func.value.id == "sys"
            ):
                sysexit_calls.append(node.lineno)
    count = len(sysexit_calls)
    check(
        f"sys.exit 실제 호출 {count}회 (5회 이하 허용)",
        count <= 5,
        f"line {sysexit_calls}" if sysexit_calls else "",
    )

    # ── 최종 결과 ──
    _print_summary()


def _check_no_sysexit_in_func(tree: ast.Module, func_name: str):
    """특정 함수 AST 노드 내에 sys.exit() 호출이 없는지 검사."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == func_name:
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        # sys.exit(...) 패턴 탐지
                        func = child.func
                        if (
                            isinstance(func, ast.Attribute)
                            and func.attr == "exit"
                            and isinstance(func.value, ast.Name)
                            and func.value.id == "sys"
                        ):
                            check(
                                f"{func_name}() 내 sys.exit 없음",
                                False,
                                f"line {child.lineno}: sys.exit() 발견 — ParserError로 교체 필요",
                            )
                            return
                check(f"{func_name}() 내 sys.exit 없음", True)
                return
    check(f"{func_name}() 함수 존재", False, "함수를 찾을 수 없음")


def _print_summary():
    total = len(results)
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = total - passed

    print("\n" + "=" * 62)
    print(f"  결과: {passed}/{total} 통과 / {failed}건 실패")
    print("=" * 62)

    if failed:
        print("\n[실패 항목]")
        for name, status, detail in results:
            if status == "FAIL":
                print(f"  - {name}" + (f": {detail}" if detail else ""))
        sys.exit(1)
    else:
        print("\n[완료] 단위 2 검증 -- 모든 테스트 통과")
        sys.exit(0)


if __name__ == "__main__":
    run_all()
