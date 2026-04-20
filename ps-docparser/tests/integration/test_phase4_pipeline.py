# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
"""
T1: Phase 4 단위 테스트 (API 키 불필요)

테스트 항목:
  T1-1: BomSection / BomExtractionResult 데이터클래스
  T1-2: bom_table_parser — Markdown 파이프 파싱
  T1-3: bom_table_parser — HTML 테이블 파싱
  T1-4: bom_table_parser — normalize_columns
  T1-5: bom_table_parser — filter_noise_rows
  T1-6: bom_extractor — _sanitize_html
  T1-7: bom_extractor — extract_bom 상태머신 (앵커 있는 케이스)
  T1-8: bom_extractor — extract_bom 상태머신 (앵커 없는 케이스)
  T1-9: bom_extractor — to_sections Phase2 호환 구조
  T1-10: detector — BOM 키워드 감지
  T1-11: presets.bom — 인터페이스 확인
  T1-12: config — ZAI/MISTRAL/TESSERACT 변수 로딩
"""
import sys
import traceback

PASS = []
FAIL = []


def test(name, fn):
    try:
        fn()
        print(f"  PASS  {name}")
        PASS.append(name)
    except Exception as e:
        msg = str(e)
        print(f"  FAIL  {name}")
        print(f"         {msg}")
        FAIL.append((name, msg))


# ─── T1-1: 데이터클래스 ───────────────────────────────────────────
def t1_1():
    from extractors.bom_types import BomSection, BomExtractionResult
    s = BomSection(section_type="bom", headers=["S/N", "SIZE"], rows=[["1", "100A"]])
    assert s.parsed_row_count == 1
    assert s.raw_row_count == 0  # 기본값

    r = BomExtractionResult(bom_sections=[s])
    assert r.has_bom
    assert r.total_bom_rows == 1
    assert not r.has_line_list


# ─── T1-2: Markdown 파이프 파싱 ──────────────────────────────────
def t1_2():
    from parsers.bom_table_parser import parse_markdown_pipe_table
    text = """
| S/N | SIZE  | MAT'L | Q'TY |
|-----|-------|-------|------|
| 1   | 100A  | SS304 | 2    |
| 2   | 150A  | SS304 | 1    |
"""
    rows = parse_markdown_pipe_table(text)
    assert len(rows) == 3, f"예상 3행(헤더포함), 실제 {len(rows)}"
    assert rows[0][0] == "S/N"
    assert rows[1][2] == "SS304"


# ─── T1-3: HTML 테이블 파싱 ──────────────────────────────────────
def t1_3():
    from parsers.bom_table_parser import parse_html_bom_tables
    from presets.bom import get_bom_keywords
    kw = get_bom_keywords()

    html = """
<table>
<tr><th>S/N</th><th>SIZE</th><th>Q'TY</th></tr>
<tr><td>1</td><td>100A</td><td>2</td></tr>
<tr><td>2</td><td>150A</td><td>1</td></tr>
</table>
"""
    result = parse_html_bom_tables(html, kw)
    assert result.has_bom, "BOM 감지 실패"
    assert result.total_bom_rows >= 2, f"행 수 부족: {result.total_bom_rows}"


# ─── T1-4: normalize_columns ─────────────────────────────────────
def t1_4():
    from parsers.bom_table_parser import normalize_columns
    rows = [
        ["A", "B", "C"],
        ["1", "2"],          # 짧음 → 패딩
        ["x", "y", "z", "w"],  # 긺 → 병합
    ]
    result = normalize_columns(rows, reference_col_count=3)
    assert all(len(r) == 3 for r in result), f"정규화 실패: {result}"


# ─── T1-5: filter_noise_rows ─────────────────────────────────────
def t1_5():
    from parsers.bom_table_parser import filter_noise_rows
    rows = [
        ["1", "100A", "2"],
        ["DRW'D", "CHK'D", "APP'D"],   # 노이즈
        ["", "", ""],                    # 빈 행
        ["2", "150A", "1"],
    ]
    result = filter_noise_rows(rows, ["DRW'D", "CHK'D"])
    assert len(result) == 2, f"필터 실패: {result}"
    assert result[0][0] == "1"
    assert result[1][0] == "2"


# ─── T1-6: _sanitize_html ────────────────────────────────────────
def t1_6():
    from extractors.bom_extractor import _sanitize_html
    html = "<table><tr><td>S/N</td><td>SIZE</td></tr><tr><td>1</td><td>100A</td></tr></table>"
    result = _sanitize_html(html)
    assert "|" in result, "파이프 변환 실패"
    assert "<td>" not in result, "HTML 태그 잔존"


# ─── T1-7: 상태머신 — 앵커 있음 ─────────────────────────────────
def t1_7():
    from extractors.bom_extractor import extract_bom
    from presets.bom import get_bom_keywords
    kw = get_bom_keywords()

    text = """
BILL OF MATERIALS

| S/N | SIZE | SPEC   | Q'TY |
|-----|------|--------|------|
| 1   | 100A | SS304  | 2    |
| 2   | 150A | SS304  | 1    |

TOTAL WEIGHT: 45 KG
"""
    result = extract_bom(text, kw)
    assert result.has_bom, "BOM 감지 실패"
    assert result.total_bom_rows >= 2, f"행 수: {result.total_bom_rows}"


# ─── T1-8: 상태머신 — 앵커 없음 (헤더 직접 감지) ────────────────
def t1_8():
    from extractors.bom_extractor import extract_bom
    from presets.bom import get_bom_keywords
    kw = get_bom_keywords()

    text = """
| MARK | SIZE  | SPECIFICATION | Q'TY | WEIGHT |
|------|-------|---------------|------|--------|
| A    | 50A   | CS            | 4    | 1.2    |
| B    | 80A   | CS            | 2    | 0.8    |
"""
    result = extract_bom(text, kw)
    assert result.has_bom, f"앵커 없는 BOM 감지 실패 (bom_sections={result.bom_sections})"


# ─── T1-9: to_sections Phase2 호환 구조 ─────────────────────────
def t1_9():
    from extractors.bom_extractor import to_sections
    from extractors.bom_types import BomSection, BomExtractionResult

    bom = BomSection(
        section_type="bom",
        headers=["S/N", "SIZE", "Q'TY"],
        rows=[["1", "100A", "2"], ["2", "150A", "1"]],
        raw_row_count=2,
    )
    result = BomExtractionResult(bom_sections=[bom])
    sections = to_sections(result)

    assert len(sections) == 1
    s = sections[0]
    assert s["section_id"] == "BOM-1"
    assert s["tables"][0]["type"] == "BOM_자재"
    assert len(s["tables"][0]["rows"]) == 2
    # Phase2 호환 필드 확인
    for field in ("clean_text", "notes", "conditions", "cross_references"):
        assert field in s, f"필드 누락: {field}"


# ─── T1-10: detector BOM 감지 ────────────────────────────────────
def t1_10():
    from detector import detect_document_type, suggest_preset

    bom_text = "BILL OF MATERIALS\nS/N SIZE Q'TY MAT'L\n1 100A SS304 2"
    doc_type = detect_document_type(bom_text)
    assert "bom" in doc_type, f"BOM 미감지: {doc_type}"

    suggestion = suggest_preset(bom_text)
    assert suggestion is not None, "suggest_preset이 None 반환"
    assert "bom" in suggestion.lower(), f"bom 제안 없음: {suggestion}"


# ─── T1-11: presets.bom 인터페이스 ──────────────────────────────
def t1_11():
    from presets.bom import (
        get_bom_keywords, get_image_settings,
        get_table_type_keywords, get_excel_config, get_division_names,
    )
    kw = get_bom_keywords()
    assert "anchor_bom" in kw
    assert "kill" in kw
    assert "noise_row" in kw

    img = get_image_settings()
    assert img["default_dpi"] == 400
    assert img["retry_dpi"] == 600

    assert get_table_type_keywords() is not None
    assert get_excel_config() is None   # BOM은 현재 커스텀 없음
    assert get_division_names() is None


# ─── T1-12: config 변수 ──────────────────────────────────────────
def t1_12():
    import config
    # ZAI/MISTRAL 키가 .env에 있으면 None이 아니어야 함
    # 없으면 None이어도 OK (경고용)
    assert hasattr(config, "ZAI_API_KEY"), "ZAI_API_KEY 없음"
    assert hasattr(config, "MISTRAL_API_KEY"), "MISTRAL_API_KEY 없음"
    assert hasattr(config, "TESSERACT_PATH"), "TESSERACT_PATH 없음"
    assert hasattr(config, "BOM_DEFAULT_ENGINE"), "BOM_DEFAULT_ENGINE 없음"
    print(f"\n        ZAI_API_KEY={bool(config.ZAI_API_KEY and 'ZAI' not in config.ZAI_API_KEY)}")
    print(f"        MISTRAL_API_KEY={bool(config.MISTRAL_API_KEY and 'MISTRAL' not in config.MISTRAL_API_KEY)}")
    print(f"        TESSERACT_PATH={config.TESSERACT_PATH}")
    print(f"        BOM_DEFAULT_ENGINE={config.BOM_DEFAULT_ENGINE}")


# ─── 실행 ────────────────────────────────────────────────────────
print("=" * 60)
print("T1: Phase 4 단위 테스트")
print("=" * 60)

test("T1-1  BomSection/BomExtractionResult 데이터클래스", t1_1)
test("T1-2  Markdown 파이프 테이블 파싱", t1_2)
test("T1-3  HTML <table> BOM 파싱", t1_3)
test("T1-4  normalize_columns (패딩/병합)", t1_4)
test("T1-5  filter_noise_rows", t1_5)
test("T1-6  _sanitize_html HTML->파이프", t1_6)
test("T1-7  상태머신 - BILL OF MATERIALS 앵커", t1_7)
test("T1-8  상태머신 - 앵커 없는 헤더 직접 감지", t1_8)
test("T1-9  to_sections Phase2 호환 구조", t1_9)
test("T1-10 detector BOM 감지 + suggest_preset", t1_10)
test("T1-11 presets.bom 인터페이스", t1_11)
test("T1-12 config ZAI/MISTRAL/TESSERACT 변수", t1_12)

print()
print("=" * 60)
print(f"결과: {len(PASS)}/{len(PASS)+len(FAIL)} PASS")
if FAIL:
    print("실패 항목:")
    for name, msg in FAIL:
        print(f"  - {name}: {msg}")
print("=" * 60)
