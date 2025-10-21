"""Высокоуровневый торговый движок.

Модуль ``engine`` инкапсулирует общую логику, которая ранее была
разбросана между ``run_live_cycle`` и ``run_backtests``.  Теперь вся
подготовка провайдера данных, стратегий, риск‑менеджера и брокера
выполняется внутри одного класса :class:`Engine`.  Это позволяет
использовать единый код как для живой торговли, так и для офлайн
бэктестов, а также легче строить дополнительные интерфейсы
управления.

Класс поддерживает асинхронный живой цикл.  Потоковые котировки
передаются через очередь ``asyncio.Queue``; если стриминг недоступен,
движок переходит в режим периодического опроса CSV/REST источников.
Для офлайн‑режима предусмотрен метод :meth:`run_backtests`, который
делегирует расчёты существующему модулю ``core.backtester``.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Optional, Callable, Dict

import pandas as pd

from .backtester import load_strategies_from_config, run_backtests as _run_backtests
from .config import load_config
from .data_provider import DataProvider
from .portfolio_manager import PortfolioManager
from .risk import RiskManager, RiskJournal
from .tinkoff_stream_provider import TinkoffStreamProvider
from .broker import Trader

logger = logging.getLogger(__name__)


def _to_bool(value: object, default: bool = False) -> bool:
    """Корректно приводим произвольное значение к булеву типу."""

    if value is None:
        return default
    if isinstance(value, bool):
        return value
    try:
        if isinstance(value, (int, float)):
            return bool(value)
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
    except Exception:
        return default


@dataclass
class EngineState:
    """Внутреннее состояние движка."""

    running: bool = False
    trade_mode: str = "sandbox"
    last_prices: dict[str, float] = field(default_factory=dict)
    stream_started: bool = False
    bot_started: bool = False
    disabled_strategies: set[str] = field(default_factory=set)


class Engine:
    """Единый движок для живой и офлайн торговли."""

    def __init__(
        self,
        cfg: dict[str, Any],
        *,
        data_provider: DataProvider | None = None,
        trader: Trader | None = None,
        risk_manager: RiskManager | None = None,
        portfolio_manager: PortfolioManager | None = None,
        queue_max_size: int = 1000,
    ) -> None:
        self.cfg = cfg
        self.state = EngineState()
        self._queue: asyncio.Queue[tuple[str, float]] = asyncio.Queue(maxsize=queue_max_size)

        self.data_provider = data_provider or self._create_data_provider(cfg)
        self.strategies = load_strategies_from_config(cfg)
        self.trader = trader or self._create_trader(cfg)
        self.risk_manager = risk_manager or self._create_risk_manager(cfg)
        self.portfolio_manager = portfolio_manager or self._create_portfolio_manager(cfg)
        self.journal = RiskJournal.from_config(cfg)
        self.risk_manager.attach_journal(self.journal)
        self.risk_manager.set_notifier(self._notify_risk)
        self.risk_manager.set_force_exit_callback(self._force_exit_position)

        initial_mode = cfg.get("trade_mode") or "sandbox"
        self.state.trade_mode = str(initial_mode)

        self._stream_thread: Optional[threading.Thread] = None
        self._stream_lock = threading.Lock()

    @classmethod
    def from_config(cls, cfg: dict[str, Any] | None = None) -> "Engine":
        if cfg is None:
            cfg = load_config()
        return cls(cfg)

    # ------------------------------------------------------------------
    # Управление стратегиями
    # ------------------------------------------------------------------
    def list_strategies(self) -> list[str]:
        return sorted(self.strategies.keys())

    def is_strategy_enabled(self, name: str) -> bool:
        return name not in self.state.disabled_strategies

    def set_strategy_enabled(self, name: str, enabled: bool) -> None:
        if enabled:
            self.state.disabled_strategies.discard(name)
        else:
            self.state.disabled_strategies.add(name)

    def toggle_strategy(self, name: str) -> bool:
        enabled = not self.is_strategy_enabled(name)
        self.set_strategy_enabled(name, enabled)
        return enabled

    def _create_data_provider(self, cfg: dict[str, Any]) -> DataProvider:
        data_dir = cfg.get("data_path", "data")
        tinkoff_cfg = cfg.get("tinkoff", {}) or {}
        token = tinkoff_cfg.get("token")
        sandbox = _to_bool(tinkoff_cfg.get("sandbox"), default=True)
        if token:
            try:
                provider = TinkoffStreamProvider(
                    token=token,
                    account_id=tinkoff_cfg.get("account_id"),
                    sandbox=sandbox,
                    data_dir=data_dir,
                )
            except Exception as exc:  # pragma: no cover - защитный код
                logger.warning("Не удалось инициализировать потоковый провайдер: %s", exc)
                provider = DataProvider(data_dir)
        else:
            provider = DataProvider(data_dir)
        return provider

    def _create_trader(self, cfg: dict[str, Any]) -> Trader:
        tinkoff_cfg = cfg.get("tinkoff", {}) or {}
        telegram_cfg = cfg.get("telegram", {}) or {}
        return Trader(
            token=tinkoff_cfg.get("token"),
            account_id=tinkoff_cfg.get("account_id"),
            sandbox=_to_bool(tinkoff_cfg.get("sandbox"), default=True),
            trade_mode=self.state.trade_mode,
            telegram_token=telegram_cfg.get("token"),
            telegram_chat_id=telegram_cfg.get("chat_id"),
        )

    def _create_risk_manager(self, cfg: dict[str, Any]) -> RiskManager:
        capital = cfg.get("capital") or cfg.get("start_capital") or 1_000_000
        try:
            capital = float(capital)
        except Exception:
            capital = 1_000_000.0
        risk_cfg = (cfg.get("risk") or {}).copy()
        instrument_limits_cfg = risk_cfg.pop("instrument_limits", {}) or {}
        asset_class_limits_cfg = risk_cfg.pop("asset_class_limits", {}) or {}
        instrument_classes_cfg = risk_cfg.pop("instrument_classes", {}) or {}
        risk_cfg.pop("journal", None)
        monitor_interval = risk_cfg.get("monitor_interval")
        rm = RiskManager(initial_capital=capital, **risk_cfg)
        rm.configure_instrument_limits(instrument_limits_cfg)
        rm.configure_asset_class_limits(asset_class_limits_cfg)
        rm.set_instrument_classes(instrument_classes_cfg)
        if monitor_interval is not None:
            try:
                rm.monitor_interval = float(monitor_interval)
                rm.stop_monitoring()
                if rm.monitor_interval > 0:
                    rm.start_monitoring()
            except Exception:
                pass
        return rm

    def _create_portfolio_manager(self, cfg: dict[str, Any]) -> PortfolioManager | None:
        portfolio_cfg = cfg.get("portfolio", {}) or {}
        target_allocations = portfolio_cfg.get("target_allocations", {}) or {}
        if not target_allocations:
            return None
        try:
            return PortfolioManager(
                target_allocations=target_allocations, risk_manager=self.risk_manager
            )
        except Exception as exc:
            logger.warning("Не удалось создать менеджер портфеля: %s", exc)
            return None

    def start(self) -> None:
        self.state.running = True
        logger.info("🚀 Торговый движок запущен в режиме %s", self.state.trade_mode)

    def stop(self) -> None:
        self.state.running = False
        logger.info("⏸ Торговый движок остановлен")

    def toggle_mode(self) -> str:
        self.state.trade_mode = "real" if self.state.trade_mode == "sandbox" else "sandbox"
        self.trader.trade_mode = self.state.trade_mode
        logger.info("🔁 Переключение режима на %s", self.state.trade_mode)
        return self.state.trade_mode

    def _notify_risk(self, message: str) -> None:
        telegram_cfg = self.cfg.get("telegram", {}) or {}
        token = telegram_cfg.get("token")
        chat_id = telegram_cfg.get("chat_id")
        if token and chat_id:
            try:
                from ..reporting.report_builder import send_telegram_message

                send_telegram_message(message, [], token, chat_id)
            except Exception as exc:
                logger.debug("Risk notification failed: %s", exc)

    def _force_exit_position(self, symbol: str) -> None:
        symbol = symbol.upper()
        pos = self.risk_manager.positions.get(symbol)
        if not pos:
            return
        qty = int(pos.get("quantity", 0))
        if qty > 0:
            self.trader.sell(figi=symbol, lots=qty)
        elif qty < 0:
            self.trader.buy(figi=symbol, lots=abs(qty))
        self.risk_manager.exit_position(symbol)

    def _ensure_streaming(self) -> None:
        if not isinstance(self.data_provider, TinkoffStreamProvider):
            return
        if self.state.stream_started:
            return
        with self._stream_lock:
            if self.state.stream_started:
                return
            symbols: set[str] = set()
            for name, spec in (self.cfg.get("strategies") or {}).items():
                if name not in self.strategies:
                    continue
                for sym in spec.get("symbols") or []:
                    symbols.add(str(sym).upper())
            if not symbols:
                return

            def _on_price(symbol: str, price: float) -> None:
                try:
                    symbol = str(symbol).upper()
                    self.state.last_prices[symbol] = price
                    if not self._queue.full():
                        self._queue.put_nowait((symbol, float(price)))
                except Exception:
                    return

            self._stream_thread = threading.Thread(
                target=self.data_provider.subscribe_prices,
                args=(list(symbols), _on_price),
                kwargs={"interval": 1.0},
                daemon=True,
            )
            self._stream_thread.start()
            self.state.stream_started = True

    async def _wait_for_price(self, symbol: str, *, timeout: float = 2.0) -> Optional[float]:
        symbol = symbol.upper()
        if symbol in self.state.last_prices:
            return self.state.last_prices[symbol]
        if not isinstance(self.data_provider, TinkoffStreamProvider):
            price = self.data_provider.latest_price(symbol)
            if price is not None:
                self.state.last_prices[symbol] = price
            return price
        try:
            while True:
                sym, price = await asyncio.wait_for(self._queue.get(), timeout=timeout)
                self.state.last_prices[sym] = price
                if sym == symbol:
                    return price
        except asyncio.TimeoutError:
            return self.data_provider.latest_price(symbol)

    async def run_live_once(self) -> None:
        if not self.state.running:
            logger.info("⏸ Цикл пропущен: движок остановлен")
            return

        if not self.strategies:
            logger.warning("Стратегии не загружены — нечего исполнять")
            return

        self._ensure_streaming()
        telegram_cfg = self.cfg.get("telegram", {}) or {}
        token = telegram_cfg.get("token")
        chat_id = telegram_cfg.get("chat_id")

        for strat_name, strat_callable in self.strategies.items():
            if strat_name in self.state.disabled_strategies:
                logger.debug("Стратегия %s отключена", strat_name)
                continue
            spec = (self.cfg.get("strategies") or {}).get(strat_name, {}) or {}
            symbols = spec.get("symbols", []) or []
            if not symbols:
                continue
            for symbol in symbols:
                symbol_uc = str(symbol).upper()
                history = self.data_provider.load_history(symbol_uc, interval="hour", days=90)
                if history.empty:
                    continue
                price = await self._wait_for_price(symbol_uc)
                if price is None:
                    continue
                self.risk_manager.update_position_price(symbol_uc, price)
                if self.risk_manager.check_exit(symbol_uc, price):
                    lots_to_close = int(
                        self.risk_manager.positions.get(symbol_uc, {}).get("quantity", 0)
                    )
                    if lots_to_close > 0:
                        self.trader.sell(figi=symbol_uc, lots=lots_to_close)
                    elif lots_to_close < 0:
                        self.trader.buy(figi=symbol_uc, lots=abs(lots_to_close))
                    self.risk_manager.exit_position(symbol_uc)
                    if token and chat_id:
                        try:
                            from ..reporting.report_builder import send_telegram_message

                            send_telegram_message(
                                f"Закрытие позиции {symbol_uc} по сигналу риск‑менеджера",
                                [],
                                token,
                                chat_id,
                            )
                        except Exception:
                            pass
                    continue

                try:
                    signals: pd.Series = strat_callable(history)
                except Exception as exc:
                    logger.error("Ошибка расчёта сигналов %s/%s: %s", strat_name, symbol_uc, exc)
                    continue
                if signals.empty:
                    continue
                last_signal = float(signals.iloc[-1])
                allowed_lots = self.risk_manager.allowed_position_size(price, symbol=symbol_uc)

                if last_signal > 0:
                    await self._ensure_long(symbol_uc, price, allowed_lots, strat_name)
                elif last_signal < 0:
                    await self._ensure_short(symbol_uc, price, allowed_lots, strat_name)

        self._mark_to_market()

    async def _ensure_long(
        self, symbol: str, price: float, allowed_lots: int, strat_name: str
    ) -> None:
        if symbol not in self.risk_manager.positions:
            if allowed_lots <= 0:
                return
            self.trader.buy(figi=symbol, lots=allowed_lots)
            self.risk_manager.register_entry(symbol, price, allowed_lots)
            self._update_portfolio(symbol, allowed_lots, price, strat_name)
            return
        qty = int(self.risk_manager.positions[symbol].get("quantity", 0))
        if qty < 0:
            self.trader.buy(figi=symbol, lots=abs(qty))
            self.risk_manager.exit_position(symbol)
            self._remove_portfolio(symbol)
            if allowed_lots > 0:
                self.trader.buy(figi=symbol, lots=allowed_lots)
                self.risk_manager.register_entry(symbol, price, allowed_lots)
                self._update_portfolio(symbol, allowed_lots, price, strat_name)

    async def _ensure_short(
        self, symbol: str, price: float, allowed_lots: int, strat_name: str
    ) -> None:
        if not self.risk_manager.allow_short:
            return
        qty = int(self.risk_manager.positions.get(symbol, {}).get("quantity", 0))
        if qty > 0:
            self.trader.sell(figi=symbol, lots=qty)
            self.risk_manager.exit_position(symbol)
            self._remove_portfolio(symbol)
        if allowed_lots > 0:
            self.trader.sell(figi=symbol, lots=allowed_lots)
            self.risk_manager.register_entry(symbol, price, -allowed_lots)
            self._update_portfolio(symbol, -allowed_lots, price, strat_name)

    def _update_portfolio(self, symbol: str, quantity: int, price: float, strategy: str) -> None:
        if not self.portfolio_manager:
            return
        try:
            self.portfolio_manager.update_position(symbol, quantity, price, strategy)
        except Exception:
            return

    def _remove_portfolio(self, symbol: str) -> None:
        if not self.portfolio_manager:
            return
        try:
            self.portfolio_manager.remove_position(symbol)
        except Exception:
            return

    def _mark_to_market(self) -> None:
        equity = self.risk_manager.initial_capital
        for symbol, pos in self.risk_manager.positions.items():
            qty = float(pos.get("quantity", 0.0))
            price = float(pos.get("last_price", pos.get("entry_price", 0.0)))
            equity += qty * price
        self.risk_manager.update_equity(equity)
        self.journal.record_equity(equity)

    def run_backtests(self, **kwargs: Any):
        data_glob = kwargs.pop("data_glob", None)
        if data_glob is None:
            data_glob_cfg = (self.cfg.get("data") or {}).get("glob", "data/*_hour_90d.csv")
            from pathlib import Path

            project_root = Path(__file__).resolve().parents[1]
            data_glob = str(project_root / data_glob_cfg)
        start_capital = kwargs.pop("start_capital", None)
        if start_capital is None:
            start_capital = self.risk_manager.initial_capital
        leverage = kwargs.pop("leverage", None)
        if leverage is None:
            leverage = float((self.cfg.get("risk") or {}).get("max_leverage", 1.0))
        borrow_rate = kwargs.pop("borrow_rate", None)
        if borrow_rate is None:
            borrow_rate = float((self.cfg.get("risk") or {}).get("borrow_rate_pct", 0.0)) / 100.0
        short_rate = kwargs.pop("short_rate", None)
        if short_rate is None:
            short_cfg = (self.cfg.get("risk") or {}).get("short_borrow_rate_pct")
            short_rate = float(short_cfg) / 100.0 if short_cfg is not None else None
        periods_per_year = kwargs.pop("periods_per_year", None)
        if periods_per_year is None:
            periods_per_year = int(
                (self.cfg.get("risk") or {}).get("financing_periods_per_year", 252)
            )
        return _run_backtests(
            data_glob,
            self.strategies,
            start_capital,
            leverage=leverage,
            borrow_rate=borrow_rate,
            short_rate=short_rate,
            periods_per_year=periods_per_year,
        )


__all__ = ["Engine"]
