from __future__ import annotations
from typing import Optional
try:
    from tinkoff.invest import Client
except Exception:
    Client = None

# Bring static universe helper from moex_bot.universe_ru.  This keeps the
# figi module self‑contained but enables callers to retrieve a list of
# tradable instruments without importing the universe module directly.
def get_universe() -> list[dict[str, str]]:
    """Return the list of Russian instruments available in the bot's universe.

    This helper forwards to :func:`moex_bot.universe_ru.get_universe` and
    falls back to returning an empty list if the universe cannot be
    imported (e.g. stripped during packaging).  Callers should treat
    the returned list as read‑only.

    Returns:
        List of dictionaries with ``ticker``, ``figi`` and ``board`` keys.
    """
    try:
        from moex_bot.universe_ru import get_universe as _get
        return _get()
    except Exception:
        return []

def ticker_to_figi(ticker: str, token: str) -> Optional[str]:
    """Resolve MOEX ticker to FIGI using Tinkoff Invest API."""
    if not Client or not ticker or not token:
        return None
    t = ticker.strip().upper()
    try:
        with Client(token) as client:
            res = client.instruments.find_instrument(query=t)
            # prefer exact ticker match
            matches = [i for i in res.instruments if i.ticker.upper() == t]
            if matches:
                return matches[0].figi
            if res.instruments:
                return res.instruments[0].figi
    except Exception:
        return None
    return None
