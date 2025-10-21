# -*- coding: utf-8 -*-
"""
MOEX bot web app (fixed #4):
- NEW: /metrics endpoint returning stored strategy metrics from DB (sanitized).
- Keeps previous fixes:
  * no JS prompt on index
  * unified /status
  * optional HTTP Basic auth (MOEX_API_USER/MOEX_API_PASS)
  * aggressive sanitization for JSON (no NaN/Inf, numpy scalars -> python)
"""
from __future__ import annotations

import os
import math
from pathlib import Path
from typing import Optional, Dict, Any

import pandas as pd
import numpy as np
from fastapi import FastAPI, HTTPException, Depends, Form, Header
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.middleware.wsgi import WSGIMiddleware
from pydantic import BaseModel, Field

# ---- Project imports
from ..core.config import load_config
from ..core.storage import fetch_metrics, fetch_reports, init_db
from ..core import live_loop
from ..core.engine import Engine
from .dashboard import create_dashboard_app

cfg = load_config()

project_root = Path(__file__).resolve().parents[1]
results_dir = cfg.get("results_dir", "results")
db_path = project_root / cfg.get("database", f"{results_dir}/history.db")
init_db(str(db_path))

security = HTTPBasic()


def _verify_auth(credentials: HTTPBasicCredentials = Depends(security)) -> None:
    user = (os.getenv("MOEX_API_USER") or "").strip()
    pwd = (os.getenv("MOEX_API_PASS") or "").strip()
    if not user or not pwd:
        return  # auth disabled
    if not (credentials.username == user and credentials.password == pwd):
        raise HTTPException(
            status_code=401, detail="Not authenticated", headers={"WWW-Authenticate": "Basic"}
        )


def require_admin(x_token: str = Header(...)) -> None:
    token = os.getenv("MOEX_ADMIN_TOKEN")
    if token and x_token != token:
        raise HTTPException(status_code=403, detail="Forbidden: invalid admin token")


app = FastAPI(title="MOEX Bot Analytics API", dependencies=[Depends(_verify_auth)])

_engine = Engine.from_config(cfg)
_risk_manager = _engine.risk_manager
_data_provider = _engine.data_provider
dash_app = create_dashboard_app(_engine)
app.mount("/dashboard", WSGIMiddleware(dash_app.server))


class TradeRequest(BaseModel):
    symbol: str = Field(..., description="Ticker symbol to trade")
    lots: int = Field(1, description="Number of lots to trade", gt=0)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return """
    <html><head>
    <meta charset="utf-8"/>
    <title>MOEX Bot Analytics API</title>
    <style>
      body{font-family:Segoe UI,Arial,sans-serif;background:#f7f7f7;color:#111;margin:24px}
      a{color:#1a73e8;text-decoration:none} a:hover{text-decoration:underline}
      .badge{display:inline-block;padding:4px 8px;border-radius:6px;background:#eee;margin-right:8px}
    </style></head><body>
    <h1>MOEX Bot Analytics API</h1>
    <div><span class="badge">Статус: см. /status</span>
         <span class="badge">режим: зависит от live_loop</span></div>
    <p>Available endpoints:</p>
    <ul>
      <li><a href="/metrics">/metrics</a></li>
      <li><a href="/reports">/reports</a></li>
      <li><a href="/portfolio_metrics">/portfolio_metrics</a></li>
      <li><a href="/correlation">/correlation</a></li>
      <li><a href="/plot/equity/Portfolio">/plot/equity/Portfolio</a></li>
    </ul>
    </body></html>
    """


@app.get("/status")
def get_status() -> JSONResponse:
    equity = _risk_manager.portfolio_equity
    positions = {
        sym: {"quantity": pos.get("quantity", 0), "entry_price": pos.get("entry_price")}
        for sym, pos in _risk_manager.positions.items()
    }
    status = {
        "running": getattr(live_loop, "RUNNING", False),
        "mode": getattr(live_loop, "TRADE_MODE", "undefined"),
        "equity": equity,
        "positions": positions,
    }
    return JSONResponse(content=status)


def _sanitize_for_json(obj: Any):
    """Recursively convert numpy types and strip NaN/Inf -> None."""
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    # numpy scalars
    if hasattr(obj, "item") and type(obj).__module__ == "numpy":
        obj = obj.item()
    if isinstance(obj, float):
        if not math.isfinite(obj):
            return None
        return float(obj)
    return obj


@app.get("/metrics")
def get_metrics() -> JSONResponse:
    """Return strategy metrics stored in DB (sanitized JSON)."""
    try:
        rows = fetch_metrics(str(db_path))  # expected list[dict] or similar
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch metrics: {exc}") from exc
    safe_rows = _sanitize_for_json(rows)
    return JSONResponse(content=safe_rows)


@app.get("/portfolio_metrics")
def get_portfolio_metrics() -> JSONResponse:
    metrics_file = project_root / results_dir / "portfolio_metrics.csv"
    if not metrics_file.exists():
        raise HTTPException(
            status_code=404, detail="portfolio_metrics.csv not found; run backtests first"
        )
    df = pd.read_csv(metrics_file)
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    data = df.where(pd.notnull(df), None).to_dict(orient="records")
    safe_data = _sanitize_for_json(data)
    return JSONResponse(content=safe_data)


@app.get("/correlation")
def get_correlation_matrix() -> JSONResponse:
    corr_file = project_root / results_dir / "correlation_matrix.csv"
    if not corr_file.exists():
        raise HTTPException(
            status_code=404, detail="correlation_matrix.csv not found; run backtests first"
        )
    corr_df = pd.read_csv(corr_file, index_col=0)
    corr_df.replace([np.inf, -np.inf], np.nan, inplace=True)
    data = corr_df.where(pd.notnull(corr_df), None).to_dict()
    safe_data = _sanitize_for_json(data)
    return JSONResponse(content=safe_data)


@app.get("/plot/equity/{strategy}")
def get_equity_plot(strategy: str) -> FileResponse:
    if strategy.lower() == "portfolio":
        path = project_root / results_dir / "portfolio_equity.png"
        if not path.exists():
            raise HTTPException(status_code=404, detail="portfolio_equity.png not found")
        return FileResponse(path)
    pattern = f"*_{strategy}.png"
    matches = list((project_root / results_dir).glob(pattern))
    if matches:
        return FileResponse(matches[0])
    raise HTTPException(status_code=404, detail=f"Equity plot for {strategy} not found")


@app.get("/reports")
def get_reports() -> JSONResponse:
    reports = fetch_reports(str(db_path))
    return JSONResponse(content=reports)


@app.get("/reports/{report_id}")
def get_report_file(report_id: int) -> FileResponse:
    reports = fetch_reports(str(db_path))
    for r in reports:
        if r["id"] == report_id:
            file_path = (
                project_root / r["file_path"]
                if not Path(r["file_path"]).is_absolute()
                else Path(r["file_path"])
            )
            if file_path.exists():
                return FileResponse(file_path)
            raise HTTPException(status_code=404, detail="Report file not found")
    raise HTTPException(status_code=404, detail="Report ID not found")


@app.get("/reports/latest")
def latest_report():
    reports_dir_path = project_root / results_dir
    if not reports_dir_path.exists():
        return JSONResponse(content={"error": "Нет отчетов"}, status_code=404)
    files = [p for p in reports_dir_path.glob("*.html")]
    if not files:
        return JSONResponse(content={"error": "Нет HTML отчетов"}, status_code=404)
    latest = max(files, key=lambda p: p.stat().st_mtime)
    return FileResponse(str(latest))


# Admin controls
@app.post("/control/start")
async def control_start(x_token: str = Header(...)):
    require_admin(x_token)
    live_loop.start_trading()
    return {"status": "started"}


@app.post("/control/stop")
async def control_stop(x_token: str = Header(...)):
    require_admin(x_token)
    live_loop.stop_trading()
    return {"status": "stopped"}


@app.post("/control/toggle_mode")
async def control_toggle(x_token: str = Header(...)):
    require_admin(x_token)
    new_mode = live_loop.toggle_mode()
    return {"status": f"mode switched to {new_mode}"}


__all__ = ["app"]
