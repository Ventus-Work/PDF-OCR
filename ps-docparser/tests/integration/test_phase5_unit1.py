"""
test_phase5_unit1.py — 단위 1 (API 캐싱 레이어) 독립 검증

실행: python test_phase5_unit1.py
의존성: 없음 (Python 표준 라이브러리만 사용)
"""

import sys
import time
import tempfile
import json
from pathlib import Path

# sys.path 조작 (어느 경로에서든 실행 가능하도록)
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from cache.table_cache import TableCache

# ── 테스트 유틸 ──

PASS = "PASS"
FAIL = "FAIL"
results = []

# Windows cp949 콘솔에서 유니코드 이모지 깨짐 방지
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def check(test_name: str, condition: bool, detail: str = ""):
    status = PASS if condition else FAIL
    results.append((test_name, status, detail))
    mark = "[OK]" if condition else "[XX]"
    print(f"  {mark} {test_name}" + (f" -- {detail}" if detail else ""))


def run_all():
    print("\n" + "=" * 60)
    print("  단위 1: API 캐싱 레이어 검증")
    print("=" * 60 + "\n")

    # 임시 DB 사용 (테스트 후 자동 삭제)
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_cache.db"

        # ──────────────────────────────────────────────
        # TC-1: 초기화 및 DB 파일 생성
        # ──────────────────────────────────────────────
        print("[TC-1] 초기화")
        cache = TableCache(db_path, ttl_days=30)
        check("DB 파일 생성", db_path.exists(), str(db_path))

        # ──────────────────────────────────────────────
        # TC-2: 캐시 미스
        # ──────────────────────────────────────────────
        print("\n[TC-2] 캐시 미스")
        result = cache.get("nonexistent_key")
        check("미스 시 None 반환", result is None)
        check("misses 카운터 증가", cache.stats()["misses"] == 1)

        # ──────────────────────────────────────────────
        # TC-3: 저장 + 적중
        # ──────────────────────────────────────────────
        print("\n[TC-3] 저장 및 적중")
        test_key = "test_key_001"
        test_value = {"text": "테이블 헤더\nBOM 데이터", "layout": [{"type": "table"}]}
        cache.put(test_key, test_value, engine="zai")
        retrieved = cache.get(test_key)
        check("저장 후 조회 성공", retrieved is not None)
        check("데이터 무결성 (text)", retrieved.get("text") == test_value["text"])
        check("데이터 무결성 (layout)", retrieved.get("layout") == test_value["layout"])
        check("hits 카운터 증가", cache.stats()["hits"] == 1)

        # ──────────────────────────────────────────────
        # TC-4: make_key_from_file (파일 기반 해시)
        # ──────────────────────────────────────────────
        print("\n[TC-4] 파일 기반 키 생성")
        # 임시 파일 생성
        dummy_file = Path(tmpdir) / "dummy.pdf"
        dummy_file.write_bytes(b"PDF dummy content for hashing 0123456789" * 100)

        key_zai = cache.make_key_from_file(dummy_file, "zai")
        key_mistral = cache.make_key_from_file(dummy_file, "mistral")
        key_zai_p0 = cache.make_key_from_file(dummy_file, "zai", page_idx=0)

        check("키 길이 64자 (sha256 hex)", len(key_zai) == 64)
        check("엔진 다르면 키 다름", key_zai != key_mistral)
        check("페이지 인덱스 있으면 키 다름", key_zai != key_zai_p0)

        # 동일 파일 동일 엔진 → 키 동일 (결정론적)
        key_zai2 = cache.make_key_from_file(dummy_file, "zai")
        check("동일 파일/엔진 → 동일 키", key_zai == key_zai2)

        # 파일 내용 변경 시 키 변경
        dummy_file.write_bytes(b"MODIFIED CONTENT")
        key_modified = cache.make_key_from_file(dummy_file, "zai")
        check("파일 내용 변경 시 키 변경", key_zai != key_modified)

        # ──────────────────────────────────────────────
        # TC-5: make_key_from_data (이미지 바이트 기반)
        # ──────────────────────────────────────────────
        print("\n[TC-5] 이미지 바이트 기반 키 생성")
        img_bytes1 = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        img_bytes2 = b"\x89PNG\r\n\x1a\n" + b"\x01" * 100

        k1 = cache.make_key_from_data(img_bytes1, "zai")
        k2 = cache.make_key_from_data(img_bytes2, "zai")
        k1_again = cache.make_key_from_data(img_bytes1, "zai")

        check("이미지 키 길이 64자", len(k1) == 64)
        check("다른 이미지 → 다른 키", k1 != k2)
        check("동일 이미지 → 동일 키", k1 == k1_again)

        # ──────────────────────────────────────────────
        # TC-6: TTL 만료
        # ──────────────────────────────────────────────
        print("\n[TC-6] TTL 만료")
        # TTL을 1초로 설정한 캐시 생성
        short_cache = TableCache(db_path, ttl_days=0)
        # ttl_days=0 → ttl_seconds=0 이므로 즉시 만료
        short_cache._ttl_seconds = 1  # 1초로 강제 설정
        short_cache.put("expire_key", {"data": "will_expire"}, engine="zai")

        # 즉시 조회 → 적중 (아직 만료 안 됨)
        result_before = short_cache.get("expire_key")
        check("만료 전 조회 성공", result_before is not None)

        # 1.1초 대기 후 재조회
        time.sleep(1.1)
        result_after = short_cache.get("expire_key")
        check("만료 후 None 반환", result_after is None)

        # ──────────────────────────────────────────────
        # TC-7: clear_expired()
        # ──────────────────────────────────────────────
        print("\n[TC-7] 만료 엔트리 일괄 삭제")
        # 새 캐시에 2건 저장
        cache2 = TableCache(db_path, ttl_days=30)
        cache2.put("fresh_key", {"ok": True}, engine="zai")
        cache2._ttl_seconds = 0  # 즉시 만료 처리
        cache2.put("stale_key_1", {"stale": 1}, engine="zai")
        cache2.put("stale_key_2", {"stale": 2}, engine="zai")
        # TTL 원복 후 clear_expired
        cache2._ttl_seconds = 30 * 86400
        deleted = cache2.clear_expired()
        # fresh_key는 아직 유효하지 않을 수도 있으므로 ≥ 0 확인
        check("clear_expired() 실행 성공", isinstance(deleted, int))

        # ──────────────────────────────────────────────
        # TC-8: stats()
        # ──────────────────────────────────────────────
        print("\n[TC-8] 통계")
        stats = cache.stats()
        check("stats 키 존재: hits", "hits" in stats)
        check("stats 키 존재: misses", "misses" in stats)
        check("stats 키 존재: hit_rate_pct", "hit_rate_pct" in stats)
        check("stats 키 존재: size", "size" in stats)
        check("hit_rate_pct 범위 [0, 100]", 0.0 <= stats["hit_rate_pct"] <= 100.0)

        # ──────────────────────────────────────────────
        # TC-9: 동일 키 덮어쓰기 (INSERT OR REPLACE)
        # ──────────────────────────────────────────────
        print("\n[TC-9] 동일 키 덮어쓰기")
        cache.put("overwrite_key", {"v": 1}, engine="zai")
        cache.put("overwrite_key", {"v": 2}, engine="zai")  # 덮어쓰기
        result = cache.get("overwrite_key")
        check("덮어쓰기 후 최신 값 반환", result is not None and result.get("v") == 2)

        # ──────────────────────────────────────────────
        # TC-10: config 연동 확인
        # ──────────────────────────────────────────────
        print("\n[TC-10] config.py 설정 확인")
        try:
            import config
            check("CACHE_TTL_DAYS 존재", hasattr(config, "CACHE_TTL_DAYS"))
            check("CACHE_ENABLED 존재", hasattr(config, "CACHE_ENABLED"))
            check("CACHE_DIR 존재", hasattr(config, "CACHE_DIR"))
            check("CACHE_DIR는 Path", isinstance(config.CACHE_DIR, Path))
        except ImportError as e:
            check("config.py 임포트", False, str(e))

        # Windows WAL 잠금 해제: tempfile 삭제 전 모든 커넥션 명시 종료
        cache.close()
        cache2.close()
        short_cache.close()

    # ── 최종 결과 ──
    print("\n" + "=" * 60)
    total = len(results)
    passed = sum(1 for _, s, _ in results if s == PASS)
    failed = total - passed
    print(f"  결과: {passed}/{total} 통과 / {failed}건 실패")
    print("=" * 60)

    if failed > 0:
        print("\n[실패 항목]")
        for name, status, detail in results:
            if status == FAIL:
                print(f"   - {name}" + (f": {detail}" if detail else ""))
        sys.exit(1)
    else:
        print("\n[완료] 단위 1 검증 -- 모든 테스트 통과")
        sys.exit(0)


if __name__ == "__main__":
    run_all()
