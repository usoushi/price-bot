import os
import sqlite3
import contextlib
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "/tmp/price_bot.db")


@contextlib.contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                url TEXT NOT NULL,
                name TEXT NOT NULL,
                current_price INTEGER NOT NULL,
                lowest_price INTEGER NOT NULL,
                registered_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                price INTEGER NOT NULL,
                checked_at TEXT NOT NULL,
                FOREIGN KEY (item_id) REFERENCES items(id)
            );
        """)


def upsert_user(user_id: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id, created_at) VALUES (?, ?)",
            (user_id, datetime.utcnow().isoformat()),
        )


def add_item(user_id: str, url: str, name: str, price: int) -> int:
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO items (user_id, url, name, current_price, lowest_price, registered_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, url, name, price, price, now),
        )
        item_id = cur.lastrowid
        conn.execute(
            "INSERT INTO price_history (item_id, price, checked_at) VALUES (?, ?, ?)",
            (item_id, price, now),
        )
    return item_id


def get_items_by_user(user_id: str) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM items WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()


def get_all_items() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM items").fetchall()


def delete_item(user_id: str, item_index: int) -> str | None:
    """1-based index within the user's item list. Returns deleted item name or None."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, name FROM items WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
        if item_index < 1 or item_index > len(rows):
            return None
        target = rows[item_index - 1]
        conn.execute("DELETE FROM price_history WHERE item_id = ?", (target["id"],))
        conn.execute("DELETE FROM items WHERE id = ?", (target["id"],))
        return target["name"]


def update_price(item_id: int, new_price: int):
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        row = conn.execute("SELECT lowest_price FROM items WHERE id = ?", (item_id,)).fetchone()
        lowest = min(row["lowest_price"], new_price)
        conn.execute(
            "UPDATE items SET current_price = ?, lowest_price = ? WHERE id = ?",
            (new_price, lowest, item_id),
        )
        conn.execute(
            "INSERT INTO price_history (item_id, price, checked_at) VALUES (?, ?, ?)",
            (item_id, new_price, now),
        )
