"""Utilities for working with FIGI identifiers.

This module provides helpers for resolving ticker symbols to FIGI codes and
fetching dynamic universes of Russian equities from the Tinkoff Invest API.

All functions are defensive: if the Tinkoff Invest SDK is not installed or the
API call fails they return safe fallbacks so the rest of the bot can continue to
operate (e.g. when running offline backtests).
"""

from __future__ import annotations

from typing import Iterable, Optional

try:  # pragma: no cover - import guard exercised in tests via monkeypatch.
    from tinkoff.invest import Client, InstrumentStatus
except Exception:  # pragma: no cover - the SDK might be absent in CI.
    Client = None
    InstrumentStatus = None

__all__ = [
    "get_universe",
    "list_russian_shares",
    "ticker_to_figi",
]


def get_universe() -> list[dict[str, str]]:
    """Return the list of Russian instruments available in the bot's universe.

    The helper forwards to :func:`moex_bot.universe_ru.get_universe` and falls
    back to returning an empty list if the module cannot be imported.
    """

    try:
        from moex_bot.universe_ru import get_universe as _get

        return _get()
    except Exception:
        return []


def ticker_to_figi(ticker: str, token: str) -> Optional[str]:
    """Resolve MOEX ticker to FIGI using the Tinkoff Invest API."""

    if not Client or not ticker or not token:
        return None

    t = ticker.strip().upper()
    try:
        with Client(token) as client:
            res = client.instruments.find_instrument(query=t)
            # Prefer an exact ticker match if it exists in the response.
            matches = [i for i in res.instruments if i.ticker.upper() == t]
            if matches:
                return matches[0].figi
            if res.instruments:
                return res.instruments[0].figi
    except Exception:
        return None

    return None


def list_russian_shares(
    token: str,
    levels: Iterable[int] | None = (1, 2, 3),
) -> list[dict[str, str]]:
    """Return FIGI data for Russian shares of the selected listing levels.

    Args:
        token: API token for Tinkoff Invest.
        levels: Sequence of listing levels ("echelons") to include.  ``None``
            disables the filter and returns all Russian shares.

    Returns:
        List of dictionaries with ``ticker``, ``figi``, ``isin``, ``class_code``,
        ``list_level`` and ``name`` fields.  An empty list is returned if the
        SDK or the API is unavailable.
    """

    if not Client or not token:
        return []

    level_filter = None
    if levels is not None:
        level_filter = {
            int(lvl) if isinstance(lvl, int) else int(str(lvl))
            for lvl in levels
            if str(lvl).strip().isdigit()
        }

    try:
        instrument_status = (
            getattr(InstrumentStatus, "INSTRUMENT_STATUS_BASE")
            if InstrumentStatus
            else None
        )
        with Client(token) as client:
            response = client.instruments.shares(
                instrument_status=instrument_status
            )
            shares = getattr(response, "instruments", [])
    except Exception:
        return []

    result: list[dict[str, str]] = []
    for share in shares:
        try:
            if getattr(share, "country_of_risk", "") != "RU":
                continue
            exchange = getattr(share, "exchange", "").upper()
            if exchange not in {"MOEX", "TQBR", "RUS"}:
                continue
            if getattr(share, "otc_flag", False):
                continue
            list_level = int(getattr(share, "list_level", 0))
            if level_filter and list_level not in level_filter:
                continue
            result.append(
                {
                    "ticker": getattr(share, "ticker", ""),
                    "figi": getattr(share, "figi", ""),
                    "isin": getattr(share, "isin", ""),
                    "class_code": getattr(share, "class_code", ""),
                    "list_level": list_level,
                    "name": getattr(share, "name", ""),
                }
            )
        except Exception:
            # Skip malformed entries but continue processing the rest.
            continue

    result.sort(key=lambda item: (item.get("list_level", 0), item.get("ticker", "")))
    return result

