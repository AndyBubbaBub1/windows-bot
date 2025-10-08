import pandas as pd

from .base import BaseStrategy

STRATEGY_NAME = "momentum"


class MomentumStrategy(BaseStrategy):
    """Simple momentum strategy.

    Calculates momentum as the percent change over a lookback period.
    Generates a long signal when momentum is positive, a short signal
    when it is negative, and 0 otherwise.

    Args:
        lookback: Number of periods to compute percent change (default 12).
    """

    def __init__(self, lookback: int = 12) -> None:
        super().__init__(lookback=lookback)
        if lookback <= 0:
            raise ValueError("lookback must be positive")
        self.lookback = lookback

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        if 'close' not in df.columns:
            return pd.Series(0, index=df.index)
        c = df["close"].astype(float)
        mom = c.pct_change(self.lookback)
        sig = pd.Series(0, index=df.index)
        sig[mom > 0] = 1
        sig[mom < 0] = -1
        return sig.fillna(0)


def strategy(df: pd.DataFrame) -> pd.Series:
    """Functional wrapper for Momentum strategy with defaults."""
    strat = MomentumStrategy()
    return strat.generate_signals(df)


__all__ = ["MomentumStrategy", "strategy"]