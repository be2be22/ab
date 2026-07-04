import json

from config import Config
from cf_client import CloudflareAIClient, CloudflareError
from tools import TOOLS, TOOL_IMPLEMENTATIONS

SYSTEM_PROMPT = (
    "تو یک دستیار هوشمند فارسی‌زبان هستی که روی یک سرور لینوکسی اجرا می‌شی. "
    "به ترمینال سرور از طریق run_shell_command و run_python دسترسی داری و می‌تونی "
    "تو وب با web_search و web_fetch جستجو کنی.\n\n"
    "## قوانین مهم:\n\n"
    "1. **ساده پاسخ بده:** برای سوالات ساده (مثل سلام، معرفی خودت، شعر، توضیح مفهوم) "
    "مستقیم جواب بده و از ابزارها استفاده نکن. ابزارها فقط برای کارهای واقعی لازم هستن.\n\n"
    "2. **جستجوی وب:** فقط وقتی به اطلاعات به‌روز نیاز داری (قیمت امروز، اخبار، "
    "آب‌وهوا، نسخه‌ی جدید یه نرم‌افزار) از web_search استفاده کن. برای سوالات عمومی "
    "نیازی به جستجو نیست.\n\n"
    "3. **اجرای کد:** وقتی کاربر خواست یه محاسبه انجام بشه، فایل بررسی بشه، یا "
    "هر کار عملی دیگه، از run_python یا run_shell_command استفاده کن.\n\n"
    "4. **ارسال فایل:** فقط وقتی کاربر صریحاً خواست یه فایل بفرستی (مثلاً «یه عکس "
    "بساز و بفرست» یا «یه PDF بده») از send_telegram_file استفاده کن. برای پاسخ‌های "
    "متنی معمولی نیازی به این ابزار نیست.\n\n"
    "5. **زبان:** پاسخ نهایی رو همیشه به فارسی روان بنویس. برای کد از بلاک‌های "
    "مارک‌داون (```) استفاده کن.\n\n"
    "6. **احتیاط:** قبل از اجرای دستورات مخرب (حذف فایل‌های مهم) با احتیاط عمل کن."
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


def _looks_like_tool_call_json(text: str) -> bool:
    """بررسی می‌کنه که آیا متن مدل به‌جای یه پاسخ واقعی، یه JSON tool_call هست."""
    if not text:
        return False
    text = text.strip()
    if not (text.startswith("{") and text.endswith("}")):
        return False
    lowered = text.lower()
    keywords = ["\"name\"", "\"parameters\"", "\"arguments\"", "run_python", "run_shell", "web_search", "web_fetch", "send_telegram"]
    return any(k.lower() in lowered for k in keywords)


# کلمات کلیدی که نشون می‌دن کاربر واقعاً به یه ابزار نیاز داره
_TOOL_KEYWORDS = [
    # اجرای کد / شل — فقط کلمات فنی
    "run_python", "run_shell", "run python", "run shell",
    "python", "shell", "ترمینال", "terminal", "bash",
    "کد بزن", "کد بنویس", "اجرای کد", "اجرا کن",
    # جستجوی وب
    "جستجو", "سرچ", "search", "گوگل", "google", "اینترنت", "وب‌سرچ", "web search",
    "قیمت", "اخبار", "نرخ", "هواشناسی", "آب و هوا", "آب‌وهوا",
    "امروز", "الان", "اخیر", "جدیدترین", "به‌روز", "به روز",
    # فایل
    "فایل بفرست", "file send", "دانلود کن", "آپلود کن",
    "send_telegram", "عکس بفرست", "تصویر بفرست",
    # تحلیل فنی
    "تحلیل کن", "بررسی کن", "analyze", "inspect",
]


def _needs_tools(user_content) -> bool:
    """بررسی می‌کنه که آیا پیام کاربر به ابزارها نیاز داره یا نه."""
    # اگه لیست (تصویر) هست، tools بفرست
    if isinstance(user_content, list):
        return True
    if not isinstance(user_content, str):
        return True
    text = user_content.lower()
    # اگه پیام خیلی کوتاهه (مثل «سلام»، «چطوری»، «ممنون»)، tools لازم نیست
    if len(text.strip()) < 15:
        return False
    # اگه کلمات کلیدی tool داره، tools بفرست
    return any(k in text for k in _TOOL_KEYWORDS)


def run_agent(
    client: CloudflareAIClient,
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

    اگه on_content_delta پاس داده بشه، به صورت استریم صدا زده می‌شه.
    on_usage: بعد از هر درخواست موفق صدا زده می‌شه با اطلاعات مصرف توکن و
    اینکه آیا توکن عوض شده یا نه.
    tool_context: دیکشنری‌ای که دست ابزارهایی مثل send_telegram_file می‌رسه.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_content})

    thoughts: list[str] = []
    # اگه SHELL_ENABLED=false باشه، فقط ابزارهای وب و send_telegram_file در دسترسن
    if Config.SHELL_ENABLED:
        all_tools = TOOLS
    else:
        all_tools = [t for t in TOOLS if t["function"]["name"] in ("web_search", "web_fetch", "send_telegram_file")]

    # ⚡ بهینه‌سازی سرعت: اگه پیام کاربر به ابزار نیاز نداره (سوال ساده، سلام، شعر و ...),
    # tools رو اصلاً به مدل نمی‌فرستیم. اینطوری مدل مستقیم جواب می‌ده و سریع‌تر می‌شه.
    if all_tools and not _needs_tools(user_content):
        tools = None
    else:
        tools = all_tools
    tool_context = tool_context or {}

    for step in range(Config.MAX_AGENT_ITERATIONS):
        if on_step_start:
            on_step_start()
        try:
            # ⚡ بهینه‌سازی سرعت برای مدل‌های reasoning (مثل GLM-5.2):
            # اگه سوال ساده‌ست (به tool نیاز نداره)، max_tokens رو کم می‌کنیم تا
            # reasoning سریع‌تر تموم بشه.
            if not tools and step == 0 and not _needs_tools(user_content):
                max_tok = 800  # سوال ساده — کافیه
            elif tools:
                max_tok = 2000  # برای tool_call بیشتر لازمه
            else:
                max_tok = 1500  # حالت وسط

            if on_content_delta or on_reasoning_delta:
                message = client.chat_stream(
                    messages,
                    tools=tools,
                    model=model,
                    on_content_delta=on_content_delta,
                    on_reasoning_delta=on_reasoning_delta,
                    on_usage=on_usage,
                    max_tokens=max_tok,
                )
            else:
                message = client.chat(
                    messages,
                    tools=tools,
                    model=model,
                    on_usage=on_usage,
                    max_tokens=max_tok,
                )
        except CloudflareError as e:
            err_msg = f"⚠️ خطای Cloudflare: {e}"
            print(f"⚠️ Agent CloudflareError at step {step}: {e}")
            return AgentResult(thoughts=thoughts, final_answer=err_msg)
        except Exception as e:
            err_msg = f"⚠️ خطا در ارتباط با مدل: {e}"
            print(f"⚠️ Agent error at step {step}: {type(e).__name__}: {e}")
            return AgentResult(thoughts=thoughts, final_answer=err_msg)

        reasoning = message.get("reasoning_content")
        if reasoning:
            thoughts.append(f"💭 {reasoning}")

        tool_calls = message.get("tool_calls")
        if tool_calls:
            # اگه مدل همزمان content و tool_calls داره، content رو هم تو thoughts ذخیره کن
            inline_content = (message.get("content") or "").strip()
            if inline_content:
                thoughts.append(f"💬 {inline_content}")

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
                try:
                    result = impl(args, tool_context) if impl else f"[خطا] ابزار ناشناخته: {fn_name}"
                except Exception as e:
                    result = f"[خطا] اجرای ابزار `{fn_name}` شکست خورد: {e}"

                thoughts.append(f"📤 خروجی `{fn_name}`:\n{result}")

                # اگه tool_call_id نبود، یه id ساختگی بساز
                tc_id = tc.get("id") or f"call_{fn_name}_{len(messages)}"
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": str(result),
                    }
                )
            continue

        final_answer = (message.get("content") or "").strip()
        # اگه مدل content رو به‌شکل JSON tool_call فرستاده، دوباره بدون tools امتحان کن
        if final_answer and _looks_like_tool_call_json(final_answer) and step == 0 and tools:
            try:
                retry_msg = client.chat(messages, tools=None, model=model, on_usage=on_usage, max_tokens=1500)
                retry_content = (retry_msg.get("content") or "").strip()
                if retry_content and not _looks_like_tool_call_json(retry_content):
                    final_answer = retry_content
            except Exception:
                pass

        if not final_answer and not thoughts:
            final_answer = "(پاسخ خالی برگشت)"
        elif not final_answer:
            final_answer = "(مدل فقط فکر کرد ولی پاسخ نهایی متنی برنگردوند)"
        return AgentResult(thoughts=thoughts, final_answer=final_answer)

    return AgentResult(
        thoughts=thoughts,
        final_answer="⚠️ تعداد مراحل agent به سقف مجاز رسید بدون رسیدن به پاسخ نهایی.",
    )
