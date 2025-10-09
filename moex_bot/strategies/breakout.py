from __future__ import annotations

import pandas as pd

from .base import BaseStrategy

# Exported strategy name.  This constant is referenced by the loader
# and report builder.  Do not modify without updating the configuration.
STRATEGY_NAME = "breakout"


def strategy(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """20-period high/low breakout strategy."""
    return BreakoutStrategy(window=window).generate_signals(df)


class BreakoutStrategy(BaseStrategy):
    """High/low breakout trading strategy."""

    def __init__(self, window: int = 20, **params) -> None:
        super().__init__(window=window, **params)
        self.window = window

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Generate breakout signals."""
        if df.empty or 'close' not in df.columns:
            return pd.Series(0, index=df.index)
        close = df['close'].astype(float)
        high = close.rolling(self.window).max()
        low = close.rolling(self.window).min()
        signals = pd.Series(0, index=df.index)
        signals[close > high.shift(1)] = 1
        signals[close < low.shift(1)] = -1
        return signals.fillna(0)


__all__ = ["STRATEGY_NAME", "strategy", "BreakoutStrategy"]
