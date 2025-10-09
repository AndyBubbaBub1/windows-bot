"""Integration tests for FIGI utilities."""

from __future__ import annotations

from types import SimpleNamespace

from moex_bot.core.utils import figi


def test_ticker_to_figi_prefers_exact_match(monkeypatch) -> None:
    instruments = [SimpleNamespace(ticker='SBER', figi='FIGI1'), SimpleNamespace(ticker='GAZP', figi='FIGI2')]

    class FakeClient:
        def __init__(self, token):
            self.token = token
            self.instruments = self

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def find_instrument(self, query):  # noqa: D401 - fake SDK call
            return SimpleNamespace(instruments=instruments)

    monkeypatch.setattr('moex_bot.core.utils.figi.Client', FakeClient)
    result = figi.ticker_to_figi('SBER', 'token')
    assert result == 'FIGI1'


def test_ticker_to_figi_returns_first_when_no_exact(monkeypatch) -> None:
    instruments = [SimpleNamespace(ticker='OTHER', figi='FIGI3')]

    class FakeClient:
        def __init__(self, token):
            self.token = token
            self.instruments = self

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def find_instrument(self, query):
            return SimpleNamespace(instruments=instruments)

    monkeypatch.setattr('moex_bot.core.utils.figi.Client', FakeClient)
    result = figi.ticker_to_figi('SBER', 'token')
    assert result == 'FIGI3'


def test_ticker_to_figi_handles_failures(monkeypatch) -> None:
    class FakeClient:
        def __init__(self, token):
            raise RuntimeError('boom')

    monkeypatch.setattr('moex_bot.core.utils.figi.Client', FakeClient)
    assert figi.ticker_to_figi('SBER', 'token') is None
