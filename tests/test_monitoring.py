"""Tests covering Prometheus metrics integration."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from moex_bot.core import monitoring
from moex_bot.core.alerts import AlertDispatcher
from moex_bot.core.broker import Trader


@pytest.fixture(autouse=True)
def reset_metrics() -> None:
    monitoring.order_submissions_total._metrics.clear()
    monitoring.outstanding_orders_gauge._value.set(0)
    monitoring.risk_limit_breaches_total._metrics.clear()
    monitoring.alert_dispatch_counter._metrics.clear()


def test_order_metrics_increment_on_buy(monkeypatch: pytest.MonkeyPatch) -> None:
    trader = Trader(token=None, account_id=None, sandbox=True)
    trader.buy('FIGI123', lots=2)
    value = monitoring.order_submissions_total.labels(side='buy')._value.get()
    assert value == 1.0
    assert monitoring.outstanding_orders_gauge._value.get() == 0.0


def test_alert_dispatcher_records_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_post(url, json=None, timeout=0):  # noqa: D401 - test stub
        captured['url'] = url
        captured['payload'] = json
        return SimpleNamespace(status_code=200)

    monkeypatch.setattr('moex_bot.core.alerts.requests.post', fake_post)
    dispatcher = AlertDispatcher(telegram_token='token', telegram_chat_id='chat', slack_webhook=None, min_interval_seconds=0)
    dispatcher.send('hello')
    value = monitoring.alert_dispatch_counter.labels(channel='telegram')._value.get()
    assert value == 1.0
    assert 'token' in captured['url']
