
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

## Плечо и шорты
В `config.yaml` добавлен блок `trading`, позволяющий включить маржинальную торговлю.

```yaml
trading:
  leverage: 2.0      # плечо 1:2 в бэктестах и отчётах
  allow_short: true  # разрешить короткие позиции во всех компонентах
```

Раздел `risk` автоматически наследует эти настройки. При необходимости можно
переопределить `max_leverage` и `allow_short` для строгого контроля риска.

## Автоматический подбор стратегий
Отчёт `results/auto_report.html` теперь сортирует стратегии по интегральному
`auto_score`, комбинирующему доходность, Sharpe/Sortino и глубину просадки.
Значение `auto_score` также сохраняется в CSV/JSON/Parquet отчётах, что упрощает
выбор лучших комбинаций для портфеля.

## Windows автонастройка
Запустите `setup_env.bat` (двойной клик) — создаст venv и установит пакет.

## Переменные окружения
См. `.env.example` внутри `moex_bot/`.


# MOEX Bot (Windows-ready)

## Установка (Windows 11)
1. Установите Python 3.10+ c опцией «Add to PATH».
2. Скачайте и установите [Microsoft Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe).
3. Распакуйте проект и запустите `setup_env.bat` — создаст виртуальное окружение
   и установит зависимости.
4. Скопируйте `.env.example` в `.env`, пропишите токены Tinkoff/Telegram.
5. Запустите тестовое соединение с Tinkoff (см. ниже), чтобы убедиться, что API
   доступен.

Команды:
- `moex-live` — запуск торговли
- `moex-backtests` — бэктесты
- `moex-server` — веб-сервер (http://127.0.0.1:8000, есть `/reports/latest`)
- `moex-all` — общий сценарий

## Переменные окружения
См. `.env.example` — храните токены только локально (не коммитьте `.env`).

## Проверка подключения к Tinkoff Invest API
После заполнения `.env` выполните в активированном окружении:

```bash
python - <<'PY'
from moex_bot.core.broker import Trader
trader = Trader(token="${TINKOFF_TOKEN}", account_id="${TINKOFF_ACCOUNT_ID}", trade_mode="sandbox")
trader.verify_connection()
PY
```

В логах появится сообщение об успешном соединении или текст ошибки.

## FIGI
Перед отправкой ордеров используйте `ticker_to_figi()` из `moex_bot.core.utils.figi`.

## DataProvider
`DataProvider(stream=..., rest=...)` делает fallback: stream→REST→cache. 
Отключение сети: `provider.enabled = False`.

## Шорты
Теперь короткие позиции доступны сразу после установки (`allow_short: true`).
Для отключения выставьте `trading.allow_short: false`.

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

## Идеи для оптимизации
- Включите Prometheus-метрики (`PROM_PORT=8001`) и отслеживайте `auto_score` и
  итоговую просадку в Grafana.
- Используйте новое поле `trading.leverage`, чтобы протестировать различные
  значения плеча в бэктестах, не меняя код стратегий.
- Примените автоподбор стратегий: запускайте `moex-backtests` по расписанию и
  автоматически импортируйте top-N стратегий из `best_strategies_top3.parquet`
  в живой портфель.
