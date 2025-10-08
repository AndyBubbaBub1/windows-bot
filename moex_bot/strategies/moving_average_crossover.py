import pandas as pd

from .base import BaseStrategy

STRATEGY_NAME = "moving_average_crossover"


class MovingAverageCrossoverStrategy(BaseStrategy):
    """Moving average crossover strategy using exponential moving averages.

    Generates a long signal when the fast EMA rises above the slow EMA
    and a short signal when it falls below.  Signals are emitted only
    when the state changes to avoid repeated entries.

    Args:
        fast_span: Span (in periods) for the fast EMA (default 10).
        slow_span: Span for the slow EMA (default 40).
    """

    def __init__(self, fast_span: int = 10, slow_span: int = 40) -> None:
        super().__init__(fast_span=fast_span, slow_span=slow_span)
        if fast_span <= 0 or slow_span <= 0:
            raise ValueError("spans must be positive")
        if fast_span >= slow_span:
            raise ValueError("fast_span must be less than slow_span")
        self.fast_span = fast_span
        self.slow_span = slow_span

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        if 'close' not in df.columns:
            return pd.Series(0, index=df.index)
        c = df["close"].astype(float)
        fast = c.ewm(span=self.fast_span, adjust=False).mean()
        slow = c.ewm(span=self.slow_span, adjust=False).mean()
        sig = (fast > slow).astype(int) - (fast < slow).astype(int)
        sig = sig.where(sig != sig.shift(1), 0)
        return sig.fillna(0)


def strategy(df: pd.DataFrame) -> pd.Series:
    """Functional wrapper for moving average crossover strategy."""
    strat = MovingAverageCrossoverStrategy()
    return strat.generate_signals(df)


__all__ = ["MovingAverageCrossoverStrategy", "strategy"]