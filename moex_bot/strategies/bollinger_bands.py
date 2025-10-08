import pandas as pd

from .base import BaseStrategy

STRATEGY_NAME = "bollinger_bands"


class BollingerBandsStrategy(BaseStrategy):
    """Bollinger Bands mean-reversion strategy.

    Uses a moving average and standard deviation to compute upper and
    lower bands.  Generates long signals when price is below the
    lower band and short signals when price is above the upper band.

    Args:
        window: Rolling window length for mean and std (default 20).
        multiplier: Number of standard deviations for the bands (default 2).
    """

    def __init__(self, window: int = 20, multiplier: float = 2.0) -> None:
        super().__init__(window=window, multiplier=multiplier)
        if window <= 0:
            raise ValueError("window must be positive")
        self.window = window
        self.multiplier = multiplier

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        if 'close' not in df.columns:
            return pd.Series(0, index=df.index)
        c = df["close"].astype(float)
        m = c.rolling(self.window).mean()
        s = c.rolling(self.window).std()
        upper = m + self.multiplier * s
        lower = m - self.multiplier * s
        sig = pd.Series(0, index=df.index)
        sig[c < lower] = 1
        sig[c > upper] = -1
        return sig.fillna(0)


def strategy(df: pd.DataFrame) -> pd.Series:
    """Functional wrapper for Bollinger Bands strategy with defaults."""
    strat = BollingerBandsStrategy()
    return strat.generate_signals(df)


__all__ = ["BollingerBandsStrategy", "strategy"]