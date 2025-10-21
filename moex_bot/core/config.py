"""Загрузка конфигурации проекта из одного или нескольких YAML-файлов."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml


def _expand_env_vars(obj: Any) -> Any:
    """Рекурсивно разворачивает переменные окружения в строках."""

    if isinstance(obj, dict):
        return {k: _expand_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env_vars(v) for v in obj]
    if isinstance(obj, str):
        parts: list[str] = []
        i = 0
        while i < len(obj):
            if obj[i] == "$" and i + 1 < len(obj) and obj[i + 1] == "{":
                j = obj.find("}", i + 2)
                if j != -1:
                    var_name = obj[i + 2 : j]
                    parts.append(os.getenv(var_name, ""))
                    i = j + 1
                    continue
            parts.append(obj[i])
            i += 1
        return "".join(parts)
    return obj


def _deep_merge(base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    """Аккуратно объединяет два словаря конфигурации."""

    for key, value in extra.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            base[key] = _deep_merge(dict(base[key]), value)
        elif key in base and isinstance(base[key], list) and isinstance(value, list):
            existing = list(base[key])
            existing.extend(item for item in value if item not in existing)
            base[key] = existing
        else:
            base[key] = value
    return base


def _load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return _expand_env_vars(yaml.safe_load(fh) or {})


def load_config(
    path: str | Path | None = None,
    *,
    fragments_dir: str | Path | None = None,
) -> Dict[str, Any]:
    """Загружает базовую конфигурацию и опциональные фрагменты."""

    if path is None:
        base = Path(__file__).resolve().parents[1]
        path = base / "config.yaml"

    cfg_path = Path(path)
    if not cfg_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {cfg_path}")

    config = _load_yaml(cfg_path)

    fragments_root = (
        Path(fragments_dir)
        if fragments_dir is not None
        else cfg_path.with_suffix("").with_name("config.d")
    )
    if fragments_root.exists() and fragments_root.is_dir():
        for fragment in sorted(fragments_root.glob("*.yaml")):
            fragment_cfg = _load_yaml(fragment)
            config = _deep_merge(config, fragment_cfg)

    return config


__all__ = ["load_config"]
