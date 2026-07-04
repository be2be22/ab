import json
import re
import httpx

from config import Config
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
        # HTTP/2 + connection pool بزرگ‌تر برای کاهش latency
        self._client = httpx.Client(
            timeout=httpx.Timeout(120.0, connect=10.0),
            http2=True,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
        )

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
        max_key_attempts: int | None = None,
        on_usage=None,
    ) -> dict:
        """یک چرخه‌ی chat completion می‌زنه و دیکشنری message خام (شامل content, reasoning_content, tool_calls) رو برمی‌گردونه."""
        use_model = model or self.model
        attempts = max_key_attempts or self.key_manager.total_keys()
        last_error: Exception | None = None

        for _ in range(attempts):
            api_key = self.key_manager.get_next_key()
            if api_key is None:
                wait = self.key_manager.seconds_until_next_available()
                raise AllKeysExhaustedError(
                    f"همه‌ی کلیدها موقتاً محدود شدن. حدود {wait:.0f} ثانیه دیگه دوباره امتحان کن."
                )

            payload = {"model": use_model, "messages": messages}
            payload["chat_template_kwargs"] = {"enable_thinking": Config.ENABLE_MODEL_THINKING, "clear_thinking": False}
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
                # برای خطاهای دیگه (400, 500, ...) کلید رو نمی‌سوزونیم،
                # فقط آخرین خطا رو نگه می‌داریم و با کلید بعدی امتحان می‌کنیم.
                last_error = RuntimeError(f"خطای NVIDIA API ({resp.status_code}): {resp.text[:500]}")
                continue

            data = resp.json()
            message = data["choices"][0]["message"]
            self._report_usage(api_key, data.get("usage") or {}, on_usage)
            return _normalize_message(message)

        raise AllKeysExhaustedError(
            f"بعد از {attempts} تلاش با کلیدهای مختلف، درخواست موفق نشد. آخرین خطا: {last_error}"
        )

    def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
        max_key_attempts: int | None = None,
        on_content_delta=None,
        on_reasoning_delta=None,
        on_usage=None,
    ) -> dict:
        """
        نسخه‌ی استریم‌شده: با stream=True به NIM وصل می‌شه و chunk‌های SSE رو می‌خونه.
        به محض رسیدن هر تکه از content/reasoning، callback مربوطه صدا زده می‌شه (برای
        ادیت زنده‌ی پیام تلگرام). در پایان، همون دیکشنری نرمال‌شده‌ی message رو
        (مثل chat()) برمی‌گردونه تا بقیه‌ی حلقه‌ی agent بدون تغییر کار کنه.
        """
        use_model = model or self.model
        attempts = max_key_attempts or self.key_manager.total_keys()
        last_error: Exception | None = None

        for _ in range(attempts):
            api_key = self.key_manager.get_next_key()
            if api_key is None:
                wait = self.key_manager.seconds_until_next_available()
                raise AllKeysExhaustedError(
                    f"همه‌ی کلیدها موقتاً محدود شدن. حدود {wait:.0f} ثانیه دیگه دوباره امتحان کن."
                )

            payload = {"model": use_model, "messages": messages, "stream": True}
            payload["stream_options"] = {"include_usage": True}
            payload["chat_template_kwargs"] = {"enable_thinking": Config.ENABLE_MODEL_THINKING, "clear_thinking": False}
            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"

            content_parts: list[str] = []
            reasoning_parts: list[str] = []
            tool_calls_acc: dict[int, dict] = {}
            usage: dict = {}
            role = "assistant"

            try:
                with self._client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=payload,
                ) as resp:
                    if resp.status_code == 429:
                        resp.read()
                        retry_after = _parse_retry_after(resp.headers.get("retry-after"))
                        self.key_manager.mark_rate_limited(api_key, retry_after)
                        last_error = RuntimeError("429 rate limited")
                        continue
                    if resp.status_code in (401, 403):
                        resp.read()
                        self.key_manager.mark_invalid(api_key)
                        last_error = RuntimeError(f"{resp.status_code} auth error")
                        continue
                    if resp.status_code >= 400:
                        body = resp.read()
                        # برای خطاهای دیگه (400, 500, ...) کلید رو نمی‌سوزونیم
                        last_error = RuntimeError(f"خطای NVIDIA API ({resp.status_code}): {body[:500]}")
                        continue

                    for line in resp.iter_lines():
                        if not line:
                            continue
                        if not line.startswith("data:"):
                            continue
                        data_str = line[len("data:"):].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        chunk_usage = chunk.get("usage")
                        if chunk_usage:
                            usage = chunk_usage

                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        role = delta.get("role", role)

                        content_piece = delta.get("content")
                        if content_piece:
                            content_parts.append(content_piece)
                            if on_content_delta:
                                on_content_delta(content_piece)

                        reasoning_piece = delta.get("reasoning_content") or delta.get("reasoning")
                        if reasoning_piece:
                            reasoning_parts.append(reasoning_piece)
                            if on_reasoning_delta:
                                on_reasoning_delta(reasoning_piece)

                        for tc_delta in delta.get("tool_calls") or []:
                            idx = tc_delta.get("index", 0)
                            entry = tool_calls_acc.setdefault(
                                idx,
                                {"id": None, "type": "function", "function": {"name": "", "arguments": ""}},
                            )
                            if tc_delta.get("id"):
                                entry["id"] = tc_delta["id"]
                            fn_delta = tc_delta.get("function") or {}
                            if fn_delta.get("name"):
                                entry["function"]["name"] += fn_delta["name"]
                            if fn_delta.get("arguments"):
                                entry["function"]["arguments"] += fn_delta["arguments"]

            except (httpx.RequestError, httpx.StreamError) as e:
                # StreamError (مثل StreamClosed) subclasses RuntimeError هستن،
                # نه RequestError، برای همین خودشون هم باید صریح catch بشن.
                # این مهمه چون بعد از [DONE] ممکنه یه StreamClosed بیاد.
                last_error = e
                continue

            self._report_usage(api_key, usage, on_usage)

            tool_calls = [tool_calls_acc[i] for i in sorted(tool_calls_acc)] if tool_calls_acc else []
            message = {
                "role": role,
                "content": "".join(content_parts),
                "reasoning_content": "".join(reasoning_parts),
                "tool_calls": tool_calls,
            }
            return _normalize_message(message)

        raise AllKeysExhaustedError(
            f"بعد از {attempts} تلاش با کلیدهای مختلف، درخواست موفق نشد. آخرین خطا: {last_error}"
        )

    def _report_usage(self, api_key: str, usage: dict, on_usage) -> None:
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        previous_masked = self.key_manager.active_key_masked()
        switched = self.key_manager.record_usage(api_key, prompt_tokens, completion_tokens)
        if on_usage:
            try:
                on_usage(
                    {
                        "masked_key": self.key_manager.active_key_masked(),
                        "previous_masked_key": previous_masked,
                        "switched": switched,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                    }
                )
            except Exception:
                pass


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
