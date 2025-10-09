"""Typed configuration models for the MOEX bot."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping

from pydantic import BaseModel, Field, validator


class TelegramSettings(BaseModel):
    token: str = ""
    chat_id: str = ""
    allowed_users: List[int] = Field(default_factory=list)

    @validator('allowed_users', pre=True)
    def _coerce_users(cls, value: Any) -> List[int]:  # noqa: D401 - pydantic hook
        if value in (None, "", []):
            return []
        if isinstance(value, str):
            return [int(v) for v in value.split(',') if v.strip()]
        return [int(v) for v in value]


class RiskSettings(BaseModel):
    max_drawdown_pct: float = Field(default=0.2, ge=0, le=1)
    max_daily_loss_pct: float = Field(default=0.1, ge=0, le=1)
    max_position_pct: float = Field(default=0.2, ge=0, le=1)
    per_trade_risk_pct: float = Field(default=0.02, ge=0, le=1)
    stop_loss_pct: float = Field(default=0.05, ge=0, le=1)
    take_profit_pct: float = Field(default=0.1, ge=0, le=1)
    max_positions: int = Field(default=5, ge=1)
    allow_short: bool = False
    max_portfolio_exposure_pct: float = Field(default=1.0, ge=0, le=5)


class PortfolioSettings(BaseModel):
    target_allocations: Dict[str, float] = Field(default_factory=dict)

    @validator('target_allocations')
    def _validate_allocations(cls, value: Dict[str, float]) -> Dict[str, float]:
        if not value:
            return {}
        total = sum(value.values())
        if total <= 0:
            raise ValueError('Sum of target allocations must be positive')
        return value


class ScheduleEntry(BaseModel):
    func: str
    cron: Any
    args: List[Any] = Field(default_factory=list)
    kwargs: Dict[str, Any] = Field(default_factory=dict)


class ScheduleSettings(BaseModel):
    __root__: Dict[str, ScheduleEntry] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {name: entry.dict() for name, entry in self.__root__.items()}


class TinkoffSettings(BaseModel):
    token: str = ""
    account_id: str = ""
    sandbox: bool | str | None = True
    sandbox_token: str = ""
    account_id_sandbox: str = ""

    @validator('sandbox', pre=True)
    def _coerce_bool(cls, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if value in (None, ""):
            return True
        if isinstance(value, (int, float)):
            return bool(value)
        return str(value).strip().lower() in {"1", "true", "yes", "on"}


class ServerSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=0, le=65535)


class AppSettings(BaseModel):
    capital: float = 1_000_000.0
    commission: float = Field(default=0.0, ge=0)
    data_path: str = "data"
    results_path: str = "results"
    results_dir: str = "results"
    db_path: str = "results/history.db"
    trade_mode: str = "sandbox"
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    strategies: Mapping[str, Any] = Field(default_factory=dict)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    schedule: ScheduleSettings = Field(default_factory=ScheduleSettings)
    portfolio: PortfolioSettings = Field(default_factory=PortfolioSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    tinkoff: TinkoffSettings = Field(default_factory=TinkoffSettings)
    database: str = "results/history.db"
    alerts: Dict[str, Any] = Field(default_factory=dict)

    @property
    def results_directory(self) -> Path:
        return Path(self.results_dir)


_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _expand_str(value: str) -> str:
    return _ENV_PATTERN.sub(lambda m: os.getenv(m.group(1), ''), value)


def expand_env_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: expand_env_values(v) for k, v in value.items()}
    if isinstance(value, list):
        return [expand_env_values(v) for v in value]
    if isinstance(value, str):
        return _expand_str(value)
    return value


__all__ = [
    'AppSettings',
    'TelegramSettings',
    'RiskSettings',
    'PortfolioSettings',
    'ScheduleSettings',
    'ScheduleEntry',
    'TinkoffSettings',
    'ServerSettings',
    'expand_env_values',
]
