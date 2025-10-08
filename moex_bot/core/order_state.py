from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Optional, Tuple

SCHEMA = """
CREATE TABLE IF NOT EXISTS pending_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    lots INTEGER NOT NULL,
    side TEXT NOT NULL, -- BUY or SELL
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

class OrderState:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as con:
            con.execute(SCHEMA)

    def save_intent(self, user_id: str, ticker: str, lots: int, side: str) -> int:
        with sqlite3.connect(self.db_path) as con:
            cur = con.execute(
                "INSERT INTO pending_orders(user_id, ticker, lots, side) VALUES (?,?,?,?)",
                (str(user_id), ticker.upper(), int(lots), side.upper()),
            )
            return cur.lastrowid

    def pop_last_for_user(self, user_id: str) -> Optional[Tuple[int, str, int, str]]:
        with sqlite3.connect(self.db_path) as con:
            cur = con.execute(
                "SELECT id, ticker, lots, side FROM pending_orders WHERE user_id=? ORDER BY id DESC LIMIT 1",
                (str(user_id),)
            )
            row = cur.fetchone()
            if not row:
                return None
            con.execute("DELETE FROM pending_orders WHERE id=?", (row[0],))
            return row  # (id, ticker, lots, side)
