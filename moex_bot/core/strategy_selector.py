"""Utilities for automatically selecting high-performing strategy sets."""

from __future__ import annotations

import logging
from importlib import import_module
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

import pandas as pd

from .hyperopt import hyperparameter_search

logger = logging.getLogger(__name__)


def _coerce_numeric(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _load_data_frame(file_path: str | Path, data_glob: str | None = None) -> pd.DataFrame:
    candidate = Path(file_path)
    if not candidate.exists():
        if data_glob:
            try:
                for path in Path.cwd().glob(data_glob):
                    if path.name == candidate.name:
                        candidate = path
                        break
            except Exception:
                pass
        if not candidate.exists():
            try:
                candidate = Path.cwd() / candidate
            except Exception:
                pass
    try:
        return pd.read_csv(candidate)
    except Exception as exc:
        logger.debug("Failed to load %s for hyperopt: %s", candidate, exc)
        return pd.DataFrame()


def _apply_hyperopt(
    selection: pd.DataFrame,
    hyperopt_cfg: Mapping[str, Any],
    strategy_specs: Mapping[str, Any],
    data_glob: str,
    start_capital: float,
    leverage: float,
    borrow_rate: float,
    short_rate: float | None,
    periods_per_year: int,
) -> pd.DataFrame:
    if not hyperopt_cfg or not hyperopt_cfg.get("enabled"):
        return selection
    per_strategy: Mapping[str, Any] = hyperopt_cfg.get("per_strategy") or hyperopt_cfg.get("strategies") or {}
    if not per_strategy:
        return selection
    metric = hyperopt_cfg.get("metric", "sharpe")
    updated_rows = []
    for _, row in selection.iterrows():
        strat_name = row.get("strategy")
        grid = per_strategy.get(strat_name)
        if not strat_name or not grid:
            updated_rows.append(row)
            continue
        spec = strategy_specs.get(strat_name, {}) if isinstance(strategy_specs, Mapping) else {}
        module_name = spec.get("module") or strat_name
        class_name = spec.get("class")
        if not class_name:
            updated_rows.append(row)
            continue
        try:
            module = import_module(f"moex_bot.strategies.{module_name}")
            strategy_class = getattr(module, class_name)
        except Exception as exc:
            logger.debug("Hyperopt import failed for %s: %s", strat_name, exc)
            updated_rows.append(row)
            continue
        file_path = row.get("file")
        df = pd.DataFrame()
        if isinstance(file_path, str):
            df = _load_data_frame(file_path, data_glob)
        if df.empty:
            updated_rows.append(row)
            continue
        try:
            opt_df = hyperparameter_search(
                df,
                strategy_class,
                grid,
                start_capital=start_capital,
                leverage=leverage,
                borrow_rate=borrow_rate,
                short_rate=short_rate,
                periods_per_year=periods_per_year,
            )
        except Exception as exc:
            logger.debug("Hyperopt search failed for %s: %s", strat_name, exc)
            updated_rows.append(row)
            continue
        if opt_df.empty or metric not in opt_df.columns:
            updated_rows.append(row)
            continue
        opt_df = opt_df.sort_values(metric, ascending=False)
        best = opt_df.iloc[0]
        row = row.copy()
        params = {k.replace("param_", ""): v for k, v in best.items() if k.startswith("param_")}
        if params:
            row["optimized_params"] = params
        for key in ["pnl_pct", "sharpe", "max_drawdown", "avg_leverage", "max_leverage"]:
            opt_key = f"opt_{key}"
            if key in best:
                row[opt_key] = best[key]
        updated_rows.append(row)
    return pd.DataFrame(updated_rows)


def auto_select_strategies(
    results: pd.DataFrame,
    cfg: Mapping[str, Any] | None,
    data_glob: str,
    strategies: Mapping[str, Any],
    start_capital: float,
    leverage: float,
    borrow_rate: float,
    short_rate: float | None,
    periods_per_year: int,
    strategy_specs: Mapping[str, Any],
) -> pd.DataFrame:
    if results is None or results.empty:
        return pd.DataFrame()
    cfg = cfg or {}
    _ = strategies  # reserved for future use (live auto-allocation)
    df = results.copy()
    df = _coerce_numeric(df, ["pnl_pct", "sharpe", "max_drawdown", "avg_leverage", "max_leverage"])
    if "strategy" not in df.columns:
        return pd.DataFrame()
    df = df.dropna(subset=["strategy"]).copy()
    min_sharpe = float(cfg.get("min_sharpe", 0.0) or 0.0)
    if "sharpe" in df.columns:
        df = df[df["sharpe"] >= min_sharpe]
    max_drawdown = cfg.get("max_drawdown_pct")
    if max_drawdown is not None and "max_drawdown" in df.columns:
        threshold = -abs(float(max_drawdown))
        df = df[df["max_drawdown"] >= threshold]
    max_avg_leverage = cfg.get("max_avg_leverage")
    if max_avg_leverage is not None and "avg_leverage" in df.columns:
        df = df[df["avg_leverage"] <= float(max_avg_leverage)]
    if df.empty:
        return df
    sort_by = cfg.get("sort_by") or ["pnl_pct", "sharpe"]
    if isinstance(sort_by, str):
        sort_by = [sort_by]
    ascending = cfg.get("ascending")
    if ascending is None:
        ascending = [False] * len(sort_by)
    elif isinstance(ascending, bool):
        ascending = [ascending] * len(sort_by)
    df = df.sort_values(sort_by, ascending=ascending, na_position="last")
    diversify_key = cfg.get("diversify_by") or cfg.get("group_by")
    top_per_group = int(cfg.get("top_per_group", 1))
    selection: pd.DataFrame
    if diversify_key and diversify_key in df.columns:
        rows = []
        for _, group in df.groupby(diversify_key, sort=False):
            rows.extend(group.head(top_per_group).to_dict("records"))
        selection = pd.DataFrame(rows)
    else:
        top_n = int(cfg.get("top_n", 5))
        selection = df.head(top_n)
    if selection.empty:
        return selection
    hyperopt_cfg = cfg.get("hyperopt", {})
    if hyperopt_cfg.get("enabled"):
        selection = _apply_hyperopt(
            selection,
            hyperopt_cfg,
            strategy_specs,
            data_glob,
            start_capital,
            leverage,
            borrow_rate,
            short_rate,
            periods_per_year,
        )
    weight_metric = cfg.get("weight_metric", "sharpe")
    weights = None
    if weight_metric in selection.columns:
        metric = selection[weight_metric].fillna(0.0)
        metric = metric.clip(lower=0.0)
        total = float(metric.sum())
        if total > 0:
            weights = metric / total
    if weights is None:
        weights = pd.Series([1.0 / len(selection)] * len(selection), index=selection.index)
    selection = selection.copy()
    selection["weight"] = weights
    weight_sum = float(selection["weight"].sum())
    if weight_sum > 0:
        selection["weight"] = selection["weight"] / weight_sum
    keep_order = ["strategy"]
    for col in ["file", "pnl_pct", "sharpe", "max_drawdown", "avg_leverage", "max_leverage", "weight", "optimized_params", "opt_sharpe", "opt_pnl_pct"]:
        if col in selection.columns and col not in keep_order:
            keep_order.append(col)
    return selection[keep_order].reset_index(drop=True)


def format_selection_for_config(
    selection: pd.DataFrame,
    strategy_specs: Mapping[str, Any],
) -> Dict[str, Any]:
    if selection is None or selection.empty:
        return {}
    portfolio_weights = {row["strategy"]: float(row["weight"]) for _, row in selection.iterrows() if "weight" in selection.columns}
    selected_strategies = {}
    for _, row in selection.iterrows():
        name = row["strategy"]
        spec = strategy_specs.get(name, {}) if isinstance(strategy_specs, Mapping) else {}
        if isinstance(spec, Mapping):
            selected_strategies[name] = spec
        if "optimized_params" in row and isinstance(row["optimized_params"], dict):
            selected_strategies.setdefault(name, {})
            params = selected_strategies[name].get("params", {})
            params.update(row["optimized_params"])
            selected_strategies[name]["params"] = params
    return {
        "strategies": selected_strategies,
        "portfolio": {"target_allocations": portfolio_weights},
    }


__all__ = ["auto_select_strategies", "format_selection_for_config"]
