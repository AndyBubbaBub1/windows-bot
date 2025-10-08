"""Portfolio-level analytics (placeholder).

This module will provide functions to analyse portfolios comprised of
multiple strategies.  It will compute capital allocation, correlations
between strategy returns, aggregated equity curves and advanced
statistics such as the Sortino ratio, Calmar ratio and time to
recovery.  The actual implementation is left as an exercise for
future development.
"""

from __future__ import annotations

from typing import Dict, Iterable, Tuple
import numpy as np
import pandas as pd

from .metrics import evaluate_strategy

def aggregate_returns(strategies_returns: Dict[str, pd.Series], weights: Dict[str, float] | None = None) -> pd.Series:
    """Compute equal-weighted portfolio returns from a set of strategies.

    Args:
        strategies_returns: Mapping from strategy name to a Series of returns.

        weights: Optional mapping of strategy names to portfolio weights.  If
            not provided, strategies are weighted equally.

    Returns:
        A Series of portfolio returns.
    """
    if not strategies_returns:
        return pd.Series(dtype=float)
    aligned = pd.concat(strategies_returns.values(), axis=1).dropna(how='all')
    aligned = aligned.fillna(0.0)
    if weights is None:
        # equal weights
        w = np.repeat(1.0 / aligned.shape[1], aligned.shape[1])
    else:
        # align weights vector with column order
        w = np.array([weights.get(k, 0.0) for k in strategies_returns.keys()])
        if w.sum() != 0:
            w = w / w.sum()
    return aligned.to_numpy().dot(w)

def compute_correlation_matrix(strategies_returns: Dict[str, pd.Series]) -> pd.DataFrame:
    """Compute correlation matrix between strategy returns.

    Args:
        strategies_returns: Mapping from strategy name to returns Series.

    Returns:
        A pandas DataFrame containing pairwise correlation coefficients.
    """
    if not strategies_returns:
        return pd.DataFrame()
    aligned = pd.concat(strategies_returns, axis=1).fillna(0.0)
    return aligned.corr()


def compute_portfolio_metrics(strategies_returns: Dict[str, pd.Series], start_capital: float, weights: Dict[str, float] | None = None) -> dict:
    """Compute performance metrics for an aggregate portfolio of strategies.

    Args:
        strategies_returns: Mapping from strategy names to return series.
        start_capital: Initial capital for computing absolute returns.
        weights: Optional dictionary of portfolio weights for each strategy.

    Returns:
        Dictionary of performance metrics using the same structure as
        :func:`evaluate_strategy`.  The ``trades`` metric is omitted since
        positions are aggregated.
    """
    port_returns = aggregate_returns(strategies_returns, weights)
    # Build dummy signals (positions) as ones for aggregated returns; we cannot
    # count trades in the same way, so pass signals equal to return signs
    dummy_signals = np.sign(port_returns)
    metrics = evaluate_strategy(port_returns, dummy_signals, start_capital)
    metrics.pop('trades', None)
    return metrics


def compute_capital_allocation(strategies_metrics: Dict[str, dict], method: str = 'equal') -> Dict[str, float]:
    """Determine capital allocation weights for a set of strategies.

    The allocation can be based on a variety of methods:

    * ``'equal'`` – equal weighting across all strategies.
    * ``'sharpe'`` – weights proportional to Sharpe ratio (non-negative only).
    * ``'pnl'`` – weights proportional to absolute PnL percentage.

    Args:
        strategies_metrics: Mapping from strategy name to computed metrics.
        method: Allocation method ('equal', 'sharpe', 'pnl').

    Returns:
        Normalised weights summing to 1.0.
    """
    n = len(strategies_metrics)
    if n == 0:
        return {}
    weights = {}
    if method == 'equal':
        for k in strategies_metrics:
            weights[k] = 1.0 / n
    elif method == 'sharpe':
        vals = [max(0.0, strategies_metrics[k].get('sharpe', 0.0) or 0.0) for k in strategies_metrics]
        total = sum(vals)
        if total == 0:
            # fallback to equal
            return compute_capital_allocation(strategies_metrics, 'equal')
        for k, v in zip(strategies_metrics.keys(), vals):
            weights[k] = v / total
    elif method == 'pnl':
        vals = [abs(strategies_metrics[k].get('pnl_pct', 0.0) or 0.0) for k in strategies_metrics]
        total = sum(vals)
        if total == 0:
            return compute_capital_allocation(strategies_metrics, 'equal')
        for k, v in zip(strategies_metrics.keys(), vals):
            weights[k] = v / total
    else:
        raise ValueError(f"Unknown allocation method: {method}")
    return weights


__all__ = [
    'aggregate_returns', 'compute_correlation_matrix', 'compute_portfolio_metrics',
    'compute_capital_allocation'
]

__all__ = ['aggregate_returns', 'compute_correlation_matrix']