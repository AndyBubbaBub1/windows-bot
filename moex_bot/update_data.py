"""Автоматическое обновление исторических данных."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Set

import pandas as pd

from moex_bot.core.config import load_config
from moex_bot.core.tinkoff_api_provider import TinkoffAPIProvider
from moex_bot.core.data_provider import DataProvider

logger = logging.getLogger(__name__)


def _collect_symbols(cfg: dict) -> Set[str]:
    symbols: Set[str] = set()
    for strat_cfg in (cfg.get("strategies") or {}).values():
        for symbol in (strat_cfg or {}).get("symbols", []) or []:
            symbols.add(str(symbol).upper())
    for extra in (cfg.get("data", {}) or {}).get("extra_symbols", []) or []:
        symbols.add(str(extra).upper())
    return symbols


def _resolve_provider(cfg: dict) -> DataProvider:
    tinkoff_cfg = cfg.get("tinkoff", {}) or {}
    provider = TinkoffAPIProvider(
        token=tinkoff_cfg.get("token"),
        account_id=tinkoff_cfg.get("account_id"),
        sandbox=bool(tinkoff_cfg.get("sandbox", True)),
        data_dir=cfg.get("data_path", "data"),
    )
    if provider.enabled:
        logger.info("Используем поток tinkoff.invest для обновления данных")
        return provider
    logger.info("Падаем в файловый провайдер, так как API недоступно")
    return DataProvider(cfg.get("data_path", "data"))


def update_symbol(
    provider: DataProvider, symbol: str, *, interval: str, days: int, data_dir: Path
) -> None:
    df = provider.load_history(symbol, interval=interval, days=days)
    if df is None or getattr(df, "empty", False):
        logger.warning("Нет данных для %s", symbol)
        return
    path = data_dir / f"{symbol}_{interval}_{days}d.csv"
    data_dir.mkdir(parents=True, exist_ok=True)
    if isinstance(df, pd.DataFrame):
        df.to_csv(path, index=False)
    else:
        pd.DataFrame(df).to_csv(path, index=False)
    logger.info("Обновлены данные %s → %s", symbol, path)


def update_all(symbols: Iterable[str] | None = None) -> None:
    cfg = load_config()
    data_dir = Path(cfg.get("data_path", "data"))
    provider = _resolve_provider(cfg)
    symbols_to_update = set(symbols or _collect_symbols(cfg))
    if not symbols_to_update:
        logger.warning("Список тикеров пуст — нечего обновлять")
        return
    interval = (cfg.get("data", {}) or {}).get("interval", "hour")
    days = int((cfg.get("data", {}) or {}).get("history_days", 90))
    for symbol in sorted(symbols_to_update):
        update_symbol(provider, symbol, interval=interval, days=days, data_dir=data_dir)


def run_scheduled_update() -> None:
    logging.basicConfig(level=logging.INFO)
    update_all()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    update_all()
