"""Broker integration for placing orders.

This module wraps the Tinkoff Invest API (when available) or falls
back to a dummy implementation when the package cannot be imported.
It provides a :class:`Trader` class with methods to buy and sell
instruments.  Each order uses a unique identifier to avoid
accidental duplication.  All API calls are wrapped in
try/except blocks to prevent unhandled exceptions from crashing the
application.  When used in sandbox mode no real trades are placed.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

try:
    from tinkoff.invest import Client
except Exception:
    # When tinkoff.invest is not available, define a stub Client
    Client = None  # type: ignore

logger = logging.getLogger(__name__)


class Trader:
    def _resolve_figi(self, ticker: str) -> str:
        # TODO: Здесь можно подключить реальный вызов API для поиска FIGI по тикеру
        # Временно возвращаем сам тикер (для песочницы достаточно)
        return ticker
    
    """Execute trades via the Tinkoff Invest API or a stub and optionally
    notify via Telegram.

    The Trader can operate in several modes controlled by configuration:

    * ``live``: connect to the production Tinkoff Invest API and execute
      real orders.
    * ``sandbox``: connect to the sandbox environment (if available) to
      execute paper trades.
    * ``virtual``: generate signals using live data but log orders
      without executing them.

    Additionally, if a Telegram bot token and chat ID are provided the
    Trader will send a notification for each placed order describing
    the action, instrument and quantity.

    Args:
        token: OAuth token for the API.  If empty or ``None``, the
            Trader operates in dry‑run mode and only logs orders.
        account_id: Account identifier provided by the broker.
        sandbox: Whether to use the sandbox environment.  Ignored if
            ``trade_mode`` is provided.
        trade_mode: Optional string specifying the trading mode.  One of
            ``"live"``, ``"sandbox"`` or ``"virtual"``.  Overrides the
            ``sandbox`` flag when provided.
        telegram_token: Optional Telegram bot token.  If provided
            together with ``telegram_chat_id`` order notifications
            will be sent via Telegram.
        telegram_chat_id: Optional Telegram chat identifier.  Must be
            provided along with ``telegram_token``.
    """

    def __init__(self, token: Optional[str], account_id: Optional[str], sandbox: bool = False,
                 trade_mode: Optional[str] = None,
                 telegram_token: Optional[str] = None,
                 telegram_chat_id: Optional[str] = None) -> None:
        self.token = token or ''
        self.account_id = account_id or ''
        # Determine operational mode
        mode = (trade_mode or '').lower()
        if mode == 'live':
            self.sandbox = False
            self.virtual = False
        elif mode == 'virtual':
            self.sandbox = False
            self.virtual = True
        elif mode == 'sandbox':
            self.sandbox = True
            self.virtual = False
        else:
            # fallback to sandbox flag
            self.sandbox = bool(sandbox)
            self.virtual = False
        self._client: Optional[Client] = None
        # Telegram configuration
        self.telegram_token = telegram_token or ''
        self.telegram_chat_id = telegram_chat_id or ''
        # If virtual mode or no token, operate in dry run
        if self.virtual or not self.token or Client is None:
            if not self.token:
                logger.info("No API token provided; broker will operate in dry‑run mode.")
            if self.virtual:
                logger.info("Operating in virtual mode: orders will not be sent to API.")
            self._client = None
        else:
            try:
                self._client = Client(
                    self.token,
                    app_name="moex_bot",
                    sandbox=self.sandbox
                )  # type: ignore[arg-type]
            except Exception as e:
                logger.warning(f"Failed to initialise Tinkoff Client: {e}. Operating in dry‑run mode.")
                self._client = None

    def _generate_order_id(self, side: str, figi: str, lots: int) -> str:
        """Generate a unique order identifier for idempotent requests."""
        uid = uuid.uuid4().hex[:8]
        return f"{side}-{figi}-{lots}-{uid}"

    def _notify_trade(self, direction: int, figi: str, lots: int, limit_price: Optional[float], order_id: str) -> None:
        """Send a Telegram notification about an executed or logged order.

        If Telegram credentials are not set or sending fails, this
        function quietly returns without raising exceptions.

        Args:
            direction: 1 for buy, 2 for sell.
            figi: FIGI or ticker of the instrument.
            lots: Number of lots traded.
            limit_price: Optional price for limit orders.
            order_id: Unique identifier of the order.
        """
        if not self.telegram_token or not self.telegram_chat_id:
            return
        # Compose message text
        action = 'BUY' if direction == 1 else 'SELL'
        price_part = f" at {limit_price}" if limit_price is not None else " at MARKET"
        text = f"{action} {lots} of {figi}{price_part} (order_id={order_id})"
        import requests  # Imported here to avoid dependency if notifications unused
        base = f"https://api.telegram.org/bot{self.telegram_token}"
        try:
            requests.post(f"{base}/sendMessage", json={"chat_id": self.telegram_chat_id, "text": text})
        except Exception:
            # Swallow any errors silently; we do not want to interrupt trading
            pass

    def _submit_order(
        self, figi: str, lots: int, direction: int, limit_price: Optional[float] = None
    ) -> str:
        """Internal helper to submit an order through the API or log it."""

        order_id = self._generate_order_id('buy' if direction == 1 else 'sell', figi, lots)
        if self._client is None:
            logger.info(
                f"[DRY‑RUN] {'BUY' if direction == 1 else 'SELL'} {lots} of {figi} @ {limit_price or 'MARKET'} "
                f"(sandbox={self.sandbox}) [order_id={order_id}]"
            )
            self._notify_trade(direction, figi, lots, limit_price, order_id)
            return order_id
        try:
            with self._client as client:
                if self.sandbox and hasattr(client, 'sandbox'):
                    client.sandbox.post_sandbox_order(
                        account_id=self.account_id,
                        figi=figi,
                        quantity=lots,
                        price=None if limit_price is None else {'units': int(limit_price), 'nano': 0},
                        direction=direction,
                        order_type=2,
                        order_id=order_id,
                    )
                else:
                    client.orders.post_order(
                        account_id=self.account_id,
                        figi=figi,
                        quantity=lots,
                        price=None if limit_price is None else {'units': int(limit_price), 'nano': 0},
                        direction=direction,
                        order_type=2,
                        order_id=order_id,
                    )
            logger.info(
                f"Submitted order {order_id}: {'BUY' if direction == 1 else 'SELL'} {lots} of {figi} @ "
                f"{limit_price or 'MARKET'}"
            )
            self._notify_trade(direction, figi, lots, limit_price, order_id)
        except Exception as e:
            logger.error(f"Error submitting order {order_id} for {figi}: {e}")
        return order_id

    def buy(self, figi: str, lots: int = 1, limit_price: Optional[float] = None) -> str:
        """Place a buy order for the specified instrument."""

        return self._submit_order(figi, lots, direction=1, limit_price=limit_price)

    def sell(self, figi: str, lots: int = 1, limit_price: Optional[float] = None) -> str:
        """Place a sell order for the specified instrument."""

        return self._submit_order(figi, lots, direction=2, limit_price=limit_price)

    def cancel_all_orders(self) -> None:
        """Attempt to cancel all open orders for the configured account."""

        if self._client is None:
            logger.info("cancel_all_orders: no active API client, skipping cancellation")
            return
        try:
            with self._client as client:
                active_orders = []
                try:
                    response = client.orders.get_orders(account_id=self.account_id)
                    active_orders = getattr(response, 'orders', [])
                except Exception:
                    active_orders = []
                for order in active_orders:
                    try:
                        client.orders.cancel_order(account_id=self.account_id, order_id=order.order_id)
                    except Exception as exc:
                        logger.warning(
                            "Failed to cancel order %s: %s", getattr(order, 'order_id', 'unknown'), exc
                        )
            logger.info("Requested cancellation of %d open orders", len(active_orders))
        except Exception as exc:
            logger.error("cancel_all_orders failed: %s", exc)

__all__ = ['Trader']
