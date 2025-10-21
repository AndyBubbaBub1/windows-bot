"""Асинхронный торговый цикл поверх единого движка."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from .config import load_config
from .engine import Engine

logger = logging.getLogger(__name__)

RUNNING: bool = False
TRADE_MODE: str = "sandbox"
ENGINE: Engine | None = None


def _ensure_engine(cfg: Dict[str, Any] | None = None) -> Engine:
    """Возвращает singleton движка, пересоздавая его при необходимости."""

    global ENGINE
    if cfg is not None:
        ENGINE = Engine.from_config(cfg)
    elif ENGINE is None:
        ENGINE = Engine.from_config()
    return ENGINE


def start_trading() -> None:
    """Запускаем торговый цикл."""

    global RUNNING
    engine = _ensure_engine()
    engine.start()
    RUNNING = True


def stop_trading() -> None:
    """Останавливаем торговый цикл."""

    global RUNNING
    engine = _ensure_engine()
    engine.stop()
    RUNNING = False


def toggle_mode() -> str:
    """Переключаем режим между ``sandbox`` и ``real``."""

    global TRADE_MODE
    engine = _ensure_engine()
    TRADE_MODE = engine.toggle_mode()
    return TRADE_MODE


def run_live_cycle(cfg: Dict[str, Any] | None = None) -> None:
    """Выполняем одну итерацию цикла через :class:`Engine`."""

    global RUNNING, TRADE_MODE
    if not RUNNING:
        logger.info("⏸ Торговый цикл приостановлен")
        return
    if cfg is None:
        cfg = load_config()
    cfg["trade_mode"] = TRADE_MODE
    engine = _ensure_engine(cfg)
    engine.state.running = RUNNING
    engine.state.trade_mode = TRADE_MODE
    engine.trader.trade_mode = TRADE_MODE
    try:
        asyncio.run(engine.run_live_once())
    except RuntimeError:
        # Event loop уже запущен (например, внутри uvicorn).  В этом случае
        # используем существующий цикл через create_task.
        loop = asyncio.get_event_loop()
        loop.run_until_complete(engine.run_live_once())

