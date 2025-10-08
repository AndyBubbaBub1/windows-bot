from __future__ import annotations

import pandas as pd

from .base import BaseStrategy

# Exported strategy name.  This constant is referenced by the loader
# and report builder.  Do not modify without updating the configuration.
STRATEGY_NAME = "volatility_filter"


def strategy(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """Volatility filter strategy."""
    # Retained for backward compatibility with the functional API.
    return VolatilityFilterStrategy(window=window).generate_signals(df)


class VolatilityFilterStrategy(BaseStrategy):
    """Simple volatility filter trading strategy."""

    def __init__(self, window: int = 20, **params) -> None:
        super().__init__(window=window, **params)
        self.window = window

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Generate volatility filter signals."""
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
