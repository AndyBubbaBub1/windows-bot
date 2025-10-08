import pandas as pd
import numpy as np

# Exported strategy name.  This constant is referenced by the loader
# and report builder.  Do not modify without updating the configuration.
STRATEGY_NAME = "atr_trend"

def strategy(df: pd.DataFrame, atr_period: int = 14, multiplier: float = 2.0) -> pd.Series:
    """ATR-based trend following strategy.

    This function is retained for backward compatibility.  It
    delegates to :class:`ATRTrendStrategy` so that both functional
    and object-oriented invocation styles are supported.

    Args:
        df: DataFrame with price columns.
        atr_period: Exponential moving average window for ATR.
        multiplier: Multiplier applied to ATR to derive the band distance.

    Returns:
        Series of signals: 1 for long, -1 for short, 0 for flat.
    """
    return ATRTrendStrategy(atr_period=atr_period, multiplier=multiplier).generate_signals(df)


from .base import BaseStrategy


class ATRTrendStrategy(BaseStrategy):
    """Trend following strategy based on the Average True Range.

    The strategy defines upper and lower bands around the close price
    using an exponentially weighted moving average of the ATR and
    enters long or short positions when price breaks above or below
    these bands.  Parameters ``atr_period`` and ``multiplier``
    control the smoothing of the ATR and the band distance.

    Args:
        atr_period: Span for the exponential moving average used in
            ATR calculation.
        multiplier: Coefficient applied to ATR to compute the band
            distance.
        **params: Additional keyword arguments accepted for API
            consistency but ignored.
    """

    def __init__(self, atr_period: int = 14, multiplier: float = 2.0, **params) -> None:
        super().__init__(atr_period=atr_period, multiplier=multiplier, **params)
        self.atr_period = atr_period
        self.multiplier = multiplier

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Generate long/short signals based on ATR bands.

        Returns a Series of 1 for long, -1 for short and 0 for flat.
        """
        if df.empty or 'close' not in df.columns:
            return pd.Series(0, index=df.index)
        c = df['close'].astype(float)
        h = df.get('high', c).astype(float)
        l = df.get('low', c).astype(float)
        tr = pd.concat([
            (h - l),
            (h - c.shift()).abs(),
            (l - c.shift()).abs()
        ], axis=1).max(axis=1)
        atr = tr.ewm(span=self.atr_period, adjust=False).mean()
        up = c.rolling(1).max() - self.multiplier * atr
        dn = c.rolling(1).min() + self.multiplier * atr
        trend = pd.Series(0, index=df.index)
        long_cond = c > up.shift(1)
        short_cond = c < dn.shift(1)
        trend[long_cond] = 1
        trend[short_cond] = -1
        # Reset signal when not trending
        trend = trend.where(trend != trend.shift(1), 0)
        return trend.fillna(0)


__all__ = ["STRATEGY_NAME", "strategy", "ATRTrendStrategy"]