import os
import contextlib
from datetime import datetime

import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ["DATABASE_URL"]


@contextlib.contextmanager
def get_conn():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    name TEXT NOT NULL,
                    current_price INTEGER NOT NULL,
                    lowest_price INTEGER NOT NULL,
                    registered_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS price_history (
                    id SERIAL PRIMARY KEY,
                    item_id INTEGER NOT NULL,
                    price INTEGER NOT NULL,
                    checked_at TEXT NOT NULL,
                    FOREIGN KEY (item_id) REFERENCES items(id)
                )
            """)


def upsert_user(user_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (user_id, created_at) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (user_id, datetime.utcnow().isoformat()),
            )


def add_item(user_id: str, url: str, name: str, price: int) -> int:
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO items (user_id, url, name, current_price, lowest_price, registered_at) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (user_id, url, name, price, price, now),
            )
            item_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO price_history (item_id, price, checked_at) VALUES (%s, %s, %s)",
                (item_id, price, now),
            )
    return item_id


def get_items_by_user(user_id: str) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM items WHERE user_id = %s ORDER BY id",
                (user_id,),
            )
            return cur.fetchall()


def get_all_items() -> list[dict]:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM items")
            return cur.fetchall()


def delete_item(user_id: str, item_index: int) -> str | None:
    """1-based index within the user's item list. Returns deleted item name or None."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, name FROM items WHERE user_id = %s ORDER BY id",
                (user_id,),
            )
            rows = cur.fetchall()
            if item_index < 1 or item_index > len(rows):
                return None
            target = rows[item_index - 1]
            cur.execute("DELETE FROM price_history WHERE item_id = %s", (target["id"],))
            cur.execute("DELETE FROM items WHERE id = %s", (target["id"],))
            return target["name"]


def update_price(item_id: int, new_price: int):
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT lowest_price FROM items WHERE id = %s", (item_id,))
            row = cur.fetchone()
            lowest = min(row["lowest_price"], new_price)
            cur.execute(
                "UPDATE items SET current_price = %s, lowest_price = %s WHERE id = %s",
                (new_price, lowest, item_id),
            )
            cur.execute(
                "INSERT INTO price_history (item_id, price, checked_at) VALUES (%s, %s, %s)",
                (item_id, new_price, now),
            )
