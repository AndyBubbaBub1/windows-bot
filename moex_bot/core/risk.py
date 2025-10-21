"""Расширенный модуль риск-менеджмента."""

from __future__ import annotations

import csv
import datetime as dt
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class InstrumentLimit:
    """Индивидуальные ограничения по инструменту."""

    symbol: str
    max_position_pct: Optional[float] = None
    max_lots: Optional[int] = None
    max_leverage: Optional[float] = None


@dataclass
class AssetClassLimit:
    """Ограничения по классу активов."""

    name: str
    max_leverage: Optional[float] = None
    max_exposure_pct: Optional[float] = None


class RiskJournal:
    """Журнал событий риск-менеджера."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._records: list[dict[str, object]] = []

    @classmethod
    def from_config(cls, cfg: Dict[str, object] | None) -> "RiskJournal":
        risk_cfg = (cfg or {}).get("risk") if cfg else None
        journal_cfg = (risk_cfg or {}).get("journal") if isinstance(risk_cfg, dict) else None
        enabled = True
        if isinstance(journal_cfg, dict):
            enabled = bool(journal_cfg.get("enabled", True))
        return cls(enabled=enabled)

    def record_equity(self, value: float) -> None:
        if not self.enabled:
            return
        self._records.append(
            {
                "timestamp": dt.datetime.utcnow().isoformat(),
                "type": "equity",
                "level": "info",
                "symbol": "portfolio",
                "value": float(value),
                "message": "",
            }
        )

    def record_event(
        self,
        message: str,
        *,
        level: str = "info",
        symbol: Optional[str] = None,
        value: Optional[float] = None,
    ) -> None:
        if not self.enabled:
            return
        self._records.append(
            {
                "timestamp": dt.datetime.utcnow().isoformat(),
                "type": "event",
                "level": level,
                "symbol": symbol or "",
                "value": value,
                "message": message,
            }
        )

    def flush(self, path: Path | str) -> None:
        if not self.enabled or not self._records:
            return
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_exists = path.exists()
        fieldnames = ["timestamp", "type", "level", "symbol", "value", "message"]
        with path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            for row in self._records:
                writer.writerow(row)
        self._records.clear()


@dataclass
class RiskManager:
    """Комплексный контроль рисков портфеля."""

    initial_capital: float
    max_drawdown_pct: float = 0.2
    max_daily_loss_pct: float = 0.1
    max_position_pct: float = 0.2
    per_trade_risk_pct: float = 0.02
    stop_loss_pct: float = 0.05
    take_profit_pct: float = 0.1
    max_positions: int = 5
    allow_short: bool = False
    max_portfolio_exposure_pct: float = 1.0
    max_leverage: float = 1.0
    borrow_rate_pct: float = 0.0
    short_borrow_rate_pct: float | None = None
    financing_periods_per_year: int = 252
    monitor_interval: float = 5.0
    instrument_limits: Dict[str, InstrumentLimit] = field(default_factory=dict)
    instrument_classes: Dict[str, str] = field(default_factory=dict)
    asset_class_limits: Dict[str, AssetClassLimit] = field(default_factory=dict)
    notifier: Optional[Callable[[str], None]] = None
    journal: RiskJournal | None = None
    halt_trading: bool = field(default=False, init=False)
    last_equity_date: dt.date = field(init=False)
    portfolio_equity: float = field(init=False)
    peak_equity: float = field(init=False)
    day_start_equity: float = field(init=False)
    positions: Dict[str, Dict[str, float]] = field(default_factory=dict)
    _monitor_thread: Optional[threading.Thread] = field(default=None, init=False, repr=False)
    _monitor_stop: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _force_exit_callback: Optional[Callable[[str], None]] = field(
        default=None, init=False, repr=False
    )

    def __post_init__(self) -> None:
        self.portfolio_equity = self.initial_capital
        self.peak_equity = self.initial_capital
        self.day_start_equity = self.initial_capital
        self.last_equity_date = dt.date.today()
        if self.journal is None:
            self.journal = RiskJournal()
        if self.monitor_interval > 0:
            self.start_monitoring()

    # ------------------------------------------------------------------
    # Конфигурация
    # ------------------------------------------------------------------
    def configure_instrument_limits(self, cfg: Dict[str, Dict[str, float]]) -> None:
        for symbol, data in (cfg or {}).items():
            symbol_uc = symbol.upper()
            self.instrument_limits[symbol_uc] = InstrumentLimit(
                symbol=symbol_uc,
                max_position_pct=(
                    self._safe_float(data.get("max_position_pct"))
                    if isinstance(data, dict)
                    else None
                ),
                max_lots=self._safe_int(data.get("max_lots")) if isinstance(data, dict) else None,
                max_leverage=(
                    self._safe_float(data.get("max_leverage")) if isinstance(data, dict) else None
                ),
            )

    def configure_asset_class_limits(self, cfg: Dict[str, Dict[str, float]]) -> None:
        for name, data in (cfg or {}).items():
            self.asset_class_limits[name] = AssetClassLimit(
                name=name,
                max_leverage=(
                    self._safe_float(data.get("max_leverage")) if isinstance(data, dict) else None
                ),
                max_exposure_pct=(
                    self._safe_float(data.get("max_exposure_pct"))
                    if isinstance(data, dict)
                    else None
                ),
            )

    def set_instrument_classes(self, mapping: Dict[str, str]) -> None:
        for symbol, cls_name in (mapping or {}).items():
            self.instrument_classes[symbol.upper()] = cls_name

    def set_notifier(self, notifier: Callable[[str], None]) -> None:
        self.notifier = notifier

    def set_force_exit_callback(self, callback: Callable[[str], None]) -> None:
        self._force_exit_callback = callback

    def attach_journal(self, journal: RiskJournal | None) -> None:
        self.journal = journal or self.journal

    # ------------------------------------------------------------------
    # Мониторинг
    # ------------------------------------------------------------------
    def start_monitoring(self) -> None:
        if self._monitor_thread and self._monitor_thread.is_alive():
            return
        self._monitor_stop.clear()
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

    def stop_monitoring(self) -> None:
        self._monitor_stop.set()
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=1.0)

    def _monitor_loop(self) -> None:
        while not self._monitor_stop.is_set():
            try:
                self._check_portfolio_limits()
            except Exception as exc:
                logger.debug("Risk monitor loop error: %s", exc)
            time.sleep(max(self.monitor_interval, 0.5))

    def _check_portfolio_limits(self) -> None:
        for symbol, pos in list(self.positions.items()):
            limit = self.instrument_limits.get(symbol.upper())
            if not limit:
                continue
            price = float(pos.get("last_price", pos.get("entry_price", 0.0)))
            quantity = float(pos.get("quantity", 0.0))
            exposure = abs(quantity) * price
            if limit.max_leverage and exposure > self.portfolio_equity * limit.max_leverage:
                self._handle_violation(
                    symbol, f"Превышен лимит плеча {limit.max_leverage} по {symbol}"
                )
            if limit.max_position_pct and exposure > self.portfolio_equity * limit.max_position_pct:
                self._handle_violation(
                    symbol, f"Превышен лимит доли {limit.max_position_pct:.0%} по {symbol}"
                )
            if limit.max_lots is not None and abs(quantity) > limit.max_lots:
                self._handle_violation(
                    symbol, f"Превышено количество {limit.max_lots} лотов по {symbol}"
                )
        for cls_name, limit in self.asset_class_limits.items():
            exposure = self._asset_class_exposure(cls_name)
            if limit.max_exposure_pct and exposure > self.portfolio_equity * limit.max_exposure_pct:
                self._notify(
                    f"Класс {cls_name}: доля {exposure / max(self.portfolio_equity, 1e-9):.0%} выше лимита"
                )
                self._force_flatten(cls_name)
            if limit.max_leverage and exposure > self.portfolio_equity * limit.max_leverage:
                self._notify(f"Класс {cls_name}: плечо выше {limit.max_leverage}")
                self._force_flatten(cls_name)

    def _asset_class_exposure(self, cls_name: str) -> float:
        total = 0.0
        for symbol, pos in self.positions.items():
            if self.instrument_classes.get(symbol.upper()) != cls_name:
                continue
            qty = abs(float(pos.get("quantity", 0.0)))
            price = float(pos.get("last_price", pos.get("entry_price", 0.0)))
            total += qty * price
        return total

    def _force_flatten(self, cls_name: str) -> None:
        for symbol, pos in list(self.positions.items()):
            if self.instrument_classes.get(symbol.upper()) != cls_name:
                continue
            self._handle_violation(
                symbol, f"Принудительное закрытие из-за лимита класса {cls_name}"
            )

    # ------------------------------------------------------------------
    # Основные методы
    # ------------------------------------------------------------------
    def update_equity(self, new_equity: float) -> None:
        self.portfolio_equity = new_equity
        today = dt.date.today()
        if today != self.last_equity_date:
            self.day_start_equity = new_equity
            self.last_equity_date = today
            self.halt_trading = False
        if new_equity > self.peak_equity:
            self.peak_equity = new_equity
        drawdown = 1 - new_equity / max(self.peak_equity, 1e-9)
        if drawdown >= self.max_drawdown_pct:
            message = (
                f"Максимальная просадка {drawdown:.2%} превышает лимит {self.max_drawdown_pct:.2%}."
            )
            logger.error(message)
            self._notify("📉 " + message)
        daily_loss = (self.day_start_equity - new_equity) / max(self.day_start_equity, 1e-9)
        if daily_loss >= self.max_daily_loss_pct:
            logger.error("Достигнут дневной лимит потерь: %.2f%%", daily_loss * 100)
            self.clear_positions()
            self.halt_trading = True
            self._notify("⚠️ Дневной лимит потерь превышен. Торговля остановлена.")
        if self.journal:
            self.journal.record_equity(new_equity)

    def allowed_position_size(self, price: float, symbol: Optional[str] = None) -> int:
        if self.halt_trading or price <= 0:
            return 0
        risk_amount = self.portfolio_equity * self.per_trade_risk_pct
        stop_amount = price * self.stop_loss_pct
        base_size = risk_amount / max(stop_amount, 1e-9)
        max_size_by_equity = (self.portfolio_equity * self.max_position_pct) / price
        size = min(base_size, max_size_by_equity)
        exposure_cap_pct = self.max_leverage if self.max_leverage > 0 else 1.0
        if self.max_portfolio_exposure_pct not in (0.0, 1.0):
            exposure_cap_pct = min(exposure_cap_pct, self.max_portfolio_exposure_pct)
        total_value = self._current_gross_exposure()
        allowed_portfolio_value = max(0.0, (self.portfolio_equity * exposure_cap_pct) - total_value)
        max_by_portfolio = allowed_portfolio_value / max(price, 1e-9)
        size = min(size, max_by_portfolio)
        if symbol:
            limit = self.instrument_limits.get(symbol.upper())
            if limit:
                if limit.max_position_pct:
                    size = min(size, (self.portfolio_equity * limit.max_position_pct) / price)
                if limit.max_lots is not None:
                    size = min(size, float(limit.max_lots))
        return int(max(0, size))

    def _current_gross_exposure(self) -> float:
        total_value = 0.0
        for pos in self.positions.values():
            try:
                price = float(pos.get("last_price", pos.get("entry_price", 0.0)))
                total_value += abs(float(pos.get("quantity", 0.0))) * price
            except Exception:
                continue
        return total_value

    def portfolio_market_value(self) -> float:
        total_value = 0.0
        for pos in self.positions.values():
            try:
                price = float(pos.get("last_price", pos.get("entry_price", 0.0)))
                total_value += float(pos.get("quantity", 0.0)) * price
            except Exception:
                continue
        return total_value

    def update_position_price(self, symbol: str, price: float) -> None:
        pos = self.positions.get(symbol)
        if not pos:
            return
        try:
            pos["last_price"] = float(price)
        except (TypeError, ValueError):
            logger.debug("Некорректная цена %r для %s", price, symbol)

    def register_entry(self, symbol: str, price: float, quantity: float) -> None:
        if self.halt_trading:
            logger.warning("Торговля остановлена. Новые позиции запрещены.")
            return
        if len(self.positions) >= self.max_positions:
            logger.warning("Достигнуто максимальное число позиций")
            return
        if quantity == 0:
            return
        is_short = quantity < 0
        if is_short and not self.allow_short:
            logger.warning("Шорты запрещены. Позиция %s пропущена", symbol)
            return
        if not is_short:
            stop_price = price * (1 - self.stop_loss_pct)
            take_profit = price * (1 + self.take_profit_pct)
            trailing_stop = stop_price
        else:
            stop_price = price * (1 + self.stop_loss_pct)
            take_profit = price * (1 - self.take_profit_pct)
            trailing_stop = stop_price
        self.positions[symbol] = {
            "entry_price": price,
            "quantity": quantity,
            "stop_price": stop_price,
            "take_profit": take_profit,
            "trailing_stop": trailing_stop,
            "last_price": price,
        }
        direction = "short" if is_short else "long"
        logger.info("Открыта %s позиция %s по %s x%s", direction, symbol, price, abs(quantity))
        self._log_event(f"Открыта {direction} позиция", symbol=symbol, value=price)

    def check_exit(self, symbol: str, current_price: float) -> bool:
        pos = self.positions.get(symbol)
        if not pos:
            return False
        quantity = pos["quantity"]
        is_short = quantity < 0
        pos["last_price"] = float(current_price)
        if not is_short:
            new_trailing = current_price * (1 - self.stop_loss_pct)
            if new_trailing > pos.get("trailing_stop", pos["stop_price"]):
                pos["trailing_stop"] = new_trailing
            if current_price <= pos.get("trailing_stop", pos["stop_price"]):
                logger.info("Сработал стоп по %s", symbol)
                self._log_event("Сработал стоп", symbol=symbol, value=current_price)
                return True
            if current_price >= pos["take_profit"]:
                logger.info("Достигнут тейк-профит по %s", symbol)
                self._log_event("Тейк-профит", symbol=symbol, value=current_price)
                return True
            return False
        new_trailing = current_price * (1 + self.stop_loss_pct)
        if new_trailing < pos.get("trailing_stop", pos["stop_price"]):
            pos["trailing_stop"] = new_trailing
        if current_price >= pos.get("trailing_stop", pos["stop_price"]):
            logger.info("Сработал стоп по короткой позиции %s", symbol)
            self._log_event("Стоп по шорту", symbol=symbol, value=current_price)
            return True
        if current_price <= pos["take_profit"]:
            logger.info("Тейк-профит по шорту %s", symbol)
            self._log_event("Тейк-профит", symbol=symbol, value=current_price)
            return True
        return False

    def exit_position(self, symbol: str) -> None:
        if symbol in self.positions:
            logger.info("Позиция %s закрыта", symbol)
            self._log_event("Позиция закрыта", symbol=symbol)
            del self.positions[symbol]

    def clear_positions(self) -> None:
        for sym in list(self.positions.keys()):
            logger.info("Принудительное закрытие %s", sym)
            self._log_event("Принудительное закрытие", symbol=sym)
            del self.positions[sym]

    # ------------------------------------------------------------------
    # Служебные методы
    # ------------------------------------------------------------------
    def _notify(self, message: str) -> None:
        self._log_event(message, level="warning")
        if self.notifier:
            try:
                self.notifier(message)
            except Exception as exc:
                logger.debug("Notifier failed: %s", exc)
        self._send_alert(message)

    def _handle_violation(self, symbol: str, message: str) -> None:
        logger.warning(message)
        self._notify(message)
        if self._force_exit_callback:
            try:
                self._force_exit_callback(symbol)
                return
            except Exception as exc:
                logger.debug("Force exit callback failed: %s", exc)
        self.exit_position(symbol)

    def _log_event(
        self,
        message: str,
        *,
        symbol: Optional[str] = None,
        level: str = "info",
        value: Optional[float] = None,
    ) -> None:
        if self.journal:
            self.journal.record_event(message, level=level, symbol=symbol, value=value)

    @staticmethod
    def _safe_float(value: object) -> Optional[float]:
        try:
            if value is None:
                return None
            return float(value)
        except Exception:
            return None

    @staticmethod
    def _safe_int(value: object) -> Optional[int]:
        try:
            if value is None:
                return None
            return int(value)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Уведомления в Telegram
    # ------------------------------------------------------------------
    def _send_alert(self, message: str) -> None:
        try:
            import os
            import requests  # type: ignore

            token = os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
            chat_id = os.getenv("TELEGRAM_CHAT_ID")
            if not token or not chat_id:
                return
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, data={"chat_id": chat_id, "text": message})
        except Exception as exc:
            logger.debug("Не удалось отправить Telegram уведомление: %s", exc)


__all__ = ["RiskManager", "RiskJournal", "InstrumentLimit", "AssetClassLimit"]
