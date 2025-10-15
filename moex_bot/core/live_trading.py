"""Production-ready live trading gateway with risk integration."""

from __future__ import annotations

import datetime as dt
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .broker import OrderResult, Trader
from .risk import RiskManager
from .journal import ExecutionJournal

logger = logging.getLogger(__name__)


OrderHook = Callable[[Dict[str, object]], None]
InstrumentMapper = Callable[[str], str]


def _default_mapper(symbol: str) -> str:
    return symbol


@dataclass
class LiveTrader:
    """High-level trading orchestrator combining execution and risk controls.

    The :class:`LiveTrader` wraps a low-level :class:`Trader` implementation
    with retry logic, slippage handling, risk-manager bookkeeping and
    journalling hooks.  It exposes ``buy``/``sell`` helpers mirroring the
    underlying trader but augments them with:

    * automatic conversion of tickers into FIGI via ``instrument_mapper``;
    * configurable slippage in basis points applied to limit orders;
    * retry with exponential backoff when transient errors occur;
    * per-order journal entries persisted in ``order_history`` and optional
      callbacks (e.g. database writer, metrics pipeline);
    * integration with :class:`RiskManager` to keep risk state in sync.

    Args:
        trader: Concrete :class:`Trader` used to submit API calls.
        risk_manager: Portfolio risk manager instance.
        instrument_mapper: Optional function converting tickers into broker
            instrument identifiers (FIGI).  Defaults to identity mapping.
        slippage_bps: Slippage allowance applied to limit prices (basis points).
        max_retries: Maximum number of attempts before giving up on an order.
        journal_hook: Optional callback invoked with the order payload every
            time an order is successfully recorded.
    """

    trader: Trader
    risk_manager: RiskManager
    instrument_mapper: InstrumentMapper = _default_mapper
    slippage_bps: float = 5.0
    max_retries: int = 3
    journal_hook: Optional[OrderHook] = None
    journal: Optional[ExecutionJournal] = None
    journal_path: Optional[str] = None
    equity_hook: Optional[Callable[[float], None]] = None
    order_history: List[Dict[str, object]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.journal is None and self.journal_path:
            self.journal = ExecutionJournal(self.journal_path)

    @staticmethod
    def _is_success(result: OrderResult) -> bool:
        status = (result.status or '').lower()
        for keyword in ('reject', 'error', 'cancel'):
            if keyword in status:
                return False
        return True

    def _apply_slippage(self, price: Optional[float], side: str) -> Optional[float]:
        if price is None:
            return None
        try:
            price_float = float(price)
        except Exception:
            return None
        adjustment = price_float * (self.slippage_bps / 10_000.0)
        if side.lower() == 'buy':
            return price_float + adjustment
        return max(price_float - adjustment, 0.0)

    def _record_order(self, payload: Dict[str, object]) -> None:
        payload.setdefault('timestamp', dt.datetime.utcnow())
        self.order_history.append(payload)
        if self.journal_hook:
            try:
                self.journal_hook(payload)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("journal_hook failed: %s", exc)
        if self.journal:
            try:
                self.journal.record(payload)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("execution journal write failed: %s", exc)

    def _submit_with_retry(
        self,
        side: str,
        symbol: str,
        lots: int,
        limit_price: Optional[float],
    ) -> Optional[OrderResult]:
        if lots <= 0:
            logger.info("Skip %s order for %s: non-positive lot size (%s)", side.upper(), symbol, lots)
            return None
        mapped = self.instrument_mapper(symbol)
        price_with_slippage = self._apply_slippage(limit_price, side)
        last_error: Optional[Exception] = None
        last_rejection: Optional[str] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                if side.lower() == 'buy':
                    order_id = self.trader.buy(mapped, lots, limit_price=price_with_slippage)
                else:
                    order_id = self.trader.sell(mapped, lots, limit_price=price_with_slippage)
                payload = {
                    'side': side.lower(),
                    'symbol': symbol,
                    'figi': mapped,
                    'lots': lots,
                    'limit_price': price_with_slippage,
                    'order_id': order_id.order_id,
                    'status': order_id.status,
                    'lots_executed': order_id.lots_executed,
                    'message': order_id.message,
                    'attempt': attempt,
                }
                self._record_order(payload)
                if not self._is_success(order_id):
                    last_rejection = order_id.message or order_id.status
                    logger.warning(
                        "Attempt %s to %s %s rejected: %s", attempt, side.upper(), symbol, last_rejection
                    )
                    time.sleep(min(0.5 * attempt, 2.0))
                    continue
                return order_id
            except Exception as exc:  # pragma: no cover - network failure
                last_error = exc
                logger.warning(
                    "Attempt %s to %s %s failed: %s", attempt, side.upper(), symbol, exc
                )
                time.sleep(min(0.5 * attempt, 2.0))
        if last_error:
            logger.error("Unable to %s %s after %s attempts: %s", side.upper(), symbol, self.max_retries, last_error)
        if last_rejection:
            logger.error("Order for %s permanently rejected after retries: %s", symbol, last_rejection)
        return None

    def buy(self, symbol: str, lots: int, limit_price: Optional[float] = None) -> Optional[OrderResult]:
        """Place a buy order and register the position with the risk manager."""

        if self.risk_manager.halt_trading:
            logger.warning("Risk manager halted trading; buy order for %s skipped", symbol)
            return None
        order_id = self._submit_with_retry('buy', symbol, lots, limit_price)
        if order_id and order_id.lots_executed:
            price = order_id.limit_price if order_id.limit_price is not None else limit_price
            if price is not None:
                self.risk_manager.register_entry(symbol, float(price), order_id.lots_executed)
        return order_id

    def sell(self, symbol: str, lots: int, limit_price: Optional[float] = None) -> Optional[OrderResult]:
        """Place a sell order and clear the position from the risk manager."""

        order_id = self._submit_with_retry('sell', symbol, lots, limit_price)
        if order_id and self._is_success(order_id):
            self.risk_manager.exit_position(symbol)
        return order_id

    def cancel_all(self) -> None:
        """Cancel all open orders through the underlying trader."""

        try:
            self.trader.cancel_all_orders()
        except AttributeError:
            logger.warning("Underlying trader does not support cancel_all_orders")
        except Exception as exc:  # pragma: no cover
            logger.error("cancel_all failed: %s", exc)

    def update_price(self, symbol: str, current_price: float) -> None:
        """Pass the latest market price to the risk manager and auto-exit if needed."""

        try:
            self.risk_manager.update_position_price(symbol, current_price)
            if self.risk_manager.check_exit(symbol, current_price):
                qty = int(self.risk_manager.positions.get(symbol, {}).get('quantity', 0))
                if qty:
                    logger.info("Risk manager triggered exit for %s at %s", symbol, current_price)
                    self.sell(symbol, qty, limit_price=current_price)
        except Exception as exc:  # pragma: no cover
            logger.error("update_price failed for %s: %s", symbol, exc)

    def sync_equity(self, equity: float) -> None:
        """Update equity in the risk manager and append to journal for monitoring."""

        self.risk_manager.update_equity(equity)
        self._record_order({'type': 'equity_update', 'equity': float(equity)})
        if self.equity_hook:
            try:
                self.equity_hook(float(equity))
            except Exception as exc:  # pragma: no cover
                logger.debug("equity_hook failed: %s", exc)


__all__ = ["LiveTrader"]
