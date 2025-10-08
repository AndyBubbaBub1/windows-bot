"""Persistent storage utilities using SQLite.

This module provides a minimal abstraction over SQLite for storing and
retrieving trading data, strategy metrics, and generated reports.
By default the database is created in the results directory specified
in the configuration.  Users can provide a custom path when calling
``init_db``.

The schema defines three tables:

* ``trades`` – records individual executed trades including strategy
  name, symbol, timestamp, price, quantity, side, and fees.
* ``metrics`` – stores computed performance metrics for each
  strategy run.  The metrics include PnL, risk ratios and trade
  counts.
* ``reports`` – contains paths to generated report files along with
  metadata such as type and creation timestamp.

All functions are synchronous and use the built‑in ``sqlite3`` module
from Python's standard library.  For more advanced use cases or
concurrent access consider using a full‑featured ORM like SQLAlchemy.
"""

from __future__ import annotations

import sqlite3
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable, Dict, Any, List, Optional

def init_db(db_path: str) -> None:
    """Initialise the SQLite database and create tables if they do not exist.

    This function ensures the database uses Write-Ahead Logging (WAL)
    journaling mode for better concurrency and performance.  It
    creates the necessary tables if they are absent.

    Args:
        db_path: Filesystem path to the SQLite database file.
    """
    # Ensure parent directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    # Enable WAL mode for improved concurrent reads/writes
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    except Exception:
        pass
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_name TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                price REAL NOT NULL,
                quantity REAL NOT NULL,
                side TEXT NOT NULL,
                fees REAL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_name TEXT NOT NULL,
                run_date TEXT NOT NULL,
                pnl_pct REAL,
                pnl_abs REAL,
                sharpe REAL,
                sortino REAL,
                calmar REAL,
                max_drawdown REAL,
                time_to_recovery INTEGER,
                var REAL,
                cvar REAL,
                trades_count INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_name TEXT,
                report_type TEXT NOT NULL,
                file_path TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
    conn.close()


# ---------------------------------------------------------------------------
# Internal helpers for file‑based locking
# ---------------------------------------------------------------------------

def _acquire_db_lock(db_path: str) -> int:
    """Acquire a filesystem lock for the given database.

    This function attempts to create a ``.lock`` file next to the
    database.  If the file already exists it waits until it is
    removed.  It returns a file descriptor which must be passed to
    ``_release_db_lock`` when finished.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        An OS file descriptor for the lock file.
    """
    lock_path = f"{db_path}.lock"
    # Keep trying until the lock file can be created
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            return fd
        except FileExistsError:
            # Another process holds the lock; wait and retry
            time.sleep(0.05)


def _release_db_lock(fd: int, db_path: str) -> None:
    """Release a filesystem lock acquired with ``_acquire_db_lock``.

    Closes the file descriptor and removes the ``.lock`` file.

    Args:
        fd: File descriptor returned from ``_acquire_db_lock``.
        db_path: Path to the SQLite database file.
    """
    try:
        os.close(fd)
    except Exception:
        pass
    lock_path = f"{db_path}.lock"
    try:
        os.remove(lock_path)
    except Exception:
        pass


def save_trade_history(db_path: str, trades: Iterable[Dict[str, Any]]) -> None:
    """Insert a collection of trade records into the database.

    Each trade dictionary must contain the keys: ``strategy_name``,
    ``symbol``, ``timestamp`` (ISO format), ``price``, ``quantity``,
    ``side``, and optionally ``fees``.

    Args:
        db_path: Path to the SQLite database file.
        trades: Iterable of trade dictionaries.
    """
    # Acquire lock before writing
    lock_fd = _acquire_db_lock(db_path)
    try:
        conn = sqlite3.connect(db_path)
        with conn:
            conn.executemany(
                """
                INSERT INTO trades (strategy_name, symbol, timestamp, price, quantity, side, fees)
                VALUES (:strategy_name, :symbol, :timestamp, :price, :quantity, :side, :fees)
                """,
                trades,
            )
        conn.close()
    finally:
        _release_db_lock(lock_fd, db_path)


def save_metrics(db_path: str, strategy_name: str, metrics: Dict[str, Any], run_date: Optional[str] = None) -> None:
    """Persist performance metrics for a strategy run.

    Args:
        db_path: Path to the SQLite database file.
        strategy_name: Name of the strategy.
        metrics: Dictionary of metric values (keys must match columns).
        run_date: Optional ISO date string; defaults to current date/time.
    """
    if run_date is None:
        run_date = datetime.utcnow().isoformat()
    data = {
        'strategy_name': strategy_name,
        'run_date': run_date,
        'pnl_pct': metrics.get('pnl_pct'),
        'pnl_abs': metrics.get('pnl_abs'),
        'sharpe': metrics.get('sharpe'),
        'sortino': metrics.get('sortino'),
        'calmar': metrics.get('calmar'),
        'max_drawdown': metrics.get('max_drawdown'),
        'time_to_recovery': metrics.get('time_to_recovery'),
        'var': metrics.get('VaR'),
        'cvar': metrics.get('CVaR'),
        'trades_count': metrics.get('trades'),
    }
    lock_fd = _acquire_db_lock(db_path)
    try:
        conn = sqlite3.connect(db_path)
        with conn:
            conn.execute(
                """
                INSERT INTO metrics (
                    strategy_name, run_date, pnl_pct, pnl_abs, sharpe,
                    sortino, calmar, max_drawdown, time_to_recovery, var, cvar, trades_count
                )
                VALUES (
                    :strategy_name, :run_date, :pnl_pct, :pnl_abs, :sharpe,
                    :sortino, :calmar, :max_drawdown, :time_to_recovery, :var, :cvar, :trades_count
                )
                """,
                data,
            )
        conn.close()
    finally:
        _release_db_lock(lock_fd, db_path)


def save_report_entry(db_path: str, strategy_name: Optional[str], report_type: str, file_path: str) -> None:
    """Insert a record for a generated report file.

    Args:
        db_path: Path to the SQLite database file.
        strategy_name: Name of the strategy the report pertains to, or
            ``None`` for portfolio reports.
        report_type: Short identifier (e.g. ``'csv'``, ``'html'``, ``'portfolio'``).
        file_path: Absolute or relative path to the report file.
    """
    created_at = datetime.utcnow().isoformat()
    lock_fd = _acquire_db_lock(db_path)
    try:
        conn = sqlite3.connect(db_path)
        with conn:
            conn.execute(
                """
                INSERT INTO reports (strategy_name, report_type, file_path, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (strategy_name, report_type, file_path, created_at),
            )
        conn.close()
    finally:
        _release_db_lock(lock_fd, db_path)


def fetch_metrics(db_path: str, strategy_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve stored metrics from the database.

    Args:
        db_path: Path to the SQLite database file.
        strategy_name: Optional filter to return metrics only for a specific strategy.

    Returns:
        List of dictionaries containing metrics records.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if strategy_name:
        cursor.execute(
            """SELECT * FROM metrics WHERE strategy_name = ? ORDER BY run_date DESC""",
            (strategy_name,),
        )
    else:
        cursor.execute("SELECT * FROM metrics ORDER BY run_date DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def fetch_reports(db_path: str, strategy_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve stored report entries from the database.

    Args:
        db_path: Path to the SQLite database file.
        strategy_name: Optional filter to return only reports for the given strategy.

    Returns:
        List of dictionaries for each report entry.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if strategy_name:
        cursor.execute(
            "SELECT * FROM reports WHERE strategy_name = ? ORDER BY created_at DESC",
            (strategy_name,),
        )
    else:
        cursor.execute("SELECT * FROM reports ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]