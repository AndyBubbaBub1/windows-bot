"""Интерактивная панель мониторинга для FastAPI-приложения."""

from __future__ import annotations

from pathlib import Path
from typing import List

import dash
from dash import Dash, Input, Output, State, dcc, html, dash_table
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


def _risk_cards(snapshot: dict[str, float | int | bool]) -> list[html.Div]:
    return [
        html.Div(
            [
                html.Div(title, className="risk-label"),
                html.Div(value, className="risk-value"),
            ],
            className="risk-card",
        )
        for title, value in (
            ("Капитал", f"{snapshot['equity']:,.0f} ₽"),
            ("PnL", f"{snapshot['pnl']:,.0f} ₽"),
            ("Гросс", f"{snapshot['gross_exposure']:,.0f} ₽"),
            ("Просадка", f"{snapshot['intraday_drawdown_pct']:.2%}"),
            ("Позиции", str(snapshot["open_positions"])),
        )
    ]


def create_dashboard_app(engine: Engine) -> Dash:
    assets_dir = Path(__file__).resolve().parent / "static"
    dash_app = Dash(
        __name__,
        requests_pathname_prefix="/",
        assets_folder=str(assets_dir),
        suppress_callback_exceptions=True,
    )
    symbols = _available_symbols(engine)

    dash_app.layout = html.Div(
        [
            html.Div(
                [
                    html.H1("MOEX Bot Control Center", className="app-title"),
                    html.Div(id="mode-indicator", className="mode-indicator"),
                ],
                className="dashboard-header",
            ),
            dcc.Store(id="strategy-store"),
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
                ],
                className="controls",
            ),
            dcc.Tabs(
                id="dashboard-tabs",
                value="overview",
                children=[
                    dcc.Tab(
                        label="Обзор",
                        value="overview",
                        children=[
                            html.Div(
                                [
                                    dcc.Graph(id="price-graph", className="chart"),
                                    dcc.Graph(id="indicator-graph", className="chart"),
                                ],
                                className="chart-grid",
                            ),
                            html.Div(id="risk-summary", className="risk-grid"),
                            html.Div(
                                [
                                    dcc.Graph(id="exposure-graph", className="chart"),
                                    dash_table.DataTable(
                                        id="positions-table",
                                        columns=[
                                            {"name": "Тикер", "id": "symbol"},
                                            {"name": "Количество", "id": "quantity"},
                                            {"name": "Цена входа", "id": "entry_price"},
                                            {"name": "Текущая", "id": "last_price"},
                                            {"name": "Стратегия", "id": "strategy"},
                                        ],
                                        style_table={"height": "320px", "overflowY": "auto"},
                                        page_size=15,
                                    ),
                                ],
                                className="split-grid",
                            ),
                        ],
                    ),
                    dcc.Tab(
                        label="Стратегии",
                        value="strategies",
                        children=[
                            html.Div(
                                [
                                    html.Div(id="strategy-feedback", className="info-banner"),
                                    dcc.Checklist(
                                        id="strategy-checklist",
                                        className="strategy-checklist",
                                        inputClassName="strategy-checkbox",
                                        labelClassName="strategy-label",
                                    ),
                                    html.Button(
                                        "Запустить бэктест",
                                        id="run-backtest",
                                        className="control-btn",
                                    ),
                                    html.Div(id="backtest-status", className="info-banner"),
                                ],
                                className="strategy-panel",
                            )
                        ],
                    ),
                    dcc.Tab(
                        label="Риски",
                        value="risks",
                        children=[
                            dash_table.DataTable(
                                id="risk-events-table",
                                columns=[
                                    {"name": "Время", "id": "timestamp"},
                                    {"name": "Уровень", "id": "level"},
                                    {"name": "Символ", "id": "symbol"},
                                    {"name": "Сообщение", "id": "message"},
                                ],
                                style_table={"height": "420px", "overflowY": "auto"},
                                page_size=20,
                            ),
                            dash_table.DataTable(
                                id="session-table",
                                columns=[
                                    {"name": "Время", "id": "timestamp"},
                                    {"name": "Режим", "id": "mode"},
                                    {"name": "Капитал", "id": "equity"},
                                    {"name": "PnL", "id": "pnl"},
                                    {"name": "Просадка", "id": "intraday_drawdown_pct"},
                                    {"name": "Позиции", "id": "open_positions"},
                                ],
                                style_table={"height": "280px", "overflowY": "auto"},
                                page_size=15,
                            ),
                        ],
                    ),
                    dcc.Tab(
                        label="Планировщик",
                        value="scheduler",
                        children=[
                            dash_table.DataTable(
                                id="schedule-table",
                                columns=[
                                    {"name": "Задача", "id": "name"},
                                    {"name": "Функция", "id": "func"},
                                    {"name": "Cron", "id": "cron"},
                                ],
                                style_table={"height": "420px", "overflowY": "auto"},
                                page_size=20,
                            )
                        ],
                    ),
                ],
            ),
            html.Div(id="notification-area", className="notification"),
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
        Output("exposure-graph", "figure"),
        Output("risk-events-table", "data"),
        Output("session-table", "data"),
        Input("refresh-interval", "n_intervals"),
        Input("symbol-dropdown", "value"),
    )
    def _refresh(_: int, symbol: str):  # type: ignore[override]
        history = engine.data_provider.load_history(symbol, interval="hour", days=90)
        if isinstance(history, pd.DataFrame) and not history.empty:
            history["time"] = pd.to_datetime(history.get("time") or history.index)
            price_fig = go.Figure()
            price_fig.add_trace(
                go.Candlestick(
                    x=history["time"],
                    open=history.get("open"),
                    high=history.get("high"),
                    low=history.get("low"),
                    close=history.get("close"),
                    name="Свечи",
                )
            )
            history["SMA20"] = history["close"].rolling(window=20).mean()
            history["SMA50"] = history["close"].rolling(window=50).mean()
            price_fig.add_trace(
                go.Scatter(x=history["time"], y=history["SMA20"], mode="lines", name="SMA20")
            )
            price_fig.add_trace(
                go.Scatter(x=history["time"], y=history["SMA50"], mode="lines", name="SMA50")
            )

            indicator_fig = go.Figure()
            indicator_fig.add_trace(
                go.Bar(
                    x=history["time"],
                    y=history["close"].pct_change().fillna(0),
                    name="Доходность",
                )
            )
            indicator_fig.add_trace(
                go.Scatter(
                    x=history["time"],
                    y=history["close"].rolling(window=14).std().fillna(0),
                    mode="lines",
                    name="Волатильность",
                    yaxis="y2",
                )
            )
            indicator_fig.update_layout(yaxis2=dict(overlaying="y", side="right", title="σ"))
        else:
            price_fig = go.Figure()
            indicator_fig = go.Figure()

        positions = engine.positions_snapshot()
        summary = engine.risk_manager.session_summary()
        exposure_fig = go.Figure()
        if positions:
            exposure_fig.add_trace(
                go.Bar(
                    x=[pos["symbol"] for pos in positions],
                    y=[abs(float(pos.get("quantity", 0))) for pos in positions],
                    marker_color="#3399ff",
                    name="Лоты",
                )
            )
            exposure_fig.update_layout(title="Размер позиций")

        risk_events = engine.risk_events(limit=100)
        session_rows = engine.session_history(limit=100)

        return (
            price_fig,
            indicator_fig,
            positions,
            _risk_cards(summary),
            exposure_fig,
            risk_events,
            session_rows,
        )

    @dash_app.callback(
        Output("strategy-store", "data"),
        Input("refresh-interval", "n_intervals"),
    )
    def _refresh_strategies(_: int):  # type: ignore[override]
        return engine.list_strategies()

    @dash_app.callback(
        Output("strategy-checklist", "options"),
        Output("strategy-checklist", "value"),
        Input("strategy-store", "data"),
    )
    def _render_strategy_options(data):  # type: ignore[override]
        if not data:
            return [], []
        options = [
            {"label": f"{row['name']} ({', '.join(row.get('symbols', []))})", "value": row["name"]}
            for row in data
        ]
        value = [row["name"] for row in data if row.get("enabled")]
        return options, value

    @dash_app.callback(
        Output("strategy-feedback", "children"),
        Input("strategy-checklist", "value"),
        State("strategy-store", "data"),
        prevent_initial_call=True,
    )
    def _apply_strategy_selection(selected: list[str], data):  # type: ignore[override]
        selected = selected or []
        if not data:
            raise PreventUpdate
        for row in data:
            engine.set_strategy_enabled(row["name"], row["name"] in selected)
        return f"Активных стратегий: {len(selected)}"

    @dash_app.callback(
        Output("backtest-status", "children"),
        Input("run-backtest", "n_clicks"),
        prevent_initial_call=True,
    )
    def _run_backtest(n_clicks: int):  # type: ignore[override]
        if not n_clicks:
            raise PreventUpdate
        try:
            results = engine.run_backtests()
            return f"Бэктест завершён ({len(results)} строк)"
        except Exception as exc:  # pragma: no cover - отладочное сообщение
            return f"Ошибка бэктеста: {exc}"

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

    @dash_app.callback(Output("schedule-table", "data"), Input("refresh-interval", "n_intervals"))
    def _refresh_schedule(_: int):  # type: ignore[override]
        return engine.schedule_overview()

    return dash_app


__all__ = ["create_dashboard_app"]
