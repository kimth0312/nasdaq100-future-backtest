"""
LiveFeed: yfinance 폴링 기반 실시간 데이터 피드
일정 주기로 최신 바 데이터를 수집하여 새 바 감지 시 콜백 호출
"""
import logging
from datetime import datetime, timedelta, timezone

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# 봉 단위별 폴링 주기 (초)
POLL_INTERVAL_SECONDS = {
    "1m":  15,
    "5m":  30,
    "15m": 60,
    "60m": 120,
    "1d":  300,
}

# 초기 로드 시 가져올 히스토리 기간 (일)
INITIAL_LOOKBACK_DAYS = {
    "1m":  5,
    "5m":  30,
    "15m": 30,
    "60m": 60,
    "1d":  365,
}


class LiveFeed:
    """
    yfinance 폴링 기반 실시간 데이터 피드.

    사용법:
        feed = LiveFeed("NQ=F", "1m")
        df = feed.fetch_initial()          # 초기 히스토리 데이터
        new_bars, latest = feed.poll()     # 새 완성 바, 최신 미완성 바
    """

    def __init__(self, symbol: str, interval: str):
        self.symbol = symbol
        self.interval = interval
        self._last_ts: pd.Timestamp | None = None

    @property
    def poll_seconds(self) -> int:
        return POLL_INTERVAL_SECONDS.get(self.interval, 30)

    def fetch_initial(self) -> pd.DataFrame:
        """초기 히스토리 데이터 로드 및 last_ts 초기화"""
        days = INITIAL_LOOKBACK_DAYS.get(self.interval, 30)
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)

        df = self._fetch_range(start, end)
        if df is not None and not df.empty:
            self._last_ts = df.index[-1]
            logger.info(f"[LiveFeed] 초기 데이터: {len(df)}행, 마지막 바={self._last_ts}")
        return df if df is not None else pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

    def poll(self) -> tuple[pd.DataFrame, pd.Series | None]:
        """
        최신 데이터 폴링.

        Returns:
            (new_bars, latest_bar)
            - new_bars: 마지막 폴링 이후 새로 완성된 바 DataFrame (비어있을 수 있음)
            - latest_bar: 현재 진행 중인(미완성) 최신 바 Series (없으면 None)
        """
        end = datetime.now(timezone.utc)
        # 충분한 여유를 두고 최근 데이터 조회
        lookback_minutes = max(10, self.poll_seconds // 60 * 5 + 30)
        start = end - timedelta(minutes=lookback_minutes)

        df = self._fetch_range(start, end)
        if df is None or df.empty:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"]), None

        # 1분봉/소단위: 마지막 바는 아직 완성 중일 수 있음
        # yfinance는 현재 진행 중인 바도 포함하여 반환
        now = datetime.now(timezone.utc)
        interval_seconds = self._interval_to_seconds()
        last_bar_ts = df.index[-1]

        # 마지막 바 완성 여부 확인 (last_bar_ts + interval_duration > now 이면 미완성)
        last_bar_end = last_bar_ts + timedelta(seconds=interval_seconds)
        is_last_incomplete = last_bar_end.replace(tzinfo=timezone.utc) > now if last_bar_ts.tzinfo is None else (
            last_bar_end > now
        )

        latest_bar = df.iloc[-1] if is_last_incomplete else None
        completed_df = df.iloc[:-1] if is_last_incomplete else df

        # 이전 폴링 이후 새로 생성된 바 필터링
        if self._last_ts is not None:
            new_bars = completed_df[completed_df.index > self._last_ts]
        else:
            new_bars = completed_df

        if not new_bars.empty:
            self._last_ts = new_bars.index[-1]
            logger.info(f"[LiveFeed] 새 바 {len(new_bars)}개 감지, 마지막={self._last_ts}")

        return new_bars, latest_bar

    def get_current_price(self) -> float | None:
        """현재가 빠르게 조회"""
        try:
            ticker = yf.Ticker(self.symbol)
            info = ticker.fast_info
            price = getattr(info, "last_price", None)
            if price is not None:
                return float(price)
        except Exception as e:
            logger.debug(f"[LiveFeed] 현재가 조회 실패: {e}")
        return None

    def _fetch_range(self, start: datetime, end: datetime) -> pd.DataFrame | None:
        try:
            ticker = yf.Ticker(self.symbol)
            df = ticker.history(
                interval=self.interval,
                start=start,
                end=end,
                auto_adjust=True,
            )
        except Exception as e:
            logger.error(f"[LiveFeed] yfinance 오류: {e}")
            return None

        if df is None or df.empty:
            return None

        needed = ["Open", "High", "Low", "Close", "Volume"]
        df = df[[c for c in needed if c in df.columns]].copy()

        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")

        return df

    def _interval_to_seconds(self) -> int:
        mapping = {
            "1m": 60,
            "5m": 300,
            "15m": 900,
            "60m": 3600,
            "1d": 86400,
        }
        return mapping.get(self.interval, 60)
