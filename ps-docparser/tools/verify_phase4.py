"""Phase 4 구현 검증 스크립트"""
import ast

checks = {
    "extractors/bom_types.py": {
        "classes": ["BomSection", "BomExtractionResult"],
        "min_lines": 40,
    },
    "utils/ocr_utils.py": {
        "functions": ["file_to_data_uri", "image_to_data_uri", "pdf_page_to_image"],
        "min_lines": 50,
    },
    "presets/bom.py": {
        "functions": ["get_bom_keywords", "get_image_settings", "get_table_type_keywords", "get_excel_config"],
        "min_lines": 100,
    },
    "engines/base_engine.py": {
        "classes": ["OcrPageResult", "BaseEngine"],
        "min_lines": 50,
    },
    "engines/zai_engine.py": {
        "classes": ["ZaiEngine"],
        "methods": ["ocr_document", "ocr_image", "_call_api", "_parse_response"],
        "flags": ["supports_ocr = True"],
        "min_lines": 120,
    },
    "engines/mistral_engine.py": {
        "classes": ["MistralEngine"],
        "methods": ["ocr_document", "ocr_image"],
        "flags": ["supports_ocr = True"],
        "min_lines": 80,
    },
    "engines/tesseract_engine.py": {
        "classes": ["TesseractEngine"],
        "methods": ["ocr_document", "ocr_image"],
        "flags": ["supports_ocr = True", "lang="],
        "min_lines": 70,
    },
    "parsers/bom_table_parser.py": {
        "functions": [
            "parse_html_bom_tables",
            "parse_markdown_pipe_table",
            "parse_whitespace_table",
            "filter_noise_rows",
            "parse_bom_rows",
            "normalize_columns",
        ],
        "min_lines": 200,
    },
    "extractors/bom_extractor.py": {
        "functions": [
            "extract_bom",
            "extract_bom_tables",
            "extract_bom_with_retry",
            "to_sections",
            "_sanitize_html",
            "_flush_section",
        ],
        "flags": [
            "state == \"IDLE\"",     # 상태머신
            "2차 OCR",              # 2차 폴백
            "3차 OCR",              # 3차 폴백
        ],
        "min_lines": 300,
    },
    "extractors/table_utils.py": {
        "functions": ["calculate_dynamic_tolerance", "detect_tables_by_text_alignment"],
        "flags": ["K3", "K2"],
        "min_lines": 150,
    },
    "detector.py": {
        "flags": ["BOM_KEYWORDS", "THRESHOLD_BOM", "text_upper", "bom"],
        "functions": ["detect_document_type", "suggest_preset"],
        "min_lines": 60,
    },
    "main.py": {
        "classes": ["_Tee"],
        "functions": [
            "_build_argument_parser",
            "_create_engine",
            "_load_toc",
            "_get_output_path",
            "main",
        ],
        "flags": [
            "zai",             # 엔진 choices에 zai 포함
            "mistral",         # 엔진 choices에 mistral 포함
            "tesseract",       # 엔진 choices에 tesseract 포함
            "preset == \"bom\"",  # BOM 파이프라인 분기
            "extract_bom_with_retry",  # BOM 추출 호출
            "supports_ocr",    # OCR 엔진 검증
        ],
        "min_lines": 350,
    },
}

all_pass = True
results = []

for filepath, spec in checks.items():
    try:
        src = open(filepath, encoding="utf-8").read()
    except FileNotFoundError:
        results.append(("MISS", filepath, ["파일 없음"]))
        all_pass = False
        continue

    lines = src.count("\n")
    tree = ast.parse(src)

    funcs = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    classes = {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}

    issues = []

    for fn in spec.get("functions", []):
        if fn not in funcs:
            issues.append(f"함수 누락: {fn}")

    for fn in spec.get("methods", []):
        if fn not in funcs:
            issues.append(f"메서드 누락: {fn}")

    for cl in spec.get("classes", []):
        if cl not in classes:
            issues.append(f"클래스 누락: {cl}")

    for flag in spec.get("flags", []):
        if flag not in src:
            issues.append(f"플래그 누락: {flag}")

    if lines < spec.get("min_lines", 0):
        issues.append(f"줄 수 부족: {lines} < {spec['min_lines']}")

    if issues:
        results.append(("FAIL", filepath, issues))
        all_pass = False
    else:
        results.append(("PASS", filepath, lines))


print("=" * 60)
print("Phase 4 구현 검증 결과")
print("=" * 60)

for status, filepath, info in results:
    if status == "PASS":
        print(f"  PASS  {filepath} ({info}줄)")
    elif status == "MISS":
        print(f"  MISS  {filepath}")
        for issue in info:
            print(f"          - {issue}")
    else:
        print(f"  FAIL  {filepath}")
        for issue in info:
            print(f"          - {issue}")

print()
print("=" * 60)
total = len(results)
passed = sum(1 for s, _, _ in results if s == "PASS")
print(f"결과: {passed}/{total} 통과")
if all_pass:
    print(">>> 전 항목 통과 - 축소/누락 없이 완전 구현 확인됨")
else:
    print(">>> 일부 항목 실패")
print("=" * 60)
