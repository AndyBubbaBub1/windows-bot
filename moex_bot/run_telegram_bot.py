"""Entry point to run the Telegram bot for interactive control.

This script sets up a :class:`~moex_bot.core.telegram_bot.TelegramBot`
using the configuration defined in ``config.yaml`` and starts the
polling loop.  The Telegram bot allows authorised users to query the
current portfolio status and to issue simple trading commands such as
``/buy`` and ``/sell``.  It must be run separately from the live
trading loop and scheduler; it will not execute any scheduled jobs.

Example usage::

    python run_telegram_bot.py

Ensure that the environment variables ``TELEGRAM_TOKEN`` and
``TELEGRAM_CHAT_ID`` are set, and that ``allowed_users`` in the
configuration includes the numeric Telegram user IDs permitted to
interact with the bot.
"""

from __future__ import annotations

import logging
from pathlib import Path

# Note: The moex_bot package must be installed (e.g. via ``pip install -e .``)
# for these imports to resolve without modifying sys.path.  See ``setup.py``
# and ``pyproject.toml`` for packaging details.
from moex_bot.core.config import load_config
from moex_bot.core.broker import Trader
from moex_bot.core.risk import RiskManager
from moex_bot.core.portfolio_manager import PortfolioManager  # type: ignore
from moex_bot.core.telegram_bot import TelegramBot


def main
    # Отправляем тестовое сообщение при старте
    try:
        from telegram import Bot
        import os
        token = os.getenv('TELEGRAM_TOKEN')
        chat_id = os.getenv('TELEGRAM_CHAT_ID')
        if token and chat_id:
            Bot(token).send_message(chat_id=chat_id, text='✅ Бот запущен')
    except Exception as e:
        print('Не удалось отправить тестовое сообщение в Telegram:', e)

    def main() -> None:
    logging.basicConfig(level=logging.INFO)
    cfg = load_config()
    # Setup trader
    tinkoff_cfg = cfg.get('tinkoff', {}) or {}
    trade_mode = cfg.get('trade_mode') or 'sandbox'
    trader = Trader(
        token=tinkoff_cfg.get('token'),
        account_id=tinkoff_cfg.get('account_id'),
        sandbox=tinkoff_cfg.get('sandbox', True),
        trade_mode=trade_mode,
    )
    # Setup risk manager
    initial_capital = cfg.get('capital') or cfg.get('start_capital') or 1_000_000
    try:
        initial_capital = float(initial_capital)
    except Exception:
        initial_capital = 1_000_000.0
    risk_cfg = cfg.get('risk') or {}
    try:
        risk_manager = RiskManager(initial_capital=initial_capital, **risk_cfg)
    except TypeError:
        risk_manager = RiskManager(initial_capital=initial_capital)
    # Portfolio manager is optional; pass None if not implemented
    try:
        portfolio_manager = PortfolioManager(target_allocations={})  # type: ignore[call-arg]
    except Exception:
        portfolio_manager = None
    # Setup Telegram bot
    telegram_cfg = cfg.get('telegram', {}) or {}
    token = telegram_cfg.get('token')
    allowed_users = telegram_cfg.get('allowed_users', []) or []
    # Determine equity file path: mirror logic from live loop for consistency
    equity_file = cfg.get('equity_file')
    if not equity_file:
        res_dir = cfg.get('results_dir') or cfg.get('results_path') or 'results'
        equity_file = str((Path(res_dir) / 'portfolio_equity.txt').resolve())
    bot = TelegramBot(token, allowed_users, trader, risk_manager, portfolio_manager, equity_file=equity_file)
    # Run polling loop
    bot.run()


if __name__ == '__main__':
    main()
