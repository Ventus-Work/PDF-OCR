"""
extractors/bom_extractor.py 단위 테스트 — Phase 10 Step 10-3
목표 커버리지: 26.91% → 60%+

커버 전략:
  1. _sanitize_html          ✅ 기존 유지
  2. extract_bom 상태머신     ★ 전이 경로 전수 커버
  3. extract_bom_tables      ★ 3단계 폴백 (HTML mock)
  4. _get_table_bbox_scaled  ★ 순수 함수 케이스
  5. to_sections             ★ 결과→JSON 변환
  6. extract_bom_with_retry  ⚪ 엔진+PDF 의존 → 스킵(slow 전용)
"""
import pytest
from unittest.mock import MagicMock, patch

from extractors.bom_extractor import (
    _sanitize_html,
    extract_bom,
    extract_bom_tables,
    _get_table_bbox_scaled,
    to_sections,
)
from extractors.bom_types import BomSection, BomExtractionResult


# ══════════════════════════════════════════════════════════
# 공용 픽스처
# ══════════════════════════════════════════════════════════

@pytest.fixture
def kw():
    """상태머신 테스트용 최소 키워드 세트."""
    return {
        "anchor_bom":   ["BILL OF MATERIAL", "BOM"],
        "anchor_ll":    ["LINE LIST"],
        "bom_header_a": ["ITEM"],
        "bom_header_b": ["SIZE"],
        "bom_header_c": ["QTY"],
        "ll_header_a":  ["LINE NO", "LINE"],
        "ll_header_b":  ["FROM"],
        "ll_header_c":  ["TO"],
        "kill":         ["NOTES", "END OF BOM"],
        "noise_row":    ["소계", "합계"],
        "rev_markers":  ["REV", "DATE", "BY"],
    }


def _make_bom_result(n_bom=1, n_ll=0, rows=None):
    """테스트용 BomExtractionResult 생성."""
    rows = rows or [["1", "100A", "5"]]
    bom_secs = [BomSection("bom", ["ITEM", "SIZE", "QTY"], rows, raw_row_count=len(rows))] * n_bom
    ll_secs  = [BomSection("line_list", ["LINE NO", "SIZE", "FROM", "TO"],
                           [["L-001", "100A", "P-101", "P-102"]], raw_row_count=1)] * n_ll
    return BomExtractionResult(bom_sections=bom_secs, line_list_sections=ll_secs)


# ══════════════════════════════════════════════════════════
# _sanitize_html (기존 유지 + 보완)
# ══════════════════════════════════════════════════════════

class TestSanitizeHtml:
    def test_basic_table_to_pipe(self):
        html = "<table><tr><td>SIZE</td><td>PIPE</td></tr></table>"
        result = _sanitize_html(html)
        assert "<table>" not in result
        assert "SIZE | PIPE" in result

    def test_rows_split_on_tr_close(self):
        html = "<tr><td>A</td></tr><tr><td>B</td></tr>"
        lines = [l for l in _sanitize_html(html).split("\n") if l.strip()]
        assert len(lines) == 2

    def test_entities_unescaped(self):
        result = _sanitize_html("Size&amp;Type &#x27;Q&#x27; &nbsp;")
        assert "&amp;" not in result
        assert "&" in result

    def test_empty_input_passthrough(self):
        assert _sanitize_html("") == ""

    def test_nested_tags_removed(self):
        result = _sanitize_html("<div><b>TEXT</b></div>")
        assert "<" not in result
        assert "TEXT" in result

    def test_whitespace_compressed(self):
        result = _sanitize_html("A     B")
        assert "A B" in result


# ══════════════════════════════════════════════════════════
# extract_bom — 상태머신 전이 경로
# ══════════════════════════════════════════════════════════

class TestExtractBomStateMachine:

    # ── 기본 케이스 ──────────────────────────────────────

    def test_empty_text_no_sections(self, kw):
        res = extract_bom("", kw)
        assert res.bom_sections == []
        assert res.line_list_sections == []

    def test_no_anchor_no_sections(self, kw):
        res = extract_bom("일반 텍스트입니다.", kw)
        assert not res.has_bom
        assert not res.has_line_list

    # ── IDLE → BOM_SCAN → BOM_DATA → 데이터 수집 ────────

    def test_full_bom_flow_pipe(self, kw):
        text = (
            "BILL OF MATERIAL\n"
            "ITEM | SIZE | QTY\n"
            "1 | 100A | 5\n"
            "2 | 50A  | 3\n"
        )
        res = extract_bom(text, kw)
        assert res.has_bom
        assert res.total_bom_rows == 2

    def test_bom_anchor_case_insensitive(self, kw):
        text = (
            "bill of material\n"
            "ITEM | SIZE | QTY\n"
            "1 | 100A | 5\n"
        )
        res = extract_bom(text, kw)
        assert res.has_bom

    def test_bom_rows_content(self, kw):
        text = (
            "BOM\n"
            "ITEM | SIZE | QTY\n"
            "1 | 6\" PIPE | 10\n"
        )
        res = extract_bom(text, kw)
        assert res.has_bom
        row = res.bom_sections[0].rows[0]
        assert any("PIPE" in c or "6" in c for c in row)

    # ── IDLE → LL_SCAN → LL_DATA → 데이터 수집 ──────────

    def test_full_ll_flow(self, kw):
        text = (
            "LINE LIST\n"
            "LINE NO | FROM | TO | SIZE\n"
            "L-001 | P-101 | P-102 | 100A\n"
            "L-002 | P-103 | P-104 | 50A\n"
        )
        res = extract_bom(text, kw)
        assert res.has_line_list
        assert res.total_ll_rows == 2

    # ── IDLE → BOM_DATA 직접 (앵커 없이 헤더 즉시 감지) ─

    def test_direct_bom_header_detection_without_anchor(self, kw):
        # 앵커 없이 ITEM|SIZE|QTY 헤더가 첫 줄에 등장
        text = (
            "ITEM | SIZE | QTY\n"
            "1 | 100A | 5\n"
        )
        res = extract_bom(text, kw)
        assert res.has_bom

    # ── 킬 키워드로 섹션 종료 ────────────────────────────

    def test_kill_keyword_terminates_section(self, kw):
        text = (
            "BOM\n"
            "ITEM | SIZE | QTY\n"
            "1 | 100A | 5\n"
            "NOTES\n"          # kill keyword → flush
            "2 | 50A | 3\n"    # 이 행은 수집 안 됨
        )
        res = extract_bom(text, kw)
        assert res.has_bom
        assert res.total_bom_rows == 1  # NOTES 이전 1행만

    def test_end_of_bom_kill_keyword(self, kw):
        text = (
            "BOM\n"
            "ITEM | SIZE | QTY\n"
            "1 | 100A | 5\n"
            "END OF BOM\n"
        )
        res = extract_bom(text, kw)
        assert res.total_bom_rows == 1

    # ── 빈 행 2연속으로 섹션 종료 ────────────────────────

    def test_double_blank_terminates_section(self, kw):
        text = (
            "BOM\n"
            "ITEM | SIZE | QTY\n"
            "1 | 100A | 5\n"
            "\n"
            "\n"               # 2연속 빈 행 → flush
            "2 | 50A | 3\n"    # 이 행은 새 섹션 없으므로 수집 안 됨
        )
        res = extract_bom(text, kw)
        assert res.total_bom_rows == 1

    def test_single_blank_not_terminate(self, kw):
        text = (
            "BOM\n"
            "ITEM | SIZE | QTY\n"
            "1 | 100A | 5\n"
            "\n"               # 빈 행 1개 → 유지
            "2 | 50A | 3\n"
        )
        res = extract_bom(text, kw)
        assert res.total_bom_rows == 2

    # ── REV 헤더 감지로 섹션 종료 ────────────────────────

    def test_rev_header_terminates_section(self, kw):
        text = (
            "BOM\n"
            "ITEM | SIZE | QTY\n"
            "1 | 100A | 5\n"
            "REV | DATE | BY | DESC\n"   # REV 마커 3개 → flush
        )
        res = extract_bom(text, kw)
        assert res.total_bom_rows == 1

    # ── 반복 헤더 건너뛰기 ───────────────────────────────

    def test_repeated_header_skipped(self, kw):
        text = (
            "BOM\n"
            "ITEM | SIZE | QTY\n"
            "1 | 100A | 5\n"
            "ITEM | SIZE | QTY\n"   # 반복 헤더 → 건너뜀
            "2 | 50A | 3\n"
        )
        res = extract_bom(text, kw)
        # 반복 헤더 행은 데이터로 수집 안 됨
        for row in res.bom_sections[0].rows:
            assert "ITEM" not in [c.upper() for c in row]

    # ── 구분선 건너뛰기 ──────────────────────────────────

    def test_separator_line_skipped(self, kw):
        text = (
            "BOM\n"
            "ITEM | SIZE | QTY\n"
            "---|---|---\n"     # 구분선
            "1 | 100A | 5\n"
        )
        res = extract_bom(text, kw)
        assert res.total_bom_rows == 1

    # ── 노이즈 행 필터링 ─────────────────────────────────

    def test_noise_rows_filtered(self, kw):
        text = (
            "BOM\n"
            "ITEM | SIZE | QTY\n"
            "1 | 100A | 5\n"
            "소계 | | 5\n"
            "합계 | | 5\n"
        )
        res = extract_bom(text, kw)
        assert res.total_bom_rows == 1  # 노이즈 2행 제거

    # ── 루프 종료 후 잔여 섹션 플러시 ────────────────────

    def test_flush_on_loop_end(self, kw):
        text = (
            "BOM\n"
            "ITEM | SIZE | QTY\n"
            "1 | 100A | 5\n"
            # 킬 키워드나 빈 행 없이 파일 끝
        )
        res = extract_bom(text, kw)
        assert res.has_bom

    # ── BOM + LINE LIST 동시 추출 ─────────────────────────

    def test_bom_and_ll_in_same_text(self, kw):
        text = (
            "BILL OF MATERIAL\n"
            "ITEM | SIZE | QTY\n"
            "1 | 100A | 5\n"
            "END OF BOM\n"
            "\n"
            "LINE LIST\n"
            "LINE NO | FROM | TO\n"
            "L-001 | P-101 | P-102\n"
        )
        res = extract_bom(text, kw)
        assert res.has_bom
        assert res.has_line_list

    # ── 빈 키워드셋 ──────────────────────────────────────

    def test_empty_keywords_no_sections(self):
        text = "ITEM | SIZE | QTY\n1 | 100A | 5\n"
        res = extract_bom(text, {})
        assert isinstance(res, BomExtractionResult)

    # ── HTML 입력 전처리 후 상태머신 ─────────────────────

    def test_html_table_input_processed(self, kw):
        html = (
            "<table>"
            "<tr><th>ITEM</th><th>SIZE</th><th>QTY</th></tr>"
            "<tr><td>1</td><td>100A</td><td>5</td></tr>"
            "</table>"
        )
        # HTML이 _sanitize_html을 통해 파이프 텍스트로 변환된 후 처리
        res = extract_bom(html, kw)
        assert isinstance(res, BomExtractionResult)


# ══════════════════════════════════════════════════════════
# extract_bom_tables — 3단계 폴백
# ══════════════════════════════════════════════════════════

class TestExtractBomTables:

    def _bom_html(self, headers, rows):
        h = "".join(f"<th>{h}</th>" for h in headers)
        d = "".join(
            "<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>"
            for r in rows
        )
        return f"<table><tr>{h}</tr>{d}</table>"

    def test_stage1_html_bom_detected(self):
        """단계 1: HTML BOM 감지 성공."""
        kw = {
            "bom_header_a": ["ITEM"],
            "bom_header_b": ["SIZE"],
            "bom_header_c": ["QTY"],
            "ll_header_a": ["LINE NO"],
            "ll_header_b": [],
            "ll_header_c": [],
            "blacklist": [],
            "noise_row": [],
        }
        html = self._bom_html(["ITEM", "SIZE", "QTY"], [["1", "100A", "5"]])
        res = extract_bom_tables(html, kw)
        assert res.has_bom

    def test_stage3_sm_fallback_when_html_fails(self):
        """단계 3: HTML 실패 시 상태머신으로 BOM 추출."""
        kw = {
            "anchor_bom": ["BOM"],
            "anchor_ll": [],
            "bom_header_a": ["ITEM"],
            "bom_header_b": ["SIZE"],
            "bom_header_c": ["QTY"],
            "ll_header_a": [],
            "ll_header_b": [],
            "ll_header_c": [],
            "bom_header_a": ["ITEM"],
            "bom_header_b": ["SIZE"],
            "bom_header_c": ["QTY"],
            "blacklist": [],
            "noise_row": [],
            "kill": [],
            "rev_markers": [],
        }
        text = "BOM\nITEM | SIZE | QTY\n1 | 100A | 5\n"
        res = extract_bom_tables(text, kw)
        assert res.has_bom

    def test_layout_details_path(self):
        """단계 2: layout_details 경로 — HTML 미발견 시 layout 내용 검사."""
        kw = {
            "bom_header_a": ["ITEM"],
            "bom_header_b": ["SIZE"],
            "bom_header_c": ["QTY"],
            "ll_header_a": [],
            "ll_header_b": [],
            "ll_header_c": [],
            "blacklist": [],
            "noise_row": [],
            "anchor_bom": [],
            "anchor_ll": [],
            "kill": [],
            "rev_markers": [],
        }
        html = self._bom_html(["ITEM", "SIZE", "QTY"], [["1", "100A", "5"]])
        layout = [{"label": "table", "content": html}]
        # 메인 텍스트에는 BOM 없음, layout_details에 있음
        res = extract_bom_tables("텍스트만", kw, layout_details=layout)
        assert isinstance(res, BomExtractionResult)

    def test_empty_text_returns_result(self):
        res = extract_bom_tables("", {})
        assert isinstance(res, BomExtractionResult)
        assert not res.has_bom

    def test_returns_bom_extraction_result(self):
        res = extract_bom_tables("텍스트", {})
        assert isinstance(res, BomExtractionResult)

    def test_ll_from_sm_merged(self):
        """LINE LIST를 HTML에서 못 찾았을 때 SM에서 병합."""
        kw = {
            "anchor_bom": [],
            "anchor_ll": ["LINE LIST"],
            "bom_header_a": ["ITEM"],
            "bom_header_b": ["SIZE"],
            "bom_header_c": ["QTY"],
            "ll_header_a": ["LINE NO"],
            "ll_header_b": ["FROM"],
            "ll_header_c": ["TO"],
            "blacklist": [],
            "noise_row": [],
            "kill": [],
            "rev_markers": [],
        }
        text = "LINE LIST\nLINE NO | FROM | TO\nL-001 | P-101 | P-102\n"
        res = extract_bom_tables(text, kw)
        assert res.has_line_list


# ══════════════════════════════════════════════════════════
# _get_table_bbox_scaled — 순수 함수
# ══════════════════════════════════════════════════════════

class TestGetTableBboxScaled:

    def test_no_layout_details_returns_none(self):
        assert _get_table_bbox_scaled(None, 1000, 2000) is None
        assert _get_table_bbox_scaled([], 1000, 2000) is None

    def test_no_table_label_returns_none(self):
        layout = [{"label": "text", "bbox_2d": [0, 0, 100, 100], "width": 200, "height": 300}]
        assert _get_table_bbox_scaled(layout, 1000, 2000) is None

    def test_table_bbox_scaled_correctly(self):
        # OCR 좌표: 1000×2000, 이미지: 2000×4000 → 2배 스케일
        layout = [{
            "label": "table",
            "bbox_2d": [100, 200, 800, 1600],
            "width": 1000,
            "height": 2000,
        }]
        result = _get_table_bbox_scaled(layout, 2000, 4000)
        assert result is not None
        x1, y1, x2, y2 = result
        assert x1 == 200   # 100 * 2
        assert y1 == 400   # 200 * 2
        assert x2 == 1600  # 800 * 2
        assert y2 == 3200  # 1600 * 2

    def test_nested_list_structure_flattened(self):
        # ZAI 응답 [[{elem}, ...]] 이중 구조
        layout = [[{
            "label": "table",
            "bbox_2d": [0, 0, 500, 1000],
            "width": 1000,
            "height": 2000,
        }]]
        result = _get_table_bbox_scaled(layout, 1000, 2000)
        assert result is not None

    def test_mixed_flat_and_nested(self):
        # 비-table 요소 먼저 (width/height 제공용), table 요소 나중
        layout = [
            {"label": "text", "width": 500, "height": 1000},
            {"label": "table", "bbox_2d": [50, 100, 450, 900]},
        ]
        result = _get_table_bbox_scaled(layout, 500, 1000)
        assert result is not None

    def test_returns_integers(self):
        layout = [{
            "label": "table",
            "bbox_2d": [10, 20, 30, 40],
            "width": 100,
            "height": 200,
        }]
        result = _get_table_bbox_scaled(layout, 300, 600)
        x1, y1, x2, y2 = result
        assert all(isinstance(v, int) for v in (x1, y1, x2, y2))

    def test_no_bbox_in_table_elem(self):
        layout = [{"label": "table", "width": 100, "height": 200}]
        result = _get_table_bbox_scaled(layout, 100, 200)
        assert result is None


# ══════════════════════════════════════════════════════════
# to_sections — 결과 → JSON 변환
# ══════════════════════════════════════════════════════════

class TestToSections:

    def test_empty_result(self):
        res = BomExtractionResult()
        assert to_sections(res) == []

    def test_bom_section_converted(self):
        bom = BomSection(
            "bom",
            headers=["ITEM", "SIZE", "QTY"],
            rows=[["1", "100A", "5"], ["2", "50A", "3"]],
            raw_row_count=2,
        )
        res = BomExtractionResult(bom_sections=[bom])
        sections = to_sections(res)
        assert len(sections) == 1
        s = sections[0]
        assert s["section_id"] == "BOM-1"
        assert "BILL OF MATERIALS" in s["title"]
        assert len(s["tables"]) == 1
        assert s["tables"][0]["parsed_row_count"] == 2

    def test_ll_section_converted(self):
        ll = BomSection(
            "line_list",
            headers=["LINE NO", "FROM", "TO"],
            rows=[["L-001", "P-101", "P-102"]],
            raw_row_count=1,
        )
        res = BomExtractionResult(line_list_sections=[ll])
        sections = to_sections(res)
        assert len(sections) == 1
        assert sections[0]["section_id"] == "LL-1"
        assert "LINE LIST" in sections[0]["title"]
        assert sections[0]["type"] == "line_list"

    def test_rows_as_dicts_with_headers(self):
        bom = BomSection(
            "bom",
            headers=["ITEM", "SIZE"],
            rows=[["1", "100A"]],
            raw_row_count=1,
        )
        res = BomExtractionResult(bom_sections=[bom])
        sections = to_sections(res)
        row_dict = sections[0]["tables"][0]["rows"][0]
        assert row_dict["ITEM"] == "1"
        assert row_dict["SIZE"] == "100A"

    def test_missing_header_uses_column_index(self):
        # 헤더보다 데이터 열이 많을 때
        bom = BomSection(
            "bom",
            headers=["ITEM"],
            rows=[["1", "100A", "5"]],  # 열 3개, 헤더 1개
            raw_row_count=1,
        )
        res = BomExtractionResult(bom_sections=[bom])
        sections = to_sections(res)
        row_dict = sections[0]["tables"][0]["rows"][0]
        assert "열2" in row_dict or "열3" in row_dict

    def test_empty_bom_rows_skipped(self):
        bom = BomSection("bom", headers=["ITEM"], rows=[], raw_row_count=0)
        res = BomExtractionResult(bom_sections=[bom])
        assert to_sections(res) == []

    def test_multiple_bom_sections(self):
        bom1 = BomSection("bom", ["ITEM"], [["1"]], raw_row_count=1)
        bom2 = BomSection("bom", ["ITEM"], [["2"]], raw_row_count=1)
        res = BomExtractionResult(bom_sections=[bom1, bom2])
        sections = to_sections(res)
        assert sections[0]["section_id"] == "BOM-1"
        assert sections[1]["section_id"] == "BOM-2"

    def test_required_keys_present(self):
        bom = BomSection("bom", ["A"], [["1"]], raw_row_count=1)
        res = BomExtractionResult(bom_sections=[bom])
        s = to_sections(res)[0]
        for key in ["section_id", "title", "tables", "notes", "conditions",
                    "cross_references", "clean_text"]:
            assert key in s

    def test_bom_and_ll_both_converted(self):
        bom = BomSection("bom", ["ITEM"], [["1"]], raw_row_count=1)
        ll  = BomSection("line_list", ["LINE NO"], [["L-1"]], raw_row_count=1)
        res = BomExtractionResult(bom_sections=[bom], line_list_sections=[ll])
        sections = to_sections(res)
        ids = [s["section_id"] for s in sections]
        assert "BOM-1" in ids
        assert "LL-1" in ids

    def test_table_id_format(self):
        bom = BomSection("bom", ["A"], [["1"]], raw_row_count=1)
        res = BomExtractionResult(bom_sections=[bom])
        tbl = to_sections(res)[0]["tables"][0]
        assert tbl["table_id"] == "T-BOM-1-01"

    def test_raw_row_count_preserved(self):
        bom = BomSection("bom", ["A"], [["1"]], raw_row_count=10)
        res = BomExtractionResult(bom_sections=[bom])
        tbl = to_sections(res)[0]["tables"][0]
        assert tbl["raw_row_count"] == 10
