"""Entry point to run the interactive Telegram bot."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict

from moex_bot.core.broker import Trader
from moex_bot.core.config import load_config
from moex_bot.core.risk import RiskManager
from moex_bot.core.telegram_bot import TelegramBot

try:  # Portfolio manager is optional in some installations
    from moex_bot.core.portfolio_manager import PortfolioManager  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    PortfolioManager = None  # type: ignore


logger = logging.getLogger(__name__)


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        val = value.strip().lower()
        if val in {"1", "true", "yes", "y"}:
            return True
        if val in {"0", "false", "no", "n"}:
            return False
    return default


def _build_risk_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    trading_cfg = cfg.get("trading", {}) or {}
    risk_cfg = dict(cfg.get("risk") or {})
    if "allow_short" not in risk_cfg and "allow_short" in trading_cfg:
        risk_cfg["allow_short"] = _to_bool(trading_cfg.get("allow_short"), default=True)
    if "max_leverage" not in risk_cfg and "leverage" in trading_cfg:
        try:
            lev = float(trading_cfg.get("leverage", 1.0))
            risk_cfg.setdefault("max_leverage", lev)
            risk_cfg.setdefault("max_portfolio_exposure_pct", lev)
        except Exception:
            pass
    return risk_cfg


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    cfg = load_config()

    telegram_cfg = cfg.get("telegram", {}) or {}
    token = telegram_cfg.get("token")
    chat_id = telegram_cfg.get("chat_id")
    if token and chat_id:
        try:
            from telegram import Bot  # type: ignore

            Bot(token).send_message(chat_id=chat_id, text="✅ Бот запущен")
        except Exception as exc:  # pragma: no cover - optional dependency
            logger.debug("Failed to send startup notification: %s", exc)

    tinkoff_cfg = cfg.get("tinkoff", {}) or {}
    trade_mode = (cfg.get("trade_mode") or "sandbox").lower()
    trader = Trader(
        token=tinkoff_cfg.get("token"),
        account_id=tinkoff_cfg.get("account_id"),
        sandbox=_to_bool(tinkoff_cfg.get("sandbox"), default=True),
        trade_mode=trade_mode,
        sandbox_token=tinkoff_cfg.get("sandbox_token"),
        sandbox_account_id=tinkoff_cfg.get("account_id_sandbox"),
        telegram_token=token,
        telegram_chat_id=chat_id,
    )

    initial_capital = cfg.get("capital") or cfg.get("start_capital") or 1_000_000
    try:
        initial_capital_float = float(initial_capital)
    except Exception:
        initial_capital_float = 1_000_000.0

    risk_cfg = _build_risk_config(cfg)
    try:
        risk_manager = RiskManager(initial_capital=initial_capital_float, **risk_cfg)
    except TypeError:
        risk_manager = RiskManager(initial_capital=initial_capital_float)

    portfolio_manager = None
    if PortfolioManager is not None:
        try:
            target_allocations = (cfg.get("portfolio", {}) or {}).get("target_allocations", {}) or {}
            if target_allocations:
                portfolio_manager = PortfolioManager(target_allocations=target_allocations, risk_manager=risk_manager)  # type: ignore[arg-type]
        except Exception:
            portfolio_manager = None

    allowed_users = telegram_cfg.get("allowed_users", []) or []
    equity_file = cfg.get("equity_file")
    if not equity_file:
        res_dir = cfg.get("results_path") or cfg.get("results_dir") or "results"
        equity_file = str((Path(res_dir) / "portfolio_equity.txt").resolve())

    bot = TelegramBot(token, allowed_users, trader, risk_manager, portfolio_manager, equity_file=equity_file)
    bot.run()


if __name__ == "__main__":
    main()
