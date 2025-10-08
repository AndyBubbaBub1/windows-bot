import pandas as pd

# Exported strategy name.  This constant is referenced by the loader
# and report builder.  Do not modify without updating the configuration.
STRATEGY_NAME = "macd"

def strategy(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal_period: int = 9) -> pd.Series:
    """MACD crossover strategy.

    This function is retained for backward compatibility.  It
    delegates to :class:`MACDStrategy` so that both functional and
    object-oriented invocation styles are supported.

    Args:
        df: DataFrame with price data.
        fast: Span for the fast EMA (e.g. 12 periods).
        slow: Span for the slow EMA (e.g. 26 periods).
        signal_period: Span for the signal line EMA (e.g. 9 periods).

    Returns:
        Series of signals: 1 for long, -1 for short, 0 for flat.
    """
    return MACDStrategy(fast=fast, slow=slow, signal_period=signal_period).generate_signals(df)


from .base import BaseStrategy


class MACDStrategy(BaseStrategy):
    """Moving Average Convergence Divergence (MACD) crossover strategy.

    The MACD is computed as the difference between two exponential
    moving averages of closing prices (fast minus slow).  A signal
    line (exponential average of the MACD) is used to identify
    crossovers that trigger buy and sell signals.

    Args:
        fast: Span for the fast EMA.
        slow: Span for the slow EMA.
        signal_period: Span for the EMA used as the signal line.
        **params: Additional keyword arguments accepted for API
            consistency but ignored by this implementation.
    """

    def __init__(self, fast: int = 12, slow: int = 26, signal_period: int = 9, **params) -> None:
        super().__init__(fast=fast, slow=slow, signal_period=signal_period, **params)
        self.fast = fast
        self.slow = slow
        self.signal_period = signal_period

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Generate signals based on MACD crossovers.

        Returns a Series of 1 for long, -1 for short and 0 for flat.
        """
        if df.empty or 'close' not in df.columns:
            return pd.Series(0, index=df.index)
        c = df['close'].astype(float)
        ema_fast = c.ewm(span=self.fast, adjust=False).mean()
        ema_slow = c.ewm(span=self.slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=self.signal_period, adjust=False).mean()
        sig = pd.Series(0, index=df.index)
        sig[(macd_line > signal_line) & (macd_line.shift(1) <= signal_line.shift(1))] = 1
        sig[(macd_line < signal_line) & (macd_line.shift(1) >= signal_line.shift(1))] = -1
        return sig.fillna(0)


__all__ = ["STRATEGY_NAME", "strategy", "MACDStrategy"]