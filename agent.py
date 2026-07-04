import json

from config import Config
from nvidia_client import NvidiaAgentClient, AllKeysExhaustedError
from tools import TOOLS, TOOL_IMPLEMENTATIONS

SYSTEM_PROMPT = (
    "تو یک ایجنت هوش مصنوعی هستی که روی یک سرور لینوکسی اجرا می‌شی و به ترمینال همون سرور "
    "از طریق ابزار run_shell_command و run_python دسترسی داری. وقتی لازمه فایلی رو بررسی کنی، "
    "پکیجی نصب کنی، یا هر کار عملی دیگه‌ای انجام بدی، از ابزار مناسب استفاده کن.\n\n"
    "🔍 جستجوی وب: تو به وب دسترسی داری! از ابزار `web_search` برای جستجوی عبارت‌ها تو گوگل "
    "(از طریق Bing) استفاده کن. اگه به اطلاعات به‌روز، اخبار، قیمت‌ها، مستندات، "
    "یا هر چیزی که بعد از تاریخ آموزشت هست نیاز داشتی، حتماً جستجو کن. بعد از پیدا کردن "
    "نتیجه‌ی مناسب، با `web_fetch` می‌تونی محتوای کامل صفحه‌ی موردنظر رو هم بخونی.\n\n"
    "قوانین:\n"
    "- قبل از اجرای دستورات مخرب یا غیرقابل‌برگشت (حذف فایل‌های مهم و غیره) با احتیاط کامل عمل کن.\n"
    "- اگه کاربر سوال زمان‌مندی پرسید (قیمت امروز، اخبار، وضعیت آب‌وهوا) حتماً جستجو کن.\n"
    "- اگه لازم شد یک فایل، عکس، نمودار، یا خروجیِ ساخته‌شده رو مستقیماً برای کاربر در تلگرام "
    "بفرستی (نه فقط توی متن پاسخ توضیحش بدی)، اول با run_shell_command یا run_python فایل رو "
    "روی سرور بساز و بعد با ابزار send_telegram_file مسیرش رو بده تا مستقیماً آپلود و ارسال بشه.\n"
    "- پاسخ نهایی رو همیشه به فارسی و روشن بنویس. برای کد از بلاک‌های مارک‌داون (```) استفاده کن."
)


class AgentResult:
    def __init__(self, thoughts: list[str], final_answer: str):
        self.thoughts = thoughts
        self.final_answer = final_answer


def _assistant_message_for_history(message: dict) -> dict:
    """پیامی که باید به تاریخچه‌ی ارسالی به مدل اضافه بشه (برای دور بعدی حلقه)."""
    d = {"role": "assistant", "content": message.get("content") or ""}
    if message.get("tool_calls"):
        d["tool_calls"] = message["tool_calls"]
    return d


def run_agent(
    client: NvidiaAgentClient,
    history: list[dict],
    user_content,
    model: str | None = None,
    on_content_delta=None,
    on_reasoning_delta=None,
    on_step_start=None,
    on_usage=None,
    tool_context: dict | None = None,
) -> AgentResult:
    """
    user_content می‌تونه یک رشته‌ی ساده باشه یا یک لیست از content-part های OpenAI-style
    (برای پشتیبانی تصویر: [{"type": "text", ...}, {"type": "image_url", ...}]).

    اگه on_content_delta پاس داده بشه، فقط در آخرین مرحله (که دیگه tool_call نداره و
    پاسخ نهاییه) به صورت استریم صدا زده می‌شه؛ این یعنی پیام تلگرام می‌تونه هم‌زمان با
    تولید متن توسط مدل، آپدیت (edit) بشه.

    on_usage: بعد از هر درخواست موفق به مدل صدا زده می‌شه با اطلاعات مصرف توکن و
    اینکه آیا کلید عوض شده یا نه (برای گزارش زنده توی تاپیک آمار).

    tool_context: دیکشنری‌ای که دست ابزارهایی مثل send_telegram_file می‌رسه تا بتونن
    مستقیماً برای کاربر توی تلگرام پیام/فایل بفرستن.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_content})

    thoughts: list[str] = []
    # اگه SHELL_ENABLED=false باشه، فقط ابزارهای وب و send_telegram_file در دسترسن
    if Config.SHELL_ENABLED:
        tools = TOOLS
    else:
        tools = [t for t in TOOLS if t["function"]["name"] in ("web_search", "web_fetch", "send_telegram_file")]
    tool_context = tool_context or {}

    for step in range(Config.MAX_AGENT_ITERATIONS):
        if on_step_start:
            on_step_start()
        try:
            if on_content_delta or on_reasoning_delta:
                message = client.chat_stream(
                    messages,
                    tools=tools,
                    model=model,
                    on_content_delta=on_content_delta,
                    on_reasoning_delta=on_reasoning_delta,
                    on_usage=on_usage,
                )
            else:
                message = client.chat(messages, tools=tools, model=model, on_usage=on_usage)
        except AllKeysExhaustedError as e:
            return AgentResult(thoughts=thoughts, final_answer=f"⚠️ {e}")

        reasoning = message.get("reasoning_content")
        if reasoning:
            thoughts.append(f"💭 {reasoning}")

        tool_calls = message.get("tool_calls")
        if tool_calls:
            messages.append(_assistant_message_for_history(message))
            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                raw_args = tc["function"].get("arguments") or "{}"
                try:
                    args = json.loads(raw_args)
                except json.JSONDecodeError:
                    args = {}

                thoughts.append(f"🔧 اجرای ابزار `{fn_name}` با آرگومان‌ها: {args}")

                impl = TOOL_IMPLEMENTATIONS.get(fn_name)
                result = impl(args, tool_context) if impl else f"[خطا] ابزار ناشناخته: {fn_name}"

                thoughts.append(f"📤 خروجی `{fn_name}`:\n{result}")

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": str(result),
                    }
                )
            continue

        final_answer = (message.get("content") or "").strip()
        if not final_answer and not thoughts:
            final_answer = "(پاسخ خالی برگشت)"
        elif not final_answer:
            final_answer = "(مدل فقط فکر کرد ولی پاسخ نهایی متنی برنگردوند)"
        return AgentResult(thoughts=thoughts, final_answer=final_answer)

    return AgentResult(
        thoughts=thoughts,
        final_answer="⚠️ تعداد مراحل agent به سقف مجاز رسید بدون رسیدن به پاسخ نهایی.",
    )
