"""
Smoke tests: PySide6, pyqtgraph, yfinance 기본 동작 검증
"""
import os
import sys
import pytest

# headless 환경 설정
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_pyside6(qtbot):
    """QApplication + QMainWindow 생성 테스트"""
    from PySide6.QtWidgets import QMainWindow
    window = QMainWindow()
    # 창을 표시하지 않고 생성만
    assert window is not None


def test_pyqtgraph(qtbot):
    """PlotWidget 생성 + 데이터 플롯 테스트"""
    import pyqtgraph as pg
    import numpy as np

    widget = pg.PlotWidget()
    assert widget is not None

    x = np.arange(10)
    y = np.sin(x)
    curve = widget.plot(x, y)
    assert curve is not None


def test_yfinance():
    """NQ=F 일봉 5일치 fetch 테스트 (실제 네트워크 호출)"""
    import yfinance as yf
    import pandas as pd

    ticker = yf.Ticker("NQ=F")
    df = ticker.history(period="5d", interval="1d")

    assert isinstance(df, pd.DataFrame), "DataFrame이 반환되어야 합니다"
    assert len(df) > 0, "데이터가 있어야 합니다"
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        assert col in df.columns, f"{col} 컬럼이 있어야 합니다"
