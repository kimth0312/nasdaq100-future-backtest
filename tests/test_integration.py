"""
통합 테스트
- 데이터 정합성
- 엔진 결정론성 / 자본 드리프트 없음
- 멀티 전략 색상 및 수 검증
- 에러 핸들링 소스 검토
"""
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from data.store import DataStore
from data.fetcher import DataFetcher
from data.cache import DataCache
from engine.backtest import BacktestEngine
from engine.strategies import GoldenCross, RSIMeanReversion, MACDMomentum
from engine.performance import BacktestResult


# ─── 헬퍼 ─────────────────────────────────────────────────────────────────────

def make_ohlcv(n=300, seed=42) -> pd.DataFrame:
    idx = pd.date_range("2022-01-01", periods=n, freq="B", tz="UTC")
    rng = np.random.RandomState(seed)
    close = 18000 + np.cumsum(rng.randn(n) * 50)
    df = pd.DataFrame({
        "Open":   close - np.abs(rng.randn(n) * 10),
        "High":   close + np.abs(rng.randn(n) * 20),
        "Low":    close - np.abs(rng.randn(n) * 20),
        "Close":  close,
        "Volume": rng.randint(10000, 100000, n).astype(float),
    }, index=idx)
    # OHLCV 논리적 정합성 보정
    df["High"] = df[["Open", "Close", "High"]].max(axis=1)
    df["Low"]  = df[["Open", "Close", "Low"]].min(axis=1)
    return df


# ─── 테스트 1: 데이터 정합성 ──────────────────────────────────────────────────

class TestDataQuality:
    def test_data_quality(self):
        """NQ=F 일봉 1년치 데이터 정합성 검증"""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=365)
        end = now

        fetcher = DataFetcher()
        df = fetcher.fetch("NQ=F", "1d", start, end)

        assert df is not None, "DataFrame이 None이면 안 됩니다"
        assert len(df) > 0, "데이터가 있어야 합니다"

        # NaN 비율 < 1%
        nan_ratio = df.isnull().values.sum() / df.size
        assert nan_ratio < 0.01, f"NaN 비율 {nan_ratio:.2%} >= 1%"

        valid = df.dropna()

        # High >= max(Open, Close)
        assert (valid["High"] >= valid[["Open", "Close"]].max(axis=1) - 0.01).all(), \
            "High < max(Open, Close) 위반"

        # Low <= min(Open, Close)
        assert (valid["Low"] <= valid[["Open", "Close"]].min(axis=1) + 0.01).all(), \
            "Low > min(Open, Close) 위반"

        # Volume > 0 비율 > 95%
        vol_positive_ratio = (valid["Volume"] > 0).sum() / len(valid)
        assert vol_positive_ratio > 0.95, \
            f"Volume > 0 비율 {vol_positive_ratio:.2%} <= 95%"

    def test_all_intervals(self):
        """각 봉 단위별 fetch 1회 실행 — 비어있지 않음 확인"""
        now = datetime.now(timezone.utc)
        fetcher = DataFetcher()

        test_cases = [
            ("1m",  now - timedelta(days=3)),
            ("5m",  now - timedelta(days=30)),
            ("15m", now - timedelta(days=30)),
            ("60m", now - timedelta(days=30)),
            ("1d",  now - timedelta(days=30)),
        ]

        for interval, start in test_cases:
            df = fetcher.fetch("NQ=F", interval, start, now)
            assert df is not None and len(df) > 0, \
                f"{interval} 봉: 빈 DataFrame 반환됨"


# ─── 테스트 2: 엔진 정합성 ────────────────────────────────────────────────────

class TestEngineCorrectness:
    def test_deterministic_3runs(self):
        """GoldenCross 동일 데이터 3회 → 동일 결과"""
        df = make_ohlcv(300)
        engine = BacktestEngine()
        strategy = GoldenCross()

        results = [engine.run(df, strategy) for _ in range(3)]

        for r in results[1:]:
            assert r.metrics == results[0].metrics, "3회 실행 결과가 다릅니다"
            pd.testing.assert_series_equal(r.equity_curve, results[0].equity_curve)

    def test_no_capital_drift(self):
        """거래 없는 구간에서 equity_curve가 변하지 않음"""
        # 시그널 없는 전략
        from engine.base_strategy import BaseStrategy

        class NoSignalStrategy(BaseStrategy):
            name = "NoSignal"
            display_name = "No Signal"
            color = "#FFFFFF"

            def generate_signals(self, df):
                return pd.Series(0, index=df.index, dtype=int)

        df = make_ohlcv(100)
        engine = BacktestEngine()
        result = engine.run(df, NoSignalStrategy(), initial_capital=100000)

        # 거래 없으면 equity_curve 전체가 100000
        assert (result.equity_curve == 100000).all(), \
            "거래 없는 구간에서 equity_curve가 변했습니다"


# ─── 테스트 3: 멀티 전략 ──────────────────────────────────────────────────────

class TestMultiStrategy:
    def test_multi_strategy_colors(self):
        """run_multiple 결과 각 전략 색상이 다름"""
        df = make_ohlcv(300)
        engine = BacktestEngine()
        strategies = [GoldenCross(), RSIMeanReversion(), MACDMomentum()]

        results = engine.run_multiple(df, strategies)

        colors = [r.color for r in results if r is not None]
        assert len(set(colors)) == len(colors), \
            f"전략 색상이 중복됩니다: {colors}"

    def test_multi_strategy_count(self):
        """run_multiple 결과 3개 BacktestResult 반환"""
        df = make_ohlcv(300)
        engine = BacktestEngine()
        strategies = [GoldenCross(), RSIMeanReversion(), MACDMomentum()]

        results = engine.run_multiple(df, strategies)

        assert len(results) == 3, f"결과 수 {len(results)} != 3"
        for r in results:
            assert isinstance(r, BacktestResult), f"결과 타입 오류: {type(r)}"


# ─── 테스트 4: 에러 핸들링 (소스 코드 검토) ───────────────────────────────────

class TestErrorHandling:
    def test_worker_emits_error_on_exception(self):
        """
        worker.py에서 예외 발생 시 error_occurred 시그널 발행 확인.
        소스 코드를 읽어서 try/except → error_occurred.emit 패턴 확인.
        """
        worker_path = Path(__file__).parent.parent / "src" / "ui" / "worker.py"
        source = worker_path.read_text()

        assert "error_occurred" in source, "worker.py에 error_occurred 시그널이 없습니다"
        assert "except Exception" in source, "worker.py에 예외 처리가 없습니다"
        assert "error_occurred.emit" in source, "worker.py에서 error_occurred.emit이 없습니다"

    def test_store_handles_empty_dataframe(self):
        """DataFetcher에서 빈 DataFrame 반환 시 DataStore에서 처리 확인"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = DataCache(db_path=Path(tmpdir) / "test.db")
            mock_fetcher = MagicMock(spec=DataFetcher)
            mock_fetcher.fetch.return_value = pd.DataFrame(
                columns=["Open", "High", "Low", "Close", "Volume"]
            )

            store = DataStore(cache=cache, fetcher=mock_fetcher)
            now = datetime.now(timezone.utc)

            df = store.get_bars("NQ=F", "1d", now - timedelta(days=30), now)

            # 빈 DataFrame 반환 (예외 없음)
            assert df is not None
            assert isinstance(df, pd.DataFrame)
            # 빈 결과여야 함
            assert len(df) == 0

    def test_engine_handles_empty_dataframe(self):
        """BacktestEngine이 빈 DataFrame 입력 시 빈 BacktestResult 반환"""
        engine = BacktestEngine()
        strategy = GoldenCross()

        empty_df = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        result = engine.run(empty_df, strategy)

        assert result is not None
        assert isinstance(result, BacktestResult)
        assert result.metrics["total_trades"] == 0
