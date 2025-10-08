"""Financial performance metrics.

This module provides utility functions to compute common risk and
performance statistics from arrays or series of returns.  These metrics
are used by the backtesting framework to evaluate trading strategies.

Implemented metrics:

* ``pnl_pct`` – total percentage return over the period.
* ``pnl_abs`` – absolute return given an initial capital.
* ``sharpe_ratio`` – mean return divided by standard deviation, scaled
  by the square root of the number of periods per year.
* ``max_drawdown`` – largest observed drop from peak to trough of the
  equity curve.
* ``trades_count`` – number of trades executed.  In the simple
  backtester this is estimated by counting position changes.

Additional metrics (Sortino, Calmar, time to recovery, VaR, CVaR) are
implemented below.
"""

from __future__ import annotations

from typing import Iterable, Tuple
import numpy as np

def compute_pnl_pct(returns: Iterable[float]) -> float:
    """Compute total return as a percentage.

    Args:
        returns: Sequence of periodic returns (e.g. daily or hourly).

    Returns:
        Total return (end equity / start equity - 1.0).
    """
    r = np.asarray(returns, dtype=float)
    equity = np.cumprod(1.0 + r)
    return float(equity[-1] - 1.0) if len(equity) else 0.0

def compute_sharpe_ratio(returns: Iterable[float], periods_per_year: int = 252) -> float:
    """Compute the annualised Sharpe ratio of a return series.

    Args:
        returns: Sequence of periodic returns.
        periods_per_year: Number of periods in a year (e.g. 252 trading days).

    Returns:
        The Sharpe ratio.  If the standard deviation of returns is
        negligible, returns ``nan``.
    """
    r = np.asarray(returns, dtype=float)
    if r.size == 0:
        return float('nan')
    mean = r.mean()
    std = r.std(ddof=0)
    if std < 1e-9:
        return float('nan')
    return float((mean / std) * np.sqrt(periods_per_year))


def compute_sortino_ratio(returns: Iterable[float], periods_per_year: int = 252, target: float = 0.0) -> float:
    """Compute the annualised Sortino ratio of a return series.

    The Sortino ratio is similar to the Sharpe ratio but penalises only
    downside volatility.  A target (minimum acceptable) return can be
    specified.  If the downside deviation is negligible the ratio
    returns ``nan``.

    Args:
        returns: Sequence of periodic returns.
        periods_per_year: Number of periods in a year.
        target: Minimum acceptable return per period.

    Returns:
        The Sortino ratio.
    """
    r = np.asarray(returns, dtype=float) - target
    if r.size == 0:
        return float('nan')
    # downside deviation uses only negative deviations
    downside = r[r < 0]
    if downside.size == 0:
        return float('nan')
    downside_dev = np.sqrt(np.mean(np.square(downside)))
    mean_excess = r.mean()
    if downside_dev < 1e-9:
        return float('nan')
    return float((mean_excess / downside_dev) * np.sqrt(periods_per_year))


def compute_calmar_ratio(returns: Iterable[float], equity: Iterable[float] | None = None, periods_per_year: int = 252) -> float:
    """Compute the Calmar ratio of a return series or equity curve.

    The Calmar ratio divides the annualised return by the absolute value
    of the maximum drawdown.  An equity curve can be provided; if not
    given, it is computed from the returns assuming unit starting
    capital.  If the maximum drawdown is zero the ratio returns
    ``nan``.

    Args:
        returns: Sequence of periodic returns.
        equity: Optional sequence of equity values corresponding to the returns.
        periods_per_year: Number of periods in a year.

    Returns:
        The Calmar ratio.
    """
    r = np.asarray(returns, dtype=float)
    if r.size == 0:
        return float('nan')
    annual_return = r.mean() * periods_per_year
    if equity is None:
        equity = np.cumprod(1.0 + r)
    mdd = compute_max_drawdown(equity)
    if mdd == 0.0:
        return float('nan')
    return float(annual_return / abs(mdd))


def compute_time_to_recovery(equity: Iterable[float]) -> int:
    """Compute the longest time to recover from a drawdown in an equity curve.

    Time to recovery (TTR) measures the number of periods it takes for
    equity to surpass the previous peak after a drawdown.  The function
    returns the maximum recovery length observed in the series.

    Args:
        equity: Sequence of cumulative equity values.

    Returns:
        The maximum number of periods required to recover to a new high.
    """
    eq = np.asarray(equity, dtype=float)
    if eq.size == 0:
        return 0
    peak = eq[0]
    max_ttr = 0
    current_draw_len = 0
    for value in eq:
        if value >= peak:
            # new high reached, reset drawdown length
            peak = value
            current_draw_len = 0
        else:
            # still in drawdown
            current_draw_len += 1
            max_ttr = max(max_ttr, current_draw_len)
    return int(max_ttr)


def compute_var_cvar(returns: Iterable[float], alpha: float = 0.05) -> Tuple[float, float]:
    """Compute Value at Risk (VaR) and Conditional VaR (CVaR) at a given level.

    Both metrics are computed using the empirical distribution of returns.
    VaR is the negative of the quantile at ``alpha`` (e.g. 5% worst loss).
    CVaR (or Expected Shortfall) is the mean loss conditional on being in
    the ``alpha`` tail of the distribution.

    Args:
        returns: Sequence of periodic returns.
        alpha: Tail probability level (between 0 and 1).

    Returns:
        Tuple of (VaR, CVaR) as positive numbers representing potential
        losses.
    """
    r = np.asarray(returns, dtype=float)
    if r.size == 0:
        return float('nan'), float('nan')
    # Compute losses as negative returns
    losses = -r
    var = np.quantile(losses, 1 - alpha)
    tail_losses = losses[losses >= var]
    cvar = tail_losses.mean() if tail_losses.size > 0 else var
    return float(var), float(cvar)

def compute_max_drawdown(equity: Iterable[float]) -> float:
    """Compute the maximum drawdown of an equity curve.

    Args:
        equity: Sequence of cumulative equity values.

    Returns:
        The maximum drawdown (negative number).
    """
    eq = np.asarray(equity, dtype=float)
    if eq.size == 0:
        return 0.0
    peak = np.maximum.accumulate(eq)
    drawdown = (eq / peak) - 1.0
    return float(drawdown.min())

def compute_trades_count(signals: Iterable[float]) -> int:
    """Estimate the number of trades from a signal series.

    A trade is counted whenever the signal changes from one non-zero
    value to a different non-zero value, or from zero to non-zero,
    implying an entry or exit.

    Args:
        signals: Sequence of position signals (e.g. -1, 0, 1).

    Returns:
        Integer count of trades.
    """
    s = np.asarray(signals, dtype=float)
    if s.size == 0:
        return 0
    changes = s != np.roll(s, 1)
    changes[0] = False  # ignore the first element
    return int(np.count_nonzero(changes))

def evaluate_strategy(returns: Iterable[float], signals: Iterable[float], start_capital: float, periods_per_year: int = 252) -> dict:
    """Compute a set of performance metrics for a strategy.

    Args:
        returns: Sequence of periodic returns.
        signals: Sequence of position signals used to generate the returns.
        start_capital: Initial capital in currency units.

    Returns:
        Dictionary with metric names and values.
    """
    r = np.asarray(returns, dtype=float)
    pnl_pct = compute_pnl_pct(r)
    pnl_abs = pnl_pct * start_capital
    sharpe = compute_sharpe_ratio(r, periods_per_year)
    # compute equity curve for drawdown and time to recovery
    equity = start_capital * np.cumprod(1.0 + r)
    mdd = compute_max_drawdown(equity)
    trades = compute_trades_count(signals)
    # additional metrics
    sortino = compute_sortino_ratio(r, periods_per_year)
    calmar = compute_calmar_ratio(r, equity, periods_per_year)
    ttr = compute_time_to_recovery(equity)
    var, cvar = compute_var_cvar(r)
    return {
        'pnl_pct': pnl_pct,
        'pnl_abs': pnl_abs,
        'sharpe': sharpe,
        'sortino': sortino,
        'calmar': calmar,
        'max_drawdown': mdd,
        'time_to_recovery': ttr,
        'VaR': var,
        'CVaR': cvar,
        'trades': trades,
    }

__all__ = [
    'compute_pnl_pct', 'compute_sharpe_ratio', 'compute_sortino_ratio',
    'compute_calmar_ratio', 'compute_max_drawdown', 'compute_time_to_recovery',
    'compute_trades_count', 'compute_var_cvar', 'evaluate_strategy'
]