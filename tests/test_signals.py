"""Tests for strategy signal generators.

These tests ensure that built‑in strategies produce a signal series of
correct length with values confined to the expected set {-1, 0, 1}.
"""

import pandas as pd

from moex_bot.strategies.sma import SMAStrategy


def test_sma_strategy_signals_shape_and_values() -> None:
    """SMAStrategy should return a signal for each row and only produce -1/0/1."""
    # Construct a simple price series with known behaviour
    df = pd.DataFrame({'close': [1, 2, 3, 4, 5, 4, 3, 2, 1, 2, 3]}, index=range(11))
    strat = SMAStrategy(short_window=2, long_window=3)
    sig = strat.generate_signals(df)
    # Length matches input
    assert len(sig) == len(df)
    # Only values -1, 0, 1 are present
    unique = set(sig.unique())
    assert unique.issubset({-1, 0, 1})