"""Structured logging configuration for the MOEX bot.

This module configures :mod:`structlog` together with the standard
logging module so that every log message is emitted as JSON.  The JSON
format is easy to ingest by log aggregation systems such as ELK or
ClickHouse and keeps contextual information like module name, log
level, timestamp and stack traces.

All entry points of the project should call :func:`configure_logging`
once during start-up.  The configuration is idempotent – calling it
multiple times simply reconfigures structlog with the provided
parameters.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Mapping, MutableMapping, Optional

import structlog


def _rename_event_key(_: structlog.types.WrappedLogger,
                      __: str,
                      event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """Rename ``event`` key to ``message`` for nicer JSON output."""

    event = event_dict.pop("event", None)
    if event is not None:
        event_dict["message"] = event
    return event_dict


def configure_logging(level: int = logging.INFO,
                      json_logs: bool = True,
                      extra_processors: Optional[Iterable[structlog.types.Processor]] = None) -> None:
    """Configure structlog and standard logging.

    Args:
        level: Minimum log level for the root logger.
        json_logs: If ``True`` use :class:`structlog.processors.JSONRenderer`,
            otherwise use :class:`structlog.dev.ConsoleRenderer`.
        extra_processors: Optional iterable of additional structlog
            processors appended to the default pipeline.
    """

    logging.basicConfig(level=level, format="%(message)s")

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        _rename_event_key,
    ]
    if extra_processors:
        shared_processors.extend(extra_processors)

    renderer: structlog.types.Processor
    if json_logs:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )


def bind_context(**kwargs: Any) -> Mapping[str, Any]:
    """Bind contextual information to the current logging context."""

    structlog.contextvars.bind_contextvars(**kwargs)
    return kwargs


__all__ = ["configure_logging", "bind_context"]
