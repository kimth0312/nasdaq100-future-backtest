"""
DataFetcher: yfinance를 사용하여 NQ=F OHLCV 데이터 수집
봉 단위별 최대 조회 기간 제한 자동 적용
"""
import logging
from datetime import datetime, timedelta, timezone

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


class DataFetcher:
    # yfinance interval 매핑
    INTERVAL_MAP = {
        '1m': '1m',
        '5m': '5m',
        '15m': '15m',
        '60m': '60m',
        '1d': '1d',
    }

    # 봉 단위별 최대 조회 일수
    MAX_DAYS = {
        '1m': 7,
        '5m': 60,
        '15m': 60,
        '60m': 730,
        '1d': 36500,
    }

    def fetch(self, symbol: str, interval: str, start: datetime, end: datetime) -> pd.DataFrame:
        """
        yfinance로 OHLCV 데이터 수집.
        기간 제한 초과 시 자동 clip + 경고 로그.

        Args:
            symbol:   티커 심볼 (예: 'NQ=F')
            interval: 봉 단위 ('1m', '5m', '15m', '60m', '1d')
            start:    시작일시 (datetime)
            end:      종료일시 (datetime)

        Returns:
            OHLCV DataFrame (컬럼: Open, High, Low, Close, Volume)
        """
        if interval not in self.INTERVAL_MAP:
            raise ValueError(f"지원하지 않는 interval: {interval}. 지원: {list(self.INTERVAL_MAP.keys())}")

        max_days = self.MAX_DAYS[interval]

        # timezone-aware 처리
        now = datetime.now(timezone.utc)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        # 기간 제한: 최소 start를 (today - max_days)로 clip
        earliest_allowed = now - timedelta(days=max_days)
        if start < earliest_allowed:
            logger.warning(
                f"[DataFetcher] {interval} 봉의 최대 조회 기간({max_days}일)을 초과했습니다. "
                f"start를 {earliest_allowed.date()}로 조정합니다."
            )
            start = earliest_allowed

        # end가 현재 시각보다 미래면 now로 clip
        if end > now:
            end = now

        if start >= end:
            logger.warning("[DataFetcher] start >= end, 빈 DataFrame 반환")
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

        yf_interval = self.INTERVAL_MAP[interval]
        logger.info(f"[DataFetcher] Fetching {symbol} {yf_interval} from {start.date()} to {end.date()}")

        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(
                interval=yf_interval,
                start=start,
                end=end,
                auto_adjust=True,
            )
        except Exception as e:
            logger.error(f"[DataFetcher] yfinance 오류: {e}")
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

        if df is None or df.empty:
            logger.warning(f"[DataFetcher] 빈 데이터 반환됨: {symbol} {yf_interval}")
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

        # 필요한 컬럼만 선택
        needed = ["Open", "High", "Low", "Close", "Volume"]
        available = [c for c in needed if c in df.columns]
        df = df[available].copy()

        # 인덱스 timezone 정규화 (UTC)
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")

        logger.info(f"[DataFetcher] {len(df)} 행 수집 완료")
        return df
