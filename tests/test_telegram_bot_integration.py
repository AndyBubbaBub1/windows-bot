"""Integration tests for the Telegram bot command flow."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from moex_bot.telegram_ext.bot import TgBot, TradeCallbacks


@dataclass
class DummyCallbacks(TradeCallbacks):
    calls: list

    def execute_order(self, figi: str, lots: int, side: str) -> str:  # noqa: D401 - interface fulfilment
        self.calls.append((figi, lots, side))
        return f"{side} {lots} {figi}"


class DummyMessage:
    def __init__(self) -> None:
        self.replies: list[str] = []

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


class DummyUpdate:
    def __init__(self, user_id: int) -> None:
        self.effective_user = SimpleNamespace(id=user_id)
        self.message = DummyMessage()
        self.effective_message = self.message


@pytest.mark.asyncio
async def test_confirm_command_executes_trade(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    callbacks = DummyCallbacks(calls=[])
    bot = TgBot(db_path=str(tmp_path / 'orders.db'), tinkoff_token='token', allowed_users=[123], trade_cb=callbacks)
    bot.state.save_intent(123, 'SBER', 3, 'BUY')

    async def fake_reply(text: str) -> None:  # noqa: D401 - test stub
        update.message.replies.append(text)

    update = DummyUpdate(123)
    update.message.reply_text = fake_reply  # type: ignore[assignment]

    monkeypatch.setattr('moex_bot.telegram_ext.bot.ticker_to_figi', lambda ticker, token: 'FIGI123')
    await bot.confirm_cmd(update, None)
    assert callbacks.calls == [('FIGI123', 3, 'BUY')]
    assert any('✅' in reply for reply in update.message.replies)


@pytest.mark.asyncio
async def test_confirm_command_handles_missing_figi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    callbacks = DummyCallbacks(calls=[])
    bot = TgBot(db_path=str(tmp_path / 'orders.db'), tinkoff_token='token', allowed_users=[123], trade_cb=callbacks)
    bot.state.save_intent(123, 'SBER', 3, 'BUY')
    update = DummyUpdate(123)
    monkeypatch.setattr('moex_bot.telegram_ext.bot.ticker_to_figi', lambda ticker, token: None)
    await bot.confirm_cmd(update, None)
    assert not callbacks.calls
    assert update.message.replies[-1].startswith('Не удалось найти FIGI')
