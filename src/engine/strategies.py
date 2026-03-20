"""
내장 전략 구현:
- GoldenCross (SMA 크로스)
- RSIMeanReversion (RSI 평균회귀)
- MACDMomentum (MACD 모멘텀)
"""
import numpy as np
import pandas as pd

from engine.base_strategy import BaseStrategy
from indicators import sma, rsi, macd


class GoldenCross(BaseStrategy):
    """Golden Cross: 단기 SMA가 장기 SMA를 상향돌파 시 매수"""

    name = "GoldenCross"
    display_name = "Golden Cross (SMA)"
    color = "#2ECC71"

    def _default_params(self) -> dict:
        return {"fast": 20, "slow": 60}

    def get_param_schema(self) -> list:
        return [
            {"key": "fast", "label": "Fast Period", "type": "int", "min": 2, "max": 200, "default": 20},
            {"key": "slow", "label": "Slow Period", "type": "int", "min": 5, "max": 500, "default": 60},
        ]

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        fast = self.params.get("fast", 20)
        slow = self.params.get("slow", 60)

        fast_sma = sma(df["Close"], fast)
        slow_sma = sma(df["Close"], slow)

        signals = pd.Series(0, index=df.index, dtype=int)

        # fast > slow: 강세 구간
        bullish = fast_sma > slow_sma
        # fast < slow: 약세 구간
        bearish = fast_sma < slow_sma

        # 상향돌파: 이전 바에서 bearish → 현재 바 bullish
        cross_up = bullish & (~bullish.shift(1).fillna(False).astype(bool))
        # 하향돌파: 이전 바에서 bullish → 현재 바 bearish
        cross_down = bearish & (~bearish.shift(1).fillna(False).astype(bool))

        signals[cross_up] = 1
        signals[cross_down] = -1

        return signals

    def get_indicator_lines(self, df: pd.DataFrame) -> dict:
        fast = self.params.get("fast", 20)
        slow = self.params.get("slow", 60)
        return {
            f"SMA{fast}": sma(df["Close"], fast),
            f"SMA{slow}": sma(df["Close"], slow),
        }


class RSIMeanReversion(BaseStrategy):
    """RSI Mean Reversion: RSI 과매도 구간 매수, 과매수 구간 청산"""

    name = "RSIMeanReversion"
    display_name = "RSI Mean Reversion"
    color = "#3498DB"

    def _default_params(self) -> dict:
        return {"period": 14, "oversold": 30, "overbought": 70}

    def get_param_schema(self) -> list:
        return [
            {"key": "period", "label": "RSI Period", "type": "int", "min": 2, "max": 50, "default": 14},
            {"key": "oversold", "label": "Oversold Level", "type": "int", "min": 10, "max": 40, "default": 30},
            {"key": "overbought", "label": "Overbought Level", "type": "int", "min": 60, "max": 90, "default": 70},
        ]

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        period = self.params.get("period", 14)
        oversold = self.params.get("oversold", 30)
        overbought = self.params.get("overbought", 70)

        rsi_val = rsi(df["Close"], period)

        signals = pd.Series(0, index=df.index, dtype=int)

        # RSI가 oversold 아래로 진입: 매수
        signals[rsi_val < oversold] = 1
        # RSI가 overbought 위로 진입: 청산
        signals[rsi_val > overbought] = -1

        return signals

    def get_indicator_lines(self, df: pd.DataFrame) -> dict:
        period = self.params.get("period", 14)
        return {
            f"RSI({period})": rsi(df["Close"], period),
        }


class MACDMomentum(BaseStrategy):
    """MACD Momentum: MACD선이 시그널선을 상향돌파 시 매수, 하향돌파 시 청산"""

    name = "MACDMomentum"
    display_name = "MACD Momentum"
    color = "#E74C3C"

    def _default_params(self) -> dict:
        return {"fast": 12, "slow": 26, "signal": 9}

    def get_param_schema(self) -> list:
        return [
            {"key": "fast", "label": "Fast EMA", "type": "int", "min": 2, "max": 50, "default": 12},
            {"key": "slow", "label": "Slow EMA", "type": "int", "min": 5, "max": 100, "default": 26},
            {"key": "signal", "label": "Signal Period", "type": "int", "min": 2, "max": 30, "default": 9},
        ]

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        fast = self.params.get("fast", 12)
        slow = self.params.get("slow", 26)
        signal_period = self.params.get("signal", 9)

        macd_line, signal_line, _ = macd(df["Close"], fast, slow, signal_period)

        signals = pd.Series(0, index=df.index, dtype=int)

        # MACD > signal: 강세
        bullish = macd_line > signal_line
        bearish = macd_line < signal_line

        # 상향돌파
        cross_up = bullish & (~bullish.shift(1).fillna(False).astype(bool))
        # 하향돌파
        cross_down = bearish & (~bearish.shift(1).fillna(False).astype(bool))

        signals[cross_up] = 1
        signals[cross_down] = -1

        return signals

    def get_indicator_lines(self, df: pd.DataFrame) -> dict:
        fast = self.params.get("fast", 12)
        slow = self.params.get("slow", 26)
        signal_period = self.params.get("signal", 9)
        macd_line, signal_line, hist = macd(df["Close"], fast, slow, signal_period)
        return {
            "MACD": macd_line,
            "Signal": signal_line,
            "Histogram": hist,
        }


# 전략 레지스트리
STRATEGIES = {
    GoldenCross.name: GoldenCross,
    RSIMeanReversion.name: RSIMeanReversion,
    MACDMomentum.name: MACDMomentum,
}
