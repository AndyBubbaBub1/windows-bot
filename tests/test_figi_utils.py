from __future__ import annotations

from types import SimpleNamespace

import pytest

from moex_bot.core.utils import figi


class _FakeSharesResponse:
    def __init__(self, instruments):
        self.instruments = instruments


class _FakeInstruments:
    def __init__(self, instruments):
        self._instruments = instruments

    def shares(self, instrument_status=None):  # pragma: no cover - simple proxy
        return _FakeSharesResponse(self._instruments)


class _FakeClient:
    def __init__(self, token, instruments=None, fail=False):
        self.token = token
        self._instruments = instruments or []
        self._fail = fail

    def __enter__(self):  # pragma: no cover - trivial
        if self._fail:
            raise RuntimeError("boom")
        return self

    def __exit__(self, exc_type, exc, tb):  # pragma: no cover - trivial
        return False

    @property
    def instruments(self):  # pragma: no cover - trivial
        return _FakeInstruments(self._instruments)


@pytest.fixture(autouse=True)
def _patch_instrument_status(monkeypatch):
    monkeypatch.setattr(figi, "InstrumentStatus", SimpleNamespace(INSTRUMENT_STATUS_BASE=object()))
    yield
    monkeypatch.setattr(figi, "InstrumentStatus", None)


def test_list_russian_shares_filters(monkeypatch):
    shares = [
        SimpleNamespace(
            ticker="SBER",
            figi="FIGI1",
            isin="RU0009029540",
            class_code="TQBR",
            list_level=1,
            name="Sberbank",
            exchange="MOEX",
            country_of_risk="RU",
            otc_flag=False,
        ),
        SimpleNamespace(  # Wrong country
            ticker="AAPL",
            figi="FIGI2",
            isin="US0378331005",
            class_code="SPBXM",
            list_level=1,
            name="Apple",
            exchange="SPB",
            country_of_risk="US",
            otc_flag=False,
        ),
        SimpleNamespace(  # OTC instrument should be skipped
            ticker="GAZP",
            figi="FIGI3",
            isin="RU0007661625",
            class_code="TQBR",
            list_level=3,
            name="Gazprom",
            exchange="MOEX",
            country_of_risk="RU",
            otc_flag=True,
        ),
        SimpleNamespace(  # Different echelon
            ticker="VTBR",
            figi="FIGI4",
            isin="RU000A0JP5V6",
            class_code="TQBR",
            list_level=2,
            name="VTB",
            exchange="MOEX",
            country_of_risk="RU",
            otc_flag=False,
        ),
    ]

    fake_client = lambda token: _FakeClient(token, instruments=shares)  # noqa: E731
    monkeypatch.setattr(figi, "Client", fake_client)

    result = figi.list_russian_shares("token", levels={1, 2})
    assert [item["ticker"] for item in result] == ["SBER", "VTBR"]


def test_list_russian_shares_handles_failures(monkeypatch):
    # Missing client should lead to an empty list.
    monkeypatch.setattr(figi, "Client", None)
    assert figi.list_russian_shares("token") == []

    # Restoring the client but forcing a failure should also yield an empty list.
    monkeypatch.setattr(figi, "Client", lambda token: _FakeClient(token, fail=True))
    assert figi.list_russian_shares("token") == []

