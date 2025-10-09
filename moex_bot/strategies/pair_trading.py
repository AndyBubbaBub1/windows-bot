"""Pair trading strategy using a single instrument proxy.

This simplified pair trading strategy uses the ratio between the
closing and opening price of a single asset as a proxy for the
spread between two instruments.  It computes a rolling z‑score over a
specified window and generates contrarian signals when the z‑score
exceeds thresholds.  In practice pair trading involves two separate
assets; here we reuse available columns for demonstration.
"""

from __future__ import annotations

import pandas as pd

from .base import BaseStrategy

# Exported strategy name.  This constant is referenced by the loader
# and report builder.  Do not modify without updating the configuration.
STRATEGY_NAME = 'pair_trading'

def strategy(df: pd.DataFrame, lookback: int = 30, entry_threshold: float = 1.0, exit_threshold: float = 0.5) -> pd.Series:
    """Compute pair trading signals based on price ratio z‑score.

    This function is retained for backward compatibility.  It
    delegates to :class:`PairTradingStrategy` so that both
    functional and object-oriented invocation styles are supported.

    Args:
        df: DataFrame with at least 'close' and 'open' columns.
        lookback: Rolling window size to compute mean and std.
        entry_threshold: Threshold z‑score for entering trades.
        exit_threshold: Threshold z‑score for exiting trades.

    Returns:
        Series of signals: 1 (long), -1 (short) or 0 (flat).
    """
    return PairTradingStrategy(lookback=lookback, entry_threshold=entry_threshold, exit_threshold=exit_threshold).generate_signals(df)


class PairTradingStrategy(BaseStrategy):
    """Simplified pair trading strategy using a single instrument proxy.

    The strategy computes the ratio between the closing and opening
    price of a single asset as a proxy for the spread between two
    instruments.  It calculates a rolling mean and standard
    deviation of this ratio over a ``lookback`` window and derives a
    z‑score.  When the z‑score exceeds the ``entry_threshold`` the
    strategy opens a contrarian position (short when positive,
    long when negative).  The position is closed when the z‑score
    falls back within ±``exit_threshold``.

    Args:
        lookback: Size of the rolling window for mean/std estimation.
        entry_threshold: Z‑score absolute value to enter trades.
        exit_threshold: Z‑score absolute value below which to exit trades.
        **params: Additional keyword arguments accepted for API
            consistency but ignored by this implementation.
    """

    def __init__(self, lookback: int = 30, entry_threshold: float = 1.0, exit_threshold: float = 0.5, **params) -> None:
        super().__init__(lookback=lookback, entry_threshold=entry_threshold, exit_threshold=exit_threshold, **params)
        self.lookback = lookback
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Generate contrarian signals based on the price ratio z‑score.

        Returns a Series of 1 for long, -1 for short and 0 for flat.
        """
        close = df.get('close')
        open_ = df.get('open')
        if close is None or open_ is None or len(df) < self.lookback:
            return pd.Series(0, index=df.index)
        # Avoid division by zero and propagate last known price
        ratio = close / open_.replace(0.0, pd.NA).bfill().ffill()
        rolling_mean = ratio.rolling(window=self.lookback, min_periods=self.lookback).mean()
        rolling_std = ratio.rolling(window=self.lookback, min_periods=self.lookback).std()
        z = (ratio - rolling_mean) / (rolling_std + 1e-9)
        signal = pd.Series(0, index=df.index)
        # Contrarian entry: short when z positive and > entry_threshold, long when negative
        signal[z > self.entry_threshold] = -1
        signal[z < -self.entry_threshold] = 1
        # Flat/exit condition when z magnitude drops below exit threshold
        signal[z.abs() < self.exit_threshold] = 0
        return signal


__all__ = ["STRATEGY_NAME", "strategy", "PairTradingStrategy"]