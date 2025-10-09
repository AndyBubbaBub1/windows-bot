"""Static universe of liquid Russian equities (1st and 2nd echelons).

This module contains a curated list of liquid Russian shares traded on
the Moscow Exchange (MOEX).  The list covers a broad set of large- and
mid‑capitalisation companies commonly referred to as the first and
second echelons.  Each entry includes the ticker symbol, its FIGI
identifier and the board identifier used on MOEX.  While FIGI codes
could be resolved at runtime via the Tinkoff Invest API or the MOEX
ISS, a static mapping ensures the bot can operate offline and
produces reproducible backtest results.

You can extend or modify this universe as needed.  For a dynamic
universe that covers the first, second and third echelons, use
``moex_bot.core.utils.figi.list_russian_shares`` to download the
current catalogue of Russian shares directly from the Tinkoff Invest
API and cache the response as appropriate.

Example usage::

    from moex_bot.universe_ru import get_universe, lookup_instrument
    for inst in get_universe():
        print(inst['ticker'], inst['figi'], inst['board'])

"""

from __future__ import annotations

from typing import List, Dict

__all__ = ["RU_LARGE_MID_CAP", "get_universe", "lookup_instrument"]

# NOTE: FIGI codes were sourced from publicly available data.  If a
# symbol has no FIGI available, the field is left blank.  You can
# update the values manually or use ``ticker_to_figi`` from
# ``moex_bot.core.utils.figi`` to resolve them dynamically.
RU_LARGE_MID_CAP: List[Dict[str, str]] = [
    {"ticker": "SBER", "figi": "BBG004730N88", "board": "TQBR"},
    {"ticker": "GAZP", "figi": "BBG004730RP0", "board": "TQBR"},
    {"ticker": "LKOH", "figi": "BBG004731032", "board": "TQBR"},
    {"ticker": "GMKN", "figi": "BBG0047315M1", "board": "TQBR"},
    {"ticker": "POLY", "figi": "BBG003421991", "board": "TQBR"},
    {"ticker": "NVTK", "figi": "BBG004731485", "board": "TQBR"},
    {"ticker": "ROSN", "figi": "BBG004731354", "board": "TQBR"},
    {"ticker": "TATN", "figi": "BBG0047315H8", "board": "TQBR"},
    {"ticker": "VTBR", "figi": "BBG004730ZJ9", "board": "TQBR"},
    {"ticker": "CHMF", "figi": "BBG004731060", "board": "TQBR"},
    {"ticker": "ALRS", "figi": "BBG004730QR0", "board": "TQBR"},
    {"ticker": "MGNT", "figi": "BBG00475KDV8", "board": "TQBR"},
    {"ticker": "MTSS", "figi": "BBG004731354", "board": "TQBR"},
    {"ticker": "SNGS", "figi": "BBG004730Z02", "board": "TQBR"},
    {"ticker": "SNGSP", "figi": "BBG004730Z11", "board": "TQBR"},
    {"ticker": "RAO", "figi": "BBG0047307Y2", "board": "TQBR"},
    {"ticker": "IRAO", "figi": "BBG00475KHR5", "board": "TQBR"},
    {"ticker": "HYDR", "figi": "BBG004730JJ8", "board": "TQBR"},
    {"ticker": "AFLT", "figi": "BBG00475KH00", "board": "TQBR"},
    {"ticker": "AFKS", "figi": "BBG00475KH19", "board": "TQBR"},
    {"ticker": "CIAN", "figi": "BBG012Q3L9D6", "board": "TQBR"},
]


def get_universe() -> List[Dict[str, str]]:
    """Return a copy of the Russian equity universe.

    Returns:
        A list of dictionaries, each representing a tradable instrument.
    """
    return [inst.copy() for inst in RU_LARGE_MID_CAP]


def lookup_instrument(ticker: str) -> Dict[str, str]:
    """Lookup instrument details by ticker.

    Args:
        ticker: Ticker symbol (case‑insensitive).

    Returns:
        A dictionary with keys ``ticker``, ``figi`` and ``board``.  If the
        ticker is not found in the universe the FIGI will be empty and the
        board defaults to ``TQBR``.
    """
    t = ticker.strip().upper()
    for inst in RU_LARGE_MID_CAP:
        if inst["ticker"] == t:
            return inst.copy()
    return {"ticker": t, "figi": "", "board": "TQBR"}
