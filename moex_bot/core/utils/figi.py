"""FIGI helpers and dynamic universe utilities.

The bot ships with a static list of popular Russian equities so that it can
operate without external connectivity.  This module complements the static
universe with helpers that resolve FIGI identifiers dynamically through the
Tinkoff Invest API.  All helpers are defensive: when the optional SDK is not
available or a network call fails they fall back to returning empty results
instead of raising exceptions, keeping the rest of the bot functional.
"""

from __future__ import annotations

from typing import Iterable, Optional

try:  # pragma: no cover - optional dependency
    from tinkoff.invest import Client, InstrumentStatus
except Exception:  # pragma: no cover - keep module importable without SDK
    Client = None  # type: ignore
    InstrumentStatus = None  # type: ignore


def get_universe() -> list[dict[str, str]]:
    """Return the list of Russian instruments available in the static universe.

    This helper forwards to :func:`moex_bot.universe_ru.get_universe` and
    falls back to returning an empty list if the universe cannot be imported
    (e.g. stripped during packaging).  Callers should treat the returned list
    as read‑only.  For dynamic discovery of instruments see
    :func:`load_russian_shares_figi`.

    Returns:
        List of dictionaries with ``ticker``, ``figi`` and ``board`` keys.
    """

    try:
        from moex_bot.universe_ru import get_universe as _get

        return _get()
    except Exception:
        return []


def ticker_to_figi(ticker: str, token: str) -> Optional[str]:
    """Resolve a MOEX ticker to FIGI using the Tinkoff Invest API.

    Args:
        ticker: Symbol to resolve.
        token: Tinkoff Invest API token.

    Returns:
        FIGI identifier if it can be resolved, otherwise ``None``.
    """

    if not Client or not ticker or not token:
        return None

    t = ticker.strip().upper()
    try:
        with Client(token) as client:
            res = client.instruments.find_instrument(query=t)
            # Prefer exact ticker match to reduce ambiguity for depository receipts
            matches = [i for i in res.instruments if i.ticker.upper() == t]
            if matches:
                return matches[0].figi
            if res.instruments:
                return res.instruments[0].figi
    except Exception:
        return None
    return None


def load_russian_shares_figi(
    token: str, listing_levels: Iterable[int] = (1, 2, 3)
) -> list[dict[str, object]]:
    """Load FIGI codes for Russian shares using the Tinkoff Invest API.

    The loader requests the list of shares from the public instruments endpoint
    and filters the response down to securities with a Russian country of risk
    or domicile and a listing level present in ``listing_levels``.  The
    resulting dictionaries include useful metadata (ticker, FIGI, ISIN,
    exchange, class code and list level) that can be fed into the dynamic
    universe helper or stored for later reuse.

    Args:
        token: Tinkoff Invest API token.
        listing_levels: Iterable with the listing levels that should be
            included in the result.  Levels that cannot be coerced to integers
            are ignored.

    Returns:
        A list of dictionaries describing instruments.  If the Tinkoff Invest
        SDK is not installed, the token is empty or the request fails, an empty
        list is returned.
    """

    if not Client or not InstrumentStatus or not token:
        return []

    try:
        levels = {int(level) for level in listing_levels}
    except Exception:
        # Fallback to the default levels if coercion fails
        levels = {1, 2, 3}

    if not levels:
        return []

    try:
        with Client(token) as client:
            response = client.instruments.shares(
                instrument_status=InstrumentStatus.INSTRUMENT_STATUS_BASE
            )
    except Exception:
        return []

    instruments: list[dict[str, object]] = []
    for share in getattr(response, "instruments", []):
        try:
            level = int(getattr(share, "list_level", 0) or 0)
        except Exception:
            level = 0

        if level not in levels:
            continue

        country_risk = getattr(share, "country_of_risk", "").upper()
        country_dom = getattr(share, "country_of_domicile", "").upper()
        if country_risk != "RU" and country_dom != "RU":
            continue

        instruments.append(
            {
                "ticker": getattr(share, "ticker", ""),
                "figi": getattr(share, "figi", ""),
                "isin": getattr(share, "isin", ""),
                "class_code": getattr(share, "class_code", ""),
                "exchange": getattr(share, "exchange", ""),
                "list_level": level,
            }
        )

    instruments.sort(key=lambda item: (str(item.get("ticker", "")), str(item.get("figi", ""))))
    return instruments
