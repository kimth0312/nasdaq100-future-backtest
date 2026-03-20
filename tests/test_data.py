"""
데이터 레이어 테스트
- DataFetcher 기간 제한 로직
- DataCache 캐시 히트/미스
- 기술 지표 정확성
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# src를 path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from data.fetcher import DataFetcher
from data.cache import DataCache
from data.store import DataStore
import indicators


# ─── 테스트 헬퍼 ───────────────────────────────────────────────────────────────

def make_dummy_ohlcv(n=100) -> pd.DataFrame:
    """테스트용 더미 OHLCV DataFrame 생성"""
    idx = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    np.random.seed(42)
    close = 18000 + np.cumsum(np.random.randn(n) * 50)
    df = pd.DataFrame({
        "Open":   close - np.abs(np.random.randn(n) * 10),
        "High":   close + np.abs(np.random.randn(n) * 20),
        "Low":    close - np.abs(np.random.randn(n) * 20),
        "Close":  close,
        "Volume": np.random.randint(10000, 100000, n).astype(float),
    }, index=idx)
    return df


# ─── test_fetcher_interval_limits ─────────────────────────────────────────────

class TestFetcherIntervalLimits:
    """각 봉 단위의 기간 제한 클리핑 로직 검증 (mock yfinance)"""

    def _make_mock_return(self) -> pd.DataFrame:
        idx = pd.date_range("2024-01-01", periods=5, freq="D", tz="UTC")
        return pd.DataFrame({
            "Open": [1.0]*5, "High": [2.0]*5,
            "Low": [0.5]*5, "Close": [1.5]*5, "Volume": [1000.0]*5
        }, index=idx)

    @pytest.mark.parametrize("interval,max_days", [
        ("1m", 7), ("5m", 60), ("15m", 60), ("60m", 730), ("1d", 36500),
    ])
    def test_interval_max_days(self, interval, max_days):
        """기간 초과 요청 시 start가 클리핑되는지 확인"""
        fetcher = DataFetcher()
        now = datetime.now(timezone.utc)
        # max_days + 100일 전을 start로 설정하면 자동으로 클리핑되어야 함
        start = now - timedelta(days=max_days + 100)
        end = now

        mock_df = self._make_mock_return()
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_df

        with patch("data.fetcher.yf.Ticker", return_value=mock_ticker):
            df = fetcher.fetch("NQ=F", interval, start, end)

        # 호출이 일어났는지 확인
        mock_ticker.history.assert_called_once()
        call_kwargs = mock_ticker.history.call_args

        # start가 (now - max_days) 근처로 클리핑됐는지 확인
        called_start = call_kwargs.kwargs.get("start") or call_kwargs[1].get("start")
        if called_start is not None:
            if hasattr(called_start, 'tzinfo') and called_start.tzinfo is None:
                called_start = called_start.replace(tzinfo=timezone.utc)
            earliest_allowed = now - timedelta(days=max_days)
            # 1일 오차 허용
            assert called_start >= earliest_allowed - timedelta(days=1), \
                f"{interval}: start가 {max_days}일 제한으로 클리핑되지 않음"

    def test_invalid_interval_raises(self):
        """지원하지 않는 interval 시 ValueError"""
        fetcher = DataFetcher()
        now = datetime.now(timezone.utc)
        with pytest.raises(ValueError):
            fetcher.fetch("NQ=F", "3m", now - timedelta(days=1), now)

    def test_empty_result_on_yfinance_error(self):
        """yfinance 예외 시 빈 DataFrame 반환"""
        fetcher = DataFetcher()
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=5)

        with patch("data.fetcher.yf.Ticker", side_effect=Exception("Network error")):
            df = fetcher.fetch("NQ=F", "1d", start, now)

        assert df.empty


# ─── test_cache_hit ────────────────────────────────────────────────────────────

class TestCacheHit:
    """캐시 히트/미스 동작 검증"""

    def test_cache_hit_no_fetch(self):
        """동일 요청 2회 시 2번째는 캐시에서 (fetch 미호출 확인)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = DataCache(db_path=Path(tmpdir) / "test.db")
            mock_fetcher = MagicMock(spec=DataFetcher)
            dummy_df = make_dummy_ohlcv(50)
            mock_fetcher.fetch.return_value = dummy_df

            store = DataStore(cache=cache, fetcher=mock_fetcher)

            now = datetime.now(timezone.utc)
            start = now - timedelta(days=30)
            end = now

            # 첫 번째 호출 → fetch 발생
            df1 = store.get_bars("NQ=F", "1d", start, end)
            assert mock_fetcher.fetch.call_count == 1

            # 두 번째 호출 → 캐시 히트 (fetch 미호출)
            df2 = store.get_bars("NQ=F", "1d", start, end)
            assert mock_fetcher.fetch.call_count == 1, "2번째 호출에서 fetch가 호출되면 안 됨"

            assert len(df1) > 0
            assert len(df2) > 0

    def test_cache_ttl_expiry(self):
        """TTL 만료 후 재fetch 확인"""
        import time

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = DataCache(db_path=Path(tmpdir) / "test.db")
            key = cache._make_key("NQ=F", "1d", "2024-01-01", "2024-12-31")
            dummy_df = make_dummy_ohlcv(10)

            # TTL=0으로 즉시 만료되도록 강제로 오래된 타임스탬프 저장
            import sqlite3
            from io import BytesIO
            buf = BytesIO()
            dummy_df.to_parquet(buf)
            blob = buf.getvalue()

            old_time = time.time() - 999999  # 매우 오래된 시각
            with sqlite3.connect(cache.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO cache (key, data, created_at, interval) VALUES (?, ?, ?, ?)",
                    (key, blob, old_time, "1d")
                )
                conn.commit()

            # TTL=86400 기준으로 만료됨 → None 반환
            result = cache.get(key, "1d")
            assert result is None, "TTL 만료된 캐시는 None을 반환해야 함"

    def test_cache_stores_and_retrieves(self):
        """set 후 get으로 동일 DataFrame 반환"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = DataCache(db_path=Path(tmpdir) / "test.db")
            key = cache._make_key("NQ=F", "1d", "start", "end")
            dummy_df = make_dummy_ohlcv(20)

            cache.set(key, dummy_df, "1d")
            retrieved = cache.get(key, "1d")

            assert retrieved is not None
            assert len(retrieved) == len(dummy_df)


# ─── test_indicators ──────────────────────────────────────────────────────────

class TestIndicators:
    """기술 지표 정확성 검증"""

    def test_sma_known_value(self):
        """SMA 알려진 값 검증"""
        data = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
        result = indicators.sma(data, 3)

        # 처음 2개는 NaN
        assert pd.isna(result.iloc[0])
        assert pd.isna(result.iloc[1])

        # 3번째 값 = (1+2+3)/3 = 2.0
        assert abs(result.iloc[2] - 2.0) < 1e-10

        # 10번째 값 = (8+9+10)/3 = 9.0
        assert abs(result.iloc[9] - 9.0) < 1e-10

    def test_ema_first_value(self):
        """EMA가 NaN 없이 계산되는지 확인"""
        data = pd.Series(range(1, 21), dtype=float)
        result = indicators.ema(data, 5)
        # min_periods=5이므로 처음 4개는 NaN
        assert pd.isna(result.iloc[0])
        assert not pd.isna(result.iloc[4])

    def test_rsi_range(self):
        """RSI 값이 0~100 범위인지 확인"""
        np.random.seed(0)
        data = pd.Series(18000 + np.cumsum(np.random.randn(200) * 50))
        result = indicators.rsi(data, 14)
        valid = result.dropna()

        assert len(valid) > 0
        assert (valid >= 0).all(), f"RSI < 0 발생: {valid[valid < 0]}"
        assert (valid <= 100).all(), f"RSI > 100 발생: {valid[valid > 100]}"

    def test_macd_returns_three_series(self):
        """MACD가 3개 Series 반환"""
        data = pd.Series(range(1, 101), dtype=float)
        result = indicators.macd(data)
        assert len(result) == 3
        macd_line, signal_line, hist = result
        assert isinstance(macd_line, pd.Series)
        assert isinstance(signal_line, pd.Series)
        assert isinstance(hist, pd.Series)

    def test_bollinger_bands_ordering(self):
        """볼린저 밴드: upper >= middle >= lower"""
        np.random.seed(1)
        data = pd.Series(18000 + np.cumsum(np.random.randn(100) * 30))
        upper, middle, lower = indicators.bollinger(data, 20, 2)

        valid_mask = upper.notna() & middle.notna() & lower.notna()
        assert valid_mask.sum() > 0

        assert (upper[valid_mask] >= middle[valid_mask]).all()
        assert (middle[valid_mask] >= lower[valid_mask]).all()

    def test_sma_insufficient_data(self):
        """데이터가 period보다 적으면 전부 NaN"""
        data = pd.Series([1.0, 2.0, 3.0])
        result = indicators.sma(data, 5)
        assert result.isna().all()
