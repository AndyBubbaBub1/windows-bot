from __future__ import annotations
import os
from typing import List, Optional
from dataclasses import dataclass

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from moex_bot.telegram_ext.commands import HELP_TEXT, parse_order_args
from moex_bot.core.order_state import OrderState
from moex_bot.core.utils.figi import ticker_to_figi

@dataclass
class TradeCallbacks:
    def execute_order(self, figi: str, lots: int, side: str) -> str:
        """Override this to actually send order to broker. Should return human message."""
        return f"DEMO {side} {lots} lot(s) {figi}"

class TgBot:
    def __init__(self, db_path: str, tinkoff_token: str, allowed_users: List[int], trade_cb: TradeCallbacks):
        self.allowed = set(int(u) for u in allowed_users if str(u).strip())
        self.state = OrderState(Path(db_path))
        self.token = os.getenv("TELEGRAM_TOKEN")
        self.tinkoff_token = tinkoff_token
        self.trade_cb = trade_cb

    async def _auth(self, update: Update) -> bool:
        uid = update.effective_user.id if update.effective_user else None
        if not uid or (self.allowed and uid not in self.allowed):
            await update.effective_message.reply_text("⛔ Доступ запрещён")
            return False
        return True

    async def help_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(HELP_TEXT)

    async def status_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._auth(update):
            return
        # Простая заглушка: подключите сюда реальные баланс/позиции
        await update.message.reply_text("Статус: баланс и позиции будут показаны здесь.")

    async def buy_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._auth(update):
            return
        ticker, lots, err = parse_order_args(update.message.text)
        if err:
            await update.message.reply_text(f"⚠️ {err}")
            return
        oid = self.state.save_intent(update.effective_user.id, ticker, lots, "BUY")
        await update.message.reply_text(f"Подтвердить покупку {ticker} x{lots}? Напишите /confirm или /cancel (#{oid}).")

    async def sell_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._auth(update):
            return
        ticker, lots, err = parse_order_args(update.message.text)
        if err:
            await update.message.reply_text(f"⚠️ {err}")
            return
        oid = self.state.save_intent(update.effective_user.id, ticker, lots, "SELL")
        await update.message.reply_text(f"Подтвердить продажу {ticker} x{lots}? Напишите /confirm или /cancel (#{oid}).")

    async def confirm_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._auth(update):
            return
        row = self.state.pop_last_for_user(update.effective_user.id)
        if not row:
            await update.message.reply_text("Нет заявок для подтверждения.")
            return
        _, ticker, lots, side = row
        figi = ticker_to_figi(ticker, self.tinkoff_token)
        if not figi:
            await update.message.reply_text(f"Не удалось найти FIGI для {ticker}.")
            return
        msg = self.trade_cb.execute_order(figi=figi, lots=lots, side=side)
        await update.message.reply_text(f"✅ Исполнено: {msg}")

    async def cancel_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._auth(update):
            return
        row = self.state.pop_last_for_user(update.effective_user.id)
        if not row:
            await update.message.reply_text("Отменять нечего.")
            return
        await update.message.reply_text("❎ Последняя заявка отменена.")

    def run(self) -> None:
        if not self.token:
            raise RuntimeError("TELEGRAM_TOKEN не задан")
        app = ApplicationBuilder().token(self.token).build()
        app.add_handler(CommandHandler("help", self.help_cmd))
        app.add_handler(CommandHandler("status", self.status_cmd))
        app.add_handler(CommandHandler("buy", self.buy_cmd))
        app.add_handler(CommandHandler("sell", self.sell_cmd))
        app.add_handler(CommandHandler("confirm", self.confirm_cmd))
        app.add_handler(CommandHandler("cancel", self.cancel_cmd))
        app.run_polling()
