"""
BacktestEngine: 이벤트 드리븐 백테스트 실행 엔진
포지션/수수료/슬리피지 관리
"""
import concurrent.futures
import logging
from typing import List

import numpy as np
import pandas as pd

from engine.base_strategy import BaseStrategy
from engine.performance import BacktestResult, PerformanceAnalyzer

logger = logging.getLogger(__name__)

FLAT = 0
LONG = 1


class BacktestEngine:
    """이벤트 드리븐 백테스트 실행 엔진"""

    CONTRACT_MULTIPLIER = 20   # $20 per point
    MIN_TICK = 0.25

    def run(
        self,
        df: pd.DataFrame,
        strategy: BaseStrategy,
        initial_capital: float = 100000,
        commission: float = 2.0,
        slippage: float = 0.25,
    ) -> BacktestResult:
        """
        이벤트 드리븐 백테스트 실행.

        시그널 i → i+1 바 시가에 체결
        P&L = (exit_price - entry_price) * CONTRACT_MULTIPLIER - commission*2
        슬리피지: 진입 +slippage, 청산 -slippage

        Args:
            df:              OHLCV DataFrame
            strategy:        전략 인스턴스
            initial_capital: 초기 자본
            commission:      편도 수수료 (달러)
            slippage:        슬리피지 (포인트)

        Returns:
            BacktestResult
        """
        if df is None or len(df) < 2:
            logger.warning(f"[BacktestEngine] 데이터 부족: {len(df) if df is not None else 0}행")
            empty_equity = pd.Series([initial_capital], dtype=float)
            metrics = PerformanceAnalyzer.calculate([], empty_equity, initial_capital)
            return BacktestResult(
                strategy_name=strategy.name,
                color=strategy.color,
                trades_df=pd.DataFrame(),
                equity_curve=empty_equity,
                metrics=metrics,
            )

        # 시그널 생성
        signals = strategy.generate_signals(df)

        capital = float(initial_capital)
        position = FLAT
        entry_price = None
        entry_time = None
        trades = []
        equity = []

        n = len(df)

        for i in range(n):
            signal = signals.iloc[i]

            # 마지막 바에서 미청산 포지션 강제 청산 (다음 바 없음)
            if i == n - 1:
                if position == LONG:
                    exit_price = df.iloc[i]["Close"]
                    pnl = (exit_price - entry_price) * self.CONTRACT_MULTIPLIER
                    pnl -= commission * 2  # 왕복 수수료
                    capital += pnl
                    cumulative_pnl = sum(t["pnl"] for t in trades) + pnl
                    trades.append({
                        "entry_time": entry_time,
                        "exit_time": df.index[i],
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "pnl": pnl,
                        "cumulative_pnl": cumulative_pnl,
                    })
                    position = FLAT
                equity.append(capital)
                break

            # 다음 바 시가 (체결 기준)
            next_open = df.iloc[i + 1]["Open"]

            # 청산 처리 (LONG 보유 중 → -1 시그널)
            if position == LONG and signal == -1:
                exit_price = next_open - slippage  # 청산 슬리피지
                pnl = (exit_price - entry_price) * self.CONTRACT_MULTIPLIER
                pnl -= commission * 2  # 왕복 수수료
                capital += pnl
                cumulative_pnl = sum(t["pnl"] for t in trades) + pnl
                trades.append({
                    "entry_time": entry_time,
                    "exit_time": df.index[i + 1],
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "pnl": pnl,
                    "cumulative_pnl": cumulative_pnl,
                })
                position = FLAT
                entry_price = None
                entry_time = None

            # 진입 처리 (FLAT 상태 → +1 시그널)
            if position == FLAT and signal == 1:
                entry_price = next_open + slippage  # 진입 슬리피지
                entry_time = df.index[i + 1]
                position = LONG

            equity.append(capital)

        equity_series = pd.Series(equity, index=df.index[:len(equity)], dtype=float)

        # trades_df 생성
        if trades:
            trades_df = pd.DataFrame(trades)
        else:
            trades_df = pd.DataFrame(
                columns=["entry_time", "exit_time", "entry_price", "exit_price", "pnl", "cumulative_pnl"]
            )

        # 성과 지표 계산
        metrics = PerformanceAnalyzer.calculate(trades, equity_series, initial_capital)

        logger.info(
            f"[BacktestEngine] {strategy.name}: "
            f"거래 {metrics['total_trades']}건, "
            f"수익률 {metrics['total_return']}%"
        )

        return BacktestResult(
            strategy_name=strategy.name,
            color=strategy.color,
            trades_df=trades_df,
            equity_curve=equity_series,
            metrics=metrics,
        )

    def run_multiple(
        self,
        df: pd.DataFrame,
        strategies: List[BaseStrategy],
        initial_capital: float = 100000,
        commission: float = 2.0,
        slippage: float = 0.25,
    ) -> List[BacktestResult]:
        """
        여러 전략을 ThreadPoolExecutor로 병렬 실행.
        결과 순서는 strategies 리스트 순서와 동일.
        """
        results = [None] * len(strategies)

        def _run_one(idx, strategy):
            return idx, self.run(df, strategy, initial_capital, commission, slippage)

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(strategies)) as executor:
            futures = {
                executor.submit(_run_one, i, s): i
                for i, s in enumerate(strategies)
            }
            for future in concurrent.futures.as_completed(futures):
                try:
                    idx, result = future.result()
                    results[idx] = result
                except Exception as e:
                    logger.error(f"[BacktestEngine] 전략 실행 오류: {e}")

        return results
