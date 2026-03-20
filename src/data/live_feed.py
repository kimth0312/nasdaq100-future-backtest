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
            # yfinance는 최신 바의 Volume을 0으로 반환하는 경우가 있음.
            # Volume=0인 바는 아직 확정되지 않은 것으로 보고 _last_ts에서 제외.
            # 이 바들은 다음 poll()에서 Volume이 채워지면 new_bars로 감지됨.
            nonzero_vol = df[df["Volume"] > 0]
            self._last_ts = nonzero_vol.index[-1] if not nonzero_vol.empty else df.index[-1]
            logger.info(f"[LiveFeed] 초기 데이터: {len(df)}행, last_ts={self._last_ts}")
        return df if df is not None else pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

    def poll(self) -> tuple[pd.DataFrame, pd.Series]:
        """
        최신 데이터 폴링.

        Returns:
            (new_bars, latest_bar)
            - new_bars: 마지막 폴링 이후 새로 완성된 바 DataFrame (비어있을 수 있음)
            - latest_bar: 가장 최신 바 Series (항상 반환 — price 및 Volume 업데이트용)
        """
        end = datetime.now(timezone.utc)
        lookback_minutes = max(10, self.poll_seconds // 60 * 5 + 30)
        start = end - timedelta(minutes=lookback_minutes)

        df = self._fetch_range(start, end)
        empty = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        if df is None or df.empty:
            return empty, None

        now = datetime.now(timezone.utc)
        interval_seconds = self._interval_to_seconds()
        last_bar_ts = df.index[-1]
        last_bar_end = last_bar_ts + timedelta(seconds=interval_seconds)
        last_volume = float(df["Volume"].iloc[-1]) if "Volume" in df.columns else 1.0

        # 미완성 바 판정: 시간이 아직 안 됐거나 Volume이 0이면 미완성
        is_last_incomplete = (last_bar_end > now) or (last_volume == 0)

        # latest_bar는 항상 반환 (price 표시 + Volume 뒤늦은 업데이트 모두 처리)
        latest_bar = df.iloc[-1]
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
