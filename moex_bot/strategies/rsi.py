import pandas as pd

from .base import BaseStrategy

STRATEGY_NAME = "rsi"


class RSIStrategy(BaseStrategy):
    """Relative Strength Index strategy.

    Generates long signals when RSI drops below a lower threshold and
    short signals when RSI rises above an upper threshold.

    Args:
        period: Number of periods used to compute RSI (default 14).
        lower: RSI threshold below which to generate a long signal (default 30).
        upper: RSI threshold above which to generate a short signal (default 70).
    """

    def __init__(self, period: int = 14, lower: float = 30.0, upper: float = 70.0) -> None:
        super().__init__(period=period, lower=lower, upper=upper)
        if period <= 0:
            raise ValueError("period must be positive")
        self.period = period
        self.lower = lower
        self.upper = upper

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        if 'close' not in df.columns:
            return pd.Series(0, index=df.index)
        close = df["close"].astype(float)
        win = close.diff().clip(lower=0)
        loss = -close.diff().clip(upper=0)
        rs = (win.rolling(self.period).mean()) / (loss.rolling(self.period).mean() + 1e-9)
        rsi = 100 - (100 / (1 + rs))
        sig = pd.Series(0, index=df.index)
        sig[rsi < self.lower] = 1
        sig[rsi > self.upper] = -1
        return sig.fillna(0)


def strategy(df: pd.DataFrame) -> pd.Series:
    """Functional interface for RSI strategy.

    This wrapper retains backward compatibility with the old function
    definition.  It instantiates a :class:`RSIStrategy` with default
    parameters and returns the generated signals.
    """
    strat = RSIStrategy()
    return strat.generate_signals(df)


__all__ = ["RSIStrategy", "strategy"]