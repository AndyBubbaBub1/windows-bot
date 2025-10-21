
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

## Новая веб-панель
- После запуска `moex-server` доступна панель `/dashboard` с графиками цен, контролем стратегий и отображением позиций.
- Панель построена на Dash/Plotly и обновляется автоматически каждые 15 секунд.
- Кнопки `Старт`/`Стоп` управляют торговым циклом напрямую через общий движок, а переключатель режима меняет sandbox/real.

## Desktop GUI
- Команда `moex-desktop` запускает кросс-платформенное Tkinter‑приложение с контролем стратегий, графиками и позицией портфеля.
- Встроенный поток запускает `Engine` асинхронно, а графики обновляются каждые 10 секунд. При закрытии окна журнал рисков сохраняется автоматически.
- Для сборки автономного `.exe` воспользуйтесь `build_windows_exe.bat` (установите extras `.[packaging]`).

## Универсальный движок Engine
- Все сценарии (`moex-live`, `moex-backtests`, веб-интерфейс) используют класс `moex_bot.core.engine.Engine`.
- Движок объединяет провайдер данных, брокера, риск-менеджер и журнал, поддерживает асинхронный live-цикл и общий API для бэктестов.
- Live-цикл работает на asyncio и предпочитает потоковый провайдер Tinkoff, переключаясь на CSV при отсутствии соединения.

## Автоматическое обновление данных
- Скрипт `python -m moex_bot.update_data` загружает свечи по всем тикерам из `config.yaml` и складывает в `data/`.
- Функцию `moex_bot.update_data.run_scheduled_update` можно добавить в планировщик (`config.yaml > schedule`) для ежедневного обновления.
- Параметры интервала и дополнительных инструментов задаются в блоке `data` конфигурации.

## Расширяемая конфигурация
- Основной файл `moex_bot/config.yaml` можно дополнять фрагментами в `moex_bot/config.d/*.yaml` (стратегии, расписание, токены).
- При загрузке конфигурации все фрагменты объединяются в один словарь. В репозитории лежат безопасные примеры (`secrets.example.yaml`).
- Чтобы хранить секреты отдельно, скопируйте пример в `secrets.yaml`, добавьте в `.gitignore` и заполните значения.

## Готовые сборки
- Dockerfile в корне собирает образ с FastAPI/Dash (`docker build -t moex-bot .`).
- Для запуска: `docker run -p 8000:8000 --env-file .env moex-bot` (подключает `/dashboard`).
- На Windows используйте `build_windows_exe.bat` для сборки автономного `.exe` через PyInstaller.

## Расширенный риск-менеджер
- `RiskManager` поддерживает индивидуальные лимиты на тикер, правила по классам активов и поток мониторинга просадок.
- После каждой сессии сохраняется журнал `results/risk_journal.csv`, который можно использовать для анализа и уведомлений.
- Новые параметры (`risk.instrument_limits`, `risk.asset_class_limits`, `risk.instrument_classes`, `risk.monitor_interval`) документированы в `config.yaml`.

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

Для динамической загрузки FIGI российских акций доступна утилита
`load_russian_shares_figi()`, которая получает через API Тинькофф Инвест все
инструменты с уровнем листинга 1–3 и страной риска/домициляцией `RU`. Полученный
список можно сохранить в кэш или передать в собственную динамическую вселенную.

## DataProvider
`DataProvider` теперь поддерживает полноценный каскад источников: stream → REST →
in-memory cache → CSV из `data/`.  Для ускорения можно отключить сеть через
`provider.disable_network()`, а `latest_price()` автоматически подхватывает
последнюю цену из кэша или файлов истории.

```python
from moex_bot.core.data_provider import DataProvider

provider = DataProvider(
    data_dir="data",
    stream=stream_adapter,
    rest=rest_adapter,
    cache_ttl=5.0,
)
price = provider.get_price("SBER")
history = provider.load_history("SBER", interval="hour", days=90)
```

## LiveTrader
`LiveTrader` объединяет брокера и риск-менеджер: умеет добавлять слиппедж к лимитным
ордерам, повторно отправлять заявки, синхронизировать позиции и equity с
`RiskManager`, а также вести журнал сделок для последующей аналитики или
отправки в мониторинг.

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
