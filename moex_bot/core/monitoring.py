"""Prometheus monitoring utilities.

This module provides functions to expose application metrics via
Prometheus.  It defines global counters and gauges for tracking
backtest executions, current portfolio equity and error counts.  A
simple HTTP server can be started to serve these metrics.
"""

from __future__ import annotations

import os
from prometheus_client import start_http_server, Counter, Gauge, CollectorRegistry
try:
    # Optional multiprocess support for Prometheus
    from prometheus_client import multiprocess
except Exception:
    multiprocess = None

# Define Prometheus metrics
backtest_runs_total = Counter('backtest_runs_total', 'Total number of backtest executions')
portfolio_equity_gauge = Gauge('portfolio_equity', 'Latest portfolio equity value')
strategy_pnl_gauge = Gauge('strategy_pnl', 'Latest PnL percentage per strategy', ['strategy'])
error_counter = Counter('moex_bot_errors_total', 'Total number of errors encountered')

def init_prometheus_server(port: int = 8001) -> None:
    """Start an HTTP server to expose Prometheus metrics.

    This function transparently enables multiprocess mode when the
    ``PROMETHEUS_MULTIPROC_DIR`` environment variable is defined.
    In such cases a custom registry is created and registered with
    the multiprocess collector.  Otherwise a default registry is used.

    Args:
        port: Port on which to expose the metrics endpoint.
    """
    if multiprocess and os.environ.get('PROMETHEUS_MULTIPROC_DIR'):
        # Use a collector registry that aggregates metrics across processes
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        start_http_server(port, registry=registry)
    else:
        start_http_server(port)


def record_backtest_run() -> None:
    """Increment the backtest run counter."""
    backtest_runs_total.inc()


def update_portfolio_equity(equity: float) -> None:
    """Update the portfolio equity gauge.

    Args:
        equity: New equity value.
    """
    portfolio_equity_gauge.set(equity)


def update_strategy_pnl(strategy: str, pnl: float) -> None:
    """Update the PnL gauge for a specific strategy.

    Args:
        strategy: Name of the strategy.
        pnl: PnL percentage.
    """
    strategy_pnl_gauge.labels(strategy=strategy).set(pnl)


def record_error() -> None:
    """Increment the error counter."""
    error_counter.inc()


__all__ = [
    'init_prometheus_server', 'record_backtest_run', 'update_portfolio_equity',
    'update_strategy_pnl', 'record_error'
]