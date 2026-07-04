"""
کلاینت Cloudflare Workers AI.

Cloudflare Workers AI یه API سازگار با OpenAI ارائه می‌ده که مدل‌های مختلفی داره
از جمله GLM-5.2 (مدل reasoning فارسی‌زبان از Z-AI) و Llama-3.3-70B (سریع + باکیفیت).

این کلاینت از CloudflareTokenManager استفاده می‌کنه تا چند توکن رو مدیریت کنه.
اگه یه توکن rate-limit بخوره، خودکار میره سراغ بعدی.
"""
import json
import re
import time
import httpx

from config import Config
from cf_key_manager import CloudflareTokenManager

THINK_TAG_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)


class CloudflareError(Exception):
    """خطای مخصوص Cloudflare — اگه retry ها تموم بشن پرتاب می‌شه."""
    pass


class CloudflareAIClient:
    """
    کلاینت برای Cloudflare Workers AI.

    chat() و chat_stream() همون امضای کلاینت‌های قبلی رو دارن تا agent.py بدون تغییر کار کنه.
    پیام برگشتی: {"role", "content", "reasoning_content", "tool_calls"}
    """

    def __init__(self, token_manager: CloudflareTokenManager, base_url: str, model: str):
        self.token_manager = token_manager
        self.base_url = base_url.rstrip("/")
        self.model = model
        # HTTP/2 + connection pool بزرگ‌تر برای کاهش latency
        self._client = httpx.Client(
            timeout=httpx.Timeout(60.0, connect=8.0),
            http2=True,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
        )

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
        on_usage=None,
        max_tokens: int | None = None,
        reasoning_effort: str | None = None,
    ) -> dict:
        """یک چرخه‌ی chat completion می‌زنه و دیکشنری message نرمال‌شده رو برمی‌گردونه."""
        use_model = model or self.model
        max_retries = Config.CF_MAX_RETRIES + self.token_manager.total_tokens_count()
        last_error: Exception | None = None

        for _ in range(max_retries):
            token = self.token_manager.get_next_token()
            if token is None:
                wait = self.token_manager.seconds_until_next_available()
                raise CloudflareError(
                    f"همه‌ی توکن‌ها موقتاً محدود شدن. حدود {wait:.0f} ثانیه دیگه دوباره امتحان کن."
                )

            payload = {
                "model": use_model,
                "messages": messages,
                "max_tokens": max_tokens or 4096,
            }
            if reasoning_effort:
                payload["reasoning_effort"] = reasoning_effort
            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"

            try:
                resp = self._client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            except (httpx.RequestError, httpx.StreamError) as e:
                last_error = e
                time.sleep(Config.CF_RETRY_DELAY)
                continue

            if resp.status_code == 429:
                self.token_manager.mark_rate_limited(token)
                last_error = RuntimeError("429 rate limited")
                continue

            if resp.status_code in (401, 403):
                # توکن نامعتبر — برای مدت طولانی کنارش بذار
                self.token_manager.mark_rate_limited(token, retry_after_seconds=6 * 3600)
                last_error = RuntimeError(f"{resp.status_code} auth error")
                continue

            if resp.status_code >= 400:
                body = resp.text
                # خطای Capacity — این توکن رو محدود کن و با توکن بعدی امتحان کن
                if "Capacity" in body or "capacity" in body or resp.status_code == 503:
                    self.token_manager.mark_rate_limited(token, retry_after_seconds=15)
                    last_error = RuntimeError(f"Capacity error ({resp.status_code})")
                    continue
                raise CloudflareError(f"خطای Cloudflare API ({resp.status_code}): {body[:500]}")

            data = resp.json()

            # Cloudflare خطا رو تو بدنه هم می‌تونه بذاره
            if not data.get("success", True):
                errors = data.get("errors") or []
                err_msg = errors[0].get("message", "unknown") if errors else "unknown"
                if "Capacity" in err_msg:
                    self.token_manager.mark_rate_limited(token, retry_after_seconds=15)
                    last_error = RuntimeError(f"Capacity error: {err_msg}")
                    continue
                raise CloudflareError(f"خطای Cloudflare: {err_msg}")

            message = data["choices"][0]["message"]
            usage = data.get("usage") or {}
            # ثبت مصرف
            switched = self.token_manager.record_usage(
                token,
                prompt_tokens=int(usage.get("prompt_tokens", 0)),
                completion_tokens=int(usage.get("completion_tokens", 0)),
            )
            if on_usage:
                try:
                    on_usage({
                        "masked_token": self.token_manager.active_token_masked(),
                        "switched": switched,
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                    })
                except Exception:
                    pass
            return _normalize_message(message)

        raise CloudflareError(
            f"بعد از {max_retries} تلاش، درخواست Cloudflare موفق نشد. آخرین خطا: {last_error}"
        )

    def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
        on_content_delta=None,
        on_reasoning_delta=None,
        on_usage=None,
        max_tokens: int | None = None,
        reasoning_effort: str | None = None,
    ) -> dict:
        """
        نسخه‌ی استریم‌شده: با stream=True به Cloudflare وصل می‌شه و chunk‌های SSE رو می‌خونه.
        به محض رسیدن هر تکه از content/reasoning، callback مربوطه صدا زده می‌شه.
        در پایان، همون دیکشنری نرمال‌شده‌ی message رو برمی‌گردونه.

        نکته برای GLM-5.2: مدل اول reasoning_content رو استریم می‌کنه (فکر مدل به انگلیسی)
        و بعد content رو (جواب نهایی به فارسی). با reasoning_effort می‌شه میزان این فکر
        کردن رو کنترل کرد (low = سریع‌تر، کمتر فکر می‌کنه).
        """
        use_model = model or self.model
        max_retries = Config.CF_MAX_RETRIES + self.token_manager.total_tokens_count()
        last_error: Exception | None = None

        for _ in range(max_retries):
            token = self.token_manager.get_next_token()
            if token is None:
                wait = self.token_manager.seconds_until_next_available()
                raise CloudflareError(
                    f"همه‌ی توکن‌ها موقتاً محدود شدن. حدود {wait:.0f} ثانیه دیگه دوباره امتحان کن."
                )

            payload = {
                "model": use_model,
                "messages": messages,
                "stream": True,
                "max_tokens": max_tokens or 4096,
            }
            if reasoning_effort:
                payload["reasoning_effort"] = reasoning_effort
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
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                ) as resp:
                    if resp.status_code == 429:
                        resp.read()
                        self.token_manager.mark_rate_limited(token)
                        last_error = RuntimeError("429 rate limited")
                        continue
                    if resp.status_code in (401, 403):
                        resp.read()
                        self.token_manager.mark_rate_limited(token, retry_after_seconds=6 * 3600)
                        last_error = RuntimeError(f"{resp.status_code} auth error")
                        continue
                    if resp.status_code >= 400:
                        body = resp.read().decode("utf-8", errors="replace")
                        if "Capacity" in body or resp.status_code == 503:
                            self.token_manager.mark_rate_limited(token, retry_after_seconds=15)
                            last_error = RuntimeError(f"Capacity error ({resp.status_code})")
                            continue
                        raise CloudflareError(f"خطای Cloudflare API ({resp.status_code}): {body[:500]}")

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

                        # usage معمولاً تو chunk آخر میاد
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

                        reasoning_piece = delta.get("reasoning_content")
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
                last_error = e
                time.sleep(Config.CF_RETRY_DELAY)
                continue

            # ثبت مصرف
            switched = self.token_manager.record_usage(
                token,
                prompt_tokens=int(usage.get("prompt_tokens", 0)),
                completion_tokens=int(usage.get("completion_tokens", 0)),
            )
            if on_usage:
                try:
                    on_usage({
                        "masked_token": self.token_manager.active_token_masked(),
                        "switched": switched,
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                    })
                except Exception:
                    pass

            tool_calls = [tool_calls_acc[i] for i in sorted(tool_calls_acc)] if tool_calls_acc else []
            message = {
                "role": role,
                "content": "".join(content_parts),
                "reasoning_content": "".join(reasoning_parts),
                "tool_calls": tool_calls,
            }
            return _normalize_message(message)

        raise CloudflareError(
            f"بعد از {max_retries} تلاش، درخواست استریم Cloudflare موفق نشد. آخرین خطا: {last_error}"
        )


def _normalize_message(message: dict) -> dict:
    """پیام رو نرمال می‌کنه."""
    content = message.get("content") or ""
    reasoning = message.get("reasoning_content") or message.get("reasoning") or ""

    # بعضی مدل‌ها reasoning رو داخل <think>...</think> تو content می‌ذارن
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
