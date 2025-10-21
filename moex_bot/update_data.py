"""Автоматическое обновление исторических данных."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Set, Tuple, List, Dict

import pandas as pd

from moex_bot.core.config import load_config
from moex_bot.core.tinkoff_api_provider import TinkoffAPIProvider
from moex_bot.core.data_provider import DataProvider
from moex_bot.universe_ru import (
    RU_EQUITIES_TIER1_2,
    RU_EQUITIES_TIER3,
    RU_BONDS,
    RU_ETF,
    RU_FUTURES,
    RU_FX,
    get_universe,
)

logger = logging.getLogger(__name__)


def _collect_universe(cfg: dict) -> Tuple[Set[str], List[Dict[str, str]]]:
    symbols: Set[str] = set()
    universe_records: List[Dict[str, str]] = []
    for strat_cfg in (cfg.get("strategies") or {}).values():
        for symbol in (strat_cfg or {}).get("symbols", []) or []:
            symbols.add(str(symbol).upper())
    for extra in (cfg.get("data", {}) or {}).get("extra_symbols", []) or []:
        symbols.add(str(extra).upper())

    data_cfg = cfg.get("data") or {}
    universe_cfg = (data_cfg.get("universe") or {}) if isinstance(data_cfg, dict) else {}
    if universe_cfg:
        enabled = universe_cfg.get("enabled")
        if enabled is None:
            enabled = True
        if enabled:
            classes = universe_cfg.get("classes") or []
            tiers = {str(t).lower() for t in universe_cfg.get("tiers", [])}
            exclude = {str(t).upper() for t in universe_cfg.get("exclude", [])}
            include_figi = bool(universe_cfg.get("include_figi", True))
            records = get_universe(classes=classes) if classes else get_universe()
            tier_map = {
                "tier1_2": RU_EQUITIES_TIER1_2,
                "tier3": RU_EQUITIES_TIER3,
                "bonds": RU_BONDS,
                "etf": RU_ETF,
                "futures": RU_FUTURES,
                "fx": RU_FX,
            }
            if tiers:
                tier_records: List[Dict[str, str]] = []
                for tier in tiers:
                    tier_records.extend(tier_map.get(tier, []))
                if tier_records:
                    records = tier_records
            filtered: List[Dict[str, str]] = []
            for rec in records:
                ticker = str(rec.get("ticker", "")).upper()
                if not ticker or ticker in exclude:
                    continue
                record = {"ticker": ticker, "class": rec.get("class", "").lower()}
                if include_figi:
                    record["figi"] = rec.get("figi", "")
                if rec.get("board"):
                    record["board"] = rec.get("board")
                filtered.append(record)
                symbols.add(ticker)
            universe_records = filtered
    return symbols, universe_records


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
    symbols_to_update, universe_records = _collect_universe(cfg)
    if symbols:
        symbols_to_update |= {str(sym).upper() for sym in symbols}
    if not symbols_to_update:
        logger.warning("Список тикеров пуст — нечего обновлять")
        return
    interval = (cfg.get("data", {}) or {}).get("interval", "hour")
    days = int((cfg.get("data", {}) or {}).get("history_days", 90))
    for symbol in sorted(symbols_to_update):
        update_symbol(provider, symbol, interval=interval, days=days, data_dir=data_dir)

    universe_cfg = (cfg.get("data", {}) or {}).get("universe", {}) or {}
    if universe_records and universe_cfg.get("export", True):
        export_path_cfg = universe_cfg.get("export_path")
        if export_path_cfg:
            export_path = Path(export_path_cfg)
            if not export_path.is_absolute():
                export_path = data_dir / export_path
        else:
            export_path = data_dir / "universe.csv"
        try:
            pd.DataFrame(universe_records).to_csv(export_path, index=False)
            logger.info("Сохранили перечень инструментов в %s", export_path)
        except Exception as exc:
            logger.warning("Не удалось записать universe.csv: %s", exc)


def run_scheduled_update() -> None:
    logging.basicConfig(level=logging.INFO)
    update_all()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    update_all()
