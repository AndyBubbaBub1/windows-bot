"""ATR-based trailing stop strategy.

This strategy generates long/short signals based on a trailing stop
line computed from the Average True Range (ATR).  When the price
closes above the trailing stop the strategy goes long; when it closes
below the stop it goes short.  The stop level is updated when a new
extreme price is observed.  The strategy is inspired by volatility
breakout systems.
"""

from __future__ import annotations

import pandas as pd
import numpy as np

# Exported strategy name.  This constant is referenced by the loader
# and report builder.  Do not modify without updating the configuration.
STRATEGY_NAME = 'atr_stop'

def _true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df['close'].shift(1)
    ranges = pd.concat([
        df['high'] - df['low'],
        (df['high'] - prev_close).abs(),
        (df['low'] - prev_close).abs()
    ], axis=1)
    return ranges.max(axis=1)

def strategy(df: pd.DataFrame, atr_period: int = 14, atr_mult: float = 3.0) -> pd.Series:
    """Compute ATR trailing stop signals.

    This function is retained for backward compatibility.  It
    delegates to :class:`ATRStopStrategy` so that both functional
    and object-oriented invocation styles are supported.

    Args:
        df: DataFrame with 'high', 'low', 'close' columns.
        atr_period: Period used to compute ATR.
        atr_mult: Multiplier for trailing stop distance.

    Returns:
        Series of signals: 1 for long, -1 for short, 0 for flat.
    """
    return ATRStopStrategy(atr_period=atr_period, atr_mult=atr_mult).generate_signals(df)


from .base import BaseStrategy


class ATRStopStrategy(BaseStrategy):
    """Average True Range based trailing stop strategy.

    This strategy uses a volatility-based trailing stop to follow
    price trends.  It maintains separate long and short trailing
    stops based on a multiple of the ATR.  When the price crosses
    the stop in the opposite direction the position is reversed.

    Args:
        atr_period: Number of periods for ATR calculation.
        atr_mult: Multiplier applied to the ATR to determine stop
            distance.
        **params: Additional keyword arguments accepted for API
            consistency but ignored by this implementation.
    """

    def __init__(self, atr_period: int = 14, atr_mult: float = 3.0, **params) -> None:
        super().__init__(atr_period=atr_period, atr_mult=atr_mult, **params)
        self.atr_period = atr_period
        self.atr_mult = atr_mult

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Generate long/short signals using an ATR trailing stop.

        Returns a Series of 1 for long, -1 for short and 0 for flat.
        """
        if not {'high', 'low', 'close'}.issubset(df.columns):
            return pd.Series(0, index=df.index)
        tr = _true_range(df)
        atr = tr.rolling(window=self.atr_period, min_periods=self.atr_period).mean()
        close = df['close']
        long_stop = pd.Series(index=df.index, dtype=float)
        short_stop = pd.Series(index=df.index, dtype=float)
        direction = pd.Series(index=df.index, dtype=int)
        for i in range(len(df)):
            if i < self.atr_period or atr.iloc[i] == 0 or np.isnan(atr.iloc[i]):
                direction.iloc[i] = 0
                long_stop.iloc[i] = np.nan
                short_stop.iloc[i] = np.nan
                continue
            if i == self.atr_period:
                long_stop.iloc[i] = close.iloc[i] - self.atr_mult * atr.iloc[i]
                short_stop.iloc[i] = close.iloc[i] + self.atr_mult * atr.iloc[i]
                direction.iloc[i] = 0
                continue
            # Determine current direction
            if direction.iloc[i-1] == 1:
                long_stop.iloc[i] = max(long_stop.iloc[i-1], close.iloc[i] - self.atr_mult * atr.iloc[i])
                short_stop.iloc[i] = np.nan
                if close.iloc[i] < long_stop.iloc[i]:
                    direction.iloc[i] = -1
                else:
                    direction.iloc[i] = 1
            elif direction.iloc[i-1] == -1:
                short_stop.iloc[i] = min(short_stop.iloc[i-1], close.iloc[i] + self.atr_mult * atr.iloc[i])
                long_stop.iloc[i] = np.nan
                if close.iloc[i] > short_stop.iloc[i]:
                    direction.iloc[i] = 1
                else:
                    direction.iloc[i] = -1
            else:
                long_stop.iloc[i] = close.iloc[i] - self.atr_mult * atr.iloc[i]
                short_stop.iloc[i] = close.iloc[i] + self.atr_mult * atr.iloc[i]
                if close.iloc[i] > short_stop.iloc[i]:
                    direction.iloc[i] = 1
                elif close.iloc[i] < long_stop.iloc[i]:
                    direction.iloc[i] = -1
                else:
                    direction.iloc[i] = 0
        return direction.fillna(0)

__all__ = ['STRATEGY_NAME', 'strategy', 'ATRStopStrategy']