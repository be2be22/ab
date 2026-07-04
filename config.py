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

    # --- Cloudflare Workers AI (پروایدر اصلی) ---
    # اطلاعات اکانت و توکن رو از پنل Cloudflare بگیر:
    # https://dash.cloudflare.com → My Profile → API Tokens → Create Token
    #   Permissions: Account → Workers AI → Edit
    CF_ACCOUNT_ID: str = os.environ.get("CF_ACCOUNT_ID", "")
    CF_AI_TOKEN: str = os.environ.get("CF_AI_TOKEN", "")
    CF_AI_BASE_URL: str = os.environ.get(
        "CF_AI_BASE_URL",
        f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/v1",
    )
    # مدل پیش‌فرض: GLM-5.2 (مدل reasoning فارسی‌زبان از Z-AI)
    CF_AI_MODEL: str = os.environ.get("AI_MODEL", "@cf/zai-org/glm-5.2")

    # --- NVIDIA NIM (fallback — اختیاری) ---
    # اگه Cloudflare خطا بده (مثل Capacity)، ربات خودکار میره سراغ NVIDIA.
    # اگه کلید NVIDIA نداری، خالی بذار — ربات فقط از Cloudflare استفاده می‌کنه.
    NVIDIA_API_KEYS: list[str] = _split_csv(os.environ.get("NVIDIA_API_KEYS", ""))
    NVIDIA_BASE_URL: str = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
    NVIDIA_MODEL: str = os.environ.get("NVIDIA_MODEL", "meta/llama-3.1-8b-instruct")

    # مدت زمان (ثانیه) استراحت یک کلید NVIDIA بعد از خطای rate-limit
    DEFAULT_KEY_COOLDOWN_SECONDS: int = int(os.environ.get("DEFAULT_KEY_COOLDOWN_SECONDS", "60"))

    # اگه مدل‌هات reasoning/thinking داخلی دارن (مثل glm-5.2 یا deepseek-r1)، روشن بودن این گزینه
    # باعث می‌شه قبل از جواب دادن «فکر» کنه که کیفیت رو بالا می‌بره ولی کندترش می‌کنه.
    # برای GLM-5.2 این مهم نیست چون مدل خودش reasoning می‌فرسته.
    ENABLE_MODEL_THINKING: bool = os.environ.get("ENABLE_MODEL_THINKING", "false").lower() == "true"

    # اگه بخوای سقف مصرف توکن هر کلید NVIDIA رو بدونی (برای نمایش «باقی‌مونده» در آمار)
    TOKEN_BUDGET_PER_KEY: int = int(os.environ.get("TOKEN_BUDGET_PER_KEY", "0"))

    # --- مدل‌های قابل انتخاب با /model و /models ---
    # کلید کوتاه -> (providor, شناسه واقعی مدل)
    # provider: "cf" = Cloudflare, "nvidia" = NVIDIA NIM
    MODELS: dict[str, tuple[str, str]] = {
        # Cloudflare (پیشنهادی — رایگان و پایدار)
        "glm-5.2": ("cf", "@cf/zai-org/glm-5.2"),
        "llama-3.3-70b": ("cf", "@cf/meta/llama-3.3-70b-instruct-fp8-fast"),
        "llama-3.1-8b-cf": ("cf", "@cf/meta/llama-3.1-8b-instruct"),
        "qwen2.5-coder-32b": ("cf", "@cf/qwen/qwen2.5-coder-32b-instruct"),
        "mistral-7b": ("cf", "@cf/mistral/mistral-7b-instruct-v0.3"),
        "deepseek-r1": ("cf", "@cf/deepseek-ai/deepseek-r1-distill-qwen-32b"),
        # NVIDIA (fallback)
        "llama-3.1-8b": ("nvidia", "meta/llama-3.1-8b-instruct"),
        "llama-3.2-3b": ("nvidia", "meta/llama-3.2-3b-instruct"),
        "llama-3.2-90b-vision": ("nvidia", "meta/llama-3.2-90b-vision-instruct"),
        "gemma-2-2b": ("nvidia", "google/gemma-2-2b-it"),
    }
    DEFAULT_MODEL_KEY: str = os.environ.get("DEFAULT_MODEL_KEY", "glm-5.2")

    # --- Agent / Shell ---
    SHELL_ENABLED: bool = os.environ.get("SHELL_ENABLED", "true").lower() == "true"
    SHELL_TIMEOUT_SECONDS: int = int(os.environ.get("SHELL_TIMEOUT_SECONDS", "30"))
    PYTHON_TIMEOUT_SECONDS: int = int(os.environ.get("PYTHON_TIMEOUT_SECONDS", "30"))
    ALLOW_DANGEROUS_COMMANDS: bool = os.environ.get("ALLOW_DANGEROUS_COMMANDS", "false").lower() == "true"
    MAX_AGENT_ITERATIONS: int = int(os.environ.get("MAX_AGENT_ITERATIONS", "40"))
    MAX_HISTORY_MESSAGES: int = int(os.environ.get("MAX_HISTORY_MESSAGES", "20"))

    # --- فایل / تصویر ---
    MAX_DOWNLOAD_FILE_MB: float = float(os.environ.get("MAX_DOWNLOAD_FILE_MB", "15"))
    MAX_FILE_TEXT_CHARS: int = int(os.environ.get("MAX_FILE_TEXT_CHARS", "12000"))

    # --- استریم ---
    STREAM_ENABLED: bool = os.environ.get("STREAM_ENABLED", "true").lower() == "true"
    STREAM_EDIT_MIN_INTERVAL: float = float(os.environ.get("STREAM_EDIT_MIN_INTERVAL", "0.5"))
    STREAM_FIRST_EDIT_DELAY: float = float(os.environ.get("STREAM_FIRST_EDIT_DELAY", "0.15"))

    # --- Concurrency ---
    MAX_CONCURRENT_UPDATES: int = int(os.environ.get("MAX_CONCURRENT_UPDATES", "8"))

    # --- Health/Monitoring ---
    HEALTH_PORT: int = int(os.environ.get("PORT", os.environ.get("HEALTH_PORT", "8080")))

    # --- Storage ---
    DB_PATH: str = os.environ.get("DB_PATH", "/data/bot.db")

    # --- جستجوی وب ---
    WEB_SEARCH_ENABLED: bool = os.environ.get("WEB_SEARCH_ENABLED", "true").lower() == "true"
    WEB_SEARCH_MAX_RESULTS: int = int(os.environ.get("WEB_SEARCH_MAX_RESULTS", "5"))
    WEB_SEARCH_TIMEOUT_SECONDS: int = int(os.environ.get("WEB_SEARCH_TIMEOUT_SECONDS", "15"))

    # --- ارسال خودکار عکس‌های داخل پاسخ مدل ---
    AUTO_SEND_IMAGES_IN_REPLY: bool = os.environ.get("AUTO_SEND_IMAGES_IN_REPLY", "true").lower() == "true"

    # --- تلاش مجدد برای Cloudflare ---
    # Cloudflare گاهی "Capacity temporarily exceeded" می‌ده. این تعداد تلاش مجدده.
    CF_MAX_RETRIES: int = int(os.environ.get("CF_MAX_RETRIES", "3"))
    CF_RETRY_DELAY: float = float(os.environ.get("CF_RETRY_DELAY", "1.0"))

    @classmethod
    def validate(cls) -> None:
        missing = []
        if not cls.TELEGRAM_BOT_TOKEN:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not cls.CF_ACCOUNT_ID:
            missing.append("CF_ACCOUNT_ID")
        if not cls.CF_AI_TOKEN:
            missing.append("CF_AI_TOKEN")
        if missing:
            raise RuntimeError(f"متغیرهای محیطی الزامی تنظیم نشدن: {', '.join(missing)}")
        if not cls.ALLOWED_USER_IDS:
            print("⚠️  هشدار: ALLOWED_USER_IDS خالیه یعنی هر کسی می‌تونه از ربات (و دسترسی شل!) استفاده کنه.")
        if cls.DEFAULT_MODEL_KEY not in cls.MODELS:
            print(f"⚠️  هشدار: DEFAULT_MODEL_KEY={cls.DEFAULT_MODEL_KEY!r} توی MODELS نیست.")
        if not cls.NVIDIA_API_KEYS:
            print("ℹ️  NVIDIA_API_KEYS خالیه — ربات فقط از Cloudflare استفاده می‌کنه (بدون fallback).")
