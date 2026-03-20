"""
DataStore: DataFetcher + DataCache를 조합한 단일 인터페이스
결측치 처리 (ffill + dropna) 포함
"""
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from data.fetcher import DataFetcher
from data.cache import DataCache

logger = logging.getLogger(__name__)


class DataStore:
    """캐시와 fetcher를 조합한 데이터 접근 인터페이스"""

    def __init__(self, cache: Optional[DataCache] = None, fetcher: Optional[DataFetcher] = None):
        self.cache = cache or DataCache()
        self.fetcher = fetcher or DataFetcher()

    def get_bars(self, symbol: str, interval: str, start: datetime, end: datetime) -> pd.DataFrame:
        """
        OHLCV 데이터 반환.
        캐시 히트 → 반환
        캐시 미스 → fetch → 캐시 저장 → 반환
        결측치 처리: ffill 후 dropna

        Args:
            symbol:   티커 심볼
            interval: 봉 단위
            start:    시작 datetime
            end:      종료 datetime

        Returns:
            OHLCV DataFrame
        """
        cache_key = self.cache._make_key(symbol, interval, start, end)

        # 캐시 확인
        cached_df = self.cache.get(cache_key, interval)
        if cached_df is not None and not cached_df.empty:
            logger.info(f"[DataStore] 캐시 히트: {symbol} {interval} ({len(cached_df)} 행)")
            return self._clean(cached_df)

        # 캐시 미스 → fetch
        logger.info(f"[DataStore] 캐시 미스, fetch 시작: {symbol} {interval}")
        df = self.fetcher.fetch(symbol, interval, start, end)

        if df is None or df.empty:
            logger.warning(f"[DataStore] 빈 데이터 반환됨: {symbol} {interval}")
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

        # 캐시 저장
        self.cache.set(cache_key, df, interval)

        return self._clean(df)

    def _clean(self, df: pd.DataFrame) -> pd.DataFrame:
        """결측치 처리: ffill 후 dropna"""
        df = df.copy()
        df = df.ffill()
        df = df.dropna()
        return df
