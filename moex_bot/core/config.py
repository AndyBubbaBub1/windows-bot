"""Configuration loading utilities with schema validation."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml
from dotenv import load_dotenv

from .settings import AppSettings, expand_env_values


def _ensure_path(path: str | Path | None) -> Path:
    if path is not None:
        return Path(path)
    return Path(__file__).resolve().parents[1] / 'config.yaml'


def _read_config(path: Path) -> Dict[str, Any]:
    with path.open('r', encoding='utf-8') as handle:
        raw = yaml.safe_load(handle) or {}
    return expand_env_values(raw)


def load_settings(path: str | Path | None = None) -> AppSettings:
    cfg_path = _ensure_path(path)
    if not cfg_path.exists():
        raise FileNotFoundError(f'Configuration file not found: {cfg_path}')
    load_dotenv()
    data = _read_config(cfg_path)
    if hasattr(AppSettings, 'model_validate'):
        return AppSettings.model_validate(data)  # type: ignore[attr-defined]
    return AppSettings.parse_obj(data)  # type: ignore[attr-defined]


@lru_cache()
def get_settings(path: str | Path | None = None) -> AppSettings:
    return load_settings(path)


def load_config(path: str | Path | None = None) -> Dict[str, Any]:
    settings = load_settings(path)
    if hasattr(settings, 'model_dump'):
        return settings.model_dump()
    return settings.dict()  # type: ignore[return-value]


__all__ = ['load_config', 'load_settings', 'get_settings']
