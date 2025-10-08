"""Market data provider using the Tinkoff Invest API.

This module defines a ``TinkoffAPIProvider`` class that extends
``DataProvider`` to fetch historical and latest price data from the
Tinkoff Invest API.  When the ``tinkoff.invest`` SDK is available
and a valid token is provided, the provider will query the API for
OHLCV candles.  Otherwise it falls back to the base ``DataProvider``
implementation which reads data from CSV files.  This design
allows seamless switching between local file data and remote data
sources based on runtime availability and configuration.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, List

try:
    from tinkoff.invest import Client, CandleInterval
except Exception:
    Client = None  # type: ignore
    CandleInterval = None  # type: ignore

from .data_provider import DataProvider


class TinkoffAPIProvider(DataProvider):
    """Fetch market data via Tinkoff Invest API.

    Args:
        token: OAuth token for Tinkoff API.  If empty, falls back
            to CSV-based ``DataProvider``.
        account_id: Unused but kept for future use; the API
            currently does not require an account to fetch candles.
        sandbox: Whether to use sandbox environment (unused for
            fetching candles).  Provided for future extensibility.
        data_dir: Path to local data files used as a fallback.
    """

    def __init__(self, token: Optional[str], account_id: Optional[str] = None,
                 sandbox: bool = False, data_dir: str = 'data') -> None:
        super().__init__(data_dir)
        self.token = token or ''
        self.account_id = account_id or ''
        self.sandbox = bool(sandbox)
        self.enabled = bool(Client and self.token)

    def _fetch_candles(self, figi: str, interval: str, days: int) -> Optional[List[dict]]:
        """Fetch candle data from the API.

        Args:
            figi: FIGI code of the instrument.  Note that for MOEX
                equities the ticker often matches FIGI, but mapping
                might be required for other instruments.
            interval: Timeframe string ('hour', 'day', etc.).
            days: Number of days of history to fetch.

        Returns:
            A list of candle dictionaries or ``None`` if the API is
            unavailable or an error occurs.
        """
        if not self.enabled or Client is None or CandleInterval is None:
            return None
        # Map interval string to CandleInterval enum; default to 1 hour
        interval_map = {
            'minute': CandleInterval.CANDLE_INTERVAL_1_MIN,
            'hour': CandleInterval.CANDLE_INTERVAL_HOUR,
            'day': CandleInterval.CANDLE_INTERVAL_DAY,
        }
        candle_int = interval_map.get(interval, CandleInterval.CANDLE_INTERVAL_HOUR)
        to_dt = datetime.utcnow()
        from_dt = to_dt - timedelta(days=days)
        try:
            with Client(self.token, sandbox=self.sandbox) as client:
                candles = client.market_data.get_candles(
                    figi=figi,
                    from_=from_dt,
                    to=to_dt,
                    interval=candle_int,
                ).candles
            return candles
        except Exception:
            return None

    def load_history(self, symbol: str, interval: str = 'hour', days: int = 90) -> 'pd.DataFrame':  # type: ignore[override]
        """Return historical price data for the given symbol.

        Attempts to fetch candles from the API first; if that fails
        falls back to the parent implementation which reads from
        CSV files.
        """
        import pandas as pd  # local import to avoid global dependency
        # Try API
        candles = self._fetch_candles(symbol, interval, days)
        if candles:
            # Convert candles to DataFrame; use 'close' as closing price
            df = pd.DataFrame([
                {
                    'time': c.time,
                    'open': c.open.units + c.open.nano / 1e9,
                    'high': c.high.units + c.high.nano / 1e9,
                    'low': c.low.units + c.low.nano / 1e9,
                    'close': c.close.units + c.close.nano / 1e9,
                    'volume': c.volume,
                }
                for c in candles
            ])
            return df
        # Fallback to CSV
        return super().load_history(symbol, interval, days)

    def latest_price(self, symbol: str, interval: str = 'hour', days: int = 1) -> Optional[float]:  # type: ignore[override]
        """Return the most recent closing price.

        Uses API when available, otherwise the base implementation.
        """
        if not self.enabled:
            return super().latest_price(symbol, interval, days)
        candles = self._fetch_candles(symbol, interval, days)
        if candles:
            last = candles[-1]
            return float(last.close.units + last.close.nano / 1e9)
        return super().latest_price(symbol, interval, days)


__all__ = ['TinkoffAPIProvider']