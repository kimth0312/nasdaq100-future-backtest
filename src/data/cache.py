"""
DataCache: SQLite 기반 로컬 캐시
TTL: 1m=1시간, 5m/15m=4시간, 60m=12시간, 1d=24시간
저장 경로: ~/.nq_backtester/cache.db
"""
import hashlib
import logging
import sqlite3
import time
from io import BytesIO
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# TTL (초 단위)
TTL_SECONDS = {
    '1m': 3600,       # 1시간
    '5m': 14400,      # 4시간
    '15m': 14400,     # 4시간
    '60m': 43200,     # 12시간
    '1d': 86400,      # 24시간
}


class DataCache:
    """SQLite 기반 DataFrame 캐시"""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            cache_dir = Path.home() / ".nq_backtester"
            cache_dir.mkdir(parents=True, exist_ok=True)
            db_path = cache_dir / "cache.db"
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """캐시 테이블 초기화"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    data BLOB NOT NULL,
                    created_at REAL NOT NULL,
                    interval TEXT NOT NULL
                )
            """)
            conn.commit()

    def _make_key(self, symbol: str, interval: str, start, end) -> str:
        """캐시 키 생성 (MD5 해시)"""
        raw = f"{symbol}|{interval}|{start}|{end}"
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, key: str, interval: str = '1d') -> Optional[pd.DataFrame]:
        """
        캐시에서 DataFrame 조회.
        TTL 만료 시 None 반환.
        """
        ttl = TTL_SECONDS.get(interval, 86400)
        now = time.time()

        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    "SELECT data, created_at FROM cache WHERE key = ?",
                    (key,)
                ).fetchone()
        except Exception as e:
            logger.warning(f"[DataCache] get 오류: {e}")
            return None

        if row is None:
            return None

        data_blob, created_at = row
        if now - created_at > ttl:
            logger.debug(f"[DataCache] 캐시 만료: key={key[:8]}...")
            self._delete(key)
            return None

        try:
            df = pd.read_parquet(BytesIO(data_blob))
            logger.debug(f"[DataCache] 캐시 히트: key={key[:8]}... ({len(df)} 행)")
            return df
        except Exception as e:
            logger.warning(f"[DataCache] 파싱 오류: {e}")
            return None

    def set(self, key: str, df: pd.DataFrame, interval: str = '1d'):
        """DataFrame을 캐시에 저장"""
        if df is None or df.empty:
            return

        try:
            buf = BytesIO()
            df.to_parquet(buf)
            data_blob = buf.getvalue()

            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO cache (key, data, created_at, interval) VALUES (?, ?, ?, ?)",
                    (key, data_blob, time.time(), interval)
                )
                conn.commit()
            logger.debug(f"[DataCache] 캐시 저장: key={key[:8]}... ({len(df)} 행)")
        except Exception as e:
            logger.warning(f"[DataCache] set 오류: {e}")

    def _delete(self, key: str):
        """캐시 항목 삭제"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                conn.commit()
        except Exception as e:
            logger.warning(f"[DataCache] delete 오류: {e}")

    def clear(self):
        """전체 캐시 삭제"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM cache")
                conn.commit()
            logger.info("[DataCache] 전체 캐시 삭제 완료")
        except Exception as e:
            logger.warning(f"[DataCache] clear 오류: {e}")
