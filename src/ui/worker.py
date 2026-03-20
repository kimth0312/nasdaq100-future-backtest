"""
BacktestWorker: 백테스트를 별도 QThread에서 실행
progress/finished/error 시그널 발행
"""
import logging
from datetime import datetime, timezone

from PySide6.QtCore import QThread, Signal

from engine.backtest import BacktestEngine

logger = logging.getLogger(__name__)


class BacktestWorker(QThread):
    """백테스트 백그라운드 실행 스레드"""

    progress_updated = Signal(int)    # 0~100
    finished = Signal(list)           # list[BacktestResult]
    error_occurred = Signal(str)      # 오류 메시지

    def __init__(self, store, strategies, symbol, interval, start, end, parent=None):
        """
        Args:
            store:      DataStore 인스턴스
            strategies: list[BaseStrategy]
            symbol:     티커 심볼
            interval:   봉 단위
            start:      시작 datetime
            end:        종료 datetime
        """
        super().__init__(parent)
        self._store = store
        self._strategies = strategies
        self._symbol = symbol
        self._interval = interval
        self._start = start
        self._end = end
        self._engine = BacktestEngine()
        self._loaded_df = None  # 로드된 DataFrame 저장 (MainWindow에서 접근용)

    def run(self):
        """데이터 로드 + 백테스트 실행"""
        try:
            # 1단계: 데이터 로드 (0% → 50%)
            self.progress_updated.emit(10)
            logger.info(f"[Worker] 데이터 로드 시작: {self._symbol} {self._interval}")

            # timezone-aware 변환
            start = self._start
            end = self._end
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)

            df = self._store.get_bars(self._symbol, self._interval, start, end)
            self.progress_updated.emit(50)

            if df is None or len(df) == 0:
                self.error_occurred.emit(
                    f"데이터를 가져오지 못했습니다.\n"
                    f"심볼: {self._symbol}, 봉 단위: {self._interval}\n"
                    f"기간: {start.date()} ~ {end.date()}"
                )
                return

            logger.info(f"[Worker] 데이터 로드 완료: {len(df)} 행")
            self._loaded_df = df

            # 2단계: 백테스트 실행 (50% → 100%)
            self.progress_updated.emit(60)
            logger.info(f"[Worker] 백테스트 시작: {len(self._strategies)}개 전략")

            results = self._engine.run_multiple(df, self._strategies)
            self.progress_updated.emit(100)

            logger.info(f"[Worker] 백테스트 완료")
            self.finished.emit(results)

        except Exception as e:
            logger.error(f"[Worker] 오류: {e}", exc_info=True)
            self.error_occurred.emit(f"백테스트 실행 중 오류가 발생했습니다:\n{str(e)}")
