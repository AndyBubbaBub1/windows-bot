"""Simple moving average crossover strategy implemented as a class.

This strategy generates long and short signals based on the
relationship between a short and a long simple moving average of
the closing price.  When the short moving average rises above the
long moving average a long signal (+1) is generated; when it falls
below a short signal (-1) is produced.  Consecutive identical
signals are suppressed so that a position is opened only when the
state changes.  Flat (0) is indicated when there is no change.

The class inherits from :class:`~moex_bot.strategies.base.BaseStrategy`
and can be used both in backtests and in live trading.  Parameters
for the moving average windows can be passed via the ``params``
dictionary in the configuration file.
"""

from __future__ import annotations

import pandas as pd

from .base import BaseStrategy


class SMAStrategy(BaseStrategy):
    """Simple moving average crossover strategy.

    Args:
        short_window: Number of periods for the short moving average.
        long_window: Number of periods for the long moving average.
    """

    def __init__(self, short_window: int = 5, long_window: int = 20) -> None:
        super().__init__(short_window=short_window, long_window=long_window)
        if short_window <= 0 or long_window <= 0:
            raise ValueError("Moving average windows must be positive integers")
        if short_window >= long_window:
            raise ValueError("short_window must be smaller than long_window")
        self.short_window = short_window
        self.long_window = long_window

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Return a series of trade signals based on SMA crossover.

        The signals are computed by comparing the short and long
        moving averages.  Signals are only emitted on a change in
        state to prevent repeated entries.

        Args:
            df: DataFrame with a 'close' column of prices.

        Returns:
            pandas Series of length equal to ``df`` with values -1, 0, 1.
        """
        if 'close' not in df.columns:
            # No price data -> no trades
            return pd.Series(0, index=df.index)
        close = df['close'].astype(float)
        short_ma = close.rolling(self.short_window).mean()
        long_ma = close.rolling(self.long_window).mean()
        # Generate raw signals
        sig = (short_ma > long_ma).astype(int) - (short_ma < long_ma).astype(int)
        # Only emit signal when it changes
        sig = sig.where(sig != sig.shift(1), 0)
        return sig.fillna(0)


__all__ = ["SMAStrategy"]