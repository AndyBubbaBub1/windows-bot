"""CLI скрипт для запуска живого цикла через :class:`Engine`."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from dotenv import load_dotenv

from moex_bot.core.config import load_config
from moex_bot.core.engine import Engine

load_dotenv()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    cfg = load_config()
    engine = Engine.from_config(cfg)
    engine.start()

    async def _runner() -> None:
        while engine.state.running:
            await engine.run_live_once()
            await asyncio.sleep(float(cfg.get("live_interval", 5.0)))

    try:
        asyncio.run(_runner())
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()
        journal_path = Path(cfg.get("results_dir", "results")) / "risk_journal.csv"
        engine.journal.flush(journal_path)


if __name__ == "__main__":
    main()
