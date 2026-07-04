import os


def _split_csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


class Config:
    # --- Telegram ---
    TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")

    # لیست آیدی عددی کاربران مجاز (خیلی مهم، چون ربات دسترسی اجرای شل داره)
    # مثال: ALLOWED_USER_IDS=123456789,987654321
    ALLOWED_USER_IDS: list[int] = [
        int(x) for x in _split_csv(os.environ.get("ALLOWED_USER_IDS", "")) if x.isdigit()
    ]

    # --- NVIDIA NIM ---
    # چند کلید با کاما جدا کن: NVIDIA_API_KEYS=nvapi-xxx,nvapi-yyy,nvapi-zzz
    NVIDIA_API_KEYS: list[str] = _split_csv(os.environ.get("NVIDIA_API_KEYS", ""))
    NVIDIA_BASE_URL: str = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
    NVIDIA_MODEL: str = os.environ.get("NVIDIA_MODEL", "z-ai/glm-5.2")

    # مدت زمان (ثانیه) استراحت یک کلید بعد از خطای rate-limit، اگه سرور retry-after نداد
    DEFAULT_KEY_COOLDOWN_SECONDS: int = int(os.environ.get("DEFAULT_KEY_COOLDOWN_SECONDS", "60"))

    # --- مدل‌های قابل انتخاب با /model و /models ---
    # کلید کوتاه -> شناسه واقعی مدل روی NVIDIA NIM (build.nvidia.com)
    MODELS: dict[str, str] = {
        "glm-5.2": "z-ai/glm-5.2",
        "glm-4.5": "z-ai/glm-4.5",
        "llama-3.1": "meta/llama-3.1-405b-instruct",
        "llama-3.1-70b": "meta/llama-3.1-70b-instruct",
        "llama-3.1-8b": "meta/llama-3.1-8b-instruct",
        "qwen3": "qwen/qwen3-235b-a22b",
        "deepseek-r1": "deepseek-ai/deepseek-r1",
        "mistral-large": "mistralai/mistral-large-2-instruct",
    }
    DEFAULT_MODEL_KEY: str = os.environ.get("DEFAULT_MODEL_KEY", "glm-5.2")

    # --- Agent / Shell ---
    SHELL_ENABLED: bool = os.environ.get("SHELL_ENABLED", "true").lower() == "true"
    SHELL_TIMEOUT_SECONDS: int = int(os.environ.get("SHELL_TIMEOUT_SECONDS", "30"))
    PYTHON_TIMEOUT_SECONDS: int = int(os.environ.get("PYTHON_TIMEOUT_SECONDS", "30"))
    # اگه true باشه، حتی دستورات خطرناک هم بدون تایید اجرا می‌شن (پیشنهاد نمی‌شه)
    ALLOW_DANGEROUS_COMMANDS: bool = os.environ.get("ALLOW_DANGEROUS_COMMANDS", "false").lower() == "true"
    MAX_AGENT_ITERATIONS: int = int(os.environ.get("MAX_AGENT_ITERATIONS", "6"))
    MAX_HISTORY_MESSAGES: int = int(os.environ.get("MAX_HISTORY_MESSAGES", "20"))

    # --- وب‌سرچ ---
    WEB_SEARCH_ENABLED: bool = os.environ.get("WEB_SEARCH_ENABLED", "true").lower() == "true"

    # --- فایل / تصویر ---
    MAX_DOWNLOAD_FILE_MB: float = float(os.environ.get("MAX_DOWNLOAD_FILE_MB", "15"))
    MAX_FILE_TEXT_CHARS: int = int(os.environ.get("MAX_FILE_TEXT_CHARS", "12000"))

    # --- استریم ---
    STREAM_ENABLED: bool = os.environ.get("STREAM_ENABLED", "true").lower() == "true"
    STREAM_EDIT_MIN_INTERVAL: float = float(os.environ.get("STREAM_EDIT_MIN_INTERVAL", "1.2"))

    # --- Concurrency ---
    MAX_CONCURRENT_UPDATES: int = int(os.environ.get("MAX_CONCURRENT_UPDATES", "8"))

    # --- Health/Monitoring ---
    HEALTH_PORT: int = int(os.environ.get("PORT", os.environ.get("HEALTH_PORT", "8080")))

    # --- Storage ---
    DB_PATH: str = os.environ.get("DB_PATH", "/data/bot.db")

    @classmethod
    def validate(cls) -> None:
        missing = []
        if not cls.TELEGRAM_BOT_TOKEN:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not cls.NVIDIA_API_KEYS:
            missing.append("NVIDIA_API_KEYS")
        if missing:
            raise RuntimeError(f"متغیرهای محیطی الزامی تنظیم نشدن: {', '.join(missing)}")
        if not cls.ALLOWED_USER_IDS:
            print("⚠️  هشدار: ALLOWED_USER_IDS خالیه یعنی هر کسی می‌تونه از ربات (و دسترسی شل!) استفاده کنه.")
        if cls.DEFAULT_MODEL_KEY not in cls.MODELS:
            print(f"⚠️  هشدار: DEFAULT_MODEL_KEY={cls.DEFAULT_MODEL_KEY!r} توی MODELS نیست.")
