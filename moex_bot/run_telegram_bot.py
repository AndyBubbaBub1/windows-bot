"""Entry point for running the Telegram control bot."""

from __future__ import annotations

import os
from pathlib import Path

import structlog

from moex_bot.core.alerts import AlertDispatcher
from moex_bot.core.broker import Trader
from moex_bot.core.config import load_config
from moex_bot.core.logging_config import configure_logging
from moex_bot.core.portfolio_manager import PortfolioManager
from moex_bot.core.risk import RiskManager
from moex_bot.core.telegram_bot import TelegramBot


def main() -> None:
    configure_logging()
    logger = structlog.get_logger(__name__)

    cfg = load_config()
    telegram_cfg = cfg.get('telegram', {}) or {}
    token = telegram_cfg.get('token') or os.getenv('TELEGRAM_TOKEN')
    allowed_users = telegram_cfg.get('allowed_users', []) or []
    if not token:
        raise RuntimeError('TELEGRAM_TOKEN must be provided via config or environment')

    tinkoff_cfg = cfg.get('tinkoff', {}) or {}
    trade_mode = (cfg.get('trade_mode') or 'sandbox').lower()
    trader = Trader(
        token=tinkoff_cfg.get('token'),
        account_id=tinkoff_cfg.get('account_id'),
        sandbox=bool(tinkoff_cfg.get('sandbox', True)),
        trade_mode=trade_mode,
    )

    initial_capital = cfg.get('capital') or cfg.get('start_capital') or 1_000_000
    try:
        initial_capital_float = float(initial_capital)
    except Exception:
        initial_capital_float = 1_000_000.0
    risk_cfg = cfg.get('risk') or {}
    alerts_cfg = cfg.get('alerts') if isinstance(cfg, dict) else {}
    dispatcher = AlertDispatcher.from_config(alerts_cfg if isinstance(alerts_cfg, dict) else None)
    try:
        risk_manager = RiskManager(initial_capital=initial_capital_float, alert_dispatcher=dispatcher, **risk_cfg)
    except TypeError:
        risk_manager = RiskManager(initial_capital=initial_capital_float, alert_dispatcher=dispatcher)

    try:
        portfolio_manager = PortfolioManager(target_allocations={})
    except Exception:
        portfolio_manager = None

    results_dir = cfg.get('results_path') or cfg.get('results_dir') or 'results'
    equity_file = cfg.get('equity_file') or str(Path(results_dir) / 'portfolio_equity.txt')

    bot = TelegramBot(
        token=token,
        allowed_users=allowed_users,
        trader=trader,
        risk_manager=risk_manager,
        portfolio_manager=portfolio_manager,
        equity_file=equity_file,
    )
    logger.info('starting telegram bot polling')
    bot.run()


if __name__ == '__main__':
    main()
