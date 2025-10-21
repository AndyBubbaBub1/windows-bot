"""Расширенный список российских инструментов."""

from __future__ import annotations

from typing import Dict, Iterable, List, Sequence

__all__ = [
    "RU_EQUITIES_TIER1_2",
    "RU_EQUITIES_TIER3",
    "RU_BONDS",
    "RU_ETF",
    "RU_FUTURES",
    "RU_FX",
    "get_universe",
    "lookup_instrument",
]

RU_EQUITIES_TIER1_2: List[Dict[str, str]] = [
    {"ticker": "SBER", "figi": "BBG004730N88", "board": "TQBR", "class": "equity"},
    {"ticker": "GAZP", "figi": "BBG004730RP0", "board": "TQBR", "class": "equity"},
    {"ticker": "LKOH", "figi": "BBG004731032", "board": "TQBR", "class": "equity"},
    {"ticker": "GMKN", "figi": "BBG0047315M1", "board": "TQBR", "class": "equity"},
    {"ticker": "POLY", "figi": "BBG003421991", "board": "TQBR", "class": "equity"},
    {"ticker": "NVTK", "figi": "BBG004731485", "board": "TQBR", "class": "equity"},
    {"ticker": "ROSN", "figi": "BBG004731354", "board": "TQBR", "class": "equity"},
    {"ticker": "TATN", "figi": "BBG0047315H8", "board": "TQBR", "class": "equity"},
    {"ticker": "VTBR", "figi": "BBG004730ZJ9", "board": "TQBR", "class": "equity"},
    {"ticker": "CHMF", "figi": "BBG004731060", "board": "TQBR", "class": "equity"},
    {"ticker": "ALRS", "figi": "BBG004730QR0", "board": "TQBR", "class": "equity"},
    {"ticker": "MGNT", "figi": "BBG00475KDV8", "board": "TQBR", "class": "equity"},
    {"ticker": "MTSS", "figi": "BBG004731354", "board": "TQBR", "class": "equity"},
    {"ticker": "SNGS", "figi": "BBG004730Z02", "board": "TQBR", "class": "equity"},
    {"ticker": "SNGSP", "figi": "BBG004730Z11", "board": "TQBR", "class": "equity"},
    {"ticker": "IRAO", "figi": "BBG00475KHR5", "board": "TQBR", "class": "equity"},
    {"ticker": "HYDR", "figi": "BBG004730JJ8", "board": "TQBR", "class": "equity"},
    {"ticker": "AFLT", "figi": "BBG00475KH00", "board": "TQBR", "class": "equity"},
    {"ticker": "AFKS", "figi": "BBG00475KH19", "board": "TQBR", "class": "equity"},
    {"ticker": "CIAN", "figi": "BBG012Q3L9D6", "board": "TQBR", "class": "equity"},
]

RU_EQUITIES_TIER3: List[Dict[str, str]] = [
    {"ticker": "BELU", "figi": "BBG004S68473", "board": "TQBR", "class": "equity"},
    {"ticker": "FLOT", "figi": "BBG004S683W7", "board": "TQBR", "class": "equity"},
    {"ticker": "PHOR", "figi": "BBG0047315D0", "board": "TQBR", "class": "equity"},
    {"ticker": "ENPG", "figi": "BBG004731489", "board": "TQBR", "class": "equity"},
    {"ticker": "MOEX", "figi": "BBG004S68438", "board": "TQBR", "class": "equity"},
]

RU_BONDS: List[Dict[str, str]] = [
    {"ticker": "SU26238RMFS6", "figi": "BBG00R13S0H3", "board": "TQCB", "class": "bond"},
    {"ticker": "OFZ26240", "figi": "BBG00R13S0K7", "board": "TQOB", "class": "bond"},
    {"ticker": "RU000A1058F0", "figi": "BBG0143H4Z17", "board": "TQOB", "class": "bond"},
]

RU_ETF: List[Dict[str, str]] = [
    {"ticker": "FXRL", "figi": "BBG00QPYJ5H0", "board": "TQTF", "class": "etf"},
    {"ticker": "FXUS", "figi": "BBG00QPYJ5F8", "board": "TQTF", "class": "etf"},
    {"ticker": "VTBM", "figi": "BBG00QPYJ5G9", "board": "TQTF", "class": "etf"},
]

RU_FUTURES: List[Dict[str, str]] = [
    {"ticker": "RI", "figi": "FUTRI0000020", "board": "RFUD", "class": "futures"},
    {"ticker": "Si", "figi": "FUTSI0000020", "board": "RFUD", "class": "futures"},
]

RU_FX: List[Dict[str, str]] = [
    {"ticker": "USD000UTSTOM", "figi": "BBG0013HGFT4", "board": "CETS", "class": "fx"},
    {"ticker": "EUR_RUB__TOM", "figi": "BBG0013HGFT3", "board": "CETS", "class": "fx"},
]

_ALL_UNIVERSES: Sequence[List[Dict[str, str]]] = [
    RU_EQUITIES_TIER1_2,
    RU_EQUITIES_TIER3,
    RU_BONDS,
    RU_ETF,
    RU_FUTURES,
    RU_FX,
]


def get_universe(classes: Iterable[str] | None = None) -> List[Dict[str, str]]:
    target = {c.lower() for c in classes} if classes else None
    instruments: List[Dict[str, str]] = []
    for bucket in _ALL_UNIVERSES:
        for inst in bucket:
            if target and inst.get("class", "").lower() not in target:
                continue
            instruments.append(inst.copy())
    return instruments


def lookup_instrument(ticker: str) -> Dict[str, str]:
    t = ticker.strip().upper()
    for bucket in _ALL_UNIVERSES:
        for inst in bucket:
            if inst["ticker"].upper() == t:
                return inst.copy()
    return {"ticker": t, "figi": "", "board": "TQBR", "class": "equity"}
