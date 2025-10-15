"""Report generation utilities.

This module produces CSV and HTML reports summarising backtest results
and generates equity curve charts using Matplotlib.  It can also
dispatch Telegram notifications when configured via environment
variables or the configuration file.

Example usage:

.. code-block:: python

    from moex_bot.reporting.report_builder import generate_reports
    generate_reports(results_df, data_glob='data/*_hour_90d.csv', strategies=strategies,
                     out_dir='results', start_capital=1_000_000)

"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests

from ..core.metrics import evaluate_strategy
from ..core.portfolio import (
    compute_correlation_matrix,
    compute_capital_allocation,
    compute_portfolio_metrics,
)

STRATEGY_LABELS = {
    "sma_strategy": "Скользящие средние (SMA)",
    "macd_strategy": "MACD",
    "momentum_strategy": "Импульс",
    "pairs_strategy": "Парный трейдинг",
    "ml_strategy": "ML-модель",
}
METRIC_LABELS = {
    "sharpe": "Коэффициент Шарпа",
    "sortino": "Коэффициент Сортино",
    "calmar": "Коэффициент Кальмара",
    "cagr": "CAGR",
    "max_drawdown": "Макс. просадка",
    "volatility": "Волатильность",
    "win_rate": "Доля прибыльных",
}
def translate_name(name: str) -> str:
    return STRATEGY_LABELS.get(name, name)


def translate_metrics_df(df: pd.DataFrame) -> pd.DataFrame:
    cols = [METRIC_LABELS.get(c, c) for c in df.columns]
    out = df.copy()
    out.columns = cols
    return out

def _compute_equity(df: pd.DataFrame, strategy_fn, start_capital: float) -> pd.Series:
    """Compute equity curve for a single strategy.

    Args:
        df: DataFrame with price data.
        strategy_fn: Callable returning a signal series.
        start_capital: Starting capital for scaling equity.

    Returns:
        A pandas Series representing cumulative equity over time.
    """
    close = df['close'].astype(float)
    returns = close.pct_change().fillna(0.0)
    sig = strategy_fn(df).fillna(0.0)
    pos = sig.replace(0.0, np.nan).ffill().fillna(0.0).clip(-1.0, 1.0)
    strat_ret = pos.shift(1).fillna(0.0) * returns
    equity = (1.0 + strat_ret).cumprod() * start_capital
    return equity


def _plot_equity_curve(equity: pd.Series, title: str, filepath: Path) -> None:
    """Save an equity curve plot to a PNG file."""
    plt.figure(figsize=(8, 4))
    plt.plot(equity.values, label=title)
    plt.title(title)
    plt.ylabel('Equity')
    plt.legend()
    plt.tight_layout()
    filepath.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(filepath)
    plt.close()


def generate_reports(results: pd.DataFrame,
                     data_glob: str,
                     strategies: Dict[str, callable],
                     out_dir: str,
                     start_capital: float,
                     top_n: int = 3) -> None:
    """Generate CSV/HTML reports and equity curve charts.

    Args:
        results: DataFrame returned by ``run_backtests``.
        data_glob: Glob pattern to locate data CSV files.
        strategies: Mapping of strategy names to callables.
        out_dir: Directory where outputs will be saved.
        start_capital: Initial capital used for scaling equity curves.
        top_n: Number of top strategies per instrument to include.
    """
    out = Path(out_dir)
    out.mkdir(exist_ok=True)

    # Save full backtest report
    full_csv = out / 'backtest_report.csv'
    results.to_csv(full_csv, index=False)
    # Additional serialisations: JSON and Parquet
    try:
        full_json = out / 'backtest_report.json'
        results.to_json(full_json, orient='records', force_ascii=False)
        full_parquet = out / 'backtest_report.parquet'
        results.to_parquet(full_parquet, index=False)
    except Exception:
        # Non‑critical if serialisation fails
        pass

    # Group by file and select top_n strategies for each instrument
    rows: List[dict] = []
    equity_curves: List[pd.Series] = []
    returns_by_strategy: Dict[str, List[np.ndarray]] = {}
    for file, grp in results.groupby('file'):
        top = grp.nlargest(top_n, ['pnl_pct', 'sharpe']) if 'pnl_pct' in grp.columns else grp.head(top_n)
        for _, row in top.iterrows():
            strat_name = row['strategy']
            rows.append({'file': file, **row.to_dict()})
            # Compute equity curve and store returns for portfolio analysis
            try:
                # Locate file path; results 'file' column may contain basename
                file_path = None
                # Try relative path inside current working directory
                if Path(file).exists():
                    file_path = Path(file)
                else:
                    # search under data_glob directory
                    matches = list(Path().glob(file))
                    if matches:
                        file_path = matches[0]
                if file_path is None:
                    continue
                df = pd.read_csv(file_path)
                # compute strategy returns for correlation/portfolio metrics
                close = df['close'].astype(float)
                r = close.pct_change().fillna(0.0)
                sig = strategies[strat_name](df).fillna(0.0)
                pos = sig.replace(0.0, np.nan).ffill().fillna(0.0).clip(-1.0, 1.0)
                strat_ret = pos.shift(1).fillna(0.0) * r
                # accumulate returns by strategy
                returns_by_strategy.setdefault(strat_name, []).append(strat_ret.to_numpy())
                # compute equity curve
                eq = (1.0 + strat_ret).cumprod() * start_capital
                equity_curves.append(eq.reset_index(drop=True))
                chart_path = out / f"{file}_{strat_name}.png"
                _plot_equity_curve(eq, f"{file} – {strat_name}", chart_path)
            except Exception:
                continue
    # Save top strategies report
    best_df = pd.DataFrame(rows)
    if not best_df.empty:
        best_csv = out / 'best_strategies_top3.csv'
        best_df.to_csv(best_csv, index=False)
        html_out = out / 'auto_report.html'
        best_df.pipe(translate_metrics_df).to_html(html_out, index=False, border=0, justify="center")
        # Persist best strategies as JSON and Parquet
        try:
            best_json = out / 'best_strategies_top3.json'
            best_df.to_json(best_json, orient='records', force_ascii=False)
            best_parquet = out / 'best_strategies_top3.parquet'
            best_df.to_parquet(best_parquet, index=False)
        except Exception:
            pass
    # Portfolio equity curve chart (equal weighting of top strategies)
    if equity_curves:
        min_len = min(map(len, equity_curves))
        aligned = [eq.iloc[:min_len].reset_index(drop=True) for eq in equity_curves]
        portfolio = pd.concat(aligned, axis=1).mean(axis=1)
        port_equity = portfolio
        port_chart = out / 'portfolio_equity.png'
        _plot_equity_curve(port_equity, 'Portfolio Equity Curve', port_chart)

    # ===== Portfolio-level analysis =====
    # Flatten returns_by_strategy across files
    aggregated_returns: Dict[str, np.ndarray] = {}
    for strat, ret_list in returns_by_strategy.items():
        # Concatenate returns across different files; remove NaNs
        concat = np.concatenate([np.asarray(r, dtype=float) for r in ret_list]) if ret_list else np.array([])
        aggregated_returns[strat] = concat
    if aggregated_returns:
        # Compute metrics for each strategy on aggregated returns
        metrics_by_strategy: Dict[str, dict] = {}
        for strat, ret in aggregated_returns.items():
            # Use sign of returns as dummy signals for trade count approximation
            signals = np.sign(ret)
            metrics = evaluate_strategy(ret, signals, start_capital)
            metrics_by_strategy[strat] = metrics
        # Determine capital allocation weights (equal weighting)
        weights = compute_capital_allocation(metrics_by_strategy, method='equal')
        # Compute portfolio metrics
        port_metrics = compute_portfolio_metrics(
            {k: pd.Series(v) for k, v in aggregated_returns.items()}, start_capital, weights
        )
        # Compute correlation matrix
        corr_df = compute_correlation_matrix({k: pd.Series(v) for k, v in aggregated_returns.items()})
        # Save metrics table with weights
        metrics_rows = []
        for strat, m in metrics_by_strategy.items():
            row = {'strategy': strat, **m, 'weight': weights.get(strat, 0.0)}
            metrics_rows.append(row)
        # Append portfolio summary row
        metrics_rows.append({'strategy': 'Portfolio', **port_metrics, 'weight': 1.0})
        metrics_df = pd.DataFrame(metrics_rows)
        metrics_csv = out / 'portfolio_metrics.csv'
        metrics_df.to_csv(metrics_csv, index=False)
        # Persist portfolio metrics in JSON and Parquet formats
        try:
            metrics_json = out / 'portfolio_metrics.json'
            metrics_df.to_json(metrics_json, orient='records', force_ascii=False)
            metrics_parquet = out / 'portfolio_metrics.parquet'
            metrics_df.to_parquet(metrics_parquet, index=False)
        except Exception:
            pass
        # Save correlation matrix to CSV
        corr_csv = out / 'correlation_matrix.csv'
        corr_df.to_csv(corr_csv)
        # Persist correlation matrix to JSON and Parquet
        try:
            corr_json = out / 'correlation_matrix.json'
            corr_df.to_json(corr_json, orient='split', force_ascii=False)
            corr_parquet = out / 'correlation_matrix.parquet'
            corr_df.to_parquet(corr_parquet)
        except Exception:
            pass
        # Plot correlation heatmap
        try:
            import seaborn as sns  # optionally available
            plt.figure(figsize=(6, 5))
            sns.heatmap(corr_df, annot=True, cmap='coolwarm', vmin=-1, vmax=1)
            plt.title('Strategy Return Correlation')
            plt.tight_layout()
            heatmap_path = out / 'correlation_heatmap.png'
            plt.savefig(heatmap_path)
            plt.close()
        except Exception:
            # Fallback: simple matplotlib plot without seaborn
            plt.figure(figsize=(6, 5))
            plt.imshow(corr_df, cmap='coolwarm', vmin=-1, vmax=1)
            plt.colorbar()
            plt.xticks(range(len(corr_df.columns)), corr_df.columns, rotation=45, ha='right')
            plt.yticks(range(len(corr_df.index)), corr_df.index)
            plt.title('Strategy Return Correlation')
            plt.tight_layout()
            heatmap_path = out / 'correlation_heatmap.png'
            plt.savefig(heatmap_path)
            plt.close()


def send_telegram_message(text: str, files: Iterable[Path], token: str, chat_id: str) -> None:
    """Send a Telegram message with optional file attachments.

    Args:
        text: The message text.
        files: Iterable of file paths to send as documents.
        token: Telegram bot token.
        chat_id: Chat ID to send the message to.
    """
    base = f"https://api.telegram.org/bot{token}"
    try:
        requests.post(f"{base}/sendMessage", json={"chat_id": chat_id, "text": text})
    except Exception:
        pass
    for f in files:
        try:
            with open(f, 'rb') as fh:
                files_payload = {'document': (f.name, fh)}
                requests.post(f"{base}/sendDocument", data={"chat_id": chat_id}, files=files_payload)
        except Exception:
            continue

__all__ = ['generate_reports', 'send_telegram_message']