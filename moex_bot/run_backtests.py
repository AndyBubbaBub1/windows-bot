"""Entry point to run backtests and generate reports.

This script reads configuration from ``config.yaml``, loads the
specified strategies and historical data, runs the backtests and
produces CSV/HTML reports.  Optionally, it sends a Telegram message
with the results when Telegram credentials are provided in the
configuration.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# Note: The moex_bot package must be installed (e.g. via ``pip install -e .``)
# for these imports to resolve without modifying sys.path.  See ``setup.py``
# and ``pyproject.toml`` for packaging details.
from moex_bot.core.config import load_config
from moex_bot.core.backtester import run_backtests, load_strategies_from_config
from moex_bot.core.storage import init_db, save_metrics, save_report_entry
from moex_bot.core.monitoring import (
    init_prometheus_server,
    record_backtest_run,
    update_portfolio_equity,
    update_strategy_pnl,
)
from moex_bot.core.logging_config import configure_logging
from moex_bot.reporting.report_builder import generate_reports, send_telegram_message


def main() -> None:
    load_dotenv()
    # Configure logging once at script entry
    configure_logging()
    logger = logging.getLogger(__name__)
    cfg = load_config()
    # Determine initial capital: prefer 'capital' key, fall back to legacy 'start_capital'
    start_capital = cfg.get('capital') or cfg.get('start_capital') or 1_000_000
    data_glob_cfg = (cfg.get('data') or {}).get('glob', 'data/*_hour_90d.csv')
    # Resolve glob relative to project root
    project_root = Path(__file__).resolve().parent
    data_glob = str(project_root / data_glob_cfg)
    strategies = load_strategies_from_config(cfg)
    if not strategies:
        logger.warning("No valid strategies found in configuration; nothing to backtest.")
        return
    # Run backtests using optional concurrency defined by MOEX_BACKTEST_WORKERS
    results = run_backtests(data_glob, strategies, start_capital)
    if results.empty:
        logger.warning("No data matched the glob pattern; nothing to backtest.")
        return
    # Determine output directory once
    out_dir_cfg = (cfg.get('results_dir') or 'results')
    out_dir = str(project_root / out_dir_cfg)
    # Generate standard backtest reports (CSV/HTML/JSON/Parquet)
    generate_reports(results, data_glob, strategies, out_dir, start_capital)
    logger.info(f"Reports generated in {out_dir}")

    # ------------------------------------------------------------------
    # Walk‑forward / out‑of‑sample evaluation
    # ------------------------------------------------------------------
    try:
        from moex_bot.core.walk_forward import walk_forward
        import pandas as _pd  # local import to avoid mandatory dependency for runtime
        walk_rows = []
        # Use three splits by default; override via config
        wf_cfg = cfg.get('walk_forward', {}) or {}
        try:
            n_splits = int(wf_cfg.get('n_splits', 3))
        except Exception:
            n_splits = 3
        for file in results['file'].unique():
            # Try to resolve file path relative to the project root
            file_path = None
            fp = project_root / file
            if fp.exists():
                file_path = fp
            else:
                # Search within data_glob pattern
                try:
                    matches = list((project_root / '.').glob(file))
                except Exception:
                    matches = []
                if matches:
                    file_path = matches[0]
            if not file_path:
                continue
            try:
                df = _pd.read_csv(file_path)
            except Exception:
                continue
            if df.empty:
                continue
            for strat_name, strat_fn in strategies.items():
                try:
                    summary = walk_forward(
                        df.copy(), strat_fn, n_splits=n_splits, start_capital=start_capital
                    )
                except Exception:
                    continue
                if summary.empty:
                    continue
                summary['file'] = file
                summary['strategy'] = strat_name
                walk_rows.append(summary)
        if walk_rows:
            wf_df = _pd.concat(walk_rows, ignore_index=True)
            # Save walk-forward report in various formats
            wf_csv = project_root / out_dir_cfg / 'walk_forward_report.csv'
            wf_df.to_csv(wf_csv, index=False)
            try:
                wf_json = project_root / out_dir_cfg / 'walk_forward_report.json'
                wf_df.to_json(wf_json, orient='records', force_ascii=False)
                wf_parquet = project_root / out_dir_cfg / 'walk_forward_report.parquet'
                wf_df.to_parquet(wf_parquet, index=False)
            except Exception:
                pass
            logger.info(f"Walk-forward report saved to {wf_csv}")
    except Exception as wf_exc:
        logger.debug(f"Walk-forward evaluation failed: {wf_exc}")

    # Prometheus monitoring: start metrics server on first run
    try:
        init_prometheus_server(port=int(os.getenv('PROM_PORT', '8001')))
    except Exception as exc:
        logger.debug(f"Prometheus server init failed: {exc}")
    # Record backtest run metric
    record_backtest_run()
    # Update strategy PnL gauges
    for _, row in results.iterrows():
        strategy_name = row.get('strategy')
        pnl = row.get('pnl_pct')
        if strategy_name is not None and pnl is not None:
            try:
                update_strategy_pnl(strategy_name, pnl)
            except Exception:
                pass
    # Update portfolio equity gauge using last value from portfolio equity curve file
    # To update gauge we need numeric value; approximate using metrics file
    metrics_file = Path(out_dir) / 'portfolio_metrics.csv'
    if metrics_file.exists():
        try:
            import pandas as pd
            dfm = pd.read_csv(metrics_file)
            # portfolio row last metrics maybe final absolute PnL
            portfolio_row = dfm[dfm['strategy'] == 'Portfolio']
            if not portfolio_row.empty:
                pnl_pct = portfolio_row.iloc[0].get('pnl_pct', 0.0)
                update_portfolio_equity(start_capital * (1 + pnl_pct))
        except Exception as exc:
            logger.debug(f"Failed to update portfolio equity gauge: {exc}")

    # Initialise and record metrics and report entries in the database
    db_path_cfg = cfg.get('database') or f"{out_dir_cfg}/history.db"
    db_path = str(project_root / db_path_cfg)
    init_db(db_path)
    # Save metrics for each strategy in results
    if not results.empty:
        for _, row in results.iterrows():
            metrics = row.to_dict()
            strategy_name = metrics.pop('strategy', None)
            # Remove non-metric columns
            metrics.pop('file', None)
            save_metrics(db_path, strategy_name or 'unknown', metrics)
    # Save report entries
    save_report_entry(db_path, None, 'csv', str(Path(out_dir)/'backtest_report.csv'))
    save_report_entry(db_path, None, 'csv', str(Path(out_dir)/'best_strategies_top3.csv'))
    save_report_entry(db_path, None, 'html', str(Path(out_dir)/'auto_report.html'))
    # Telegram notification
    telegram_cfg = cfg.get('telegram') or {}
    token = telegram_cfg.get('token')
    chat_id = telegram_cfg.get('chat_id')
    if token and chat_id:
        text = f"Backtests complete. Files: {len(results['file'].unique())}"
        files = [Path(out_dir)/'backtest_report.csv', Path(out_dir)/'best_strategies_top3.csv', Path(out_dir)/'auto_report.html']
        try:
            send_telegram_message(text, files, token, chat_id)
            logger.info("Telegram notification sent.")
        except Exception as exc:
            logger.warning(f"Failed to send Telegram notification: {exc}")


if __name__ == '__main__':
    main()