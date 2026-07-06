import subprocess
import sys
import tempfile
import os
import re
import urllib.parse
import httpx

from config import Config

# الگوهای پرخطر که پیش‌فرض بلاک می‌شن مگر اینکه ALLOW_DANGEROUS_COMMANDS=true باشه
DANGEROUS_PATTERNS = [
    "rm -rf /",
    "rm -rf /*",
    "mkfs",
    "dd if=",
    ":(){ :|:& };:",
    "shutdown",
    "reboot",
    "> /dev/sda",
    "chmod -R 777 /",
    "chown -R",
    "userdel",
    "passwd",
]

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_TELEGRAM_UPLOAD_BYTES = 45 * 1024 * 1024  # کمی زیر سقف ۵۰ مگابایتی تلگرام برای اطمینان

SHELL_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "run_shell_command",
        "description": (
            "یک دستور شل (bash) روی سرور اجرا می‌کنه و خروجی stdout/stderr رو برمی‌گردونه. "
            "برای بررسی فایل‌ها، نصب پکیج، دیباگ، اجرای هر زبان برنامه‌نویسی دیگه، یا هر کار "
            "دیگه‌ای که نیاز به ترمینال داره استفاده کن."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "دستور کامل شل برای اجرا، مثلا: ls -la /app",
                }
            },
            "required": ["command"],
        },
    },
}

PYTHON_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "run_python",
        "description": (
            "کد پایتون رو در یک پروسه‌ی جدا اجرا می‌کنه و stdout/stderr رو برمی‌گردونه. "
            "برای محاسبات، پردازش داده، تست الگوریتم، یا هر چیزی که سریع‌تر با پایتون "
            "حل می‌شه استفاده کن."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "کد کامل پایتون برای اجرا.",
                }
            },
            "required": ["code"],
        },
    },
}

SEND_FILE_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "send_telegram_file",
        "description": (
            "یک فایل که روی سرور ساختی یا دانلود کردی (سند، عکس، PDF، CSV، نمودار و غیره) رو "
            "مستقیماً برای کاربر در چت تلگرام ارسال می‌کنه. اول با run_shell_command یا run_python "
            "فایل رو روی دیسک بساز، بعد مسیر کاملش رو اینجا بده. اگه پسوند فایل عکس باشه "
            "(jpg/jpeg/png/webp/gif) به صورت عکس نمایش داده می‌شه، وگرنه به‌عنوان سند/فایل "
            "قابل‌دانلود ارسال می‌شه. حداکثر حجم پشتیبانی‌شده حدود ۴۵ مگابایته."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "مسیر کامل فایل روی سرور، مثلا /tmp/output.png یا /tmp/report.pdf",
                },
                "caption": {
                    "type": "string",
                    "description": "توضیح کوتاه اختیاری که همراه فایل نمایش داده می‌شه.",
                },
            },
            "required": ["file_path"],
        },
    },
}

WEB_SEARCH_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "یک عبارت رو تو گوگل/بینگ جستجو می‌کنه و لیستی از نتایج (عنوان، URL، "
            "خلاصه) رو برمی‌گردونه. برای پیدا کردن اطلاعات به‌روز، اخبار، قیمت‌ها، "
            "مستندات و هر چیزی که نیاز به وب داره استفاده کن. فقط متن ساده جستجو کن. "
            "این ابزار همیشه فعال هست و باید برای سوالات زمان‌مندی حتماً ازش استفاده کنی."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "عبارت جستجو، مثلا: 'قیمت بیت‌کوین امروز'",
                },
                "max_results": {
                    "type": "integer",
                    "description": "حداکثر تعداد نتایج (پیش‌فرض: 5).",
                }
            },
            "required": ["query"],
        },
    },
}

WEB_FETCH_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_fetch",
        "description": (
            "محتوای متنی یک صفحه‌ی وب رو از روی URL می‌خونه و برمی‌گردونه. برای خواندن "
            "جزئیات یکی از نتایج جستجو، مستندات، یا هر صفحه‌ی دیگه استفاده کن. HTML به "
            "متن ساده تبدیل می‌شه."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL کامل صفحه‌ای که می‌خوای بخونی.",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "حداکثر تعداد کاراکتر متن برگشتی (پیش‌فرض: 6000).",
                }
            },
            "required": ["url"],
        },
    },
}


def is_dangerous(command: str) -> bool:
    lowered = command.lower()
    return any(pattern in lowered for pattern in DANGEROUS_PATTERNS)


def run_shell_command(command: str) -> str:
    if not Config.SHELL_ENABLED:
        return "[خطا] اجرای شل روی این ربات غیرفعاله (SHELL_ENABLED=false)."

    if is_dangerous(command) and not Config.ALLOW_DANGEROUS_COMMANDS:
        return (
            f"[بلاک شد] این دستور به عنوان دستور پرخطر شناسایی شد و اجرا نشد: {command}\n"
            "اگه مطمئنی، ALLOW_DANGEROUS_COMMANDS=true رو در env تنظیم کن."
        )

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=Config.SHELL_TIMEOUT_SECONDS,
        )
        output = ""
        if result.stdout:
            output += f"stdout:\n{result.stdout.strip()}\n"
        if result.stderr:
            output += f"stderr:\n{result.stderr.strip()}\n"
        output += f"exit_code: {result.returncode}"
        # جلوگیری از پیام‌های خیلی طولانی
        if len(output) > 3500:
            output = output[:3500] + "\n...[بریده شد]"
        return output
    except subprocess.TimeoutExpired:
        return f"[خطا] دستور بعد از {Config.SHELL_TIMEOUT_SECONDS} ثانیه timeout شد."
    except Exception as e:
        return f"[خطا] اجرای دستور شکست خورد: {e}"


def run_python(code: str) -> str:
    """
    کد پایتون رو در یک پروسه‌ی مجزا (subprocess) با timeout اجرا می‌کنه.
    توجه امنیتی: این ابزار، مثل run_shell_command، اجرای کد دلخواه روی همون کانتینر
    رو ممکن می‌کنه. حتما ALLOWED_USER_IDS رو محدود نگه دار.
    """
    if not Config.SHELL_ENABLED:
        return "[خطا] اجرای کد روی این ربات غیرفعاله (SHELL_ENABLED=false)."

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        path = f.name

    try:
        result = subprocess.run(
            [sys.executable, path],
            capture_output=True,
            text=True,
            timeout=Config.PYTHON_TIMEOUT_SECONDS,
        )
        output = ""
        if result.stdout:
            output += f"stdout:\n{result.stdout.strip()}\n"
        if result.stderr:
            output += f"stderr:\n{result.stderr.strip()}\n"
        output += f"exit_code: {result.returncode}"
        if len(output) > 3500:
            output = output[:3500] + "\n...[بریده شد]"
        return output
    except subprocess.TimeoutExpired:
        return f"[خطا] اجرای کد بعد از {Config.PYTHON_TIMEOUT_SECONDS} ثانیه timeout شد."
    except Exception as e:
        return f"[خطا] اجرای کد شکست خورد: {e}"
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def send_telegram_file(file_path: str, caption: str, context: dict) -> str:
    """
    context باید شامل tg (نمونه‌ی TelegramAPI)، chat_id و answer_topic_id باشه؛
    این‌ها رو agent.run_agent از main.py دریافت و پاس می‌ده.
    """
    tg = context.get("tg")
    chat_id = context.get("chat_id")
    thread_id = context.get("answer_topic_id")

    if not tg or not chat_id:
        return "[خطا] امکان ارسال فایل در این حالت وجود نداره (context تلگرام در دسترس نیست)."

    if not file_path or not os.path.isfile(file_path):
        return f"[خطا] فایلی با مسیر «{file_path}» پیدا نشد."

    size = os.path.getsize(file_path)
    if size > MAX_TELEGRAM_UPLOAD_BYTES:
        return (
            f"[خطا] فایل خیلی بزرگه ({size / (1024 * 1024):.1f} مگابایت). "
            f"سقف ارسال مستقیم حدود {MAX_TELEGRAM_UPLOAD_BYTES / (1024 * 1024):.0f} مگابایته."
        )

    filename = os.path.basename(file_path)
    ext = os.path.splitext(filename)[1].lower()

    try:
        with open(file_path, "rb") as f:
            content_bytes = f.read()

        if ext in IMAGE_EXTENSIONS:
            tg.send_photo(chat_id, content_bytes, caption=caption or None, message_thread_id=thread_id)
            return f"[موفق] عکس «{filename}» برای کاربر در تلگرام ارسال شد."

        tg.send_document(
            chat_id,
            filename=filename,
            content_bytes=content_bytes,
            caption=caption or None,
            message_thread_id=thread_id,
        )
        return f"[موفق] فایل «{filename}» برای کاربر در تلگرام ارسال شد."
    except Exception as e:
        return f"[خطا] ارسال فایل شکست خورد: {e}"


# ---------------------------------------------------------------------------
# جستجوی وب (Bing HTML scraping — بدون نیاز به API key)
# ---------------------------------------------------------------------------

_WEB_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7",
}

# فقط متن رو از HTML استخراج می‌کنه — وابسته به beautifulsoup4 نیست (regex سبک)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)


def _html_to_text(html: str) -> str:
    """HTML رو به متن ساده تبدیل می‌کنه (نسخه‌ی سبک بدون bs4)."""
    html = _SCRIPT_STYLE_RE.sub("", html)
    # بریک‌های خط رو حفظ کن
    html = re.sub(r"<(br|/p|/div|/h\d|/li)[^>]*>", "\n", html, flags=re.IGNORECASE)
    text = _TAG_RE.sub("", html)
    # decode entityهای رایج
    text = (text
            .replace("&nbsp;", " ")
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"')
            .replace("&#39;", "'"))
    text = _WS_RE.sub(" ", text)
    lines = [ln.strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)


def web_search(query: str, max_results: int | None = None) -> str:
    """
    با Bing HTML جستجو می‌کنه و نتایج رو برمی‌گردونه.
    این روش بدون نیاز به API key هست و معمولاً پایدار کار می‌کنه.
    (DuckDuckGo از دیتاسنترها معمولاً challenge میده، برای همین Bing انتخاب شد.)
    """
    if not Config.WEB_SEARCH_ENABLED:
        return "[خطا] جستجوی وب روی این ربات غیرفعاله (WEB_SEARCH_ENABLED=false)."

    # پاک‌سازی query: مدل بعضی وقتا کوتیشین اضافی می‌فرسته (مثل 'قیمت بیت کوین')
    query = (query or "").strip()
    if (query.startswith("'") and query.endswith("'")) or (query.startswith('"') and query.endswith('"')):
        query = query[1:-1].strip()
    # پاک‌سازی کوتیشین‌های داخل query که مدل ممکنه اضافه کرده باشه
    if not query:
        return "[خطا] query خالیه."

    limit = max_results or Config.WEB_SEARCH_MAX_RESULTS
    encoded = urllib.parse.quote_plus(query)
    # setlang و cc رو هم ست می‌کنیم تا نتایج مرتبط‌تر بیان
    url = f"https://www.bing.com/search?q={encoded}&count={limit + 5}&setlang=en&cc=US"

    try:
        with httpx.Client(timeout=Config.WEB_SEARCH_TIMEOUT_SECONDS, follow_redirects=True, http2=False) as client:
            resp = client.get(url, headers=_WEB_HEADERS)
            if resp.status_code != 200:
                return f"[خطا] Bing کد {resp.status_code} برگردوند."
            html = resp.text
    except Exception as e:
        return f"[خطا] جستجو ناموفق بود: {e}"

    # Bing هر نتیجه رو توی <li class="b_algo"> می‌ذاره.
    # title: <h2><a href="...">title</a></h2>
    # URL: <cite>...</cite>
    # snippet: <p class="b_lineclamp...">...</p>
    results = []
    blocks = re.split(r'<li class="b_algo"', html)[1:limit + 5]
    for block in blocks:
        # عنوان + URL اصلی از لینک داخل h2
        title_link_m = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
        if title_link_m:
            raw_url = title_link_m.group(1)
            title = _html_to_text(title_link_m.group(2))
        else:
            # fallback: h2 فقط، بدون لینک
            h2_m = re.search(r'<h2[^>]*>(.*?)</h2>', block, re.DOTALL)
            cite_only = re.search(r'<cite[^>]*>(.*?)</cite>', block, re.DOTALL)
            if not (h2_m and cite_only):
                continue
            title = _html_to_text(h2_m.group(1))
            raw_url = _html_to_text(cite_only.group(1))

        # اگه URL cite بود، از cite استفاده کن (تمیزتره و معمولاً نهایی‌تره)
        cite_m = re.search(r'<cite[^>]*>(.*?)</cite>', block, re.DOTALL)
        if cite_m:
            cite_url = _html_to_text(cite_m.group(1))
            # cite معمولاً به شکل "example.com › path" هست
            if not cite_url.startswith("http"):
                cite_url = "https://" + cite_url.replace(" › ", "/").replace(" ", "")
            clean_url = cite_url
        else:
            clean_url = raw_url

        snippet_m = re.search(r'<p class="b_lineclamp[^"]*"[^>]*>(.*?)</p>', block, re.DOTALL)
        snippet = _html_to_text(snippet_m.group(1)) if snippet_m else ""

        if not title or not clean_url:
            continue
        results.append({"title": title, "url": clean_url, "snippet": snippet})
        if len(results) >= limit:
            break

    if not results:
        return f"نتیجه‌ای برای «{query}» پیدا نشد."

    out_lines = [f"🔍 نتایج جستجو برای: {query}", ""]
    for i, r in enumerate(results, 1):
        out_lines.append(f"{i}. {r['title']}")
        out_lines.append(f"   🔗 {r['url']}")
        if r["snippet"]:
            out_lines.append(f"   📝 {r['snippet'][:300]}")
        out_lines.append("")
    return "\n".join(out_lines).strip()


def web_fetch(url: str, max_chars: int | None = None) -> str:
    """محتوای یک صفحه‌ی وب رو می‌خونه و به متن ساده تبدیل می‌کنه."""
    limit = max_chars or 6000
    try:
        with httpx.Client(timeout=Config.WEB_SEARCH_TIMEOUT_SECONDS, follow_redirects=True, http2=False) as client:
            resp = client.get(url, headers=_WEB_HEADERS)
            if resp.status_code != 200:
                return f"[خطا] کد {resp.status_code} از {url}"
            html = resp.text
    except Exception as e:
        return f"[خطا] خواندن صفحه ناموفق بود: {e}"

    text = _html_to_text(html)
    if len(text) > limit:
        text = text[:limit] + "\n...[بریده شد]"
    return text


BACKGROUND_TASK_SCHEMA = {
    "type": "function",
    "function": {
        "name": "schedule_background_task",
        "description": (
            "یک اسکریپت پایتون را در پس‌زمینه (Background) بدون تایم‌اوت اجرا می‌کند. "
            "مناسب برای کارهای زمان‌بندی شده (Cron jobs)، چک کردن سایت‌ها در حلقه‌های بی‌نهایت، "
            "یا یادآوری‌ها (Reminders). در این اسکریپت می‌توانید از کتابخانه‌های requests و time استفاده کنید. "
            "برای ارسال پیام به کاربر، باید از requests.post برای ارسال پیام به API تلگرام (https://api.telegram.org/bot<TOKEN>/sendMessage) استفاده کنید. "
            "توکن ربات و chat_id کاربر را باید در اسکریپت هاردکد کنید (از context بدست آورید)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "کد پایتون برای اجرای پس‌زمینه.",
                }
            },
            "required": ["code"],
        },
    },
}

TOOLS = [
    BACKGROUND_TASK_SCHEMA,SHELL_TOOL_SCHEMA, PYTHON_TOOL_SCHEMA, SEND_FILE_TOOL_SCHEMA, WEB_SEARCH_TOOL_SCHEMA, WEB_FETCH_TOOL_SCHEMA]

def schedule_background_task(code: str, context: dict) -> str:
    import threading
    import tempfile
    import subprocess
    import sys
    
    bot_token = Config.TELEGRAM_BOT_TOKEN
    chat_id = context.get("chat_id", "")
    
    # Inject variables into code
    injected_code = f"""import os
os.environ['TELEGRAM_BOT_TOKEN'] = '{bot_token}'
CHAT_ID = '{chat_id}'

# Your code:
{code}
"""
    
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(injected_code)
        path = f.name
        
    def run_it():
        subprocess.run([sys.executable, path])
        
    t = threading.Thread(target=run_it, daemon=True)
    t.start()
    return "✅ تسک در پس‌زمینه با موفقیت اجرا شد. متغیرهای TELEGRAM_BOT_TOKEN (در os.environ) و CHAT_ID به صورت سراسری در دسترس کد شما هستند."

TOOL_IMPLEMENTATIONS = {
    "schedule_background_task": lambda args, context: schedule_background_task(args.get("code", ""), context),
    "run_shell_command": lambda args, context: run_shell_command(args.get("command", "")),
    "run_python": lambda args, context: run_python(args.get("code", "")),
    "send_telegram_file": lambda args, context: send_telegram_file(
        args.get("file_path", ""), args.get("caption", ""), context
    ),
    "web_search": lambda args, context: web_search(
        args.get("query", ""),
        _safe_int(args.get("max_results")),
    ),
    "web_fetch": lambda args, context: web_fetch(
        args.get("url", ""),
        _safe_int(args.get("max_chars")),
    ),
}


def _safe_int(value, default=None):
    """یه مقدار رو به int تبدیل می‌کنه. اگه value یه string عددی باشه (مثل '5')،
    به int تبدیلش می‌کنه. اگه None یا غیرعددی باشه، default برمی‌گرده."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default
