"""ADX-based trend following strategy.

The Average Directional Index (ADX) measures trend strength.  This
strategy computes the ADX along with the +DI and -DI indicators.  It
generates a long signal when ADX exceeds a threshold and +DI > -DI,
and a short signal when ADX exceeds the threshold and -DI > +DI.  In
other cases the position is flat.
"""

from __future__ import annotations

import pandas as pd
import numpy as np


# Exported strategy name.  This constant is referenced by the loader
# and report builder.  Do not modify without updating the configuration.
STRATEGY_NAME = 'adx_trend'

def _di_adx(df: pd.DataFrame, period: int = 14) -> tuple[pd.Series, pd.Series, pd.Series]:
    high = df['high']
    low = df['low']
    close = df['close']
    prev_high = high.shift(1)
    prev_low = low.shift(1)
    prev_close = close.shift(1)
    plus_dm = high - prev_high
    minus_dm = prev_low - low
    plus_dm[plus_dm < 0] = 0
    plus_dm[plus_dm < minus_dm] = 0
    minus_dm[minus_dm < 0] = 0
    minus_dm[minus_dm < plus_dm] = 0
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(period, min_periods=period).mean()
    plus_di = 100 * (plus_dm.rolling(period, min_periods=period).sum() / atr)
    minus_di = 100 * (minus_dm.rolling(period, min_periods=period).sum() / atr)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx = dx.rolling(period, min_periods=period).mean()
    return plus_di, minus_di, adx

def strategy(df: pd.DataFrame, period: int = 14, adx_threshold: float = 20.0) -> pd.Series:
    """Compute ADX trend signals.

    This function is retained for backward compatibility.  It
    delegates to :class:`ADXTrendStrategy` so that both functional
    and object-oriented invocation styles are supported.

    Args:
        df: DataFrame with 'high', 'low', 'close'.
        period: Smoothing period for DI/ADX.
        adx_threshold: Minimum ADX value to consider a trend.

    Returns:
        Series of signals: 1 (long), -1 (short), 0 (flat).
    """
    return ADXTrendStrategy(period=period, adx_threshold=adx_threshold).generate_signals(df)


from .base import BaseStrategy


class ADXTrendStrategy(BaseStrategy):
    """Average Directional Index (ADX) based trend strategy.

    This strategy computes the ADX along with the +DI and -DI
    indicators and enters a long or short position when the ADX
    indicates a strong trend.  When the DI lines flip the position is
    reversed.  Parameters ``period`` and ``adx_threshold`` control
    smoothing and trend strength respectively.

    Args:
        period: Lookback period for DI/ADX calculation.
        adx_threshold: Minimum ADX value considered a trend.
        **params: Additional keyword arguments ignored by this
            implementation but accepted for API consistency.
    """

    def __init__(self, period: int = 14, adx_threshold: float = 20.0, **params) -> None:
        super().__init__(period=period, adx_threshold=adx_threshold, **params)
        self.period = period
        self.adx_threshold = adx_threshold

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Generate long/short signals based on ADX and DI lines.

        Returns a Series of 1 for long, -1 for short and 0 for flat.
        """
        if not {'high', 'low', 'close'}.issubset(df.columns):
            return pd.Series(0, index=df.index)
        plus_di, minus_di, adx = _di_adx(df, self.period)
        signal = pd.Series(0, index=df.index)
        trending = adx >= self.adx_threshold
        long_cond = trending & (plus_di > minus_di)
        short_cond = trending & (minus_di > plus_di)
        signal[long_cond] = 1
        signal[short_cond] = -1
        return signal


__all__ = ['STRATEGY_NAME', 'strategy', 'ADXTrendStrategy']