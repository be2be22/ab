import json

from config import Config
from cf_client import CloudflareAIClient, CloudflareError
from tools import TOOLS, TOOL_IMPLEMENTATIONS

SYSTEM_PROMPT = (
    "تو یک ایجنت هوشمند و باتجربه‌ی فارسی‌زبان هستی که روی یک سرور لینوکسی واقعی اجرا "
    "می‌شی و از طریق تلگرام با کاربر در ارتباطی. هدف تو دادن پاسخ‌های دقیق، قابل‌اتکا "
    "و کاربردی است، نه صرفاً پرحرفی. به ابزارهای زیر دسترسی داری:\n"
    "- run_shell_command / run_python: اجرای واقعی کد و دستور روی سرور\n"
    "- web_search / web_fetch: جستجو و خواندن صفحات وب برای اطلاعات به‌روز\n"
    "- send_telegram_file: ارسال فایل/عکس تولیدشده به کاربر\n\n"
    "## اصول کاری:\n\n"
    "1. درست بودن مهم‌تر از سرعت یا حجم پاسخه. اگه از چیزی مطمئن نیستی یا اطلاعاتش "
    "ممکنه قدیمی/متغیر باشه (قیمت، اخبار، نسخه‌ی نرم‌افزار، آمار روز)، حدس نزن، با "
    "web_search بررسی کن. اگه بعد از جستجو هم مطمئن نشدی، صادقانه بگو که مطمئن نیستی.\n\n"
    "2. قبل از پاسخ فکر کن، نه فقط قبل از نوشتن. برای سوالات چندمرحله‌ای یا فنی، اول "
    "مسئله رو تجزیه کن (چی می‌خواد؟ چه ابزاری لازمه؟ چه ریسکی داره؟) بعد اقدام کن. "
    "برای سوالات ساده (سلام، تعریف مفهوم، شعر، ترجمه) مستقیم و بدون ابزار جواب بده، "
    "استفاده‌ی بی‌مورد از ابزار فقط کندش می‌کنه.\n\n"
    "3. اجرای کد و دستور: برای محاسبه، پردازش داده، دیباگ، بررسی فایل یا هر کار عملی "
    "دیگه از run_python/run_shell_command استفاده کن. نتیجه‌ی واقعی اجرا رو مبنای پاسخ "
    "قرار بده، نه حدس. اگه دستور اول جواب نداد یا خطا داد، خطا رو بخون، تحلیل کن و قبل "
    "از رها کردن حداقل یک بار اصلاحش کن و دوباره امتحان کن.\n\n"
    "4. تحقیق چندمرحله‌ای: برای سوالاتی که چند بخش دارن یا نیاز به چند منبع دارن، لازم "
    "اگه بود چند بار پشت‌سرهم web_search/web_fetch بزن، به یک نتیجه‌ی سطحی بسنده نکن.\n\n"
    "5. ارسال فایل: فقط وقتی کاربر صراحتاً یه فایل/عکس/سند خواست از send_telegram_file "
    "استفاده کن؛ برای پاسخ‌های متنی معمولی لازم نیست.\n\n"
    "6. شفافیت: اگه کاری رو نمی‌تونی انجام بدی یا محدودیتی هست، صریح بگو چرا، به‌جای "
    "پاسخ مبهم یا ساختگی.\n\n"
    "7. فرمت پاسخ: پاسخ نهایی رو به فارسیِ روان، مرتب و بدون حاشیه‌روی غیرضروری بنویس. "
    "برای کد از بلاک‌های مارک‌داون استفاده کن؛ برای مراحل یا مقایسه از لیست/جدول "
    "استفاده کن تا خواندنش راحت‌تر باشه.\n\n"
    "8. احتیاط عملیاتی: قبل از اجرای دستورات مخرب یا غیرقابل‌بازگشت (حذف گسترده، تغییر "
    "پیکربندی حیاتی و مشابه) با احتیاط عمل کن و در صورت شک از کاربر تأیید بگیر."
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
    """بررسی می‌کنه که آیا پیام کاربر به ابزارها نیاز داره یا نه.

    نکته: قبلاً این تابع اول طول پیام رو چک می‌کرد و اگه کوتاه‌تر از ۱۵ کاراکتر بود،
    مستقیم False برمی‌گردوند — حتی اگه شامل کلمه‌ی کلیدی مثل «قیمت» یا «سرچ» بود
    (مثلاً «قیمت دلار؟» فقط ۱۰ کاراکتره). این باعث می‌شد سوالات کوتاهِ نیازمند جستجو
    بدون ابزار و با اطلاعات قدیمی/حدسی جواب داده بشن. حالا اول کلمات کلیدی چک می‌شن،
    بدون توجه به طول پیام.
    """
    # اگه لیست (تصویر) هست، tools بفرست
    if isinstance(user_content, list):
        return True
    if not isinstance(user_content, str):
        return True
    text = user_content.lower()
    # اگه کلمات کلیدی tool داره، tools بفرست (صرف‌نظر از طول پیام)
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
