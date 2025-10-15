from types import SimpleNamespace

import pytest

from moex_bot.core.utils import figi


def test_load_russian_shares_figi_returns_empty_without_sdk(monkeypatch):
    monkeypatch.setattr(figi, "Client", None)
    monkeypatch.setattr(figi, "InstrumentStatus", None)
    assert figi.load_russian_shares_figi("token") == []


def test_load_russian_shares_figi_filters_by_listing_levels_and_country(monkeypatch):
    shares = [
        SimpleNamespace(
            ticker="SBER",
            figi="BBG00000001",
            isin="ISIN0001",
            class_code="TQBR",
            exchange="MOEX",
            list_level=1,
            country_of_risk="RU",
            country_of_domicile="RU",
        ),
        SimpleNamespace(
            ticker="GAZP",
            figi="BBG00000002",
            isin="ISIN0002",
            class_code="TQBR",
            exchange="MOEX",
            list_level=4,
            country_of_risk="RU",
            country_of_domicile="RU",
        ),
        SimpleNamespace(
            ticker="YNDX",
            figi="BBG00000003",
            isin="ISIN0003",
            class_code="SPBXM",
            exchange="SPB",
            list_level=3,
            country_of_risk="US",
            country_of_domicile="US",
        ),
        SimpleNamespace(
            ticker="MGNT",
            figi="BBG00000004",
            isin="ISIN0004",
            class_code="TQBR",
            exchange="MOEX",
            list_level=2,
            country_of_risk="RU",
            country_of_domicile="CY",
        ),
    ]

    status_holder: dict[str, object] = {}

    class DummyInstrumentsService:
        def shares(self, instrument_status):  # pragma: no cover - passthrough
            status_holder["status"] = instrument_status
            return SimpleNamespace(instruments=shares)

    class DummyClient:
        def __init__(self, token):
            self.token = token
            self.instruments = DummyInstrumentsService()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(figi, "Client", DummyClient)
    monkeypatch.setattr(
        figi,
        "InstrumentStatus",
        SimpleNamespace(INSTRUMENT_STATUS_BASE="BASE"),
    )

    result = figi.load_russian_shares_figi("token", listing_levels=[1, 2, 3])

    assert status_holder["status"] == "BASE"
    assert [item["ticker"] for item in result] == ["MGNT", "SBER"]
    assert all(item["figi"].startswith("BBG") for item in result)
    assert {item["list_level"] for item in result} == {1, 2}
    assert all(item["exchange"] for item in result)
