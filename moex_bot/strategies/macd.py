from __future__ import annotations

import pandas as pd

from .base import BaseStrategy

# Exported strategy name.  This constant is referenced by the loader
# and report builder.  Do not modify without updating the configuration.
STRATEGY_NAME = "macd"


def strategy(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> pd.Series:
    """MACD crossover strategy."""
    return MACDStrategy(fast=fast, slow=slow, signal_period=signal_period).generate_signals(df)


class MACDStrategy(BaseStrategy):
    """Moving Average Convergence Divergence (MACD) crossover strategy."""

    def __init__(self, fast: int = 12, slow: int = 26, signal_period: int = 9, **params) -> None:
        super().__init__(fast=fast, slow=slow, signal_period=signal_period, **params)
        self.fast = fast
        self.slow = slow
        self.signal_period = signal_period

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Generate signals based on MACD crossovers."""
        if df.empty or 'close' not in df.columns:
            return pd.Series(0, index=df.index)
        close = df['close'].astype(float)
        ema_fast = close.ewm(span=self.fast, adjust=False).mean()
        ema_slow = close.ewm(span=self.slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=self.signal_period, adjust=False).mean()
        signals = pd.Series(0, index=df.index)
        signals[(macd_line > signal_line) & (macd_line.shift(1) <= signal_line.shift(1))] = 1
        signals[(macd_line < signal_line) & (macd_line.shift(1) >= signal_line.shift(1))] = -1
        return signals.fillna(0)


__all__ = ["STRATEGY_NAME", "strategy", "MACDStrategy"]
