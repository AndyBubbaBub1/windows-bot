"""Tests for performance metric calculations.

These tests verify that evaluate_strategy returns sensible
values for simple synthetic return series.
"""

from moex_bot.core.metrics import evaluate_strategy


def test_evaluate_strategy_positive_return() -> None:
    """A positive cumulative return should yield positive pnl and pnl_pct."""
    returns = [0.05, -0.02, 0.03, 0.01]
    signals = [1, 1, 1, 1]
    metrics = evaluate_strategy(returns, signals, start_capital=1000.0)
    assert metrics['pnl_pct'] > 0
    assert metrics['pnl_abs'] > 0