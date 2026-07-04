import re
import httpx

from key_manager import NvidiaKeyManager

THINK_TAG_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)


class AllKeysExhaustedError(Exception):
    pass


class NvidiaAgentClient:
    """
    کلاینت مستقیم روی HTTP (نه از طریق SDK رسمی openai) تا فیلدهای اضافه‌ای مثل
    reasoning_content که مدل‌های reasoning روی NIM برمی‌گردونن، از دست نره.
    """

    def __init__(self, key_manager: NvidiaKeyManager, base_url: str, model: str):
        self.key_manager = key_manager
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client = httpx.Client(timeout=120.0)

    def chat(self, messages: list[dict], tools: list[dict] | None = None, max_key_attempts: int | None = None) -> dict:
        """یک چرخه‌ی chat completion می‌زنه و دیکشنری message خام (شامل content, reasoning_content, tool_calls) رو برمی‌گردونه."""
        attempts = max_key_attempts or self.key_manager.total_keys()
        last_error: Exception | None = None

        for _ in range(attempts):
            api_key = self.key_manager.get_next_key()
            if api_key is None:
                wait = self.key_manager.seconds_until_next_available()
                raise AllKeysExhaustedError(
                    f"همه‌ی کلیدها موقتاً محدود شدن. حدود {wait:.0f} ثانیه دیگه دوباره امتحان کن."
                )

            payload = {"model": self.model, "messages": messages}
            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"

            try:
                resp = self._client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=payload,
                )
            except httpx.RequestError as e:
                last_error = e
                continue

            if resp.status_code == 429:
                retry_after = _parse_retry_after(resp.headers.get("retry-after"))
                self.key_manager.mark_rate_limited(api_key, retry_after)
                last_error = RuntimeError(f"429 rate limited: {resp.text[:200]}")
                continue

            if resp.status_code in (401, 403):
                self.key_manager.mark_invalid(api_key)
                last_error = RuntimeError(f"{resp.status_code} auth error: {resp.text[:200]}")
                continue

            if resp.status_code >= 400:
                raise RuntimeError(f"خطای NVIDIA API ({resp.status_code}): {resp.text[:500]}")

            data = resp.json()
            message = data["choices"][0]["message"]
            return _normalize_message(message)

        raise AllKeysExhaustedError(
            f"بعد از {attempts} تلاش با کلیدهای مختلف، درخواست موفق نشد. آخرین خطا: {last_error}"
        )


def _normalize_message(message: dict) -> dict:
    content = message.get("content") or ""
    reasoning = message.get("reasoning_content") or message.get("reasoning") or ""

    if not reasoning and "<think>" in content.lower():
        match = THINK_TAG_RE.search(content)
        if match:
            reasoning = match.group(1).strip()
            content = THINK_TAG_RE.sub("", content).strip()

    return {
        "role": message.get("role", "assistant"),
        "content": content,
        "reasoning_content": reasoning.strip() if reasoning else "",
        "tool_calls": message.get("tool_calls") or [],
    }


def _parse_retry_after(value):
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None
