"""Streaming market data provider using the Tinkoff Invest API.

This module defines a :class:`TinkoffStreamProvider` that offers a simple
interface to subscribe to live price updates.  When the
``tinkoff.invest`` gRPC client is available and a valid token has been
configured, the provider attempts to establish a streaming connection to
Tinkoff's market data API.  Incoming price updates are passed to a
user‑supplied callback.  If the SDK is unavailable or a token is not
provided, the provider falls back to periodically polling the latest
price using the base :class:`~moex_bot.core.data_provider.DataProvider`.

Note that this implementation is deliberately conservative: it does
not maintain long‑lived websocket connections, nor does it attempt
dynamic subscriptions.  The intent is to demonstrate where streaming
integration would reside.  For production use one should implement
proper error handling, reconnection logic and subscription management
using the official Tinkoff Invest Python SDK.
"""

from __future__ import annotations

import time
from typing import Callable, Iterable, Optional

try:
    # The tinkoff-invest SDK provides a high level streaming API via
    # ``market_data_stream``.  Import conditionally so the module
    # gracefully degrades when the dependency is absent.
    from tinkoff.invest import Client
except Exception:  # pragma: no cover - optional dependency
    Client = None  # type: ignore

from .data_provider import DataProvider


class TinkoffStreamProvider(DataProvider):
    """Market data provider with optional streaming capability.

    This class extends :class:`DataProvider` and attempts to use the
    Tinkoff Invest gRPC streaming API to obtain real‑time price updates.
    If the SDK is not installed or no token is supplied, it falls
    back to polling prices via the base provider.

    Args:
        token: OAuth token for Tinkoff Invest.  If empty, streaming is
            disabled and the provider reverts to polling.
        account_id: Unused in the current implementation; reserved for
            future use.
        sandbox: Whether to connect to the sandbox environment.
        data_dir: Directory containing CSV files for the base provider.
    """

    def __init__(
        self,
        token: Optional[str],
        account_id: Optional[str] = None,
        sandbox: bool = False,
        data_dir: str = "data",
    ) -> None:
        super().__init__(data_dir)
        self.token = token or ""
        self.account_id = account_id or ""
        self.sandbox = bool(sandbox)
        # Enable streaming only if both the client and token are present
        self.enabled: bool = bool(Client and self.token)

    def subscribe_prices(
        self, symbols: Iterable[str], on_price: Callable[[str, float], None], interval: float = 1.0
    ) -> None:
        """Subscribe to live prices for the given symbols.

        For each price update received, the ``on_price`` callback is
        invoked with the symbol and the latest price.  When streaming
        is unavailable, this method falls back to polling the most
        recent price from the base provider at the specified interval.

        Args:
            symbols: Iterable of ticker symbols to subscribe to.
            on_price: Callback invoked with ``(symbol, price)`` for
                each update.  Users should ensure that the callback is
                non‑blocking.
            interval: Polling interval in seconds when streaming is
                not available.  Ignored when streaming is active.

        Note:
            In its current form this method blocks the calling thread
            and runs an infinite loop.  Consumers should therefore
            start it in a separate thread or process.  In a production
            system you would instead integrate with an event loop and
            handle reconnections gracefully.
        """
        # Normalise symbols to uppercase strings
        syms = [str(s).upper() for s in symbols]
        if not syms:
            return
        # If the streaming client is available, attempt to open a
        # streaming connection.  The tinkoff.invest SDK exposes a
        # ``market_data_stream`` method on the Client which returns
        # an object supporting subscription.  To avoid introducing a
        # heavy dependency here, we do not import gRPC protos.
        if self.enabled and Client:
            try:
                with Client(self.token, sandbox=self.sandbox) as client:
                    # Lazily import to avoid issues when the SDK is absent
                    from tinkoff.invest import market_data_pb2, market_data_stream_pb2
                    # Build subscription requests for each symbol to receive
                    # the last traded price (market data).  In Tinkoff API
                    # terminology, this is a ``SubscribeLastPriceRequest``.
                    requests = []
                    for ticker in syms:
                        req = market_data_stream_pb2.MarketDataRequest(
                            subscribe_last_price=market_data_pb2.SubscribeLastPriceRequest(
                                instruments=[market_data_pb2.InstrumentLastPriceRequest(instrument_id=ticker)]
                            )
                        )
                        requests.append(req)
                    stream = client.market_data_stream.market_data_stream(iter(requests))
                    # Process incoming events until the connection closes
                    for event in stream:
                        try:
                            if hasattr(event, "last_price"):
                                lp = event.last_price
                                # Each last price event has an instrument_id and price
                                symbol = lp.instrument_id
                                price = float(lp.price.units + lp.price.nano / 1e9)
                                on_price(symbol, price)
                        except Exception:
                            # Continue processing even if callback fails
                            continue
            except Exception:
                # If streaming subscription fails, fall back to polling below
                pass
        # Fallback: poll latest price at a regular interval
        while True:
            for ticker in syms:
                try:
                    price = self.latest_price(ticker)
                    if price is not None:
                        on_price(ticker, price)
                except Exception:
                    continue
            try:
                time.sleep(max(interval, 0.1))
            except KeyboardInterrupt:
                break


__all__ = ["TinkoffStreamProvider"]