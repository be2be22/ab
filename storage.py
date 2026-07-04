import sqlite3
import json
import os
import threading


class Storage:
    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_schema()

    def _init_schema(self):
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_topics (
                    user_id INTEGER PRIMARY KEY,
                    thoughts_topic_id INTEGER,
                    answer_topic_id INTEGER,
                    stats_topic_id INTEGER
                )
                """
            )
            # مهاجرت برای دیتابیس‌های قدیمی‌تر که ستون stats_topic_id رو نداشتن
            try:
                self._conn.execute("ALTER TABLE user_topics ADD COLUMN stats_topic_id INTEGER")
            except sqlite3.OperationalError:
                pass
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
    def get_topics(self, user_id: int) -> tuple[int, int, int | None] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT thoughts_topic_id, answer_topic_id, stats_topic_id FROM user_topics WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return tuple(row) if row else None

    def save_topics(
        self, user_id: int, thoughts_topic_id: int, answer_topic_id: int, stats_topic_id: int | None = None
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO user_topics (user_id, thoughts_topic_id, answer_topic_id, stats_topic_id)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    thoughts_topic_id = excluded.thoughts_topic_id,
                    answer_topic_id = excluded.answer_topic_id,
                    stats_topic_id = COALESCE(excluded.stats_topic_id, user_topics.stats_topic_id)
                """,
                (user_id, thoughts_topic_id, answer_topic_id, stats_topic_id),
            )
            self._conn.commit()

    def count_users(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM user_topics").fetchone()
        return row[0] if row else 0

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

    def get_full_history(self, user_id: int) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT role, content, created_at FROM history WHERE user_id = ? ORDER BY id ASC",
                (user_id,),
            ).fetchall()
        return [{"role": r, "content": c, "created_at": t} for r, c, t in rows]

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

    def reset_history(self, user_id: int) -> int:
        """تاریخچه‌ی یک کاربر رو پاک می‌کنه. تعداد ردیف‌های حذف‌شده رو برمی‌گردونه."""
        with self._lock:
            cur = self._conn.execute("DELETE FROM history WHERE user_id = ?", (user_id,))
            self._conn.commit()
            return cur.rowcount

    def count_messages(self, user_id: int | None = None) -> int:
        with self._lock:
            if user_id is None:
                row = self._conn.execute("SELECT COUNT(*) FROM history").fetchone()
            else:
                row = self._conn.execute(
                    "SELECT COUNT(*) FROM history WHERE user_id = ?", (user_id,)
                ).fetchone()
        return row[0] if row else 0

    # --- bot state (مثل offset آخرین آپدیت تلگرام، مدل فعال و ...) ---
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

    # --- مدل فعلیِ هر کاربر (سوییچ مدل شخصی‌سازی‌شده) ---
    def get_user_model(self, user_id: int) -> str | None:
        return self.get_state(f"user_model:{user_id}")

    def set_user_model(self, user_id: int, model_key: str) -> None:
        self.set_state(f"user_model:{user_id}", model_key)
