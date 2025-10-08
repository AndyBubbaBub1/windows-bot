import pandas as pd

from .base import BaseStrategy

STRATEGY_NAME = "mean_reversion"


class MeanReversionStrategy(BaseStrategy):
    """Simple mean-reversion strategy using a z-score of price.

    Calculates a moving average and standard deviation over a window.
    Generates a long signal when price deviates below the mean by a
    threshold number of standard deviations and a short signal when
    price deviates above the mean by the same threshold.

    Args:
        window: Rolling window length for the moving average (default 20).
        threshold: Z-score threshold for entering positions (default 1).
    """

    def __init__(self, window: int = 20, threshold: float = 1.0) -> None:
        super().__init__(window=window, threshold=threshold)
        if window <= 0:
            raise ValueError("window must be positive")
        self.window = window
        self.threshold = threshold

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        if 'close' not in df.columns:
            return pd.Series(0, index=df.index)
        c = df["close"].astype(float)
        ma = c.rolling(self.window).mean()
        std = c.rolling(self.window).std() + 1e-9
        z = (c - ma) / std
        sig = pd.Series(0, index=df.index)
        sig[z < -self.threshold] = 1
        sig[z > self.threshold] = -1
        return sig.fillna(0)


def strategy(df: pd.DataFrame) -> pd.Series:
    """Functional wrapper for mean-reversion strategy."""
    strat = MeanReversionStrategy()
    return strat.generate_signals(df)


__all__ = ["MeanReversionStrategy", "strategy"]