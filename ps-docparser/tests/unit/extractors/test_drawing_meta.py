"""
extractors/drawing_meta.py 단위 테스트 — Phase 14 Step 14-1

목표 커버리지: 95%+
테스트 범위:
    - 정상 추출 (단순 줄, 파이프 인라인, 복합)
    - 경계값 (빈 입력, None 없이 모든 필드, 중복 키 first-match-wins)
    - HTML 정규화 (<br>, &nbsp;, 태그)
    - 마크다운 구분선 / 빈 테이블 행 skip
    - 대소문자 무관 매칭
    - BomExtractionResult.drawing_metadata 필드 신규 추가 확인
"""

import pytest
from extractors.drawing_meta import extract_drawing_meta, _FIELD_KEYS
from extractors.bom_types import BomExtractionResult


# ══════════════════════════════════════════════════════════
# 픽스처
# ══════════════════════════════════════════════════════════

@pytest.fixture
def typical_raw_text() -> str:
    """실제 BOM 도면에서 흔히 보이는 타이틀 블록 텍스트."""
    return (
        "TITLE: PIPE SUPPORT DETAIL\n"
        "DWG NO. KO-D-010-14-16N\n"
        "REV. 0\n"
        "DATE: 2024-03-15\n"
        "PROJECT: 고려아연 창녕공장\n"
        "CLIENT: 고려아연\n"
        "DRAWN BY: KIM\n"
        "CHECKED BY: LEE\n"
        "APPROVED BY: PARK\n"
        "SCALE: 1:50\n"
        "SHEET: 1 OF 3\n"
    )


@pytest.fixture
def pipe_inline_text() -> str:
    """파이프 구분 인라인 형태 — 여러 필드가 한 줄에."""
    return "TITLE: PIPE SUPPORT DETAIL | DWG NO. KO-D-010-14-16N | REV. 0\n"


# ══════════════════════════════════════════════════════════
# 반환 구조
# ══════════════════════════════════════════════════════════

class TestReturnStructure:
    def test_returns_dict(self):
        result = extract_drawing_meta("")
        assert isinstance(result, dict)

    def test_all_keys_present(self):
        result = extract_drawing_meta("")
        for key in _FIELD_KEYS:
            assert key in result, f"키 누락: {key}"

    def test_empty_input_all_none(self):
        result = extract_drawing_meta("")
        assert all(v is None for v in result.values())

    def test_whitespace_only_input_all_none(self):
        result = extract_drawing_meta("   \n\t  ")
        assert all(v is None for v in result.values())


# ══════════════════════════════════════════════════════════
# 단순 줄 매칭
# ══════════════════════════════════════════════════════════

class TestSimpleLineMatching:
    def test_dwg_no_with_dot(self):
        r = extract_drawing_meta("DWG NO. KO-D-010-14-16N")
        assert r["dwg_no"] == "KO-D-010-14-16N"

    def test_dwg_no_without_dot(self):
        r = extract_drawing_meta("DWG NO KO-001")
        assert r["dwg_no"] == "KO-001"

    def test_drawing_no_alias(self):
        r = extract_drawing_meta("DRAWING NO. ABC-123")
        assert r["dwg_no"] == "ABC-123"

    def test_rev_basic(self):
        r = extract_drawing_meta("REV. 2")
        assert r["rev"] == "2"

    def test_revision_alias(self):
        r = extract_drawing_meta("REVISION: B")
        assert r["rev"] == "B"

    def test_title_basic(self):
        r = extract_drawing_meta("TITLE: PIPE SUPPORT DETAIL")
        assert r["title"] == "PIPE SUPPORT DETAIL"

    def test_date_basic(self):
        r = extract_drawing_meta("DATE: 2024-03-15")
        assert r["date"] == "2024-03-15"

    def test_issued_alias(self):
        r = extract_drawing_meta("ISSUED: 2024-01-01")
        assert r["date"] == "2024-01-01"

    def test_project_basic(self):
        r = extract_drawing_meta("PROJECT: 고려아연 창녕공장")
        assert r["project"] == "고려아연 창녕공장"

    def test_job_no_alias(self):
        r = extract_drawing_meta("JOB NO. 2024-KZ-001")
        assert r["project"] == "2024-KZ-001"

    def test_client_basic(self):
        r = extract_drawing_meta("CLIENT: 고려아연")
        assert r["client"] == "고려아연"

    def test_owner_alias(self):
        r = extract_drawing_meta("OWNER: KZC")
        assert r["client"] == "KZC"

    def test_contractor_alias(self):
        r = extract_drawing_meta("CONTRACTOR: PS IND")
        assert r["client"] == "PS IND"

    def test_drawn_by_basic(self):
        r = extract_drawing_meta("DRAWN BY: KIM")
        assert r["drawn_by"] == "KIM"

    def test_drawn_alias(self):
        r = extract_drawing_meta("DRAWN: LEE")
        assert r["drawn_by"] == "LEE"

    def test_drwd_alias(self):
        r = extract_drawing_meta("DRW'D: HONG")
        assert r["drawn_by"] == "HONG"

    def test_checked_by_basic(self):
        r = extract_drawing_meta("CHECKED BY: PARK")
        assert r["checked_by"] == "PARK"

    def test_chkd_alias(self):
        r = extract_drawing_meta("CHK'D: KIM")
        assert r["checked_by"] == "KIM"

    def test_approved_by_basic(self):
        r = extract_drawing_meta("APPROVED BY: CHOI")
        assert r["approved_by"] == "CHOI"

    def test_appd_alias(self):
        r = extract_drawing_meta("APP'D: LEE")
        assert r["approved_by"] == "LEE"

    def test_scale_basic(self):
        r = extract_drawing_meta("SCALE: 1:50")
        assert r["scale"] == "1:50"

    def test_sheet_basic(self):
        r = extract_drawing_meta("SHEET: 1 OF 3")
        assert r["sheet"] == "1 OF 3"


# ══════════════════════════════════════════════════════════
# 대소문자 무관
# ══════════════════════════════════════════════════════════

class TestCaseInsensitive:
    def test_lowercase_key(self):
        r = extract_drawing_meta("title: lowercase test")
        assert r["title"] == "lowercase test"

    def test_mixed_case_key(self):
        r = extract_drawing_meta("Dwg No. MIXED-001")
        assert r["dwg_no"] == "MIXED-001"

    def test_all_caps(self):
        r = extract_drawing_meta("SCALE: NTS")
        assert r["scale"] == "NTS"


# ══════════════════════════════════════════════════════════
# 전형적 텍스트 (전체 필드 추출)
# ══════════════════════════════════════════════════════════

class TestTypicalRawText:
    def test_all_fields_extracted(self, typical_raw_text):
        r = extract_drawing_meta(typical_raw_text)
        assert r["dwg_no"] == "KO-D-010-14-16N"
        assert r["rev"] == "0"
        assert r["title"] == "PIPE SUPPORT DETAIL"
        assert r["date"] == "2024-03-15"
        assert r["project"] == "고려아연 창녕공장"
        assert r["client"] == "고려아연"
        assert r["drawn_by"] == "KIM"
        assert r["checked_by"] == "LEE"
        assert r["approved_by"] == "PARK"
        assert r["scale"] == "1:50"
        assert r["sheet"] == "1 OF 3"

    def test_no_none_values_when_all_present(self, typical_raw_text):
        r = extract_drawing_meta(typical_raw_text)
        assert all(v is not None for v in r.values())


# ══════════════════════════════════════════════════════════
# 파이프 인라인 매칭
# ══════════════════════════════════════════════════════════

class TestPipeInlineMatching:
    def test_three_fields_one_line(self, pipe_inline_text):
        r = extract_drawing_meta(pipe_inline_text)
        assert r["title"] == "PIPE SUPPORT DETAIL"
        assert r["dwg_no"] == "KO-D-010-14-16N"
        assert r["rev"] == "0"

    def test_two_fields_one_line(self):
        text = "DWG NO. ABC-001 | REV. A\n"
        r = extract_drawing_meta(text)
        assert r["dwg_no"] == "ABC-001"
        assert r["rev"] == "A"

    def test_pipe_without_matching_fields_ignored(self):
        text = "RANDOM TEXT | MORE RANDOM\n"
        r = extract_drawing_meta(text)
        assert all(v is None for v in r.values())


# ══════════════════════════════════════════════════════════
# First-match-wins (중복 키)
# ══════════════════════════════════════════════════════════

class TestFirstMatchWins:
    def test_first_dwg_no_wins(self):
        text = "DWG NO. FIRST-001\nDWG NO. SECOND-002\n"
        r = extract_drawing_meta(text)
        assert r["dwg_no"] == "FIRST-001"

    def test_first_rev_wins(self):
        text = "REV. A\nREVISION: B\n"
        r = extract_drawing_meta(text)
        assert r["rev"] == "A"

    def test_pipe_then_line_first_wins(self):
        # 파이프 줄에서 먼저 dwg_no 추출 → 다음 줄 DWG NO 무시
        text = "DWG NO. PIPE-001 | REV. 0\nDWG NO. LINE-002\n"
        r = extract_drawing_meta(text)
        assert r["dwg_no"] == "PIPE-001"


# ══════════════════════════════════════════════════════════
# HTML 정규화
# ══════════════════════════════════════════════════════════

class TestHtmlNormalization:
    def test_br_tag_becomes_newline(self):
        text = "DWG NO. KO-001<br>REV. 0"
        r = extract_drawing_meta(text)
        assert r["dwg_no"] == "KO-001"
        assert r["rev"] == "0"

    def test_br_self_closing(self):
        text = "TITLE: TEST<br/>SCALE: 1:100"
        r = extract_drawing_meta(text)
        assert r["title"] == "TEST"
        assert r["scale"] == "1:100"

    def test_nbsp_entity_decoded(self):
        text = "DWG&nbsp;NO. NBSP-001"
        r = extract_drawing_meta(text)
        # &nbsp; 디코드 후 "DWG NO. NBSP-001" → 패턴 매칭
        assert r["dwg_no"] == "NBSP-001"

    def test_html_tags_stripped(self):
        text = "<p>TITLE: TAGGED TITLE</p>"
        r = extract_drawing_meta(text)
        assert r["title"] == "TAGGED TITLE"


# ══════════════════════════════════════════════════════════
# 마크다운 구분선 / 빈 테이블 행 skip
# ══════════════════════════════════════════════════════════

class TestSkipLines:
    def test_md_separator_skipped(self):
        text = "DWG NO. SKIP-001\n---|---|---\nREV. 1\n"
        r = extract_drawing_meta(text)
        assert r["dwg_no"] == "SKIP-001"
        assert r["rev"] == "1"

    def test_empty_table_row_skipped(self):
        text = "TITLE: VALID\n|   |   |\nSCALE: 1:1\n"
        r = extract_drawing_meta(text)
        assert r["title"] == "VALID"
        assert r["scale"] == "1:1"

    def test_triple_dash_separator(self):
        text = "---\nDWG NO. AFTER-SEP\n"
        r = extract_drawing_meta(text)
        assert r["dwg_no"] == "AFTER-SEP"


# ══════════════════════════════════════════════════════════
# 값 정규화
# ══════════════════════════════════════════════════════════

class TestValueNormalization:
    def test_leading_trailing_whitespace_stripped(self):
        r = extract_drawing_meta("TITLE:   SPACED VALUE   ")
        assert r["title"] == "SPACED VALUE"

    def test_double_space_collapsed(self):
        r = extract_drawing_meta("TITLE: DOUBLE  SPACE")
        assert r["title"] == "DOUBLE SPACE"

    def test_empty_value_becomes_none(self):
        r = extract_drawing_meta("TITLE:")
        assert r["title"] is None

    def test_whitespace_only_value_becomes_none(self):
        r = extract_drawing_meta("TITLE:   ")
        assert r["title"] is None


# ══════════════════════════════════════════════════════════
# 미매칭 줄 무시
# ══════════════════════════════════════════════════════════

class TestUnmatchedLines:
    def test_bom_table_lines_ignored(self):
        text = (
            "| NO | TAG NO | SIZE |\n"
            "|---|---|---|\n"
            "| 1 | P-001 | 2\" |\n"
            "DWG NO. AFTER-TABLE\n"
        )
        r = extract_drawing_meta(text)
        assert r["dwg_no"] == "AFTER-TABLE"

    def test_random_text_ignored(self):
        text = "SOME RANDOM TEXT LINE\nDWG NO. VALID-001\n"
        r = extract_drawing_meta(text)
        assert r["dwg_no"] == "VALID-001"


# ══════════════════════════════════════════════════════════
# BomExtractionResult.drawing_metadata 필드 확인
# ══════════════════════════════════════════════════════════

class TestBomExtractionResultField:
    def test_field_exists_with_default(self):
        """기존 코드 호환성: 기본값이 빈 dict여야 함."""
        result = BomExtractionResult()
        assert hasattr(result, "drawing_metadata")
        assert result.drawing_metadata == {}

    def test_field_accepts_drawing_meta(self):
        """extract_drawing_meta() 결과를 할당할 수 있어야 함."""
        meta = extract_drawing_meta("DWG NO. KO-001")
        result = BomExtractionResult(drawing_metadata=meta)
        assert result.drawing_metadata["dwg_no"] == "KO-001"

    def test_existing_fields_unaffected(self):
        """drawing_metadata 추가가 기존 필드를 깨지 않는지 확인."""
        result = BomExtractionResult(raw_text="TEST", ocr_engine="zai")
        assert result.raw_text == "TEST"
        assert result.ocr_engine == "zai"
        assert result.bom_sections == []
        assert result.drawing_metadata == {}
