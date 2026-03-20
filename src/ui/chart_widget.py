"""
ChartWidget: pyqtgraph 기반 캔들스틱 차트
- 캔들스틱 (상승=초록, 하락=빨강)
- 거래량 서브플롯 (x축 동기화)
- 마우스 크로스헤어
- OHLCV 툴팁
- 전략 마커 오버레이
- 지표선 오버레이
- Replay 지원
"""
import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QPicture, QColor, QPen, QBrush
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy
from pyqtgraph import GraphicsObject


class CandlestickItem(GraphicsObject):
    """캔들스틱 렌더링 GraphicsObject"""

    def __init__(self):
        super().__init__()
        self._picture = None
        self._data = []  # list of (t, open, high, low, close)
        self._rect = None

    def set_data(self, data):
        """
        data: list of (t, open, high, low, close)
              t는 float (timestamp)
        """
        self._data = data
        self._generate_picture()
        self.informViewBoundsChanged()

    def _generate_picture(self):
        if not self._data:
            self._picture = QPicture()
            return

        picture = QPicture()
        painter = QPainter(picture)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        w = 0.3  # 캔들 반폭

        for t, o, h, l, c in self._data:
            if c >= o:
                color = QColor("#2ECC71")  # 상승: 초록
            else:
                color = QColor("#E74C3C")  # 하락: 빨강

            pen = QPen(color)
            pen.setWidth(0)
            painter.setPen(pen)

            # 윅 (고가-저가 선)
            painter.drawLine(QPointF(t, l), QPointF(t, h))

            # 몸통 (open-close 사각형)
            painter.setBrush(QBrush(color))
            body_top = max(o, c)
            body_bottom = min(o, c)
            body_height = max(body_top - body_bottom, 0.001)  # 최소 높이
            painter.drawRect(
                int(t * 1000 - w * 1000) / 1000,
                body_bottom,
                w * 2,
                body_height,
            )

        painter.end()
        self._picture = picture

    def paint(self, painter, *args):
        if self._picture:
            self._picture.play(painter)

    def boundingRect(self):
        if not self._data:
            return pg.QtCore.QRectF(0, 0, 1, 1)
        ts = [d[0] for d in self._data if not np.isnan(d[0])]
        lows = [d[3] for d in self._data if not np.isnan(d[3])]
        highs = [d[2] for d in self._data if not np.isnan(d[2])]
        if not ts or not lows or not highs:
            return pg.QtCore.QRectF(0, 0, 1, 1)
        return pg.QtCore.QRectF(
            min(ts) - 0.5,
            min(lows),
            max(ts) - min(ts) + 1,
            max(highs) - min(lows),
        )


class ChartWidget(QWidget):
    """메인 차트 위젯"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._df = None
        self._results = []
        self._replay_index = 0
        self._marker_items = []
        self._indicator_items = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # pyqtgraph 설정
        pg.setConfigOption("background", "#1E1E1E")
        pg.setConfigOption("foreground", "#CCCCCC")

        # GraphicsLayoutWidget
        self.graphics_layout = pg.GraphicsLayoutWidget()
        layout.addWidget(self.graphics_layout)

        # 캔들 플롯
        self.candle_plot = self.graphics_layout.addPlot(row=0, col=0)
        self.candle_plot.setLabel("left", "Price")
        self.candle_plot.showGrid(x=True, y=True, alpha=0.3)
        self.candle_plot.setMenuEnabled(False)

        # 거래량 플롯
        self.volume_plot = self.graphics_layout.addPlot(row=1, col=0)
        self.volume_plot.setLabel("left", "Volume")
        self.volume_plot.showGrid(x=True, y=True, alpha=0.3)
        self.volume_plot.setMenuEnabled(False)
        self.volume_plot.setMaximumHeight(120)

        # x축 동기화
        self.volume_plot.setXLink(self.candle_plot)

        # 캔들스틱 아이템
        self.candle_item = CandlestickItem()
        self.candle_plot.addItem(self.candle_item)

        # 거래량 바 — 초기 데이터를 [0], [0]으로 설정하여 NaN 방지
        self.volume_bars = pg.BarGraphItem(x=[0], height=[0], width=0.6, brush="#5599BB")
        self.volume_plot.addItem(self.volume_bars)

        # 초기 auto-range 비활성화 (빈 상태에서 NaN 방지)
        self.candle_plot.disableAutoRange()
        self.volume_plot.disableAutoRange()
        self.candle_plot.setRange(xRange=[0, 1], yRange=[0, 1])
        self.volume_plot.setRange(xRange=[0, 1], yRange=[0, 1])

        # 크로스헤어
        self.vline = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("#FFFFFF", width=1, style=Qt.PenStyle.DashLine))
        self.hline = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen("#FFFFFF", width=1, style=Qt.PenStyle.DashLine))
        self.candle_plot.addItem(self.vline)
        self.candle_plot.addItem(self.hline)

        # 툴팁 레이블
        self.tooltip_label = pg.TextItem(text="", anchor=(0, 1), color="#FFFFFF")
        self.tooltip_label.setZValue(100)
        self.candle_plot.addItem(self.tooltip_label)

        # "데이터 없음" 레이블
        self.no_data_label = pg.TextItem(
            text="데이터가 없습니다",
            anchor=(0.5, 0.5),
            color="#888888",
        )
        self.no_data_label.setFont(pg.QtGui.QFont("Arial", 16))
        self.candle_plot.addItem(self.no_data_label)
        self.no_data_label.setVisible(False)

        # 마우스 이벤트 연결
        self.proxy = pg.SignalProxy(
            self.candle_plot.scene().sigMouseMoved,
            rateLimit=60,
            slot=self._on_mouse_moved,
        )

    def _on_mouse_moved(self, evt):
        pos = evt[0]
        if self.candle_plot.sceneBoundingRect().contains(pos):
            mouse_point = self.candle_plot.vb.mapSceneToView(pos)
            x = mouse_point.x()
            y = mouse_point.y()

            self.vline.setPos(x)
            self.hline.setPos(y)

            if self._df is not None and len(self._df) > 0:
                idx = int(round(x))
                if 0 <= idx < len(self._df):
                    row = self._df.iloc[idx]
                    dt = self._df.index[idx]
                    text = (
                        f"{dt.strftime('%Y-%m-%d %H:%M')}\n"
                        f"O:{row['Open']:.2f} H:{row['High']:.2f} "
                        f"L:{row['Low']:.2f} C:{row['Close']:.2f}\n"
                        f"V:{int(row.get('Volume', 0)):,}"
                    )
                    self.tooltip_label.setText(text)
                    self.tooltip_label.setPos(x, y)

    def update_candles(self, df: pd.DataFrame):
        """캔들 데이터 렌더링"""
        self._df = df

        if df is None or len(df) == 0:
            self.candle_item.set_data([])
            self.volume_bars.setOpts(x=[0], height=[0], width=0.6)
            self.no_data_label.setVisible(True)
            self.no_data_label.setPos(0.5, 0.5)
            self.candle_plot.disableAutoRange()
            self.volume_plot.disableAutoRange()
            return

        self.no_data_label.setVisible(False)

        # NaN 행 제거
        clean_df = df.dropna(subset=["Open", "High", "Low", "Close"])
        if len(clean_df) == 0:
            self.candle_item.set_data([])
            self.volume_bars.setOpts(x=[0], height=[0], width=0.6)
            self.no_data_label.setVisible(True)
            return

        self._df = clean_df

        candle_data = []
        ts = list(range(len(clean_df)))
        for i, (idx, row) in enumerate(clean_df.iterrows()):
            candle_data.append((i, float(row["Open"]), float(row["High"]),
                                float(row["Low"]), float(row["Close"])))

        self.candle_item.set_data(candle_data)

        # 거래량 바
        volumes = clean_df["Volume"].fillna(0).astype(float).values
        self.volume_bars.setOpts(x=ts, height=volumes, width=0.6)

        # auto-range 활성화 후 범위 설정
        self.candle_plot.enableAutoRange()
        self.volume_plot.enableAutoRange()
        self.candle_plot.setXRange(0, len(clean_df) - 1, padding=0.05)

    def update_trades(self, results):
        """전략별 색상 마커 오버레이"""
        # 기존 마커 제거
        for item in self._marker_items:
            self.candle_plot.removeItem(item)
        self._marker_items.clear()

        if self._df is None or len(self._df) == 0:
            return

        # 인덱스 → 위치 매핑
        idx_to_pos = {ts: i for i, ts in enumerate(self._df.index)}

        for result in results:
            if result is None or result.trades_df is None or len(result.trades_df) == 0:
                continue

            color = result.color
            entry_xs = []
            entry_ys = []
            exit_xs = []
            exit_ys = []

            for _, trade in result.trades_df.iterrows():
                entry_t = trade["entry_time"]
                exit_t = trade["exit_time"]

                entry_pos = idx_to_pos.get(entry_t)
                exit_pos = idx_to_pos.get(exit_t)

                if entry_pos is not None:
                    entry_xs.append(entry_pos)
                    entry_ys.append(self._df.iloc[entry_pos]["Low"] * 0.999)

                if exit_pos is not None:
                    exit_xs.append(exit_pos)
                    exit_ys.append(self._df.iloc[exit_pos]["High"] * 1.001)

            if entry_xs:
                entry_scatter = pg.ScatterPlotItem(
                    x=entry_xs, y=entry_ys,
                    symbol="t1",  # 위쪽 삼각형
                    size=12,
                    pen=pg.mkPen(color),
                    brush=pg.mkBrush(color),
                )
                self.candle_plot.addItem(entry_scatter)
                self._marker_items.append(entry_scatter)

            if exit_xs:
                exit_scatter = pg.ScatterPlotItem(
                    x=exit_xs, y=exit_ys,
                    symbol="t",  # 아래쪽 삼각형
                    size=12,
                    pen=pg.mkPen(color),
                    brush=pg.mkBrush(color),
                )
                self.candle_plot.addItem(exit_scatter)
                self._marker_items.append(exit_scatter)

    def update_indicators(self, lines_dict: dict):
        """지표선 오버레이 업데이트"""
        for item in self._indicator_items:
            self.candle_plot.removeItem(item)
        self._indicator_items.clear()

        if self._df is None:
            return

        colors = ["#F39C12", "#9B59B6", "#1ABC9C", "#E67E22", "#95A5A6"]
        for i, (name, series) in enumerate(lines_dict.items()):
            if series is None or series.empty:
                continue
            valid = series.dropna()
            if len(valid) == 0:
                continue

            # 인덱스를 정수 위치로 변환
            idx_to_pos = {ts: j for j, ts in enumerate(self._df.index)}
            xs = [idx_to_pos[t] for t in valid.index if t in idx_to_pos]
            ys = [valid[t] for t in valid.index if t in idx_to_pos]

            if not xs:
                continue

            color = colors[i % len(colors)]
            curve = pg.PlotDataItem(
                x=xs, y=ys,
                pen=pg.mkPen(color, width=1.5),
                name=name,
            )
            self.candle_plot.addItem(curve)
            self._indicator_items.append(curve)

    def replay_step(self, bar_index: int):
        """바 1개씩 점진적으로 추가"""
        if self._df is None or bar_index >= len(self._df):
            return

        df_slice = self._df.iloc[:bar_index + 1].dropna(subset=["Open", "High", "Low", "Close"])
        candle_data = [
            (i, float(row["Open"]), float(row["High"]),
             float(row["Low"]), float(row["Close"]))
            for i, (idx, row) in enumerate(df_slice.iterrows())
        ]
        self.candle_item.set_data(candle_data)

        volumes = df_slice["Volume"].fillna(0).astype(float).values
        ts = list(range(len(df_slice)))
        self.volume_bars.setOpts(x=ts, height=volumes, width=0.6)

        # 자동 스크롤
        self.candle_plot.setXRange(
            max(0, bar_index - 80),
            bar_index + 5,
            padding=0,
        )

    def append_bars(self, new_df: pd.DataFrame):
        """완성된 새 바를 기존 차트에 추가 (실시간 모드용)"""
        if new_df is None or new_df.empty:
            return

        clean = new_df.dropna(subset=["Open", "High", "Low", "Close"])
        if clean.empty:
            return

        if self._df is None or self._df.empty:
            self.update_candles(clean)
            return

        # 중복 제거 후 이어붙이기
        combined = pd.concat([self._df, clean])
        combined = combined[~combined.index.duplicated(keep="last")]
        combined = combined.sort_index()

        self._df = combined
        self._redraw_candles(scroll_to_end=True)

    def update_latest_bar(self, bar: pd.Series):
        """현재 진행 중인 미완성 바 업데이트 (실시간 모드용)"""
        if self._df is None or self._df.empty:
            return

        # 마지막 바가 같은 타임스탬프면 업데이트, 아니면 임시 추가
        if bar.name in self._df.index:
            self._df.loc[bar.name] = bar
        else:
            # 임시 미완성 바 — 다음 완성 바가 오면 replace됨
            new_row = pd.DataFrame([bar], index=[bar.name])
            self._df = pd.concat([self._df, new_row])

        self._redraw_candles(scroll_to_end=True)

    def _redraw_candles(self, scroll_to_end: bool = False):
        """내부 _df 기준으로 캔들/거래량 재렌더링"""
        if self._df is None or self._df.empty:
            return

        clean_df = self._df.dropna(subset=["Open", "High", "Low", "Close"])
        if clean_df.empty:
            return

        candle_data = [
            (i, float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"]))
            for i, (_, row) in enumerate(clean_df.iterrows())
        ]
        self.candle_item.set_data(candle_data)

        volumes = clean_df["Volume"].fillna(0).astype(float).values
        ts = list(range(len(clean_df)))
        self.volume_bars.setOpts(x=ts, height=volumes, width=0.6)

        if scroll_to_end:
            n = len(clean_df)
            self.candle_plot.setXRange(max(0, n - 100), n + 2, padding=0)

    def clear(self):
        """모든 오버레이 초기화"""
        for item in self._marker_items:
            self.candle_plot.removeItem(item)
        self._marker_items.clear()

        for item in self._indicator_items:
            self.candle_plot.removeItem(item)
        self._indicator_items.clear()

        self.tooltip_label.setText("")
