"""
مدیریت API Key های 9Router (پروایدر OpenCode Free و بقیه‌ی مدل‌ها).

اگه چندتا API Key از داشبورد 9Router داری، می‌تونی چند تا رو با کاما توی
AI_API_KEYS بذاری. ربات به‌صورت sticky بینشون می‌چرخه — یعنی همون کلیدی که
کار می‌کنه رو نگه می‌داره تا وقتی که rate-limit بخوره. اگه یکی rate-limit
خورد، میره سراغ بعدی.
"""
import time
import threading
from dataclasses import dataclass


@dataclass
class TokenState:
    token: str
    cooldown_until: float = 0.0  # timestamp؛ اگه بزرگ‌تر از الان باشه یعنی هنوز محدوده
    request_count: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    last_used: float = 0.0

    def is_available(self) -> bool:
        return time.time() >= self.cooldown_until

    def masked(self) -> str:
        """نسخه‌ی ماسک‌شده برای نمایش آمار."""
        t = self.token
        if len(t) <= 12:
            return "*" * len(t)
        return f"{t[:8]}...{t[-4:]}"

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class AITokenManager:
    """
    یه استخر (pool) از چند API Key نگه می‌داره.

    استراتژی sticky: همون توکنی که داره کار می‌کنه رو نگه می‌داره تا وقتی که
    rate-limit بخوره؛ فقط اون وقت میره سراغ توکن بعدی. این یعنی:
    - فشار روی یه توکن پخش نمی‌شه، ولی توکن‌ها زودتر از موعد نمی‌سوزن
    - پیام «توکن عوض شد» فقط وقتی می‌ره که واقعاً توکن قبلی محدود شده باشه
    """

    def __init__(self, tokens: list[str], default_cooldown_seconds: int = 30):
        if not tokens:
            raise ValueError("حداقل یک API Key از 9Router لازمه")
        self._states = [TokenState(token=t) for t in tokens]
        self._default_cooldown = default_cooldown_seconds
        self._lock = threading.Lock()
        self._cursor = 0
        self._active_token: str | None = None
        self._previous_active_token: str | None = None

    def total_tokens_count(self) -> int:
        return len(self._states)

    def available_tokens_count(self) -> int:
        return sum(1 for s in self._states if s.is_available())

    def get_next_token(self) -> str | None:
        """
        یک توکن فعال برمی‌گردونه، یا None اگه همه‌شون موقتاً محدود باشن.

        استراتژی sticky: اول توکن فعلی رو امتحان می‌کنه (اگه هنوز در دسترسه).
        فقط اگه اون محدود باشه، میره سراغ توکن بعدی.
        """
        with self._lock:
            # اول: اگه توکن فعلی هنوز در دسترسه، همون رو برگردون
            if self._active_token is not None:
                for state in self._states:
                    if state.token == self._active_token and state.is_available():
                        return state.token

            # دوم: توکن بعدیِ در دسترس رو پیدا کن
            n = len(self._states)
            for i in range(n):
                idx = (self._cursor + i) % n
                state = self._states[idx]
                if state.is_available():
                    self._cursor = (idx + 1) % n
                    return state.token
            return None

    def mark_rate_limited(self, token: str, retry_after_seconds: float | None = None) -> None:
        """یه توکن رو موقتاً محدود می‌کنه."""
        cooldown = retry_after_seconds if retry_after_seconds is not None else self._default_cooldown
        with self._lock:
            for state in self._states:
                if state.token == token:
                    state.cooldown_until = time.time() + cooldown
                    break
            if self._active_token == token:
                self._previous_active_token = self._active_token
                self._active_token = None

    def record_usage(self, token: str, prompt_tokens: int, completion_tokens: int) -> bool:
        """
        بعد از یه درخواست موفق، مصرف رو ثبت می‌کنه.
        اگه توکن عوض شده باشه، True برمی‌گردونه (برای اعلان تو تاپیک آمار).
        """
        with self._lock:
            previous = self._active_token or self._previous_active_token
            switched = previous is not None and previous != token
            self._previous_active_token = previous
            self._active_token = token
            now = time.time()
            for state in self._states:
                if state.token == token:
                    state.prompt_tokens += prompt_tokens
                    state.completion_tokens += completion_tokens
                    state.request_count += 1
                    state.last_used = now
                    break
            return switched

    def active_token_masked(self) -> str | None:
        with self._lock:
            active = self._active_token
        if not active:
            return None
        for state in self._states:
            if state.token == active:
                return state.masked()
        return None

    def seconds_until_next_available(self) -> float:
        with self._lock:
            if not self._states:
                return 0.0
            return max(0.0, min(s.cooldown_until for s in self._states) - time.time())

    def usage_snapshot(self) -> list[dict]:
        """گزارش کامل مصرف هر توکن، برای نمایش توی تلگرام."""
        with self._lock:
            now = time.time()
            active = self._active_token
            snapshot = []
            for i, s in enumerate(self._states, start=1):
                snapshot.append({
                    "index": i,
                    "masked": s.masked(),
                    "is_active": s.token == active,
                    "available": s.is_available(),
                    "cooldown_seconds": max(0.0, s.cooldown_until - now),
                    "requests": s.request_count,
                    "prompt_tokens": s.prompt_tokens,
                    "completion_tokens": s.completion_tokens,
                    "total_tokens": s.total_tokens,
                    "last_used": s.last_used,
                })
            return snapshot

    def total_tokens_used(self) -> int:
        with self._lock:
            return sum(s.total_tokens for s in self._states)

    def total_requests(self) -> int:
        with self._lock:
            return sum(s.request_count for s in self._states)

    def reset_cooldowns(self) -> int:
        """تمام cooldown‌ها رو پاک می‌کنه. تعداد توکن‌هایی که از محدودیت خارج شدن رو برمی‌گردونه."""
        with self._lock:
            count = 0
            for state in self._states:
                if not state.is_available():
                    count += 1
                state.cooldown_until = 0.0
            return count
