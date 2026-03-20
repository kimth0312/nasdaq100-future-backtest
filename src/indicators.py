"""
기술 지표 계산 함수 모음
모두 numpy 벡터라이즈드 구현
"""
import numpy as np
import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    """단순 이동평균 (Simple Moving Average)"""
    return series.rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """지수 이동평균 (Exponential Moving Average)"""
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    상대강도지수 (Relative Strength Index)
    값 범위: 0 ~ 100
    """
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    avg_gain = gain.ewm(com=period - 1, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_val = 100 - (100 / (1 + rs))

    return rsi_val


def macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    MACD (Moving Average Convergence/Divergence)

    Returns:
        (macd_line, signal_line, histogram)
    """
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def bollinger(
    series: pd.Series,
    period: int = 20,
    std: int = 2,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    볼린저 밴드 (Bollinger Bands)

    Returns:
        (upper_band, middle_band, lower_band)
    """
    middle = sma(series, period)
    std_dev = series.rolling(window=period, min_periods=period).std()
    upper = middle + std * std_dev
    lower = middle - std * std_dev
    return upper, middle, lower
