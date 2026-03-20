"""
BaseStrategy: 전략 추상 기본 클래스
"""
from abc import ABC, abstractmethod

import pandas as pd


class BaseStrategy(ABC):
    name: str = ""
    display_name: str = ""
    color: str = "#FFFFFF"

    def __init__(self, params: dict = None):
        self.params = params or self._default_params()

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """
        시그널 생성.

        Returns:
            pd.Series: +1 (매수진입) / -1 (매도/청산) / 0 (홀드)
            인덱스는 df.index와 동일
        """

    def get_param_schema(self) -> list:
        """
        GUI 파라미터 폼 자동 생성용 스키마.

        Returns:
            list of dict: [{"key": str, "label": str, "type": str, "min": int, "max": int, "default": int}, ...]
        """
        return []

    def get_indicator_lines(self, df: pd.DataFrame) -> dict:
        """
        차트 오버레이용 지표선.

        Returns:
            dict[str, pd.Series]: {"라벨": Series, ...}
        """
        return {}

    def _default_params(self) -> dict:
        return {}
