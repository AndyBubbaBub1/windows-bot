"""Configuration loading utilities.

The bot uses a YAML configuration file to specify global settings such
as the starting capital, trading fees, scheduler configuration,
database connection strings and the list of enabled strategies.
Users can provide their own ``config.yaml`` in the project root to
override defaults.  Environment variables referenced in the YAML file
are expanded automatically.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml

def _expand_env_vars(obj: Any) -> Any:
    """Recursively expand environment variables in strings.

    The YAML configuration may reference environment variables using
    the ``${VAR_NAME}`` syntax.  This helper walks through the loaded
    Python object and replaces occurrences with the corresponding
    values from :mod:`os.environ`.  If a variable is not set it is
    replaced with an empty string.

    Args:
        obj: Arbitrary Python object produced by ``yaml.safe_load``.

    Returns:
        The same structure with environment variables expanded.
    """
    if isinstance(obj, dict):
        return {k: _expand_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env_vars(v) for v in obj]
    if isinstance(obj, str):
        # Expand ${VAR} inside the string
        parts = []
        i = 0
        while i < len(obj):
            if obj[i] == '$' and i + 1 < len(obj) and obj[i+1] == '{':
                j = obj.find('}', i + 2)
                if j != -1:
                    var_name = obj[i+2:j]
                    parts.append(os.getenv(var_name, ''))
                    i = j + 1
                    continue
            parts.append(obj[i])
            i += 1
        return ''.join(parts)
    return obj

def load_config(path: str | Path | None = None) -> Dict[str, Any]:
    """Load configuration from a YAML file.

    If ``path`` is not provided the function looks for ``config.yaml``
    in the parent directory of this module.  The file may use
    ``${VAR}`` placeholders which will be replaced by the
    corresponding environment variable values.

    Args:
        path: Optional path to the configuration file.  Can be a
            relative or absolute path.  If ``None``, defaults to
            ``<project_root>/config.yaml``.

    Returns:
        A dictionary containing the parsed configuration.
    """
    if path is None:
        # Default to config.yaml in the project root
        base = Path(__file__).resolve().parents[1]
        path = base / 'config.yaml'
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {cfg_path}")
    with open(cfg_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}
    return _expand_env_vars(data)

__all__ = ["load_config"]