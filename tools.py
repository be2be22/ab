import subprocess
import shlex

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
            "برای بررسی فایل‌ها، نصب پکیج، دیباگ، یا هر کار دیگه‌ای که نیاز به ترمینال داره استفاده کن."
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


TOOLS = [SHELL_TOOL_SCHEMA]

TOOL_IMPLEMENTATIONS = {
    "run_shell_command": lambda args: run_shell_command(args.get("command", "")),
}
