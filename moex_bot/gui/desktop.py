"""Tkinter desktop console for managing the trading engine."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from pathlib import Path
from typing import Dict, Iterable, Optional

import pandas as pd

try:  # pragma: no cover - optional desktop deps
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception as exc:  # pragma: no cover - headless environments
    tk = None  # type: ignore[assignment]
    ttk = None  # type: ignore[assignment]
    messagebox = None  # type: ignore[assignment]
    _TK_ERROR = exc
else:  # pragma: no cover - GUI available
    _TK_ERROR = None

try:  # pragma: no cover - optional desktop deps
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
except Exception as exc:  # pragma: no cover - matplotlib optional
    FigureCanvasTkAgg = None  # type: ignore[assignment]
    Figure = None  # type: ignore[assignment]
    _MPL_ERROR = exc
else:  # pragma: no cover - matplotlib available
    _MPL_ERROR = None

from ..core.engine import Engine

logger = logging.getLogger(__name__)


class EngineWorker(threading.Thread):
    """Background thread running the live trading loop."""

    def __init__(self, engine: Engine, interval: float) -> None:
        super().__init__(daemon=True)
        self.engine = engine
        self.interval = max(interval, 0.5)
        self._stop_event = threading.Event()

    def run(self) -> None:  # pragma: no cover - requires live event loop
        while not self._stop_event.is_set():
            if not self.engine.state.running:
                time.sleep(0.5)
                continue
            try:
                asyncio.run(self.engine.run_live_once())
            except Exception as exc:
                logger.exception("Ошибка живого цикла: %s", exc)
                time.sleep(self.interval)
            else:
                time.sleep(self.interval)

    def stop(self) -> None:
        self._stop_event.set()


class DesktopApp:
    """Simple Tkinter GUI for monitoring and controlling the bot."""

    def __init__(self, root: "tk.Tk", engine: Optional[Engine] = None) -> None:
        self.root = root
        self.root.title("MOEX Bot Desktop Console")
        self.root.geometry("1024x720")
        self.engine = engine or Engine.from_config()
        self.cfg = self.engine.cfg
        self.refresh_ms = int(float(self.cfg.get("desktop_refresh_ms", 10_000)))
        live_interval = float(self.cfg.get("live_interval", 5.0))
        self.worker = EngineWorker(self.engine, interval=live_interval)
        self.worker.start()

        self.mode_var = tk.StringVar()
        self.status_var = tk.StringVar()
        self.equity_var = tk.StringVar()
        self.risk_var = tk.StringVar()
        self.symbol_var = tk.StringVar()
        self.strategy_vars: Dict[str, tk.BooleanVar] = {}

        self._build_layout()
        self._populate_strategies()
        self._populate_symbols()
        self._refresh()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_layout(self) -> None:
        controls = ttk.Frame(self.root, padding=10)
        controls.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(controls, text="Старт", command=self._on_start).pack(side=tk.LEFT, padx=5)
        ttk.Button(controls, text="Стоп", command=self._on_stop).pack(side=tk.LEFT, padx=5)
        ttk.Button(controls, text="Переключить режим", command=self._on_toggle_mode).pack(
            side=tk.LEFT, padx=5
        )

        ttk.Label(controls, textvariable=self.mode_var, width=20).pack(side=tk.LEFT, padx=10)
        ttk.Label(controls, textvariable=self.status_var, width=20).pack(side=tk.LEFT, padx=10)
        ttk.Label(controls, textvariable=self.equity_var).pack(side=tk.LEFT, padx=10)

        main_body = ttk.Frame(self.root)
        main_body.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        left_panel = ttk.Frame(main_body, padding=10)
        left_panel.pack(side=tk.LEFT, fill=tk.Y)

        ttk.Label(left_panel, text="Стратегии", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        self.strategy_frame = ttk.Frame(left_panel)
        self.strategy_frame.pack(fill=tk.Y, expand=True)

        ttk.Label(left_panel, text="Инструмент", font=("Segoe UI", 10, "bold")).pack(
            anchor=tk.W, pady=(10, 0)
        )
        self.symbol_combo = ttk.Combobox(left_panel, textvariable=self.symbol_var, state="readonly")
        self.symbol_combo.pack(fill=tk.X, pady=5)
        self.symbol_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_chart())

        ttk.Label(left_panel, textvariable=self.risk_var, wraplength=260).pack(
            anchor=tk.W, pady=(10, 0)
        )

        right_panel = ttk.Frame(main_body, padding=10)
        right_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        columns = ("symbol", "qty", "entry", "last", "pnl")
        self.positions_tree = ttk.Treeview(
            right_panel,
            columns=columns,
            show="headings",
            height=8,
        )
        headings = {
            "symbol": "Тикер",
            "qty": "Количество",
            "entry": "Цена входа",
            "last": "Текущая цена",
            "pnl": "P/L",
        }
        for col, title in headings.items():
            self.positions_tree.heading(col, text=title)
            self.positions_tree.column(col, width=120, anchor=tk.CENTER)
        self.positions_tree.pack(fill=tk.X, pady=(0, 10))

        if FigureCanvasTkAgg and Figure:
            self.figure = Figure(figsize=(6, 4), dpi=100)
            self.ax_price = self.figure.add_subplot(211)
            self.ax_indicator = self.figure.add_subplot(212)
            self.canvas = FigureCanvasTkAgg(self.figure, master=right_panel)
            self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        else:
            warn = "Matplotlib не установлен — графики недоступны"
            if _MPL_ERROR:
                warn += f" ({_MPL_ERROR})"
            ttk.Label(right_panel, text=warn, foreground="red").pack(fill=tk.BOTH, expand=True)
            self.figure = None
            self.canvas = None
            self.ax_price = None
            self.ax_indicator = None

    def _populate_strategies(self) -> None:
        for child in self.strategy_frame.winfo_children():
            child.destroy()
        for strat in self.engine.list_strategies():
            var = tk.BooleanVar(value=self.engine.is_strategy_enabled(strat))
            chk = ttk.Checkbutton(
                self.strategy_frame,
                text=strat,
                variable=var,
                command=lambda name=strat, binding=var: self._toggle_strategy(name, binding),
            )
            chk.pack(anchor=tk.W)
            self.strategy_vars[strat] = var

    def _populate_symbols(self) -> None:
        symbols = sorted(self._collect_symbols()) or ["SBER"]
        self.symbol_combo["values"] = symbols
        if not self.symbol_var.get():
            self.symbol_var.set(symbols[0])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _collect_symbols(self) -> Iterable[str]:
        symbols = set()
        for strat in (self.engine.cfg.get("strategies") or {}).values():
            for symbol in (strat or {}).get("symbols", []) or []:
                symbols.add(str(symbol).upper())
        for symbol in self.engine.risk_manager.positions.keys():
            symbols.add(symbol.upper())
        return symbols

    def _toggle_strategy(self, name: str, var: "tk.BooleanVar") -> None:
        enabled = bool(var.get())
        self.engine.set_strategy_enabled(name, enabled)
        logger.info("Стратегия %s %s", name, "включена" if enabled else "отключена")

    def _on_start(self) -> None:
        self.engine.start()
        self.status_var.set("Статус: запущен")

    def _on_stop(self) -> None:
        self.engine.stop()
        self.status_var.set("Статус: остановлен")

    def _on_toggle_mode(self) -> None:
        mode = self.engine.toggle_mode()
        self.mode_var.set(f"Режим: {mode}")
        if messagebox:
            messagebox.showinfo("Режим", f"Переключен режим торговли: {mode}")

    def _update_positions(self) -> None:
        for item in self.positions_tree.get_children():
            self.positions_tree.delete(item)
        for symbol, pos in sorted(self.engine.risk_manager.positions.items()):
            qty = float(pos.get("quantity", 0))
            entry = float(pos.get("entry_price", 0.0) or 0.0)
            last = float(pos.get("last_price", entry) or entry)
            pnl = (last - entry) * qty
            self.positions_tree.insert(
                "",
                tk.END,
                values=(
                    symbol,
                    int(qty),
                    f"{entry:.2f}",
                    f"{last:.2f}",
                    f"{pnl:.2f}",
                ),
            )

    def _update_chart(self) -> None:
        if not getattr(self, "canvas", None):
            return
        symbol = self.symbol_var.get()
        history = self.engine.data_provider.load_history(symbol, interval="hour", days=90)
        if history is None or getattr(history, "empty", True):
            self.ax_price.clear()
            self.ax_indicator.clear()
            self.ax_price.set_title(f"Нет данных для {symbol}")
            self.canvas.draw_idle()
            return
        df = history.copy()
        df["time"] = pd.to_datetime(df.get("time") or df.index)
        df["SMA20"] = df["close"].rolling(window=20).mean()

        self.ax_price.clear()
        self.ax_price.plot(df["time"], df["close"], label="Close")
        self.ax_price.set_ylabel("Цена")
        self.ax_price.grid(True, alpha=0.2)
        self.ax_price.legend(loc="upper left")

        self.ax_indicator.clear()
        self.ax_indicator.bar(
            df["time"],
            df["close"].pct_change().fillna(0) * 100,
            label="Доходность %",
            alpha=0.4,
        )
        self.ax_indicator.plot(df["time"], df["SMA20"], color="orange", label="SMA20")
        self.ax_indicator.set_ylabel("%")
        self.ax_indicator.legend(loc="upper left")
        self.ax_indicator.grid(True, alpha=0.2)

        self.canvas.draw_idle()

    def _update_risk_summary(self) -> None:
        rm = self.engine.risk_manager
        equity = rm.portfolio_equity
        peak = max(rm.peak_equity, equity)
        drawdown = 1 - equity / max(peak, 1e-9)
        daily = (rm.day_start_equity - equity) / max(rm.day_start_equity, 1e-9)
        self.mode_var.set(f"Режим: {self.engine.state.trade_mode}")
        self.status_var.set("Статус: запущен" if self.engine.state.running else "Статус: пауза")
        self.equity_var.set(f"Капитал: {equity:,.0f} ₽ | Пик: {peak:,.0f} ₽")
        self.risk_var.set(f"Просадка: {drawdown:.2%} | Дневной результат: {-daily:.2%}")

    def _refresh(self) -> None:
        self._update_risk_summary()
        self._update_positions()
        self._update_chart()
        for name, var in self.strategy_vars.items():
            current = self.engine.is_strategy_enabled(name)
            if bool(var.get()) != current:
                var.set(current)
        self.root.after(self.refresh_ms, self._refresh)

    def _on_close(self) -> None:
        self.worker.stop()
        self.engine.stop()
        try:
            results_dir = Path(self.cfg.get("results_dir", "results"))
            results_dir.mkdir(parents=True, exist_ok=True)
            journal_path = results_dir / "risk_journal.csv"
            self.engine.journal.flush(journal_path)
        except Exception as exc:  # pragma: no cover - filesystem issues
            logger.debug("Не удалось сохранить журнал риска: %s", exc)
        self.root.destroy()


def launch_desktop(engine: Optional[Engine] = None) -> None:
    if _TK_ERROR is not None:
        raise RuntimeError(
            "Tkinter не доступен в текущем окружении. Установите tkinter/pillow пакеты."
        ) from _TK_ERROR
    root = tk.Tk()  # type: ignore[call-arg]
    DesktopApp(root, engine)
    root.mainloop()


def main() -> None:
    """CLI entry point for `python -m moex_bot.gui.desktop`."""

    logging.basicConfig(level=logging.INFO)
    launch_desktop()


__all__ = ["DesktopApp", "EngineWorker", "launch_desktop", "main"]
