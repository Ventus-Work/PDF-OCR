"""
page_spec.py 단위 테스트.

parse_page_spec의 문법:
    "15"       → [0..14]        (1~15 페이지)
    "1-15"     → [0..14]
    "16-30"    → [15..29]
    "1,3,5-10" → [0, 2, 4..9]
    "20-"      → [19..total-1]
    "1"        → [0]
"""
import pytest
from utils.page_spec import parse_page_spec


class TestParsePageSpec:

    @pytest.mark.parametrize("spec,total,expected", [
        ("15", 100, list(range(0, 15))),
        ("1-15", 100, list(range(0, 15))),
        ("16-30", 100, list(range(15, 30))),
        ("1,3,5-10", 100, [0, 2, 4, 5, 6, 7, 8, 9]),
        ("20-", 25, [19, 20, 21, 22, 23, 24]),
        ("1", 10, [0]),
    ])
    def test_valid_specs(self, spec, total, expected):
        assert parse_page_spec(spec, total) == expected

    # ── 엣지 케이스 ──
    def test_empty_string(self):
        with pytest.raises(ValueError):
            parse_page_spec("", 10)

    def test_out_of_range(self):
        """총 페이지 초과 지정 시 자동 클램프"""
        result = parse_page_spec("1-100", 10)
        assert result == list(range(0, 10))

    def test_invalid_format(self):
        with pytest.raises(ValueError):
            parse_page_spec("abc", 10)

    def test_reverse_range(self):
        """역순 범위 (10-5)는 파서가 잘못된 포맷으로 인식하거나 예외를 발생해야 함"""
        # 현재 코드의 동작을 확인하고 만약 예외가 안난다면 예외가 나는 방향으로 수정 필요할 수도 있음. 
        # 명세 상으로는 허용하지 않음.
        with pytest.raises(ValueError):
            parse_page_spec("10-5", 100)

    def test_deduplication(self):
        """중복 페이지 번호 지정 시 한 번만 포함되어야 함 (중복 제거 후 정렬)"""
        result = parse_page_spec("1,2,3,1,2", 10)
        assert result == [0, 1, 2]
