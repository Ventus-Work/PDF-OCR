"""
cache/table_cache.py — API 응답 SQLite 캐시 레이어 (Phase 5)

Why: 61개 PDF 배치 처리 시 동일 파일의 2차, 3차 재실행에서
     API를 재호출하지 않아 비용(ZAI, Mistral)과 시간을 절감한다.

설계 원칙:
    - 외부 라이브러리 불필요 (sqlite3, hashlib, json — 전부 표준 라이브러리)
    - 파일 경로 기반 해시: data_uri(수 MB 문자열) 대신 원본 파일 바이트를
      8KB 청크 단위로 읽어 sha256 해시 → 메모리 효율 극대화
    - TTL(만료일) 기반 자동 무효화
    - 통계(hits/misses) 제공으로 효율성 측정 가능
"""

import hashlib
import json
import logging
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# SQLite 스키마 (모듈 로드 시 1회 실행)
_DDL = """
CREATE TABLE IF NOT EXISTS cache (
    key       TEXT PRIMARY KEY,
    value     TEXT NOT NULL,
    engine    TEXT NOT NULL,
    created   REAL NOT NULL,
    hit_count INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_engine  ON cache(engine);
CREATE INDEX IF NOT EXISTS idx_created ON cache(created);
"""


class TableCache:
    """
    API 응답을 SQLite에 캐시한다.

    Usage:
        cache = TableCache(Path(".cache/table_cache.db"), ttl_days=30)
        key = cache.make_key_from_file(pdf_path, "zai")
        result = cache.get(key)
        if result is None:
            result = call_api(...)
            cache.put(key, result, engine="zai")

    Thread-safety:
        단일 프로세스 내 단일 스레드 사용 전제.
        배치 처리는 순차 실행이므로 추가 동기화 불필요.
    """

    def __init__(self, db_path: Path, ttl_days: int = 30) -> None:
        """
        Args:
            db_path:   SQLite 파일 경로. 부모 디렉토리가 없으면 자동 생성.
            ttl_days:  캐시 유효 기간 (일). 초과 시 자동 무효화.
        """
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        self._db_path = db_path
        self._ttl_seconds = ttl_days * 86400  # days → seconds

        # 통계 카운터 (프로세스 수명 동안 누적)
        self._hits = 0
        self._misses = 0

        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")   # 동시 읽기 성능
        self._conn.execute("PRAGMA synchronous=NORMAL")  # 속도/안전성 균형
        self._init_db()
        logger.info("캐시 DB 초기화: %s (TTL %d일)", db_path, ttl_days)

    # ── 키 생성 ──

    def make_key_from_file(
        self,
        file_path: Path,
        engine: str,
        page_idx: int | None = None,
    ) -> str:
        """
        파일 내용 + 엔진명 + 페이지 인덱스 → 64자 hex 키.

        Why 파일 기반:
            data_uri는 Base64 인코딩으로 원본 대비 1.33배 크기이므로
            수 MB 문자열을 메모리에 올리지 않고, 원본 파일을 8KB 청크로
            스트리밍 해시하여 메모리 사용을 최소화한다.

        Why page_idx 포함:
            같은 파일이라도 페이지별 처리 시 결과가 달라지므로 세분화.
        """
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                h.update(chunk)
        h.update(engine.encode("utf-8"))
        if page_idx is not None:
            h.update(str(page_idx).encode("utf-8"))
        return h.hexdigest()

    def make_key_from_data(self, data: bytes, engine: str) -> str:
        """
        이미지 바이트 + 엔진명 → 64자 hex 키.

        Why:
            ocr_image()는 PIL Image를 받으므로 파일 경로가 없다.
            이미지 바이트를 직접 해시하여 키를 생성한다.
        """
        h = hashlib.sha256()
        h.update(data)
        h.update(engine.encode("utf-8"))
        return h.hexdigest()

    # ── CRUD ──

    def get(self, key: str) -> dict | None:
        """
        캐시 조회.

        Returns:
            dict: 캐시 적중 시 역직렬화된 API 응답
            None: 미스 또는 TTL 만료
        """
        row = self._conn.execute(
            "SELECT value, created FROM cache WHERE key = ?", (key,)
        ).fetchone()

        if row is None:
            self._misses += 1
            return None

        value, created = row

        # TTL 만료 체크
        if time.time() - created > self._ttl_seconds:
            self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            self._conn.commit()
            self._misses += 1
            logger.debug("캐시 TTL 만료 삭제: %s...", key[:16])
            return None

        # 적중 카운트 갱신
        self._conn.execute(
            "UPDATE cache SET hit_count = hit_count + 1 WHERE key = ?", (key,)
        )
        self._conn.commit()
        self._hits += 1
        return json.loads(value)

    def put(self, key: str, value: dict, engine: str = "unknown") -> None:
        """
        캐시 저장 (이미 존재하면 덮어씀).

        Args:
            key:    make_key_from_file 또는 make_key_from_data의 반환값
            value:  API 응답 dict (JSON 직렬화 가능해야 함)
            engine: 엔진명 (통계/필터링용)
        """
        try:
            self._conn.execute(
                "INSERT OR REPLACE INTO cache (key, value, engine, created, hit_count) "
                "VALUES (?, ?, ?, ?, 0)",
                (key, json.dumps(value, ensure_ascii=False), engine, time.time()),
            )
            self._conn.commit()
        except Exception as e:
            # 캐시 저장 실패는 비치명적 — 로그만 남기고 계속 진행
            logger.warning("캐시 저장 실패 (계속 진행): %s", e)

    # ── 유틸리티 ──

    def stats(self) -> dict:
        """현재 세션의 캐시 통계."""
        total = self._hits + self._misses
        hit_rate = round(self._hits / total * 100, 1) if total > 0 else 0.0
        size = self._conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_pct": hit_rate,
            "size": size,
        }

    def clear_expired(self) -> int:
        """TTL 만료된 엔트리를 삭제한다. 삭제 건수 반환."""
        cutoff = time.time() - self._ttl_seconds
        cur = self._conn.execute(
            "DELETE FROM cache WHERE created < ?", (cutoff,)
        )
        self._conn.commit()
        if cur.rowcount:
            logger.info("만료 캐시 %d건 삭제", cur.rowcount)
        return cur.rowcount

    def close(self) -> None:
        """DB 커넥션 명시적 종료 (프로세스 종료 시 자동 호출됨)."""
        self._conn.close()

    # ── 내부 ──

    def _init_db(self) -> None:
        """DDL 실행 (테이블/인덱스가 없으면 생성)."""
        self._conn.executescript(_DDL)
        self._conn.commit()

    def __repr__(self) -> str:
        return (
            f"TableCache(db={self._db_path.name!r}, "
            f"hits={self._hits}, misses={self._misses})"
        )
