"""
BacktestResult 데이터클래스 및 PerformanceAnalyzer
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class BacktestResult:
    """백테스트 결과 데이터 컨테이너"""
    strategy_name: str
    color: str
    trades_df: pd.DataFrame      # entry_time, exit_time, entry_price, exit_price, pnl, cumulative_pnl
    equity_curve: pd.Series      # 인덱스=datetime, 값=누적자본
    metrics: dict = field(default_factory=dict)
    # total_return, annual_return, mdd, sharpe, win_rate, total_trades, profit_factor


class PerformanceAnalyzer:
    """성과 지표 계산기"""

    CONTRACT_MULTIPLIER = 20  # $20 per point
    RISK_FREE_RATE = 0.02     # 연 2% 무위험 수익률

    @staticmethod
    def calculate(
        trades: list,
        equity_curve: pd.Series,
        initial_capital: float,
    ) -> dict:
        """
        성과 지표 계산.

        Args:
            trades:           거래 내역 리스트 (dict 형태)
            equity_curve:     누적 자본 시계열
            initial_capital:  초기 자본

        Returns:
            dict with keys:
              total_return (%), annual_return (%), mdd (%), sharpe,
              win_rate (%), total_trades, profit_factor
        """
        metrics = {
            "total_return": 0.0,
            "annual_return": 0.0,
            "mdd": 0.0,
            "sharpe": 0.0,
            "win_rate": 0.0,
            "total_trades": 0,
            "profit_factor": 0.0,
        }

        if equity_curve is None or len(equity_curve) == 0:
            return metrics

        final_capital = equity_curve.iloc[-1]
        total_return = (final_capital - initial_capital) / initial_capital * 100
        metrics["total_return"] = round(total_return, 2)

        # 연환산 수익률
        n_days = max(len(equity_curve), 1)
        years = n_days / 252  # 거래일 기준
        if years > 0 and final_capital > 0:
            annual_return = ((final_capital / initial_capital) ** (1 / years) - 1) * 100
        else:
            annual_return = 0.0
        metrics["annual_return"] = round(annual_return, 2)

        # MDD (Maximum Drawdown)
        cummax = equity_curve.cummax()
        drawdown = (equity_curve - cummax) / cummax.replace(0, np.nan) * 100
        mdd = drawdown.min()
        metrics["mdd"] = round(float(mdd) if not np.isnan(mdd) else 0.0, 2)

        # 샤프 비율
        daily_returns = equity_curve.pct_change().dropna()
        if len(daily_returns) > 1 and daily_returns.std() > 0:
            rf_daily = PerformanceAnalyzer.RISK_FREE_RATE / 252
            excess_returns = daily_returns - rf_daily
            sharpe = excess_returns.mean() / excess_returns.std() * np.sqrt(252)
        else:
            sharpe = 0.0
        metrics["sharpe"] = round(float(sharpe), 2)

        # 거래 기반 지표
        total_trades = len(trades)
        metrics["total_trades"] = total_trades

        if total_trades > 0:
            pnls = [t.get("pnl", 0) for t in trades]
            winners = [p for p in pnls if p > 0]
            losers = [p for p in pnls if p < 0]

            win_rate = len(winners) / total_trades * 100
            metrics["win_rate"] = round(win_rate, 2)

            total_profit = sum(winners)
            total_loss = abs(sum(losers))
            if total_loss > 0:
                profit_factor = total_profit / total_loss
            elif total_profit > 0:
                profit_factor = float("inf")
            else:
                profit_factor = 0.0
            metrics["profit_factor"] = round(profit_factor, 2)

        return metrics
