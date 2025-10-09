
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
- `moex-diagnostics` — проверка окружения и подключения к Tinkoff

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

## Плечо и маржинальная торговля
- `margin.max_leverage` — желаемое плечо в бэктестах (используется и в риск-менеджере).
- `margin.borrow_rate_pct` / `margin.short_borrow_rate_pct` — годовые ставки за заёмное плечо (учитываются в доходности).
- В отчётах появляются поля `avg_leverage` и `max_leverage`, а риск-менеджер контролирует совокупную экспозицию.

## Автоподбор стратегий
- Блок `auto_selector` в `config.yaml` управляет фильтрацией по Sharpe/просадке и диверсификацией.
- После `moex-backtests` в `results/` появляются файлы `auto_selected_strategies.(csv|json)` и `auto_selected_config.yaml` с готовой конфигурацией и весами.
- Включите `auto_selector.hyperopt.enabled` и добавьте `per_strategy` с сеткой параметров, чтобы дополнительно прогонять `hyperopt`.

## Диагностика Windows/Tinkoff
- Запустите `moex-diagnostics` (после `pip install -e .`) — проверяет наличие `setup_env.bat`, версию Python и доступность Tinkoff API.
- Для проверки API положите токен в `.env` (`TINKOFF_TOKEN`) или переменные окружения.

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
