"""
백테스팅 엔진 테스트
- Lookahead 금지 검증
- 수수료 적용 확인
- 결정론성 (동일 입력 → 동일 결과)
- 멀티 전략 병렬 실행
"""
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.backtest import BacktestEngine, FLAT, LONG
from engine.base_strategy import BaseStrategy
from engine.strategies import GoldenCross, RSIMeanReversion, MACDMomentum
from engine.performance import BacktestResult


# ─── 테스트 헬퍼 ───────────────────────────────────────────────────────────────

def make_dummy_ohlcv(n=200, seed=42) -> pd.DataFrame:
    """테스트용 더미 OHLCV DataFrame"""
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
    return df


class CountingStrategy(BaseStrategy):
    """시그널 생성 시 데이터 접근 범위를 추적하는 전략"""

    name = "CountingStrategy"
    display_name = "Counting Strategy"
    color = "#FF0000"

    def __init__(self):
        super().__init__()
        self.signal_call_count = 0

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        self.signal_call_count += 1
        signals = pd.Series(0, index=df.index, dtype=int)
        return signals


class AlwaysBuyStrategy(BaseStrategy):
    """항상 첫 번째 바에서 매수, 두 번째에서 청산"""

    name = "AlwaysBuy"
    display_name = "Always Buy"
    color = "#00FF00"

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        signals = pd.Series(0, index=df.index, dtype=int)
        if len(df) >= 2:
            signals.iloc[0] = 1   # 첫 바에서 매수
            signals.iloc[1] = -1  # 두 번째 바에서 청산
        return signals


class ControlledSignalStrategy(BaseStrategy):
    """지정된 인덱스에서만 시그널 발생"""

    name = "ControlledSignal"
    display_name = "Controlled Signal"
    color = "#0000FF"

    def __init__(self, buy_idx=10, sell_idx=20):
        super().__init__()
        self.buy_idx = buy_idx
        self.sell_idx = sell_idx

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        signals = pd.Series(0, index=df.index, dtype=int)
        if self.buy_idx < len(df):
            signals.iloc[self.buy_idx] = 1
        if self.sell_idx < len(df):
            signals.iloc[self.sell_idx] = -1
        return signals


# ─── 테스트 케이스 ─────────────────────────────────────────────────────────────

class TestNoLookahead:
    """Lookahead 금지 검증"""

    def test_signals_only_use_past_data(self):
        """
        시그널 i는 df.iloc[:i+1] 데이터만 사용해야 함.
        GoldenCross는 SMA를 rolling으로 계산하므로 자동으로 lookahead 없음.
        여기서는 시그널이 미래 데이터에 의존하지 않는지 간접 검증:
        - 데이터를 앞부분만 잘라서 실행한 결과와
        - 전체 데이터로 실행한 후 앞부분 시그널이 동일한지 비교
        """
        df = make_dummy_ohlcv(100)
        strategy = GoldenCross()

        # 전체 데이터로 시그널 생성
        signals_full = strategy.generate_signals(df)

        # 앞 50행만으로 시그널 생성
        signals_partial = strategy.generate_signals(df.iloc[:50])

        # 앞 50행의 시그널은 동일해야 함 (lookahead가 없다면)
        pd.testing.assert_series_equal(
            signals_full.iloc[:50].reset_index(drop=True),
            signals_partial.reset_index(drop=True),
            check_names=False,
        )

    def test_execution_uses_next_bar_open(self):
        """
        i번째 바 시그널이 i+1번째 바 시가에 체결되는지 확인.
        AlwaysBuyStrategy: 0번 바 시그널 1 → 1번 바 시가에 체결
        """
        df = make_dummy_ohlcv(20)
        strategy = AlwaysBuyStrategy()
        engine = BacktestEngine()

        result = engine.run(df, strategy, initial_capital=100000, commission=2.0, slippage=0.0)

        assert len(result.trades_df) >= 1
        trade = result.trades_df.iloc[0]

        # 진입가 = 1번 바 시가
        expected_entry = df.iloc[1]["Open"]
        assert abs(trade["entry_price"] - expected_entry) < 1e-6, \
            f"진입가 불일치: {trade['entry_price']} vs {expected_entry}"


class TestCommissionApplied:
    """수수료 적용 확인"""

    def test_commission_reduces_capital(self):
        """거래 후 capital이 commission(왕복)만큼 감소하는지 확인"""
        df = make_dummy_ohlcv(20)
        engine = BacktestEngine()
        initial_capital = 100000.0
        commission = 5.0  # 편도 $5
        slippage = 0.0    # 슬리피지 제거

        # 무조건 0번 바 매수, 1번 바 청산
        strategy = AlwaysBuyStrategy()
        result = engine.run(df, strategy, initial_capital=initial_capital,
                            commission=commission, slippage=slippage)

        assert len(result.trades_df) >= 1

        trade = result.trades_df.iloc[0]
        entry = trade["entry_price"]
        exit_ = trade["exit_price"]

        # 기대 PnL = (exit - entry) * 20 - commission * 2
        expected_pnl = (exit_ - entry) * 20 - commission * 2
        actual_pnl = trade["pnl"]

        assert abs(actual_pnl - expected_pnl) < 1e-6, \
            f"PnL 불일치: {actual_pnl} vs {expected_pnl}"

    def test_no_trade_no_change(self):
        """거래 없으면 capital 변화 없음"""
        df = make_dummy_ohlcv(50)
        engine = BacktestEngine()
        initial_capital = 100000.0

        # 시그널 없는 전략
        counting = CountingStrategy()
        result = engine.run(df, counting, initial_capital=initial_capital)

        assert len(result.trades_df) == 0
        # equity_curve 전체가 initial_capital과 동일
        assert (result.equity_curve == initial_capital).all(), \
            "거래 없으면 capital이 변하면 안 됨"


class TestDeterministic:
    """결정론성: 동일 입력 2회 실행 → 동일 결과"""

    def test_same_result_twice(self):
        """GoldenCross 동일 데이터 2회 실행 결과 동일"""
        df = make_dummy_ohlcv(200)
        engine = BacktestEngine()
        strategy = GoldenCross()

        result1 = engine.run(df, strategy)
        result2 = engine.run(df, strategy)

        assert result1.metrics == result2.metrics
        pd.testing.assert_series_equal(result1.equity_curve, result2.equity_curve)
        if len(result1.trades_df) > 0:
            pd.testing.assert_frame_equal(result1.trades_df, result2.trades_df)


class TestMultiStrategy:
    """멀티 전략 병렬 실행"""

    def test_run_multiple_returns_three(self):
        """run_multiple로 3개 전략 실행, 결과 3개 반환 확인"""
        df = make_dummy_ohlcv(300)
        engine = BacktestEngine()
        strategies = [GoldenCross(), RSIMeanReversion(), MACDMomentum()]

        results = engine.run_multiple(df, strategies)

        assert len(results) == 3
        for r in results:
            assert isinstance(r, BacktestResult)

    def test_results_ordered_by_strategy(self):
        """결과 순서가 strategies 리스트 순서와 동일"""
        df = make_dummy_ohlcv(300)
        engine = BacktestEngine()
        strategies = [GoldenCross(), RSIMeanReversion(), MACDMomentum()]

        results = engine.run_multiple(df, strategies)

        for i, (strategy, result) in enumerate(zip(strategies, results)):
            assert result.strategy_name == strategy.name, \
                f"인덱스 {i}: 전략명 불일치 {result.strategy_name} vs {strategy.name}"

    def test_run_multiple_vs_run_single(self):
        """run_multiple과 run 개별 실행 결과 동일"""
        df = make_dummy_ohlcv(200)
        engine = BacktestEngine()

        gc = GoldenCross()
        result_single = engine.run(df, gc)
        results_multi = engine.run_multiple(df, [gc])

        assert results_multi[0].metrics == result_single.metrics
