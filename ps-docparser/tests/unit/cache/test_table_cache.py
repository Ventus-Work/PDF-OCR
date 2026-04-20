"""
table_cache.py 단위 테스트.

TableCache는 SQLite 기반 캐시:
- sha256 파일 해시 + 엔진을 키로 사용
- TTL 지난 엔트리 자동 만료
- 캐시 적중률 통계 제공
"""
import pytest
from pathlib import Path
from datetime import datetime, timedelta
import time

from cache.table_cache import TableCache


class TestTableCache:

    @pytest.fixture
    def cache(self, temp_cache_dir: Path):
        db_path = temp_cache_dir / "test.db"
        return TableCache(db_path=db_path, ttl_days=30)

    def test_initial_state(self, cache: TableCache):
        st = cache.stats()
        assert st["hits"] == 0
        assert st["misses"] == 0
        assert st["size"] == 0

    def test_put_and_get(self, cache: TableCache, tmp_path: Path):
        pdf = tmp_path / "sample.pdf"
        pdf.write_bytes(b"dummy pdf content")

        # Set
        key = cache.make_key_from_file(pdf, "zai", 0)
        cache.put(key, {"result": "test_result"}, engine="zai")

        # Get (적중)
        result = cache.get(key)
        assert result == {"result": "test_result"}
        assert cache.stats()["hits"] == 1

    def test_miss_different_page(self, cache: TableCache, tmp_path: Path):
        pdf = tmp_path / "sample.pdf"
        pdf.write_bytes(b"content")
        key = cache.make_key_from_file(pdf, "zai", 0)
        cache.put(key, {"result": "r0"}, engine="zai")
        
        wrong_key = cache.make_key_from_file(pdf, "zai", 1)
        assert cache.get(wrong_key) is None
        assert cache.stats()["misses"] == 1

    def test_miss_different_file(self, cache: TableCache, tmp_path: Path):
        pdf1 = tmp_path / "a.pdf"
        pdf1.write_bytes(b"content1")
        pdf2 = tmp_path / "b.pdf"
        pdf2.write_bytes(b"content2")

        key1 = cache.make_key_from_file(pdf1, "zai", 0)
        key2 = cache.make_key_from_file(pdf2, "zai", 0)
        
        cache.put(key1, {"result": "r1"}, engine="zai")
        assert cache.get(key2) is None

    def test_ttl_expiration(self, cache: TableCache, tmp_path: Path):
        pdf = tmp_path / "sample.pdf"
        pdf.write_bytes(b"content")

        key = cache.make_key_from_file(pdf, "zai", 0)
        cache.put(key, {"result": "old"}, engine="zai")
        
        old_time = time.time() - (31 * 86400)
        with cache._conn as conn:
            conn.execute(
                "UPDATE cache SET created = ? WHERE key = ?",
                (old_time, key)
            )

        assert cache.get(key) is None

    def test_same_content_different_filename(self, cache: TableCache, tmp_path: Path):
        pdf1 = tmp_path / "a.pdf"
        pdf2 = tmp_path / "b.pdf"
        pdf1.write_bytes(b"identical content")
        pdf2.write_bytes(b"identical content")

        key1 = cache.make_key_from_file(pdf1, "zai", 0)
        key2 = cache.make_key_from_file(pdf2, "zai", 0)
        assert key1 == key2

        cache.put(key1, {"result": "shared"}, engine="zai")
        assert cache.get(key2) == {"result": "shared"}

    def test_hit_rate_calculation(self, cache: TableCache, tmp_path: Path):
        pdf = tmp_path / "sample.pdf"
        pdf.write_bytes(b"content")
        key0 = cache.make_key_from_file(pdf, "zai", 0)
        cache.put(key0, {"result": "r"}, engine="zai")

        # 3 hits, 2 misses
        for _ in range(3):
            cache.get(key0)
        cache.get("invalid_key1")
        cache.get("invalid_key2")

        st = cache.stats()
        assert st["hits"] == 3
        assert st["misses"] == 2
        assert abs(st["hit_rate_pct"] - 60.0) < 0.001

    def test_clear_expired(self, cache: TableCache, tmp_path: Path):
        pdf = tmp_path / "sample.pdf"
        pdf.write_bytes(b"content")
        key = cache.make_key_from_file(pdf, "zai", 0)
        cache.put(key, {"result": "r"}, engine="zai")
        
        old_time = time.time() - (31 * 86400)
        with cache._conn as conn:
            conn.execute(
                "UPDATE cache SET created = ? WHERE key = ?",
                (old_time, key)
            )
        cache.clear_expired()
        assert cache.stats()["size"] == 0
