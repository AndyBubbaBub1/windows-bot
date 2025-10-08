"""Centralised logging configuration for the MOEX bot.

This module provides a single function, :func:`configure_logging`,
which sets up the Python logging system with a consistent format and
verbosity.  All top‑level scripts should call this function at
startup so that log messages across the project have the same
appearance.  By default, the logging level is set to ``INFO`` and
the format includes a timestamp, log level, logger name and message.

Usage:

.. code-block:: python

    from moex_bot.core.logging_config import configure_logging
    configure_logging(level=logging.DEBUG)

"""

from __future__ import annotations

import logging
from typing import Optional


def configure_logging(level: int = logging.INFO, fmt: Optional[str] = None) -> None:
    """Configure the root logger with a standard format and level.

    This function calls :func:`logging.basicConfig` with a predefined
    format and date format.  If the root logger already has handlers,
    this call has no effect.  Call this function at the beginning
    of any script or entry point to ensure consistent logging.

    Args:
        level: Logging level, e.g. ``logging.INFO`` or ``logging.DEBUG``.
        fmt: Optional log format string.  If ``None`` the default
            ``'%(asctime)s [%(levelname)s] %(name)s: %(message)s'`` is used.
    """
    format_str = fmt or '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    date_fmt = '%Y-%m-%d %H:%M:%S'
    logging.basicConfig(level=level, format=format_str, datefmt=date_fmt)