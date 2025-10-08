import pandas as pd

# Exported strategy name.  This constant is referenced by the loader
# and report builder.  Do not modify without updating the configuration.
STRATEGY_NAME = "volatility_filter"

def strategy(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """Volatility filter strategy.

    This function is retained for backward compatibility.  It
    delegates to :class:`VolatilityFilterStrategy` so that both
    functional and object-oriented invocation styles are supported.

    Args:
        df: DataFrame with price data.
        window: Length of the rolling window for volatility estimation.

    Returns:
        Series of signals: 1 for long, -1 for short, 0 for flat.
    """
    return VolatilityFilterStrategy(window=window).generate_signals(df)


from .base import BaseStrategy


class VolatilityFilterStrategy(BaseStrategy):
    """Simple volatility filter trading strategy.

    The strategy computes the rolling standard deviation of
    percentage price changes over a specified window and compares
    this volatility measure to its median.  It goes long when
    volatility is below the median (implying low volatility) and
    short when volatility is above the median (high volatility).

    Args:
        window: Lookback period for computing rolling volatility.
        **params: Additional keyword arguments accepted for API
            consistency but ignored by this implementation.
    """

    def __init__(self, window: int = 20, **params) -> None:
        super().__init__(window=window, **params)
        self.window = window

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Generate volatility filter signals.

        Returns a Series of 1 for long, -1 for short and 0 for flat.
        """
        if df.empty or 'close' not in df.columns:
            return pd.Series(0, index=df.index)
        c = df['close'].astype(float)
        vol = c.pct_change().rolling(self.window).std()
        med = vol.median()
        sig = pd.Series(0, index=df.index)
        sig[vol < med] = 1
        sig[vol > med] = -1
        return sig.fillna(0)


__all__ = ["STRATEGY_NAME", "strategy", "VolatilityFilterStrategy"]