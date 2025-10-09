"""Hyperparameter search utilities for trading strategies.

This module provides a simple grid‑search implementation for
evaluating different parameter combinations of a given strategy on
historical data.  It returns a DataFrame where each row
corresponds to one hyperparameter combination along with the
computed performance metrics.  The function is intentionally
lightweight and does not attempt to perform k‑fold cross‑validation
or nested walk‑forward; such functionality can be layered on top.

Example usage::

    from moex_bot.core.hyperopt import hyperparameter_search
    from moex_bot.strategies.sma import SMAStrategy
    import pandas as pd

    df = pd.read_csv("data/SBER_hour_90d.csv")
    grid = {
        "short_window": [5, 10, 15],
        "long_window": [20, 40, 60],
    }
    res = hyperparameter_search(df, SMAStrategy, grid, start_capital=1_000_000)
    print(res.sort_values("sharpe", ascending=False).head())

The returned DataFrame can be serialised to JSON or Parquet and
plotted to compare the effect of different parameter values.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Any, Dict, Iterable, List, Type

import numpy as np
import pandas as pd

from .metrics import evaluate_strategy


@dataclass
class HyperoptResult:
    """Container for storing the results of a single hyperparameter evaluation.

    Attributes:
        params: Mapping of parameter names to values used for the strategy.
        metrics: Performance metrics returned by :func:`evaluate_strategy`.
    """

    params: Dict[str, Any]
    metrics: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {f"param_{k}": v for k, v in self.params.items()}
        d.update(self.metrics)
        return d


def hyperparameter_search(
    df: pd.DataFrame,
    strategy_class: Type,
    param_grid: Dict[str, Iterable[Any]],
    start_capital: float = 1_000_000.0,
    leverage: float = 1.0,
    borrow_rate: float = 0.0,
    short_rate: float | None = None,
    periods_per_year: int = 252,
) -> pd.DataFrame:
    """Evaluate a grid of hyperparameter combinations for a strategy.

    For each combination of parameters, a new instance of
    ``strategy_class`` is created using the provided parameters.  The
    strategy is run on the entire data set, its signals are used to
    compute returns, and summary metrics are computed via
    :func:`evaluate_strategy`.  All results are collected in a DataFrame.

    Args:
        df: DataFrame containing at least a ``close`` column with
            price data.  The index should be ordered chronologically.
        strategy_class: Class of the strategy to instantiate.  It
            must implement a ``generate_signals(df)`` method returning
            a Series of signals (-1, 0, 1).
        param_grid: Dictionary mapping parameter names to iterables
            of values to explore.  Each unique combination will be
            evaluated.
        start_capital: Initial capital used for scaling return metrics.

    Returns:
        A pandas DataFrame with one row per parameter combination.
        Columns include ``param_<name>`` for each parameter along
        with the metric names returned by :func:`evaluate_strategy`.

    Raises:
        ValueError: If ``df`` does not contain a ``close`` column.
    """
    if "close" not in df.columns:
        raise ValueError("Input DataFrame must contain a 'close' column")
    # Precompute returns once to avoid repeated pct_change calls
    close = df["close"].astype(float)
    returns = close.pct_change().fillna(0.0)
    # Generate all combinations of parameter values
    keys = list(param_grid.keys())
    value_lists = [list(param_grid[k]) for k in keys]
    if not keys:
        combos = [()]
    else:
        combos = list(product(*value_lists))
    results: List[HyperoptResult] = []
    for combo in combos:
        params = dict(zip(keys, combo))
        try:
            strat = strategy_class(**params)
        except Exception:
            # Skip invalid parameter combinations gracefully
            continue
        try:
            signals = strat.generate_signals(df).fillna(0.0)
        except Exception:
            continue
        # Cap signals to +/-1 and forward fill flat positions
        pos = signals.replace(0.0, np.nan).ffill().fillna(0.0).clip(-1.0, 1.0)
        shifted_pos = pos.shift(1).fillna(0.0)
        effective_pos = shifted_pos * leverage
        strat_ret = effective_pos * returns
        if borrow_rate or short_rate:
            periods = max(int(periods_per_year), 1)
            borrow_rate_per_period = borrow_rate / periods
            short_rate_per_period = (short_rate if short_rate is not None else borrow_rate) / periods
            borrowed_ratio = np.clip(np.abs(effective_pos) - 1.0, 0.0, None)
            financing_cost = np.zeros_like(strat_ret)
            long_mask = effective_pos > 0
            short_mask = effective_pos < 0
            if np.any(long_mask) and borrow_rate_per_period:
                financing_cost[long_mask] = borrowed_ratio[long_mask] * borrow_rate_per_period
            if np.any(short_mask) and short_rate_per_period:
                financing_cost[short_mask] = np.abs(effective_pos[short_mask]) * short_rate_per_period
            strat_ret = strat_ret - financing_cost
        try:
            metrics = evaluate_strategy(strat_ret, np.sign(shifted_pos), start_capital, periods_per_year=periods_per_year)
            metrics['avg_leverage'] = float(np.mean(np.abs(effective_pos))) if effective_pos.size else 0.0
            metrics['max_leverage'] = float(np.max(np.abs(effective_pos))) if effective_pos.size else 0.0
        except Exception:
            continue
        results.append(HyperoptResult(params=params, metrics=metrics))
    # Convert to DataFrame
    rows: List[Dict[str, Any]] = [r.to_dict() for r in results]
    return pd.DataFrame(rows)


__all__ = ["hyperparameter_search", "HyperoptResult"]