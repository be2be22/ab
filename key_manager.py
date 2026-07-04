import time
import threading
from dataclasses import dataclass, field


@dataclass
class KeyState:
    key: str
    cooldown_until: float = 0.0  # timestamp یونیکس؛ اگه بزرگ‌تر از الان باشه یعنی هنوز سوخته‌ست
    prompt_tokens: int = 0
    completion_tokens: int = 0
    request_count: int = 0

    def is_available(self) -> bool:
        return time.time() >= self.cooldown_until

    def masked(self) -> str:
        k = self.key
        if len(k) <= 10:
            return "*" * len(k)
        return f"{k[:6]}...{k[-4:]}"

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class NvidiaKeyManager:
    """
    یه استخر (pool) از چند API key نگه می‌داره و به صورت round-robin بینشون می‌چرخه.
    وقتی یک کلید به rate-limit بخوره، موقتاً کنار گذاشته می‌شه تا کلیدهای دیگه استفاده بشن.
    علاوه بر این، مصرف توکن هر کلید و اینکه الان کدوم کلید «فعال» (آخرین کلیدی که واقعاً
    باهاش درخواست موفق زده شده) رو هم نگه می‌داره تا بشه توی تلگرام گزارشش داد.
    """

    def __init__(self, keys: list[str], default_cooldown_seconds: int = 60, token_budget_per_key: int = 0):
        if not keys:
            raise ValueError("حداقل یک NVIDIA API key لازمه")
        self._states = [KeyState(key=k) for k in keys]
        self._default_cooldown = default_cooldown_seconds
        self._token_budget_per_key = token_budget_per_key
        self._lock = threading.Lock()
        self._cursor = 0
        self._active_key: str | None = None

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

    def record_usage(self, key: str, prompt_tokens: int, completion_tokens: int) -> bool:
        """
        بعد از یک درخواست *موفق*، مصرف توکن اون کلید رو ثبت می‌کنه.
        اگه این کلید با آخرین کلیدی که موفق استفاده شده بود فرق داشته باشه یعنی
        سوییچ کلید اتفاق افتاده؛ در این صورت True برمی‌گردونه.
        """
        with self._lock:
            switched = self._active_key is not None and self._active_key != key
            self._active_key = key
            for state in self._states:
                if state.key == key:
                    state.prompt_tokens += prompt_tokens
                    state.completion_tokens += completion_tokens
                    state.request_count += 1
                    break
            return switched

    def active_key_masked(self) -> str | None:
        with self._lock:
            active = self._active_key
        if not active:
            return None
        for state in self._states:
            if state.key == active:
                return state.masked()
        return None

    def usage_snapshot(self) -> list[dict]:
        """گزارش کامل مصرف هر کلید، برای نمایش توی تلگرام."""
        with self._lock:
            now = time.time()
            active = self._active_key
            snapshot = []
            for i, s in enumerate(self._states, start=1):
                remaining = None
                if self._token_budget_per_key > 0:
                    remaining = max(0, self._token_budget_per_key - s.total_tokens)
                snapshot.append(
                    {
                        "index": i,
                        "masked": s.masked(),
                        "is_active": s.key == active,
                        "available": s.is_available(),
                        "cooldown_seconds": max(0.0, s.cooldown_until - now),
                        "requests": s.request_count,
                        "prompt_tokens": s.prompt_tokens,
                        "completion_tokens": s.completion_tokens,
                        "total_tokens": s.total_tokens,
                        "remaining_tokens": remaining,
                    }
                )
            return snapshot
