# MOEX Bot

Комплексное решение для алгоритмической торговли через Tinkoff Invest API. Проект объединяет
единый движок `Engine`, обновляемые рыночные данные, расширенный риск‑менеджер и набор
веб/desktop интерфейсов для управления стратегиями.

## Установка (разработка)

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -e .
```

После установки доступны команды:

- `moex-live` — запуск живого цикла через `Engine`.
- `moex-backtests` — пакетный прогон стратегий и формирование отчётов.
- `moex-server` — FastAPI + Dash сервер с веб‑панелью `/dashboard`.
- `moex-all` — последовательный запуск бэктестов, сервера и планировщика.
- `moex-diagnostics` — проверка окружения и подключения к Tinkoff API.
- `moex-desktop` — настольная оболочка на Tkinter.
- `moex-package` — сборка Docker-образа или автономного `.exe`.

## Установка (Windows)

1. Установите Python 3.10+.
2. Запустите `setup_env.bat` (создаст виртуальное окружение и установит пакет).
3. Скопируйте `.env.example` в `.env`, заполните токены (`TINKOFF_TOKEN`, `TELEGRAM_TOKEN` и т.д.).

Готовые батники `run_live.bat`, `run_backtests.bat`, `run_server.bat` и др. запускают соответствующие
сценарии без открытия терминала Python.

## Графические интерфейсы

### Веб‑панель `/dashboard`

Запустите `moex-server` и откройте `http://127.0.0.1:8000/dashboard`.

- **Обзор** — свечной график с SMA/волатильностью, таблица позиций, карта риск‑метрик и диаграмма экспозиции.
- **Стратегии** — чекбоксы включения/отключения, запуск бэктеста в один клик и отображение активных алгоритмов.
- **Риски** — live‑журнал RiskManager, история сессий (PnL, просадки, режим торговли).
- **Планировщик** — визуализация cron‑задач из `config.yaml`.

Панель обновляется каждые 15 секунд, напрямую используя методы `Engine`
(`list_strategies()`, `set_strategy_enabled()`, `positions_snapshot()` и т.д.).

### Настольное приложение `moex-desktop`

Tkinter-клиент подключается к общему движку и обеспечивает:

- кнопки «Старт», «Стоп», «Переключить режим»;
- чекбоксы стратегий, синхронизированные с состоянием движка;
- карточки капитала, PnL, gross exposure и просадки;
- таблицу позиций и live‑журнал RiskManager;
- запуск бэктеста без терминала.

Интерфейс обновляет данные каждые 2 секунды и корректно завершает торговую сессию при закрытии окна.

## Универсальный движок Engine

Все сценарии (`moex-live`, `moex-backtests`, веб/desktop UI) используют класс
`moex_bot.core.engine.Engine`. Движок инкапсулирует провайдер данных, брокера, риск‑менеджер,
портфельный менеджер и журнал сессий.

- Асинхронный live‑цикл предпочитает потоковый провайдер Tinkoff (WebSocket), переключаясь на REST/CSV при сбое.
- Методы `start()`, `run_live_once()` и `stop()` управляют торговым циклом, поддерживается переключение sandbox/live режимов.
- `run_backtests()` делегирует расчёты `core.backtester`, сохраняя единые настройки комиссий, плеча и риска.
- `session_history()` и `risk_journal` сохраняют сводки после каждой сессии и используются веб/desktop интерфейсами.

## Автоматическое обновление данных

`moex_bot/update_data.py` загружает исторические свечи, обновляет вселенную инструментов
(акции 1–3 уровней, ETF, облигации, фьючерсы, валюты) и экспортирует список FIGI.

Раздел `schedule.data_update` в `config.yaml` добавляет ежедневное обновление:

```yaml
schedule:
  data_update:
    func: "moex_bot.update_data.run_scheduled_update"
    cron: "30 6 * * 1-5"
```

Запустить все задачи можно командой `moex-all` или скриптом `run_scheduler.py`. Планировщик построен на APScheduler.

## Расширенный риск‑менеджер

`RiskManager` поддерживает:

- лимиты по инструментам (`max_position_pct`, `max_lots`, `max_leverage`);
- ограничения по классам активов и автоматическое принудительное закрытие;
- поток мониторинга просадки с регулируемым интервалом;
- журналы событий и equity (`results/risk_journal.csv`, `results/session_history.csv`);
- уведомления в Telegram и интеграцию с GUI.

Метод `session_summary()` предоставляет консистентные метрики для интерфейсов и отчётов.

## Конфигурация

Основной файл — `config.yaml`; дополнительные фрагменты можно положить в `config.d/*.yaml`.
Загрузчик `load_config` объединяет их и разворачивает переменные окружения (`${VAR}`).

Основные блоки:

- `data` — интервал/глубина истории, дополнительные тикеры, расширенный список FIGI и параметры экспорта.
- `results_dir`/`database` — каталог результатов и путь к SQLite-журналу (`results/history.db` по умолчанию).
- `strategies` — параметры стратегий и тикеры live‑наблюдения.
- `risk` — настройки RiskManager, лимиты по инструментам и классам активов, параметры мониторинга.
- `portfolio` — целевые доли стратегий для `PortfolioManager`.
- `auto_selector` — фильтры автоподбора стратегий в отчётах.
- `schedule` — cron‑задачи (бэктесты, live‑цикл, обновление данных).
- `server` и `tinkoff` — настройки FastAPI/Dash и брокерского API.

## Расширение вселенной инструментов

В модуле `moex_bot/update_data.py` доступны фильтры по ликвидности, уровню листинга и классам активов.
Для загрузки FIGI российских бумаг используйте хелперы из `moex_bot/core/utils/figi_utils.py`.
Готовый экспорт сохраняется в `data/universe.csv` и может использоваться стратегиями и отчётами.

## DataProvider и LiveTrader

`DataProvider` реализует каскад источников (stream → REST → кэш → CSV) и позволяет отключать сеть через
`provider.disable_network()`. Пример:

```python
from moex_bot.core.data_provider import DataProvider

provider = DataProvider(data_dir="data")
price = provider.get_price("SBER")
history = provider.load_history("SBER", interval="hour", days=90)
```

`Trader` и обёртка LiveTrader добавляют управление слиппеджем, повторную отправку заявок,
синхронизацию позиций с риск‑менеджером и журнал сделок для мониторинга.

## Автоподбор стратегий

Раздел `auto_selector` конфигурации управляет фильтрацией по Sharpe/просадке, диверсификацией и гипероптимизацией.
После `moex-backtests` в `results/` появляются файлы `auto_selected_strategies.(csv|json)` и
`auto_selected_config.yaml` с готовыми параметрами и весами.

## Диагностика и поддержка

- `moex-diagnostics` проверяет версии Python, наличие зависимостей и доступность Tinkoff API.
- `prometheus-client` используется для экспорта метрик; порт задаётся переменной `PROM_PORT`.
- Telegram-уведомления включаются при заполнении `telegram.token` и `telegram.chat_id`.

## Дистрибуция

Команда `moex-package` помогает собрать:

- `moex-package exe --entry moex_bot.run_server:main` — автономный `.exe` (требуется `pyinstaller`).
- `moex-package docker --tag yourname/moex-bot:latest` — Docker-образ на основе `moex_bot/Dockerfile`.

## Переменные окружения

Используйте `.env` (см. `.env.example`) или переменные системы:

- `TINKOFF_TOKEN`, `TINKOFF_ACCOUNT_ID`, `TINKOFF_SANDBOX`, `TINKOFF_SANDBOX_TOKEN`.
- `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`, `MOEX_ADMIN_TOKEN`.
- `PROM_PORT`, `MOEX_API_HOST`, `MOEX_API_PORT`.

Не коммитьте `.env`; храните секреты только локально.
