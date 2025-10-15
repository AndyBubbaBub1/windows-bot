"""Order execution journalling utilities."""

from __future__ import annotations

import datetime as dt
import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


def _serialise(value: Any) -> Any:
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    return value


@dataclass
class ExecutionJournal:
    """Append-only JSON-lines journal for order executions."""

    path: str | Path
    flush_interval: int = 1
    auto_timestamp: bool = True
    _buffer: List[Dict[str, Any]] = field(default_factory=list, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, entry: Dict[str, Any]) -> None:
        payload = {k: _serialise(v) for k, v in entry.items()}
        if self.auto_timestamp:
            payload.setdefault('timestamp', dt.datetime.utcnow().isoformat())
        with self._lock:
            self._buffer.append(payload)
            if len(self._buffer) >= self.flush_interval:
                self.flush()

    def flush(self) -> None:
        if not self._buffer:
            return
        with self.path.open('a', encoding='utf-8') as fh:
            for item in self._buffer:
                fh.write(json.dumps(item, ensure_ascii=False) + "\n")
        self._buffer.clear()

    def read_tail(self, limit: int = 50) -> List[Dict[str, Any]]:
        if limit <= 0 or not self.path.exists():
            return []
        lines: List[str]
        with self.path.open('r', encoding='utf-8') as fh:
            lines = fh.readlines()
        tail = lines[-limit:]
        result: List[Dict[str, Any]] = []
        for line in tail:
            line = line.strip()
            if not line:
                continue
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return result


__all__ = ["ExecutionJournal"]
