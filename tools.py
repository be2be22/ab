import subprocess
import sys
import tempfile
import os
import re
import html as html_lib

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

WEB_SEARCH_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "یک عبارت رو در وب جستجو می‌کنه و چند نتیجه‌ی برتر (عنوان، خلاصه، لینک) رو "
            "برمی‌گردونه. برای اطلاعات به‌روز، اخبار، یا هر چیزی که ممکنه توی دانش مدل "
            "نباشه استفاده کن."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "عبارت جستجو",
                },
                "max_results": {
                    "type": "integer",
                    "description": "حداکثر تعداد نتایج (پیش‌فرض ۵)",
                },
            },
            "required": ["query"],
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


_RESULT_BLOCK_RE = re.compile(
    r'<a rel="nofollow" class="result__a" href="([^"]+)">(.*?)</a>.*?'
    r'<a class="result__snippet"[^>]*>(.*?)</a>',
    re.DOTALL,
)


def _strip_tags(text: str) -> str:
    return html_lib.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def web_search(query: str, max_results: int = 5) -> str:
    if not Config.WEB_SEARCH_ENABLED:
        return "[خطا] ابزار وب‌سرچ روی این ربات غیرفعاله (WEB_SEARCH_ENABLED=false)."

    if not query or not query.strip():
        return "[خطا] عبارت جستجو خالیه."

    max_results = max(1, min(int(max_results or 5), 10))

    try:
        resp = httpx.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0 (compatible; TelegramAgentBot/1.0)"},
            timeout=15.0,
            follow_redirects=True,
        )
        resp.raise_for_status()
    except Exception as e:
        return f"[خطا] جستجو انجام نشد: {e}"

    matches = _RESULT_BLOCK_RE.findall(resp.text)
    if not matches:
        return f"نتیجه‌ای برای «{query}» پیدا نشد."

    lines = []
    for i, (url, title, snippet) in enumerate(matches[:max_results], start=1):
        lines.append(
            f"{i}. {_strip_tags(title)}\n   {_strip_tags(snippet)}\n   {url}"
        )
    return "\n".join(lines)


TOOLS = [SHELL_TOOL_SCHEMA, PYTHON_TOOL_SCHEMA]
if Config.WEB_SEARCH_ENABLED:
    TOOLS.append(WEB_SEARCH_TOOL_SCHEMA)

TOOL_IMPLEMENTATIONS = {
    "run_shell_command": lambda args: run_shell_command(args.get("command", "")),
    "run_python": lambda args: run_python(args.get("code", "")),
    "web_search": lambda args: web_search(args.get("query", ""), args.get("max_results", 5)),
}
