# -*- coding: utf-8 -*-
"""
main.py 연결 감사 스크립트

main.py가 직접 또는 간접적으로 사용해야 할 "진입 가능한 모듈"을
열거하고 실제 연결 여부를 판정한다.

판정 기준:
  직접 import  = main.py 텍스트 안에 해당 모듈/함수 언급
  간접 연결    = main.py가 호출하는 모듈 A가 내부에서 B를 import
  불필요       = 데이터클래스, 내부 전용, 테스트 파일
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).parent
main_src = (ROOT / "main.py").read_text(encoding="utf-8")

# ── 1. 모든 .py 파일과 공개 함수/클래스 목록 수집 ──
SKIP_FILES = {"__init__.py", "verify_phase4.py", "main.py"}
SKIP_PREFIXES = ("_test_", "__pycache__")

print("=" * 65)
print("모듈별 공개 인터페이스 현황")
print("=" * 65)

module_info = {}  # filepath -> {name: str, publics: list}

for py_file in sorted(ROOT.rglob("*.py")):
    rel = py_file.relative_to(ROOT)
    parts = rel.parts
    # 스킵 조건
    if py_file.name in SKIP_FILES:
        continue
    if any(py_file.name.startswith(p) for p in SKIP_PREFIXES):
        continue
    if "__pycache__" in parts:
        continue

    try:
        src = py_file.read_text(encoding="utf-8")
        tree = ast.parse(src)
    except Exception as e:
        print(f"  PARSE_ERR  {rel}: {e}")
        continue

    publics = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                publics.append(node.name)
        elif isinstance(node, ast.ClassDef):
            if not node.name.startswith("_"):
                publics.append(node.name)

    module_info[str(rel)] = {
        "file": py_file,
        "publics": publics,
        "src": src,
    }

# ── 2. main.py가 직접 참조하는 모듈 문자열 수집 ──
# import 문 파싱
main_tree = ast.parse(main_src)
main_imports = set()  # "engines.gemini_engine", "extractors.bom_extractor" 등
for node in ast.walk(main_tree):
    if isinstance(node, ast.Import):
        for alias in node.names:
            main_imports.add(alias.name)
    elif isinstance(node, ast.ImportFrom):
        if node.module:
            main_imports.add(node.module)

# ── 3. main.py 텍스트에서 직접 언급된 모듈 파일명 파악 ──
# (동적 import도 잡기 위해 문자열 검색 병행)
main_lines_upper = main_src  # 원문 그대로 (대소문자 유지)

# ── 4. 각 모듈 판정 ──
print()
print(f"{'모듈 파일':45}  {'상태':12}  공개 함수/클래스")
print("-" * 65)

ALWAYS_INDIRECT = {
    # 내부 전용 / 데이터클래스 / 유틸 (main이 직접 호출 불필요)
    "extractors/bom_types.py":        "간접(bom_extractor가 사용)",
    "utils/ocr_utils.py":             "간접(zai/mistral/bom_extractor 사용)",
    "parsers/bom_table_parser.py":    "간접(bom_extractor가 사용)",
    "parsers/section_splitter.py":    "간접(document_parser 사용)",
    "parsers/table_parser.py":        "간접(document_parser 사용)",
    "parsers/text_cleaner.py":        "간접(document_parser 사용)",
    "exporters/base_exporter.py":     "간접(excel/json_exporter 상속)",
    "utils/markers.py":               "간접(extractors 내부 사용)",
    "utils/text_formatter.py":        "간접(extractors 내부 사용)",
    "extractors/toc_parser.py":       "직접(toc_parser_module로 import)",
    "extractors/table_utils.py":      "간접(hybrid_extractor 사용)",
    "engines/base_engine.py":         "간접(각 엔진이 상속)",
}

issues = []  # 연결 누락 의심 항목

for rel_str, info in module_info.items():
    rel_unix = rel_str.replace("\\", "/")
    publics_str = ", ".join(info["publics"][:4])
    if len(info["publics"]) > 4:
        publics_str += f" 외 {len(info['publics'])-4}개"

    # 직접 import 확인
    # 모듈 경로를 Python import 스타일로 변환
    import_style = rel_unix.replace("/", ".").replace(".py", "")

    is_direct = (import_style in main_imports) or (import_style in main_src)

    # 파일명으로도 검색 (동적 import 대응)
    basename_no_ext = Path(rel_unix).stem
    is_mentioned = (basename_no_ext in main_src)

    # 간접 연결 여부
    indirect_note = ALWAYS_INDIRECT.get(rel_unix)

    if indirect_note:
        status = indirect_note
    elif is_direct or is_mentioned:
        status = "직접 연결 OK"
    else:
        status = "!!! 연결 없음 !!!"
        issues.append((rel_unix, info["publics"]))

    flag = "  " if "연결 없음" not in status else "!!"
    print(f"{flag} {rel_unix:43}  {status[:30]}")

# ── 5. 결론 ──
print()
print("=" * 65)
print("연결 감사 결론")
print("=" * 65)

if not issues:
    print("  모든 모듈이 main.py에 직접 또는 간접으로 연결되어 있습니다.")
else:
    print(f"  연결 누락 의심 {len(issues)}건:")
    for rel, publics in issues:
        print(f"    - {rel}")
        print(f"      공개 함수: {', '.join(publics[:6])}")
    print()
    print("  위 모듈이 실제로 필요한지 기술서와 대조 확인 필요.")

print("=" * 65)
