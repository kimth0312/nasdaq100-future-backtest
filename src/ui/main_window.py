"""
MainWindow: 전체 레이아웃 조립
패널 간 시그널/슬롯 연결
"""
import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QMainWindow, QDockWidget, QWidget,
    QMessageBox, QLabel,
)

from data.store import DataStore
from engine.strategies import GoldenCross, RSIMeanReversion, MACDMomentum
from ui.chart_widget import ChartWidget
from ui.settings_panel import SettingsPanel
from ui.performance_panel import PerformancePanel
from ui.trades_table import TradesTable
from ui.worker import BacktestWorker
from ui.live_worker import LiveWorker

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """메인 애플리케이션 창"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("NQ Backtester — 나스닥 선물 백테스팅")
        self.setMinimumSize(1200, 800)

        self._store = DataStore()
        self._worker = None
        self._live_worker = None
        self._results = []
        self._replay_timer = QTimer(self)
        self._replay_index = 0
        self._replay_df = None

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        # 전략 인스턴스 생성
        strategies = [GoldenCross(), RSIMeanReversion(), MACDMomentum()]

        # 중앙 위젯: ChartWidget
        self.chart_widget = ChartWidget()
        self.setCentralWidget(self.chart_widget)

        # 좌측 DockWidget: SettingsPanel
        self.settings_panel = SettingsPanel(strategies)
        settings_dock = QDockWidget("설정", self)
        settings_dock.setWidget(self.settings_panel)
        settings_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        settings_dock.setMinimumWidth(280)
        settings_dock.setMaximumWidth(320)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, settings_dock)

        # 우측 DockWidget: PerformancePanel
        self.performance_panel = PerformancePanel()
        perf_dock = QDockWidget("성과 비교", self)
        perf_dock.setWidget(self.performance_panel)
        perf_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        perf_dock.setMinimumWidth(250)
        perf_dock.setMaximumWidth(300)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, perf_dock)

        # 하단 DockWidget: TradesTable
        self.trades_table = TradesTable()
        trades_dock = QDockWidget("거래 내역", self)
        trades_dock.setWidget(self.trades_table)
        trades_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        trades_dock.setMinimumHeight(200)
        trades_dock.setMaximumHeight(250)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, trades_dock)

    def _connect_signals(self):
        # Settings → run
        self.settings_panel.run_clicked.connect(self._on_run)

        # Settings → replay
        self.settings_panel.replay_clicked.connect(self._on_replay)

        # Settings → live
        self.settings_panel.live_start_clicked.connect(self._on_live_start)
        self.settings_panel.live_stop_clicked.connect(self._on_live_stop)

        # Replay timer
        self._replay_timer.timeout.connect(self._replay_tick)

    def _on_run(self, symbol, interval, start, end, strategies):
        """백테스트 실행"""
        # 기존 Replay 중단
        if self._replay_timer.isActive():
            self._replay_timer.stop()

        # 기존 worker 중단
        if self._worker is not None and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(2000)

        self.settings_panel.set_running(True)
        self.chart_widget.clear()

        self._worker = BacktestWorker(
            store=self._store,
            strategies=strategies,
            symbol=symbol,
            interval=interval,
            start=start,
            end=end,
        )
        self._worker.progress_updated.connect(self.settings_panel.set_progress)
        self._worker.finished.connect(self._on_backtest_finished)
        self._worker.error_occurred.connect(self._on_backtest_error)
        self._worker.start()

    def _on_backtest_finished(self, results):
        """백테스트 완료 처리"""
        self.settings_panel.set_running(False)
        self._results = results

        if not results or all(r is None for r in results):
            QMessageBox.warning(self, "결과 없음", "백테스트 결과가 없습니다.")
            return

        # 첫 번째 유효 결과에서 DataFrame 가져오기
        df = None
        if self._worker is not None:
            # Worker에서 직접 df를 가져오는 대신 equity_curve index를 사용
            pass

        # ChartWidget 업데이트
        # equity_curve의 인덱스를 통해 원본 df 재구성 (실제론 worker에서 df를 보관해야 함)
        # worker에 df를 저장하도록 처리
        if self._worker and hasattr(self._worker, '_df') and self._worker._df is not None:
            df = self._worker._df
        else:
            # equity_curve 인덱스로부터 df를 추정하여 차트 업데이트를 할 수 없으므로
            # 데이터를 다시 가져오는 방법 사용 (이미 캐시됨)
            pass

        # worker에서 저장한 df 사용
        if hasattr(self._worker, '_loaded_df') and self._worker._loaded_df is not None:
            df = self._worker._loaded_df
            self._replay_df = df
            self.chart_widget.update_candles(df)

        # 전략 마커 업데이트
        self.chart_widget.update_trades(results)

        # 첫 번째 전략 지표선 오버레이
        if df is not None and results and results[0] is not None:
            try:
                # Worker에서 전략 인스턴스 접근
                strategies = self._worker._strategies if self._worker else []
                if strategies:
                    lines = strategies[0].get_indicator_lines(df)
                    self.chart_widget.update_indicators(lines)
            except Exception as e:
                logger.warning(f"[MainWindow] 지표선 오버레이 실패: {e}")

        # 성과 패널 업데이트
        self.performance_panel.update(results)

        # 거래 내역 업데이트
        self.trades_table.update(results)

        # Replay 버튼 활성화
        self.settings_panel.set_replay_enabled(True)

    def _on_backtest_error(self, error_msg: str):
        """백테스트 오류 처리"""
        self.settings_panel.set_running(False)
        QMessageBox.critical(self, "백테스트 오류", error_msg)

    def _on_replay(self, speed: float):
        """Replay 시작"""
        if self._replay_timer.isActive():
            self._replay_timer.stop()
            return

        if self._replay_df is None or len(self._replay_df) == 0:
            QMessageBox.information(self, "Replay", "먼저 백테스트를 실행해주세요.")
            return

        self._replay_index = 0
        # 속도에 따른 interval (ms): 1x=200ms, 10x=20ms
        interval_ms = max(20, int(200 / speed))
        self._replay_timer.setInterval(interval_ms)
        self._replay_timer.start()

    def _replay_tick(self):
        """Replay 타이머 틱"""
        if self._replay_df is None:
            self._replay_timer.stop()
            return

        self.chart_widget.replay_step(self._replay_index)
        self._replay_index += 1

        if self._replay_index >= len(self._replay_df):
            self._replay_timer.stop()
            self._replay_index = 0

    # ── 실시간 모드 ──────────────────────────────────────────────

    def _on_live_start(self, symbol: str, interval: str):
        """실시간 모드 시작"""
        # Replay 중단
        if self._replay_timer.isActive():
            self._replay_timer.stop()

        # 기존 백테스트 워커 중단
        if self._worker is not None and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(2000)

        # 기존 Live 워커 중단
        if self._live_worker is not None:
            self._live_worker.stop()
            self._live_worker = None

        self.chart_widget.clear()
        self.settings_panel.update_live_status("연결 중...")

        self._live_worker = LiveWorker(symbol, interval)
        self._live_worker.initial_data_ready.connect(self._on_live_initial_data)
        self._live_worker.new_bars.connect(self._on_live_new_bars)
        self._live_worker.latest_bar_updated.connect(self._on_live_latest_bar)
        self._live_worker.price_updated.connect(self._on_live_price_updated)
        self._live_worker.status_changed.connect(self.settings_panel.update_live_status)
        self._live_worker.error_occurred.connect(self._on_live_error)
        self._live_worker.start()

    def _on_live_stop(self):
        """실시간 모드 중단"""
        if self._live_worker is not None:
            self._live_worker.stop()
            self._live_worker = None
        self.settings_panel.update_live_status("중단됨")

    def _on_live_initial_data(self, df):
        """초기 히스토리 데이터 수신"""
        self.chart_widget.update_candles(df)

    def _on_live_new_bars(self, new_df):
        """새로 완성된 바 수신"""
        self.chart_widget.append_bars(new_df)

    def _on_live_latest_bar(self, bar):
        """현재 진행 중인 미완성 바 업데이트"""
        self.chart_widget.update_latest_bar(bar)

    def _on_live_price_updated(self, price: float, prev_close: float, change_pct: float):
        """현재가 업데이트"""
        self.settings_panel.update_live_price(price, prev_close, change_pct)

    def _on_live_error(self, error_msg: str):
        """실시간 오류 처리"""
        self.settings_panel.set_live_error()
        self.settings_panel.update_live_status("오류 발생")
        QMessageBox.critical(self, "실시간 데이터 오류", error_msg)
