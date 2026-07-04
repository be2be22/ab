import time
from openai import OpenAI, RateLimitError, AuthenticationError, APIStatusError

from key_manager import NvidiaKeyManager


class AllKeysExhaustedError(Exception):
    pass


class NvidiaAgentClient:
    def __init__(self, key_manager: NvidiaKeyManager, base_url: str, model: str):
        self.key_manager = key_manager
        self.base_url = base_url
        self.model = model

    def _build_client(self, api_key: str) -> OpenAI:
        return OpenAI(base_url=self.base_url, api_key=api_key)

    def chat(self, messages: list[dict], tools: list[dict] | None = None, max_key_attempts: int | None = None):
        """
        یک درخواست chat completion می‌فرسته. اگه به rate-limit خورد، خودکار با کلید بعدی retry می‌کنه.
        در نهایت آبجکت پاسخ (response.choices[0].message) رو برمی‌گردونه.
        """
        attempts = max_key_attempts or self.key_manager.total_keys()
        last_error: Exception | None = None

        for _ in range(attempts):
            api_key = self.key_manager.get_next_key()
            if api_key is None:
                wait = self.key_manager.seconds_until_next_available()
                raise AllKeysExhaustedError(
                    f"همه‌ی کلیدها موقتاً محدود شدن. حدود {wait:.0f} ثانیه دیگه دوباره امتحان کن."
                )

            client = self._build_client(api_key)
            try:
                kwargs = {"model": self.model, "messages": messages}
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = "auto"
                response = client.chat.completions.create(**kwargs)
                return response.choices[0].message

            except RateLimitError as e:
                retry_after = _extract_retry_after(e)
                self.key_manager.mark_rate_limited(api_key, retry_after)
                last_error = e
                continue

            except AuthenticationError as e:
                # کلید نامعتبره (اشتباه تایپی یا expired) — برای مدت طولانی کنارش بذار
                self.key_manager.mark_invalid(api_key)
                last_error = e
                continue

            except APIStatusError as e:
                # بعضی وقت‌ها rate limit با کد دیگه‌ای برمی‌گرده (مثلاً 429 داخل یک استثنای عمومی‌تر)
                if e.status_code == 429:
                    retry_after = _extract_retry_after(e)
                    self.key_manager.mark_rate_limited(api_key, retry_after)
                    last_error = e
                    continue
                raise

        raise AllKeysExhaustedError(
            f"بعد از {attempts} تلاش با کلیدهای مختلف، درخواست موفق نشد. آخرین خطا: {last_error}"
        )


def _extract_retry_after(error: Exception) -> float | None:
    try:
        headers = getattr(error, "response", None)
        if headers is not None and hasattr(headers, "headers"):
            value = headers.headers.get("retry-after")
            if value:
                return float(value)
    except Exception:
        pass
    return None
