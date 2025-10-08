"""Walk-forward and out-of-sample evaluation utilities.

This module provides a simple implementation of walk-forward analysis
for trading strategies.  In a walk-forward evaluation the data are
partitioned into sequential training and test segments.  A strategy
may be calibrated on each training segment (for example to fit
machine‑learning models or to optimise parameters) and then evaluated
on the subsequent out‑of‑sample test segment.  The performance
metrics across all test segments can then be aggregated to estimate
future performance under regime changes.

The implementation here assumes strategies do not require explicit
training; it simply runs the user‑supplied strategy function on each
test segment and computes common performance metrics using
``moex_bot.core.metrics.evaluate_strategy``.  It also returns a
summary DataFrame which can be saved as JSON or Parquet for further
analysis.

Example usage::

    import pandas as pd
    from moex_bot.strategies.sma import SMAStrategy
    from moex_bot.core.walk_forward import walk_forward

    df = pd.read_csv("data/SBER_hour_90d.csv")
    strat = SMAStrategy(short_window=5, long_window=20)
    summary = walk_forward(df, strat.generate_signals, n_splits=3, start_capital=1_000_000)
    print(summary)

"""

from __future__ import annotations

from typing import Callable, List, Dict, Any
import pandas as pd
import numpy as np

from .metrics import evaluate_strategy

def walk_forward(
    df: pd.DataFrame,
    strategy_fn: Callable[[pd.DataFrame], pd.Series],
    n_splits: int = 3,
    start_capital: float = 1_000_000.0,
    min_train_size: int | None = None,
) -> pd.DataFrame:
    """Perform a walk-forward evaluation of a trading strategy.

    Args:
        df: A DataFrame containing price data with a 'close' column.  The
            index should be ordered chronologically from oldest to
            newest.  The function does not modify ``df`` but may
            generate intermediate copies.
        strategy_fn: A callable that takes a DataFrame and returns a
            pandas Series of trading signals (-1, 0, 1).  For ML or
            parameterised strategies this function should internally
            handle any training/calibration using the provided data.
        n_splits: Number of walk-forward folds (train/test pairs).  A
            value of ``k`` will produce ``k`` evaluation segments.  At
            least two segments (one train and one test) are required.
        start_capital: Initial capital used to scale return metrics.
        min_train_size: Optional minimum number of rows to use for
            the first training segment.  If not provided, a default
            value of ``len(df) // (n_splits + 1)`` is used.

    Returns:
        DataFrame where each row corresponds to one test segment and
        contains the computed performance metrics for that segment
        along with the split index and the date range of the test.
    """
    if 'close' not in df.columns:
        raise ValueError("Input DataFrame must contain a 'close' column")
    n = len(df)
    if n_splits < 1:
        raise ValueError("n_splits must be >= 1")
    # Determine default training window length
    base = n // (n_splits + 1)
    train_size = min_train_size or base
    # If min_train_size is too small, ensure at least 2 observations for return calc
    if train_size < 2:
        train_size = 2
    results: List[Dict[str, Any]] = []
    for i in range(n_splits):
        train_end = train_size + (base * i)
        test_end = train_end + base
        if test_end > n:
            break
        train_df = df.iloc[:train_end].copy()
        test_df = df.iloc[train_end:test_end].copy()
        if len(test_df) < 2:
            continue
        # Generate signals on test data only.  For simple
        # strategies the training data are unused; more complex
        # strategies can inspect train_df within strategy_fn.
        signals = strategy_fn(test_df).fillna(0.0)
        close = test_df['close'].astype(float)
        returns = close.pct_change().fillna(0.0)
        metrics = evaluate_strategy(returns, signals, start_capital)
        # Append metadata about the test segment
        start_date = str(test_df.index[0]) if not test_df.index.empty else ''
        end_date = str(test_df.index[-1]) if not test_df.index.empty else ''
        res_row: Dict[str, Any] = {
            'split': i + 1,
            'start': start_date,
            'end': end_date,
        }
        res_row.update(metrics)
        results.append(res_row)
    return pd.DataFrame(results)