import sqlite3
import json
import os
import threading


class Storage:
    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_schema()

    def _init_schema(self):
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_topics (
                    user_id INTEGER PRIMARY KEY,
                    thoughts_topic_id INTEGER,
                    answer_topic_id INTEGER
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    role TEXT,
                    content TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_state (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
                """
            )
            self._conn.commit()

    # --- topics ---
    def get_topics(self, user_id: int) -> tuple[int, int] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT thoughts_topic_id, answer_topic_id FROM user_topics WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return tuple(row) if row else None

    def save_topics(self, user_id: int, thoughts_topic_id: int, answer_topic_id: int) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO user_topics (user_id, thoughts_topic_id, answer_topic_id)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    thoughts_topic_id = excluded.thoughts_topic_id,
                    answer_topic_id = excluded.answer_topic_id
                """,
                (user_id, thoughts_topic_id, answer_topic_id),
            )
            self._conn.commit()

    # --- history ---
    def add_message(self, user_id: int, role: str, content: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO history (user_id, role, content) VALUES (?, ?, ?)",
                (user_id, role, content),
            )
            self._conn.commit()

    def get_history(self, user_id: int, limit: int) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT role, content FROM history WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [{"role": r, "content": c} for r, c in reversed(rows)]

    def trim_history(self, user_id: int, keep_last: int) -> None:
        with self._lock:
            self._conn.execute(
                """
                DELETE FROM history WHERE user_id = ? AND id NOT IN (
                    SELECT id FROM history WHERE user_id = ? ORDER BY id DESC LIMIT ?
                )
                """,
                (user_id, user_id, keep_last),
            )
            self._conn.commit()

    # --- bot state (مثل offset آخرین آپدیت تلگرام) ---
    def get_state(self, key: str) -> str | None:
        with self._lock:
            row = self._conn.execute("SELECT value FROM bot_state WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def set_state(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO bot_state (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )
            self._conn.commit()
