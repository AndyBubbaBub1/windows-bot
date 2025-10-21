"""Configuration loading utilities.

The bot uses a YAML configuration file to specify global settings such
as the starting capital, trading fees, scheduler configuration,
database connection strings and the list of enabled strategies.
Users can provide their own ``config.yaml`` in the project root to
override defaults.  Environment variables referenced in the YAML file
are expanded automatically.

Starting with this release the loader also understands configuration
directories.  If a folder named ``config.d`` is placed next to
``config.yaml`` (or the path passed to :func:`load_config` points to a
directory) every ``*.yml``/``*.yaml`` file inside will be merged into
the resulting configuration.  This makes it easy to separate secrets,
strategy bundles and scheduler rules into individual files without
touching the primary configuration.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

import yaml


def _deep_merge(base: Dict[str, Any], other: Dict[str, Any]) -> Dict[str, Any]:
    """Deeply merge ``other`` into ``base`` in-place."""

    for key, value in other.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _expand_env_vars(obj: Any) -> Any:
    """Recursively expand environment variables in strings."""

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


def _read_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise TypeError(f"Config fragment {path} must contain a mapping at the top level")
    return _expand_env_vars(data)


def _collect_sources(base_path: Path) -> List[Path]:
    if base_path.is_file():
        return [base_path]

    if not base_path.exists():
        raise FileNotFoundError(f"Configuration path not found: {base_path}")

    yaml_files: List[Path] = []
    config_yaml = base_path / "config.yaml"
    if config_yaml.exists():
        yaml_files.append(config_yaml)

    for pattern in ("*.yml", "*.yaml"):
        for fragment in sorted(base_path.glob(pattern)):
            if fragment == config_yaml:
                continue
            yaml_files.append(fragment)

    if not yaml_files:
        raise FileNotFoundError(f"No YAML files found in configuration directory {base_path}")
    return yaml_files


def load_config(path: str | Path | None = None) -> Dict[str, Any]:
    """Load configuration from a YAML file or directory."""

    base_dir = Path(__file__).resolve().parents[1]
    if path is None:
        primary = base_dir / "config.yaml"
        if not primary.exists():
            raise FileNotFoundError(f"Configuration file not found: {primary}")
        sources: List[Path] = [primary]
        config_dir = base_dir / "config.d"
        if config_dir.exists():
            sources.extend(_collect_sources(config_dir))
    else:
        cfg_path = Path(path)
        sources = _collect_sources(cfg_path)

    config: Dict[str, Any] = {}
    for source in sources:
        fragment = _read_yaml(source)
        _deep_merge(config, fragment)
    return config


__all__ = ["load_config"]
