import pandas as pd

# Exported strategy name.  This constant is referenced by the loader
# and report builder.  Do not modify without updating the configuration.
STRATEGY_NAME = "breakout"

def strategy(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """20-period high/low breakout strategy.

    This function is retained for backward compatibility.  It
    delegates to :class:`BreakoutStrategy` so that both functional
    and object-oriented invocation styles are supported.

    Args:
        df: DataFrame with price data.
        window: Lookback period for computing breakout highs/lows.

    Returns:
        Series of signals: 1 for long, -1 for short, 0 for flat.
    """
    return BreakoutStrategy(window=window).generate_signals(df)


from .base import BaseStrategy


class BreakoutStrategy(BaseStrategy):
    """High/low breakout trading strategy.

    The strategy monitors the highest and lowest closing prices over a
    rolling window and generates a signal when the current close
    exceeds either extreme.  It goes long when the price closes
    above the prior ``window``-period high and short when it closes
    below the prior low.

    Args:
        window: Number of periods for the breakout lookback.
        **params: Additional keyword arguments accepted for API
            consistency but ignored by this implementation.
    """

    def __init__(self, window: int = 20, **params) -> None:
        super().__init__(window=window, **params)
        self.window = window

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Generate breakout signals.

        Returns a Series of 1 for long, -1 for short and 0 for flat.
        """
        if df.empty or 'close' not in df.columns:
            return pd.Series(0, index=df.index)
        c = df['close'].astype(float)
        hi = c.rolling(self.window).max()
        lo = c.rolling(self.window).min()
        sig = pd.Series(0, index=df.index)
        sig[c > hi.shift(1)] = 1
        sig[c < lo.shift(1)] = -1
        return sig.fillna(0)


__all__ = ["STRATEGY_NAME", "strategy", "BreakoutStrategy"]