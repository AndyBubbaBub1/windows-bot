"""CLI diagnostics tool for verifying environment and broker connectivity."""

from __future__ import annotations

import logging
import os
import platform
import sys
from pathlib import Path

from moex_bot.core.config import load_config
from moex_bot.core.logging_config import configure_logging

try:
    from tinkoff.invest import Client
except Exception:  # pragma: no cover - optional dependency
    Client = None  # type: ignore


def _detect_windows() -> bool:
    return platform.system().lower().startswith("win")


def _check_windows_setup(project_root: Path, logger: logging.Logger) -> None:
    script = project_root / "setup_env.bat"
    if script.exists():
        logger.info("setup_env.bat found → double click to bootstrap venv on Windows 11.")
    else:
        logger.warning("setup_env.bat not found at %s", script)
    python_version = sys.version.split()[0]
    logger.info("Python interpreter: %s", python_version)
    if not _detect_windows():
        logger.info("Diagnostics running outside Windows. For Windows 11 deploy, copy the project and run setup_env.bat.")


def _check_tinkoff_connectivity(cfg: dict[str, object], logger: logging.Logger) -> None:
    tinkoff_cfg = cfg.get("tinkoff", {}) or {}
    token = os.getenv("TINKOFF_TOKEN") or tinkoff_cfg.get("token") or ""
    sandbox_flag = tinkoff_cfg.get("sandbox")
    sandbox_env = os.getenv("TINKOFF_SANDBOX")
    sandbox = str(sandbox_env or sandbox_flag).lower() in {"1", "true", "yes"}
    if not token:
        logger.warning("Tinkoff token not provided. Set TINKOFF_TOKEN in .env for live connectivity checks.")
        return
    if Client is None:
        logger.warning("tinkoff-invest SDK is not installed; run 'pip install tinkoff-invest' to enable API calls.")
        return
    try:
        with Client(token, sandbox=sandbox) as client:
            accounts = client.users.get_accounts().accounts
            logger.info("Tinkoff API reachable. Accounts available: %s", [acc.id for acc in accounts])
    except Exception as exc:
        logger.warning("Failed to query Tinkoff API: %s", exc)


def _summarise_margin(cfg: dict[str, object], logger: logging.Logger) -> None:
    margin_cfg = cfg.get("margin") or {}
    risk_cfg = cfg.get("risk") or {}
    leverage = margin_cfg.get("max_leverage") or risk_cfg.get("max_leverage")
    borrow_rate = margin_cfg.get("borrow_rate_pct") or risk_cfg.get("borrow_rate_pct")
    logger.info("Configured max leverage: %s", leverage or 1.0)
    if borrow_rate:
        logger.info("Annual borrow rate: %s%%", borrow_rate)


def main() -> None:
    configure_logging()
    logger = logging.getLogger("moex_bot.diagnostics")
    cfg = load_config()
    project_root = Path(__file__).resolve().parents[1]
    logger.info("Project root: %s", project_root)
    _check_windows_setup(project_root, logger)
    _summarise_margin(cfg, logger)
    _check_tinkoff_connectivity(cfg, logger)
    logger.info("Diagnostics complete.")


if __name__ == "__main__":  # pragma: no cover - script entry point
    main()
