"""
test_phase5_unit3.py — 단위 3 (BOM 집계기) 독립 검증

실행: python test_phase5_unit3.py
의존성: 없음 (Python 표준 라이브러리만 사용)
"""

import sys
import json
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from exporters.bom_aggregator import aggregate_boms, _parse_float, _get_row_value

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
    print("  단위 3: BOM 집계 모듈(_aggregator) 자체 검증")
    print("=" * 62 + "\n")

    # ────────────────────────────────────────────────────────
    # TC-1: _parse_float 변환
    # ────────────────────────────────────────────────────────
    print("[TC-1] 숫자(float) 파싱 안정성 검증")
    check("정상 int 변환", _parse_float(10) == 10.0)
    check("정상 float 변환", _parse_float("15.5") == 15.5)
    check("쉼표 제거", _parse_float("1,200.5") == 1200.5)
    check("단위 혼합 추출", _parse_float("25EA") == 25.0)
    check("단위 띄어쓰기 추출", _parse_float("100 kg") == 100.0)
    check("문자열 무효값 (0 반환)", _parse_float("알수없음") == 0.0)
    check("None 무효값 (0 반환)", _parse_float(None) == 0.0)
    check("빈문자열 (0 반환)", _parse_float("   ") == 0.0)

    # ────────────────────────────────────────────────────────
    # TC-2: _get_row_value 헤더 정규화 매핑
    # ────────────────────────────────────────────────────────
    print("\n[TC-2] 다양한 헤더 포맷(Alias) 정규화 매핑")
    # 샘플 데이터 1: MAT'L, WT(kg), Q'ty 사용
    row1 = {"MAT'L": "SUS304", "WT(kg)": "5.5", "Q'ty": "10"}
    check("매핑: MATERIAL <- MAT'L", _get_row_value(row1, "MATERIAL") == "SUS304")
    check("매핑: WEIGHT <- WT(kg)", _get_row_value(row1, "WEIGHT") == "5.5")
    check("매핑: QUANTITY <- Q'ty", _get_row_value(row1, "QUANTITY") == "10")

    # 샘플 데이터 2: MATERIAL, WEIGHT, QTY 사용
    row2 = {"MATERIAL": "SS400", "WEIGHT": 12.3, "QTY": 2}
    check("매핑: MATERIAL <- MATERIAL", _get_row_value(row2, "MATERIAL") == "SS400")
    check("매핑: WEIGHT <- WEIGHT", _get_row_value(row2, "WEIGHT") == 12.3)
    check("매핑: QUANTITY <- QTY", _get_row_value(row2, "QUANTITY") == 2)
    
    # 실패 케이스 (기본값 반환 확인)
    check("매핑 실패 시 기본값", _get_row_value({"ABC": 1}, "WEIGHT", default=0) == 0)

    # ────────────────────────────────────────────────────────
    # TC-3: 다중 도면 그룹화 (Aggregation)
    # ────────────────────────────────────────────────────────
    print("\n[TC-3] 다중 서포트 도면 데이터 그룹핑 및 합산")
    
    doc1 = [{
        "type": "estimate",
        "tables": [{
            "array": [
                ["ITEM_NO", "DESCRIPTION", "SIZE", "MAT'L", "Q'TY", "WT(KG)"],
                ["1", "U-BOLT", "50A", "SS400", "10", "1.5"],
                ["2", "BASE PLATE", "100x100", "SUS304", "2", "3.0"],
                ["", "비정상 행 (빈값)", "", "", "5", "10"], # SIZE, MAT'L 없음
            ]
        }]
    }]
    
    doc2 = [{
        "type": "bom",
        "tables": [{
            "array": [
                ["NO", "DESC", "SIZE", "MATERIAL", "QTY", "WT(kg)"],
                ["1", "U-BOLT (유사품)", "50A", "SS400", "5", "1.5"],      # doc1의 행과 병합되어야 함 -> Q'TY: 15, WT: 3.0
                ["2", "PIPE SHOE", "80A", "SS400", "1", "5.2"],         # 신규
            ]
        }]
    }]
    
    # 가상의 추출 결과 JSON 파일 쓰기
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_dir_path = Path(tmpdir)
        p1 = tmp_dir_path / "1.json"
        p2 = tmp_dir_path / "2.json"
        
        with open(p1, "w", encoding="utf-8") as f:
            json.dump(doc1, f)
        with open(p2, "w", encoding="utf-8") as f:
            json.dump(doc2, f)
            
        aggregated_sections = aggregate_boms([p1, p2])
        
        check("반환 섹션 개수가 1개인가", len(aggregated_sections) == 1)
        
        merged_table = aggregated_sections[0]["tables"][0]["array"]
        headers = merged_table[0]
        data_rows = merged_table[1:]
        
        check("헤더 구성 확인", headers == ["ITEM_NO", "DESCRIPTION", "SIZE", "MATERIAL", "Q'TY", "WT(KG)"])
        check("데이터 행 수 (무효 데이터 제외)", len(data_rows) == 3) # (50A, SS400), (100x100, SUS304), (80A, SS400)
        
        # 합산 결과 찾기
        ubolt_row = next((r for r in data_rows if r[2] == "50A" and r[3] == "SS400"), None)
        plate_row = next((r for r in data_rows if r[2] == "100x100" and r[3] == "SUS304"), None)
        
        check("1번 도면 + 2번 도면 항목 합산 병합", ubolt_row is not None)
        
        q_idx = headers.index("Q'TY")
        w_idx = headers.index("WT(KG)")
        
        check("수량(Q'TY) 합산 확인 (10 + 5 = 15.0)", float(ubolt_row[q_idx]) == 15.0)
        check("중량(WT) 합산 확인 (1.5 + 1.5 = 3.0)", float(ubolt_row[w_idx]) == 3.0)
        
        check("단일 발생 항목 병합 없음 유지", float(plate_row[q_idx]) == 2.0)

    # ── 최종 결과 ──
    _print_summary()


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
        print("\n[완료] 단위 3 검증 -- 모든 테스트 통과")
        sys.exit(0)


if __name__ == "__main__":
    run_all()
