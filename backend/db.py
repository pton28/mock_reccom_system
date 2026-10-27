import json
import sqlite3
from contextlib import contextmanager

from backend.settings import data_dir
from pathlib import Path


@contextmanager
def connect():
    conn = sqlite3.connect(data_dir() / "app.sqlite3", timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with connect() as conn:
        conn.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS products(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events(event_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS orders(
            order_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS posthog_events(
            origin TEXT NOT NULL, event_id TEXT NOT NULL, payload TEXT NOT NULL,
            PRIMARY KEY(origin, event_id));
        CREATE INDEX IF NOT EXISTS events_session ON events(json_extract(payload, '$.distinct_id'), json_extract(payload, '$.session_id'));
        """)
        conn.executescript(Path(__file__).with_name("catalog.sql").read_text())


def records(table):
    if table not in {"users", "products", "events"}:
        raise ValueError("Unknown table")
    with connect() as conn:
        return [json.loads(row[0]) for row in conn.execute(f"SELECT payload FROM {table}")]


def get_record(table, key):
    if table not in {"users", "products"}:
        raise ValueError("Unknown table")
    with connect() as conn:
        row = conn.execute(f"SELECT payload FROM {table} WHERE id=?", (key,)).fetchone()
    return json.loads(row[0]) if row else None


def save_events(events):
    with connect() as conn:
        before = conn.total_changes
        conn.executemany("INSERT OR IGNORE INTO events VALUES (?, ?)",
                         [(e["event_id"], json.dumps(e)) for e in events])
        return conn.total_changes - before


def save_exported(events, origin):
    init_db()
    with connect() as conn:
        before = conn.total_changes
        conn.executemany("INSERT OR IGNORE INTO posthog_events VALUES (?, ?, ?)",
                         [(origin, e['event_id'], json.dumps(e)) for e in events])
        return conn.total_changes - before


def session_events(user, session, origin):
    with connect() as conn:
        return [json.loads(r[0]) for r in conn.execute("""SELECT payload FROM events
            WHERE json_extract(payload, '$.distinct_id')=? AND json_extract(payload, '$.session_id')=?
            AND COALESCE(json_extract(payload, '$.synthetic'), 1)=?""", (user, session, int(origin=='synthetic')))]
