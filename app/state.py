"""Estado da conversa por usuário (SQLite)."""
import json
import sqlite3
from contextlib import closing

from .config import DB_PATH


def _conn():
    return sqlite3.connect(DB_PATH)


def init():
    with closing(_conn()) as c:
        c.execute("CREATE TABLE IF NOT EXISTS sessions (user_id TEXT PRIMARY KEY, step TEXT, data TEXT)")
        c.commit()


def get(user_id: str) -> dict:
    with closing(_conn()) as c:
        row = c.execute("SELECT step, data FROM sessions WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        return {"step": "AGUARDANDO_FOTO", "data": {}}
    return {"step": row[0], "data": json.loads(row[1])}


def save(user_id: str, step: str, data: dict):
    with closing(_conn()) as c:
        c.execute(
            "INSERT INTO sessions(user_id, step, data) VALUES(?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET step=excluded.step, data=excluded.data",
            (user_id, step, json.dumps(data, ensure_ascii=False)),
        )
        c.commit()


def reset(user_id: str):
    save(user_id, "AGUARDANDO_FOTO", {})
