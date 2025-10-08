
# MOEX Bot (packaged)

## Установка (разработка)
```bash
python -m venv .venv
# Windows:
#   .venv\Scripts\activate
# Linux/Mac:
#   source .venv/bin/activate
pip install -e .
```

## Команды CLI
- `moex-live` — запустить живой трейдинг
- `moex-backtests` — бэктесты
- `moex-server` — веб-сервер (FastAPI/Uvicorn)
- `moex-all` — последовательный запуск (бэктест → сервер → планировщик)

## Windows автонастройка
Запустите `setup_env.bat` (двойной клик) — создаст venv и установит пакет.

## Переменные окружения
См. `.env.example` внутри `moex_bot/`.


# MOEX Bot (Windows-ready)

## Установка (Windows 11)
1) Установите Python 3.10+.
2) Распакуйте архив, запустите `setup_env.bat` (создаст venv и поставит пакет).
3) Скопируйте `.env.example` в `.env` и заполните переменные.

Команды:
- `moex-live` — запуск торговли
- `moex-backtests` — бэктесты
- `moex-server` — веб-сервер (http://127.0.0.1:8000, есть `/reports/latest`)
- `moex-all` — общий сценарий

## Переменные окружения
См. `.env.example` — храните токены только локально (не коммитьте `.env`).

## FIGI
Перед отправкой ордеров используйте `ticker_to_figi()` из `moex_bot.core.utils.figi`.

## DataProvider
`DataProvider(stream=..., rest=...)` делает fallback: stream→REST→cache. 
Отключение сети: `provider.enabled = False`.

## Шорты
Контролируйте через `allow_short` в `config.yaml`.

## Подключение стриминга с резервом REST

```python
import os
from moex_bot.core.data_provider import DataProvider
from moex_bot.core.adapters.stream_tinkoff import TinkoffStreamAdapter
from moex_bot.core.adapters.rest_tinkoff import TinkoffRestAdapter

token = os.getenv("TINKOFF_TOKEN")
tickers = ["SBER","GAZP","LKOH"]

stream = TinkoffStreamAdapter(token, tickers=tickers)
rest = TinkoffRestAdapter(token)
provider = DataProvider(stream=stream, rest=rest)

# старт стрима и работа
stream.start()
price = provider.get_price("SBER")  # попробует stream, затем REST, затем cache
```

Если связь недоступна:
```python
provider.enabled = False  # читать только из кэша (без сети)
```

## Telegram подтверждения (/confirm /cancel)

- `/buy SBER 10` → сохраняется «намерение» в SQLite, бот просит подтверждение.
- `/confirm` → бот резолвит FIGI и вызывает `TradeCallbacks.execute_order(...)` (замените на реальный вызов post_order).
- `/cancel` → удаляет последнюю заявку пользователя.

Файл состояния: `results/state.sqlite` (создаётся автоматически).
Разрешённые пользователи берутся из `ALLOWED_USERS` (кома-разделённый список user_id). Если список не задан — бот пускает всех.
