"""Backtesting engine for the MOEX bot.

This module provides functions to run trading strategies on historical
data and compute performance statistics.  It leverages the metrics
defined in :mod:`moex_bot.core.metrics` and the strategy
implementations in :mod:`moex_bot.strategies`.

Example:

.. code-block:: python

    from moex_bot.core import backtester
    from moex_bot.strategies import simple
    import pandas as pd

    df = pd.read_csv('data/SBER_hour_90d.csv')
    strategies = {'momentum': simple.momentum}
    results = backtester.run_backtest_for_df(df, strategies, start_capital=1_000_000)
    print(results)

"""

from __future__ import annotations

import glob
from typing import Callable, Dict, Tuple, Any

import numpy as np
import pandas as pd

from .metrics import evaluate_strategy


def _prepare_returns_and_signals(df: pd.DataFrame, strategy_fn: Callable[[pd.DataFrame], pd.Series]) -> Tuple[np.ndarray, np.ndarray]:
    """Apply a strategy function to a DataFrame to obtain returns and signals.

    The strategy function should accept a DataFrame and return a pandas
    Series of signals (-1, 0, 1).  Returns are computed as the percent
    change of the ``close`` column.  Signals are forward-shifted by
    one period so that positions are entered at the next bar.

    Args:
        df: Historical OHLCV data with at least a ``close`` column.
        strategy_fn: Callable that produces a signal series.

    Returns:
        A tuple ``(returns, signals)`` where ``returns`` is a 1D numpy
        array of periodic returns and ``signals`` is a 1D numpy array of
        positions at the same timestamps.
    """
    close = df['close'].astype(float)
    returns = close.pct_change().fillna(0.0).to_numpy()
    sig = strategy_fn(df).astype(float).fillna(0.0)
    # Position is carried forward; shift so that today's signal acts on next period
    pos = sig.replace(0.0, np.nan).ffill().fillna(0.0).clip(-1.0, 1.0)
    positions = pos.shift(1).fillna(0.0).to_numpy()
    # Strategy returns are position * returns
    strategy_returns = positions * returns
    return strategy_returns, positions


def run_backtest_for_df(df: pd.DataFrame,
                        strategies: Dict[str, Callable[[pd.DataFrame], pd.Series]],
                        start_capital: float,
                        show: bool = False) -> pd.DataFrame:
    """Run multiple strategies on a single DataFrame and compute metrics.

    Args:
        df: Historical data DataFrame.
        strategies: Mapping of strategy names to callables returning a
            signal series.
        start_capital: Initial capital for PnL calculations.
        show: If True, prints the resulting DataFrame.

    Returns:
        A pandas DataFrame containing metrics for each strategy.
    """
    rows = []
    for name, fn in strategies.items():
        try:
            r, pos = _prepare_returns_and_signals(df, fn)
            metrics = evaluate_strategy(r, pos, start_capital)
            rows.append({'strategy': name, **metrics})
        except Exception as e:
            rows.append({'strategy': name, 'error': str(e)})
    res = pd.DataFrame(rows)
    # Sort by pnl_pct descending, then sharpe descending
    if 'pnl_pct' in res.columns:
        res = res.sort_values(['pnl_pct', 'sharpe'], ascending=[False, False])
    if show:
        print(res.to_string(index=False))
    return res.reset_index(drop=True)


def _run_single_backtest(file_path: str,
                         strategies: Dict[str, Callable[[pd.DataFrame], pd.Series]],
                         start_capital: float) -> pd.DataFrame:
    """Helper to run a backtest on a single file.

    This helper function is defined at the top level so that it can
    be pickled and executed by worker threads.  It reads the CSV
    file, runs the backtest and returns the resulting DataFrame with
    a ``file`` column inserted.

    Args:
        file_path: Path to the CSV file to backtest.
        strategies: Mapping of strategy names to callables.
        start_capital: Initial capital for the backtest.

    Returns:
        DataFrame containing metrics for all strategies for this
        single file.
    """
    df = pd.read_csv(file_path)
    res = run_backtest_for_df(df, strategies, start_capital, show=False)
    res.insert(0, 'file', file_path)
    return res


def run_backtests(glob_pattern: str,
                  strategies: Dict[str, Callable[[pd.DataFrame], pd.Series]],
                  start_capital: float) -> pd.DataFrame:
    """Run backtests on all files matching a glob pattern.

    This function can optionally leverage multiple worker threads to
    speed up backtests when many CSV files are involved.  The number
    of workers is determined by the environment variable
    ``MOEX_BACKTEST_WORKERS``.  If unspecified or set to ``1``, a
    sequential loop is used.  Each worker reads its own CSV file
    and runs the backtest.  Using threads rather than processes
    avoids pickling issues with complex callables.  Since the
    majority of work is I/O bound (loading CSVs) and vectorised
    calculations release the GIL, threads can still provide a
    performance boost.

    Args:
        glob_pattern: File pattern relative to the project root (e.g.
            ``data/*_hour_90d.csv``).
        strategies: Mapping of strategy names to callables.
        start_capital: Initial capital.

    Returns:
        Concatenated results for all files with an additional ``file``
        column indicating the source file.
    """
    files = sorted(glob.glob(glob_pattern))
    if not files:
        return pd.DataFrame()
    # Determine desired number of workers from environment; default to 1
    import os
    try:
        workers = int(os.getenv('MOEX_BACKTEST_WORKERS', '1'))
    except Exception:
        workers = 1
    results = []
    # Use threads when more than one worker is requested
    if workers > 1:
        from concurrent.futures import ThreadPoolExecutor
        max_workers = min(workers, len(files))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_run_single_backtest, f, strategies, start_capital) for f in files]
            for fut in futures:
                try:
                    res = fut.result()
                    results.append(res)
                except Exception as e:
                    # In case of error, include a row indicating failure
                    err_df = pd.DataFrame([{'file': fut, 'error': str(e)}])
                    results.append(err_df)
    else:
        # Sequential execution
        for f in files:
            try:
                res = _run_single_backtest(f, strategies, start_capital)
                results.append(res)
            except Exception as e:
                err_df = pd.DataFrame([{'file': f, 'error': str(e)}])
                results.append(err_df)
    if results:
        return pd.concat(results, ignore_index=True)
    return pd.DataFrame()


def load_strategies_from_config(cfg: Dict[str, Any]) -> Dict[str, Callable[[pd.DataFrame], pd.Series]]:
    """Instantiate strategies defined in the configuration.

    The ``strategies`` section of the configuration may be either a
    list of simple names (for backward compatibility) or a mapping of
    strategy identifiers to configuration dictionaries.  Each entry
    should define at least a ``class`` or ``module`` key specifying
    where to import the strategy from.  Optional ``params`` are
    passed to the constructor of class‑based strategies.  If a class
    cannot be imported, the loader will fall back to importing a
    module‑level ``strategy`` function.  Both class instances and
    functions are returned as callables mapping a DataFrame to a
    Series of signals.

    Args:
        cfg: Parsed configuration dictionary.

    Returns:
        A mapping from user‑defined strategy names to callables.
    """
    from importlib import import_module
    import inspect
    strategies: Dict[str, Callable[[pd.DataFrame], pd.Series]] = {}
    strat_cfg = cfg.get('strategies', {})
    # Support legacy list of names
    if isinstance(strat_cfg, list):
        # Convert list into a mapping with the same key as name
        strat_cfg = {name: {'module': name} for name in strat_cfg}
    for name, spec in strat_cfg.items():
        # Determine module and class/function names
        class_name = None
        module_name = None
        params: Dict[str, Any] = {}
        if isinstance(spec, str):
            # Simple string means module name
            module_name = spec
        elif isinstance(spec, dict):
            # New style: dict with class and params
            class_name = spec.get('class')
            module_name = spec.get('module')  # allow explicit module override
            params = spec.get('params', {}) or {}
            # For backward compatibility, allow specifying module via class
            if module_name is None and class_name is not None:
                # Convert CamelCase class name to snake_case module and strip 'Strategy' suffix
                import re
                base_name = re.sub(r'Strategy$', '', class_name)
                module_name = re.sub(r'(?<!^)(?=[A-Z])', '_', base_name).lower()
        else:
            continue
        # Fallback: if module_name is still None, use the key name
        if not module_name:
            module_name = name
        mod = None
        # Try importing the strategy module using several heuristics.  Start
        # with the computed module_name, then try a version without
        # underscores and finally the lowercased base_name.  This helps
        # handle names like ``SuperTrendStrategy`` where the file is
        # ``supertrend.py``.
        candidates = []
        if module_name:
            candidates.append(module_name)
            # Remove underscores for a second attempt
            if '_' in module_name:
                candidates.append(module_name.replace('_', ''))
        # Add lowercased base_name without underscores if different
        if class_name:
            import re
            base = re.sub(r'Strategy$', '', class_name)
            lower_base = base.lower()
            if lower_base not in candidates:
                candidates.append(lower_base)
        for cand in candidates:
            try:
                mod = import_module(f'moex_bot.strategies.{cand}')
                if mod:
                    break
            except Exception:
                mod = None
        if mod is None:
            continue
        strat_callable = None
        # If class_name is specified, try to instantiate it
        if class_name:
            cls = getattr(mod, class_name, None)
            if cls and inspect.isclass(cls):
                try:
                    instance = cls(**params)
                    # Instances of BaseStrategy are callable, but check anyway
                    if callable(instance):
                        strat_callable = instance
                except Exception:
                    strat_callable = None
        # Fall back to function
        if strat_callable is None:
            func = getattr(mod, 'strategy', None)
            # If the strategy function expects parameters, capture them via closure
            if callable(func):
                # If params are provided, attempt to pass them when calling
                if params:
                    def make_fn(f: Callable, p: Dict[str, Any]) -> Callable[[pd.DataFrame], pd.Series]:
                        def wrapper(df: pd.DataFrame) -> pd.Series:
                            return f(df, **p)
                        return wrapper
                    strat_callable = make_fn(func, params)
                else:
                    strat_callable = func
        if strat_callable is not None:
            strategies[name] = strat_callable
    return strategies

__all__ = [
    'run_backtest_for_df', 'run_backtests', 'load_strategies_from_config'
]