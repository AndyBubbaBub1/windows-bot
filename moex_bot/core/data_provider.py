"""Utilities for retrieving resilient market data feeds."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


class DataValidationError(RuntimeError):
    """Raised when an upstream data source returns an invalid price."""


def _default_validator(price: Optional[float]) -> bool:
    try:
        return price is not None and float(price) > 0.0
    except Exception:
        return False


@dataclass
class DataProvider:
    """Market data provider with resilient fallback and caching.

    The provider attempts to source prices in the following order:

    1. Streaming source (if provided).
    2. REST/HTTP source (if provided).
    3. Local in-memory cache populated from previous successful calls.
    4. Historical CSV files stored under ``data_dir``.

    The class maintains a time-based cache to avoid excessive REST calls
    and automatically validates prices returned by upstream providers to
    guard against zero/negative or missing values.

    Args:
        data_dir: Directory containing CSV files with historical prices.
        stream: Optional streaming provider exposing ``get_last_price``.
        rest: Optional REST provider exposing ``get_last_price``.
        cache_ttl: Time-to-live in seconds for cached entries.  Stale
            cache entries will be ignored when fresher data is available
            from network sources but can still be returned if every
            source fails.
        validator: Callable validating upstream prices.  Defaults to a
            simple ``price > 0`` check.
    """

    data_dir: Optional[str] = None
    stream: Optional[object] = None
    rest: Optional[object] = None
    cache_ttl: float = 5.0
    validator: Callable[[Optional[float]], bool] = _default_validator
    enabled: bool = True
    _cache: Dict[str, Tuple[float, float]] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------
    def _update_cache(self, symbol: str, price: float) -> None:
        try:
            self._cache[symbol] = (float(price), time.monotonic())
        except Exception:
            # Do not allow caching errors to break data flow
            logger.debug("Failed to cache price for %s", symbol)

    def _get_cached(self, symbol: str, *, allow_stale: bool = True) -> Optional[float]:
        entry = self._cache.get(symbol)
        if not entry:
            return None
        price, ts = entry
        if allow_stale:
            return price
        if time.monotonic() - ts <= self.cache_ttl:
            return price
        return None

    def enable_network(self) -> None:
        """Re-enable network data sources after a manual disable."""

        self.enabled = True

    def disable_network(self) -> None:
        """Disable network data sources (stream and REST)."""

        self.enabled = False

    # ------------------------------------------------------------------
    # Price retrieval
    # ------------------------------------------------------------------
    def get_price(self, symbol: str) -> Optional[float]:
        """Return the most recent price for ``symbol`` from live sources."""

        symbol = symbol.upper()
        if not self.enabled:
            return self._get_cached(symbol)

        for source_name, source in ("stream", self.stream), ("rest", self.rest):
            if not source:
                continue
            try:
                price = source.get_last_price(symbol)
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("%s provider failed for %s: %s", source_name, symbol, exc)
                continue
            if not self.validator(price):
                logger.warning("Discarded invalid price %r for %s from %s provider", price, symbol, source_name)
                continue
            self._update_cache(symbol, float(price))
            return float(price)

        # Fallback to fresh cache entry
        cached = self._get_cached(symbol, allow_stale=False)
        if cached is not None:
            return cached

        # Return stale cache if nothing else available
        cached = self._get_cached(symbol, allow_stale=True)
        if cached is not None:
            logger.debug("Returning stale cached price for %s", symbol)
            return cached

        # Final fallback: attempt to read from disk
        return self.latest_price(symbol)

    # ------------------------------------------------------------------
    # Historical data helpers
    # ------------------------------------------------------------------
    def _resolve_symbol_file(self, symbol: str, interval: str, days: int) -> Optional[Path]:
        if not self.data_dir:
            return None
        base = Path(self.data_dir)
        candidates = [
            base / f"{symbol.upper()}_{interval}_{days}d.csv",
            base / f"{symbol.upper()}_{interval}.csv",
            base / f"{symbol.upper()}.csv",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        # Fallback: search for any file starting with SYMBOL_interval_
        pattern = f"{symbol.upper()}_{interval}_" + "*d.csv"
        matches = sorted(base.glob(pattern))
        if matches:
            return matches[0]
        return None

    def load_history(self, symbol: str, interval: str = "hour", days: int = 1) -> pd.DataFrame:
        """Load historical OHLCV data for ``symbol`` from CSV.

        Returns an empty :class:`pandas.DataFrame` when the file cannot be
        located or read.
        """

        path = self._resolve_symbol_file(symbol, interval, days)
        if not path:
            return pd.DataFrame()
        try:
            df = pd.read_csv(path)
            return df
        except Exception as exc:
            logger.warning("Failed to load history for %s from %s: %s", symbol, path, exc)
            return pd.DataFrame()

    def latest_price(self, symbol: str, interval: str = "hour", days: int = 1) -> Optional[float]:
        """Return the last available price for ``symbol``.

        This method first checks the live cache and then attempts to read
        the last closing price from the CSV history.
        """

        symbol = symbol.upper()
        cached = self._get_cached(symbol, allow_stale=True)
        if cached is not None:
            return cached
        df = self.load_history(symbol, interval=interval, days=days)
        if df.empty:
            return None
        for column in ("close", "Close", "c", "last", "price"):
            if column in df.columns:
                try:
                    return float(df[column].iloc[-1])
                except Exception:
                    continue
        # Fall back to last numeric value regardless of column
        for col in reversed(df.columns):
            series = df[col]
            if pd.api.types.is_numeric_dtype(series):
                try:
                    return float(series.iloc[-1])
                except Exception:
                    continue
        return None

    # Convenience alias used throughout the codebase
    def latest_prices(self, symbols: Iterable[str]) -> Dict[str, Optional[float]]:
        """Fetch latest prices for multiple symbols."""

        return {symbol: self.latest_price(symbol) for symbol in symbols}
