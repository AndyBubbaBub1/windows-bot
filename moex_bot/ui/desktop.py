"""Простое настольное приложение на Tkinter для управления ботом."""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Dict

from ..core.config import load_config
from ..core.engine import Engine

logger = logging.getLogger(__name__)


class DesktopApp:
    """Tkinter-оболочка над :class:`Engine`."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.root = tk.Tk()
        self.root.title("MOEX Bot Desktop")
        self.root.geometry("780x640")
        self.strategy_vars: Dict[str, tk.BooleanVar] = {}
        self._build_layout()
        self._update_loop()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # Сборка интерфейса
    # ------------------------------------------------------------------
    def _build_layout(self) -> None:
        controls = ttk.Frame(self.root, padding=12)
        controls.pack(fill=tk.X)

        ttk.Label(controls, text="Режим:").pack(side=tk.LEFT)
        self.mode_var = tk.StringVar(value=self.engine.state.trade_mode)
        self.mode_label = ttk.Label(controls, textvariable=self.mode_var, width=12)
        self.mode_label.pack(side=tk.LEFT, padx=(4, 16))

        ttk.Button(controls, text="Старт", command=self._start).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="Стоп", command=self._stop).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="Переключить режим", command=self._toggle_mode).pack(
            side=tk.LEFT, padx=4
        )

        ttk.Button(controls, text="Запустить бэктест", command=self._run_backtests).pack(
            side=tk.RIGHT, padx=4
        )

        body = ttk.Panedwindow(self.root, orient=tk.VERTICAL)
        body.pack(fill=tk.BOTH, expand=True)

        top = ttk.Frame(body, padding=12)
        body.add(top, weight=3)
        bottom = ttk.Frame(body, padding=12)
        body.add(bottom, weight=2)

        # Блок стратегий
        strategy_box = ttk.LabelFrame(top, text="Стратегии", padding=8)
        strategy_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 12))
        for info in self.engine.list_strategies():
            var = tk.BooleanVar(value=bool(info.get("enabled", True)))
            self.strategy_vars[info["name"]] = var
            text = f"{info['name']} ({info.get('class','')} {info.get('module','')})"
            ttk.Checkbutton(
                strategy_box,
                text=text,
                variable=var,
                command=lambda name=info["name"], var=var: self._set_strategy(name, var.get()),
            ).pack(anchor=tk.W, pady=2)

        # Блок метрик
        metrics_box = ttk.LabelFrame(top, text="Риск-метрики", padding=8)
        metrics_box.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.metrics_vars: Dict[str, tk.StringVar] = {}
        for label in ("equity", "pnl", "gross_exposure", "intraday_drawdown_pct", "open_positions"):
            caption = ttk.Label(metrics_box, text=label, width=24)
            caption.pack(anchor=tk.W)
            var = tk.StringVar(value="—")
            self.metrics_vars[label] = var
            ttk.Label(metrics_box, textvariable=var, font=("Segoe UI", 11, "bold")).pack(
                anchor=tk.W, pady=(0, 6)
            )

        # Позиции
        positions_box = ttk.LabelFrame(bottom, text="Позиции", padding=8)
        positions_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 12))
        self.positions_tree = ttk.Treeview(
            positions_box,
            columns=("symbol", "quantity", "entry", "last", "strategy"),
            show="headings",
            height=8,
        )
        for col, heading in (
            ("symbol", "Тикер"),
            ("quantity", "Кол-во"),
            ("entry", "Цена входа"),
            ("last", "Текущая"),
            ("strategy", "Стратегия"),
        ):
            self.positions_tree.heading(col, text=heading)
            self.positions_tree.column(col, width=110, anchor=tk.CENTER)
        self.positions_tree.pack(fill=tk.BOTH, expand=True)

        # Журнал
        journal_box = ttk.LabelFrame(bottom, text="События", padding=8)
        journal_box.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.journal_text = tk.Text(journal_box, height=12, wrap=tk.WORD)
        self.journal_text.pack(fill=tk.BOTH, expand=True)
        self.journal_text.configure(state=tk.DISABLED)

    # ------------------------------------------------------------------
    # Действия пользователя
    # ------------------------------------------------------------------
    def _start(self) -> None:
        if not self.engine.state.running:
            self.engine.start()
            messagebox.showinfo("MOEX Bot", "Торговый цикл запущен")

    def _stop(self) -> None:
        if self.engine.state.running:
            self.engine.stop()
            messagebox.showinfo("MOEX Bot", "Торговля остановлена")

    def _toggle_mode(self) -> None:
        mode = self.engine.toggle_mode()
        self.mode_var.set(mode)

    def _set_strategy(self, name: str, enabled: bool) -> None:
        self.engine.set_strategy_enabled(name, enabled)

    def _run_backtests(self) -> None:
        def _worker() -> None:
            try:
                results = self.engine.run_backtests()
                message = f"Бэктест завершён ({len(results)} строк)"
            except Exception as exc:  # pragma: no cover - UI предупреждение
                logger.exception("Ошибка бэктеста: %s", exc)
                message = f"Ошибка бэктеста: {exc}"
            self.root.after(0, lambda: messagebox.showinfo("MOEX Bot", message))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_close(self) -> None:
        if self.engine.state.running:
            if not messagebox.askyesno("MOEX Bot", "Остановить торговлю и выйти?"):
                return
            self.engine.stop()
        self.root.destroy()

    # ------------------------------------------------------------------
    # Обновление интерфейса
    # ------------------------------------------------------------------
    def _update_loop(self) -> None:
        try:
            summary = self.engine.risk_manager.session_summary()
            self.metrics_vars["equity"].set(f"{summary['equity']:,.0f} ₽")
            self.metrics_vars["pnl"].set(f"{summary['pnl']:,.0f} ₽")
            self.metrics_vars["gross_exposure"].set(f"{summary['gross_exposure']:,.0f} ₽")
            self.metrics_vars["intraday_drawdown_pct"].set(
                f"{summary['intraday_drawdown_pct']:.2%}"
            )
            self.metrics_vars["open_positions"].set(str(summary["open_positions"]))
        except Exception:
            pass

        for item in self.positions_tree.get_children():
            self.positions_tree.delete(item)
        for pos in self.engine.positions_snapshot():
            self.positions_tree.insert(
                "",
                tk.END,
                values=(
                    pos["symbol"],
                    pos["quantity"],
                    f"{pos['entry_price']:.2f}",
                    f"{pos['last_price']:.2f}",
                    pos.get("strategy", ""),
                ),
            )

        events = self.engine.risk_events(limit=20)
        self.journal_text.configure(state=tk.NORMAL)
        self.journal_text.delete("1.0", tk.END)
        for row in events:
            line = f"[{row.get('timestamp')}] {row.get('symbol','')}: {row.get('message')}\n"
            self.journal_text.insert(tk.END, line)
        self.journal_text.configure(state=tk.DISABLED)

        self.root.after(2_000, self._update_loop)

    # ------------------------------------------------------------------
    # Запуск
    # ------------------------------------------------------------------
    def run(self) -> None:
        self.root.mainloop()


def launch_desktop() -> None:
    """Точка входа для консольного скрипта ``moex-desktop``."""

    logging.basicConfig(level=logging.INFO)
    cfg = load_config()
    engine = Engine.from_config(cfg)
    app = DesktopApp(engine)
    app.run()


__all__ = ["DesktopApp", "launch_desktop"]
