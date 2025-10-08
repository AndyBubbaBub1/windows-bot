from __future__ import annotations

import logging
import os
from pathlib import Path

from moex_bot.core.broker import Trader
from moex_bot.core.config import load_config
from moex_bot.core.portfolio_manager import PortfolioManager  # type: ignore
from moex_bot.core.risk import RiskManager
from moex_bot.core.telegram_bot import TelegramBot


def _send_startup_notification() -> None:
    """Send a Telegram notification that the bot has started."""
    try:
        from telegram import Bot
    except Exception:
        return
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if token and chat_id:
        try:
            Bot(token).send_message(chat_id=chat_id, text="✅ Бот запущен")
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Не удалось отправить тестовое сообщение в Telegram: %s", exc
            )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    _send_startup_notification()

    cfg = load_config()
    tinkoff_cfg = cfg.get("tinkoff", {}) or {}
    trade_mode = cfg.get("trade_mode") or "sandbox"
    trader = Trader(
        token=tinkoff_cfg.get("token"),
        account_id=tinkoff_cfg.get("account_id"),
        sandbox=tinkoff_cfg.get("sandbox", True),
        trade_mode=trade_mode,
    )

    initial_capital = cfg.get("capital") or cfg.get("start_capital") or 1_000_000
    try:
        initial_capital_float = float(initial_capital)
    except Exception:
        initial_capital_float = 1_000_000.0
    risk_cfg = cfg.get("risk") or {}
    try:
        risk_manager = RiskManager(initial_capital=initial_capital_float, **risk_cfg)
    except TypeError:
        risk_manager = RiskManager(initial_capital=initial_capital_float)

    try:
        portfolio_manager = PortfolioManager(target_allocations={})  # type: ignore[call-arg]
    except Exception:
        portfolio_manager = None

    telegram_cfg = cfg.get("telegram", {}) or {}
    token = telegram_cfg.get("token")
    allowed_users = telegram_cfg.get("allowed_users", []) or []
    equity_file = cfg.get("equity_file")
    if not equity_file:
        res_dir = cfg.get("results_path") or cfg.get("results_dir") or "results"
        equity_file = str((Path(res_dir) / "portfolio_equity.txt").resolve())

    bot = TelegramBot(
        token,
        allowed_users,
        trader,
        risk_manager,
        portfolio_manager,
        equity_file=equity_file,
    )
    bot.run()


if __name__ == "__main__":
    main()
