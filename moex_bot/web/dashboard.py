"""Интерактивная панель мониторинга для FastAPI-приложения."""

from __future__ import annotations

from typing import Dict, List

import dash
from dash import Dash, Input, Output, dcc, html, dash_table
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go
import pandas as pd

from ..core.engine import Engine


def _available_symbols(engine: Engine) -> List[str]:
    symbols: set[str] = set()
    for strat in (engine.cfg.get("strategies") or {}).values():
        for symbol in (strat or {}).get("symbols", []) or []:
            symbols.add(str(symbol).upper())
    if not symbols:
        for symbol in engine.risk_manager.positions.keys():
            symbols.add(symbol.upper())
    return sorted(symbols) or ["SBER"]


def create_dashboard_app(engine: Engine) -> Dash:
    dash_app = Dash(__name__, requests_pathname_prefix="/")
    symbols = _available_symbols(engine)

    dash_app.layout = html.Div(
        [
            html.H1("MOEX Bot Control Center"),
            html.Div(
                [
                    dcc.Dropdown(
                        id="symbol-dropdown",
                        options=[{"label": sym, "value": sym} for sym in symbols],
                        value=symbols[0],
                        clearable=False,
                    ),
                    html.Button("Старт", id="start-button", n_clicks=0, className="control-btn"),
                    html.Button("Стоп", id="stop-button", n_clicks=0, className="control-btn"),
                    html.Button(
                        "Переключить режим", id="mode-button", n_clicks=0, className="control-btn"
                    ),
                    html.Div(id="mode-indicator", className="mode-indicator"),
                ],
                className="controls",
            ),
            dcc.Graph(id="price-graph"),
            dcc.Graph(id="indicator-graph"),
            dash_table.DataTable(
                id="positions-table",
                columns=[
                    {"name": "Тикер", "id": "symbol"},
                    {"name": "Количество", "id": "quantity"},
                    {"name": "Цена входа", "id": "entry_price"},
                    {"name": "Текущая цена", "id": "last_price"},
                ],
            ),
            html.Div(id="risk-summary"),
            dcc.Interval(id="refresh-interval", interval=15_000, n_intervals=0),
        ]
    )

    @dash_app.callback(
        Output("mode-indicator", "children"),
        Input("mode-button", "n_clicks"),
        prevent_initial_call=True,
    )
    def _toggle_mode(_: int) -> str:  # type: ignore[override]
        mode = engine.toggle_mode()
        return f"Текущий режим: {mode}"

    @dash_app.callback(
        Output("price-graph", "figure"),
        Output("indicator-graph", "figure"),
        Output("positions-table", "data"),
        Output("risk-summary", "children"),
        Input("refresh-interval", "n_intervals"),
        Input("symbol-dropdown", "value"),
    )
    def _refresh(_: int, symbol: str):  # type: ignore[override]
        history = engine.data_provider.load_history(symbol, interval="hour", days=90)
        if isinstance(history, pd.DataFrame) and not history.empty:
            history["time"] = pd.to_datetime(history.get("time") or history.index)
            price_fig = go.Figure()
            price_fig.add_trace(
                go.Scatter(x=history["time"], y=history["close"], mode="lines", name="Close")
            )
            history["SMA20"] = history["close"].rolling(window=20).mean()
            indicator_fig = go.Figure()
            indicator_fig.add_trace(
                go.Bar(
                    x=history["time"], y=history["close"].pct_change().fillna(0), name="Доходность"
                )
            )
            indicator_fig.add_trace(
                go.Scatter(x=history["time"], y=history["SMA20"], mode="lines", name="SMA20")
            )
        else:
            price_fig = go.Figure()
            indicator_fig = go.Figure()
        positions = []
        for sym, pos in engine.risk_manager.positions.items():
            positions.append(
                {
                    "symbol": sym,
                    "quantity": pos.get("quantity", 0),
                    "entry_price": pos.get("entry_price", 0),
                    "last_price": pos.get("last_price", pos.get("entry_price", 0)),
                }
            )
        equity = engine.risk_manager.portfolio_equity
        peak = engine.risk_manager.peak_equity
        summary = f"Капитал: {equity:,.0f} ₽ | Пик: {peak:,.0f} ₽"
        return price_fig, indicator_fig, positions, summary

    @dash_app.callback(
        Output("start-button", "n_clicks"),
        Output("stop-button", "n_clicks"),
        Input("start-button", "n_clicks"),
        Input("stop-button", "n_clicks"),
        prevent_initial_call=True,
    )
    def _control_loop(start_clicks: int, stop_clicks: int):  # type: ignore[override]
        ctx = dash.callback_context
        if not ctx.triggered:
            raise PreventUpdate
        trigger = ctx.triggered[0]["prop_id"].split(".")[0]
        if trigger == "start-button":
            engine.start()
        elif trigger == "stop-button":
            engine.stop()
        return 0, 0

    return dash_app


__all__ = ["create_dashboard_app"]
