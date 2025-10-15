from __future__ import annotations
import os
import time
from pathlib import Path

from moex_bot.core.data_provider import DataProvider
from moex_bot.core.adapters.stream_tinkoff import TinkoffStreamAdapter
from moex_bot.core.adapters.rest_tinkoff import TinkoffRestAdapter
from moex_bot.telegram_ext.bot import TgBot, TradeCallbacks

TICKERS = ["SBER","GAZP","LKOH"]

class TraderCallbacks(TradeCallbacks):
    def execute_order(self, figi: str, lots: int, side: str) -> str:
        # Здесь подключите реальный вызов брокера (Tinkoff Invest API: orders.post_order)
        # Пока просто логика-демо:
        return f"{side} {lots} lot(s) FIGI={figi}"

def main() -> None:
    token = os.getenv("TINKOFF_TOKEN")
    # --- Data provider with stream+REST ---
    stream = TinkoffStreamAdapter(token, tickers=TICKERS)
    rest = TinkoffRestAdapter(token)
    provider = DataProvider(stream=stream, rest=rest)
    stream.start()

    # --- Telegram bot ---
    allowed_env = os.getenv("ALLOWED_USERS","").strip()
    allowed = [int(x) for x in allowed_env.split(",") if x.strip().isdigit()]
    db_path = Path("./results/state.sqlite")
    _bot = TgBot(db_path=str(db_path), tinkoff_token=token, allowed_users=allowed, trade_cb=TraderCallbacks())

    # Запускаем бота в отдельном процессе/терминале при необходимости.
    # Для простоты — если хотим, запускаем его синхронно:
    # bot.run()

    # Демонстрационный цикл чтения цены и логики (без реальных ордеров)
    try:
        for _ in range(10):
            px = provider.get_price("SBER")
            print(f"[live] SBER={px}")
            time.sleep(1.0)
    finally:
        stream.stop()

if __name__ == "__main__":
    main()
