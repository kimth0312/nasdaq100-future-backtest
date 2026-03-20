"""
LiveWorker: 실시간 데이터 폴링 QThread 워커
LiveFeed를 주기적으로 호출하여 새 바/현재가를 시그널로 발행
"""
import logging

import pandas as pd
from PySide6.QtCore import QThread, Signal, QTimer

from data.live_feed import LiveFeed

logger = logging.getLogger(__name__)


class LiveWorker(QThread):
    """실시간 데이터 폴링 백그라운드 스레드"""

    # 초기 히스토리 데이터 로드 완료
    initial_data_ready = Signal(object)   # pd.DataFrame

    # 새로 완성된 바가 생겼을 때
    new_bars = Signal(object)             # pd.DataFrame

    # 현재 진행 중인 바 업데이트 (미완성)
    latest_bar_updated = Signal(object)   # pd.Series

    # 현재가 업데이트 (price, prev_close, change_pct)
    price_updated = Signal(float, float, float)

    # 상태 메시지
    status_changed = Signal(str)

    # 오류
    error_occurred = Signal(str)

    def __init__(self, symbol: str, interval: str, parent=None):
        super().__init__(parent)
        self._symbol = symbol
        self._interval = interval
        self._feed = LiveFeed(symbol, interval)
        self._timer: QTimer | None = None
        self._running = False
        self._prev_close: float | None = None

    def run(self):
        """초기 데이터 로드 후 폴링 타이머 시작"""
        self._running = True

        # 1. 초기 히스토리 데이터 로드
        self.status_changed.emit("초기 데이터 로딩 중...")
        try:
            df = self._feed.fetch_initial()
        except Exception as e:
            self.error_occurred.emit(f"초기 데이터 로드 실패: {e}")
            return

        if df is None or df.empty:
            self.error_occurred.emit("초기 데이터를 가져오지 못했습니다.")
            return

        if "Close" in df.columns and not df.empty:
            self._prev_close = float(df["Close"].iloc[-2]) if len(df) >= 2 else float(df["Close"].iloc[-1])

        self.initial_data_ready.emit(df)
        self.status_changed.emit(f"실시간 연결됨 — {self._interval} 봉")

        # 2. 폴링 타이머 (Qt 이벤트 루프 내에서 실행)
        self._timer = QTimer()
        self._timer.setInterval(self._feed.poll_seconds * 1000)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

        # 이벤트 루프 진입
        self.exec()

        # 스레드 종료 시 정리
        if self._timer:
            self._timer.stop()

    def stop(self):
        """폴링 중단 및 스레드 종료"""
        self._running = False
        if self._timer:
            self._timer.stop()
        self.quit()
        self.wait(3000)

    def _poll(self):
        """폴링 주기마다 호출 — 새 바 감지 및 현재가 업데이트"""
        if not self._running:
            return

        try:
            new_bars, latest_bar = self._feed.poll()

            if not new_bars.empty:
                if "Close" in new_bars.columns:
                    self._prev_close = float(new_bars["Close"].iloc[-1])
                self.new_bars.emit(new_bars)

            # latest_bar는 항상 반환되므로 None 체크 불필요하나 방어적으로 유지
            if latest_bar is not None:
                self.latest_bar_updated.emit(latest_bar)
                price = float(latest_bar["Close"])
                prev = self._prev_close if self._prev_close else price
                change_pct = ((price - prev) / prev * 100) if prev else 0.0
                self.price_updated.emit(price, prev, change_pct)

        except Exception as e:
            logger.warning(f"[LiveWorker] 폴링 오류: {e}")
            self.status_changed.emit(f"폴링 오류: {e}")
