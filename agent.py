import json

from config import Config
from nvidia_client import NvidiaAgentClient, AllKeysExhaustedError
from tools import TOOLS, TOOL_IMPLEMENTATIONS

SYSTEM_PROMPT = (
    "تو یک ایجنت هوش مصنوعی هستی که روی یک سرور لینوکسی اجرا می‌شی و به ترمینال همون سرور "
    "از طریق ابزار run_shell_command دسترسی داری. وقتی لازمه فایلی رو بررسی کنی، پکیجی نصب کنی، "
    "یا هر کار عملی دیگه‌ای انجام بدی، از این ابزار استفاده کن. قبل از اجرای دستورات مخرب یا "
    "غیرقابل‌برگشت (حذف فایل‌های مهم و غیره) با احتیاط کامل عمل کن. "
    "پاسخ نهایی رو همیشه به فارسی و روشن بنویس."
)


class AgentResult:
    def __init__(self, thoughts: list[str], final_answer: str):
        self.thoughts = thoughts
        self.final_answer = final_answer


def _message_to_dict(message) -> dict:
    d = {"role": "assistant", "content": message.content or ""}
    if getattr(message, "tool_calls", None):
        d["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in message.tool_calls
        ]
    return d


def run_agent(client: NvidiaAgentClient, history: list[dict], user_text: str) -> AgentResult:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_text})

    thoughts: list[str] = []
    tools = TOOLS if Config.SHELL_ENABLED else None

    for iteration in range(Config.MAX_AGENT_ITERATIONS):
        try:
            message = client.chat(messages, tools=tools)
        except AllKeysExhaustedError as e:
            return AgentResult(thoughts=thoughts, final_answer=f"⚠️ {e}")

        reasoning = getattr(message, "reasoning_content", None)
        if reasoning:
            thoughts.append(reasoning.strip())

        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            messages.append(_message_to_dict(message))
            for tc in tool_calls:
                fn_name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}

                thoughts.append(f"🔧 اجرای ابزار `{fn_name}` با آرگومان‌ها: {args}")

                impl = TOOL_IMPLEMENTATIONS.get(fn_name)
                result = impl(args) if impl else f"[خطا] ابزار ناشناخته: {fn_name}"

                thoughts.append(f"📤 خروجی `{fn_name}`:\n{result}")

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": str(result),
                    }
                )
            continue  # برو دور بعدی حلقه تا مدل با نتیجه ابزار جواب بده

        # اگه tool call نداشت، یعنی این پاسخ نهاییه
        final_answer = (message.content or "").strip()
        return AgentResult(thoughts=thoughts, final_answer=final_answer or "(پاسخ خالی برگشت)")

    return AgentResult(
        thoughts=thoughts,
        final_answer="⚠️ تعداد مراحل agent به سقف مجاز رسید بدون رسیدن به پاسخ نهایی.",
    )
