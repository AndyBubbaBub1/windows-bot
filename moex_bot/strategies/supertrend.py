"""SuperTrend indicator strategy.

This strategy uses the SuperTrend indicator, which is based on the
Average True Range (ATR) and a multiplier, to determine trend
direction.  When the price closes above the SuperTrend line the
strategy takes a long position; when it closes below the line the
strategy goes short.  In periods where the indicator is flat the
position is held constant.
"""

from __future__ import annotations

import pandas as pd
import numpy as np

# Exported strategy name.  This constant is referenced by the loader
# and report builder.  Do not modify without updating the configuration.
STRATEGY_NAME = 'supertrend'

def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    prev_close = df['close'].shift(1)
    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - prev_close).abs(),
        (df['low'] - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()

def strategy(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.Series:
    """Compute SuperTrend signals.

    This function is retained for backward compatibility.  It
    delegates to :class:`SuperTrendStrategy` so that both functional
    and object-oriented invocation styles are supported.

    Args:
        df: DataFrame with 'high', 'low', 'close' columns.
        period: ATR period.
        multiplier: Multiplier for ATR in SuperTrend calculation.

    Returns:
        Series of signals: 1 (long), -1 (short), 0 (flat).
    """
    return SuperTrendStrategy(period=period, multiplier=multiplier).generate_signals(df)


from .base import BaseStrategy


class SuperTrendStrategy(BaseStrategy):
    """SuperTrend indicator-based trading strategy.

    This strategy computes the SuperTrend indicator using an ATR of
    length ``period`` and a multiplier.  It generates long and short
    signals based on whether the closing price is above or below the
    SuperTrend line.  Parameters ``period`` and ``multiplier``
    control the indicator's sensitivity.

    Args:
        period: Lookback period for ATR calculation.
        multiplier: ATR multiplier used in SuperTrend bands.
        **params: Additional keyword arguments accepted for API
            consistency but ignored by this implementation.
    """

    def __init__(self, period: int = 10, multiplier: float = 3.0, **params) -> None:
        super().__init__(period=period, multiplier=multiplier, **params)
        self.period = period
        self.multiplier = multiplier

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Generate signals based on the SuperTrend indicator.

        Returns a Series of 1 for long, -1 for short and 0 for flat.
        """
        # Require necessary columns
        if not {'high', 'low', 'close'}.issubset(df.columns):
            return pd.Series(0, index=df.index)
        hl2 = (df['high'] + df['low']) / 2
        atr = _atr(df, self.period)
        upperband = hl2 + self.multiplier * atr
        lowerband = hl2 - self.multiplier * atr
        final_upperband = upperband.copy()
        final_lowerband = lowerband.copy()
        # Smooth the bands to avoid whipsaws
        for i in range(1, len(df)):
            if df['close'].iloc[i-1] > final_upperband.iloc[i-1]:
                final_upperband.iloc[i] = max(upperband.iloc[i], final_upperband.iloc[i-1])
            else:
                final_upperband.iloc[i] = upperband.iloc[i]
            if df['close'].iloc[i-1] < final_lowerband.iloc[i-1]:
                final_lowerband.iloc[i] = min(lowerband.iloc[i], final_lowerband.iloc[i-1])
            else:
                final_lowerband.iloc[i] = lowerband.iloc[i]
        supertrend = pd.Series(index=df.index, dtype=float)
        direction = pd.Series(index=df.index, dtype=int)
        for i in range(len(df)):
            if i == 0 or np.isnan(atr.iloc[i]):
                direction.iloc[i] = 0
                supertrend.iloc[i] = 0
                continue
            if df['close'].iloc[i-1] <= supertrend.iloc[i-1]:
                # Currently in a downtrend; check for reversal
                if df['close'].iloc[i] > final_upperband.iloc[i]:
                    direction.iloc[i] = 1
                else:
                    direction.iloc[i] = -1
            else:
                # Currently in an uptrend; check for reversal
                if df['close'].iloc[i] < final_lowerband.iloc[i]:
                    direction.iloc[i] = -1
                else:
                    direction.iloc[i] = 1
            # Assign the appropriate band as the SuperTrend
            if direction.iloc[i] == 1:
                supertrend.iloc[i] = final_lowerband.iloc[i]
            else:
                supertrend.iloc[i] = final_upperband.iloc[i]
        return direction.fillna(0)


__all__ = ['STRATEGY_NAME', 'strategy', 'SuperTrendStrategy']


__all__ = ['STRATEGY_NAME', 'strategy']