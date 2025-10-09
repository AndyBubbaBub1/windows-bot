"""Tests for the automatic strategy selector utilities."""

from __future__ import annotations

import pandas as pd
import pytest

from moex_bot.core.strategy_selector import auto_select_strategies, format_selection_for_config


def _sample_results() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"strategy": "sma", "file": "file1.csv", "pnl_pct": 0.15, "sharpe": 1.5, "max_drawdown": -0.1, "avg_leverage": 1.2},
            {"strategy": "rsi", "file": "file2.csv", "pnl_pct": 0.10, "sharpe": 1.2, "max_drawdown": -0.05, "avg_leverage": 1.0},
            {"strategy": "ml", "file": "file1.csv", "pnl_pct": 0.05, "sharpe": 0.8, "max_drawdown": -0.2, "avg_leverage": 1.5},
        ]
    )


def test_auto_select_basic_filters() -> None:
    results = _sample_results()
    cfg = {"top_n": 2, "min_sharpe": 1.0, "diversify_by": "file", "top_per_group": 1}
    selection = auto_select_strategies(
        results,
        cfg,
        data_glob="data/*.csv",
        strategies={},
        start_capital=1_000_000.0,
        leverage=1.5,
        borrow_rate=0.0,
        short_rate=None,
        periods_per_year=252,
        strategy_specs={},
    )
    assert not selection.empty
    assert set(selection["strategy"]) == {"sma", "rsi"}
    assert selection["weight"].sum() == pytest.approx(1.0)


def test_format_selection_for_config_returns_allocations() -> None:
    selection = pd.DataFrame(
        [
            {"strategy": "sma", "weight": 0.6},
            {"strategy": "rsi", "weight": 0.4},
        ]
    )
    spec = {"sma": {"module": "sma", "class": "SMAStrategy"}}
    config = format_selection_for_config(selection, spec)
    assert "strategies" in config
    assert "portfolio" in config
    assert config["portfolio"]["target_allocations"]["sma"] == 0.6
