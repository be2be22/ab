import time
import threading
from dataclasses import dataclass, field


@dataclass
class KeyState:
    key: str
    cooldown_until: float = 0.0  # timestamp یونیکس؛ اگه بزرگ‌تر از الان باشه یعنی هنوز سوخته‌ست

    def is_available(self) -> bool:
        return time.time() >= self.cooldown_until


class NvidiaKeyManager:
    """
    یه استخر (pool) از چند API key نگه می‌داره و به صورت round-robin بینشون می‌چرخه.
    وقتی یک کلید به rate-limit بخوره، موقتاً کنار گذاشته می‌شه تا کلیدهای دیگه استفاده بشن.
    """

    def __init__(self, keys: list[str], default_cooldown_seconds: int = 60):
        if not keys:
            raise ValueError("حداقل یک NVIDIA API key لازمه")
        self._states = [KeyState(key=k) for k in keys]
        self._default_cooldown = default_cooldown_seconds
        self._lock = threading.Lock()
        self._cursor = 0

    def total_keys(self) -> int:
        return len(self._states)

    def available_keys(self) -> int:
        return sum(1 for s in self._states if s.is_available())

    def get_next_key(self) -> str | None:
        """یک کلید فعال برمی‌گردونه، یا None اگه همه‌شون موقتاً سوخته باشن."""
        with self._lock:
            n = len(self._states)
            for i in range(n):
                idx = (self._cursor + i) % n
                state = self._states[idx]
                if state.is_available():
                    self._cursor = (idx + 1) % n
                    return state.key
            return None

    def seconds_until_next_available(self) -> float:
        with self._lock:
            if not self._states:
                return 0.0
            return max(0.0, min(s.cooldown_until for s in self._states) - time.time())

    def mark_rate_limited(self, key: str, retry_after_seconds: float | None = None) -> None:
        cooldown = retry_after_seconds if retry_after_seconds is not None else self._default_cooldown
        with self._lock:
            for state in self._states:
                if state.key == key:
                    state.cooldown_until = time.time() + cooldown
                    break

    def mark_invalid(self, key: str) -> None:
        """کلید کلاً نامعتبره (401/403) — برای مدت طولانی کنارش می‌ذاریم."""
        self.mark_rate_limited(key, retry_after_seconds=6 * 3600)
