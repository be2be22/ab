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

    # --- 9Router (پروایدر OpenCode Free و بقیه‌ی پروایدرهای متصل) ---
    # 9Router رو خودت روی Railway (یا هر جای دیگه) دیپلوی می‌کنی و یه اندپوینت
    # سازگار با OpenAI بهت می‌ده. این آدرس باید با /v1 تموم بشه، مثلا:
    # AI_BASE_URL=https://my-9router.up.railway.app/v1
    #
    # چند API Key: اگه چند کلید از داشبورد 9Router داری، می‌تونی با کاما بذاری.
    # ربات به‌صورت sticky بینشون می‌چرخه و اگه یکی rate-limit بخوره، میره سراغ بعدی.
    # مثال: AI_API_KEYS=key_xxx,key_yyy
    AI_BASE_URL: str = os.environ.get("AI_BASE_URL", "")
    AI_API_KEYS: list[str] = _split_csv(
        os.environ.get("AI_API_KEYS", "") or os.environ.get("AI_API_KEY", "")
    )

    # --- مدل‌های قابل انتخاب با /model و /models ---
    # این‌ها مدل‌های رایگان پروایدر OpenCode Free هستن که از طریق 9Router در دسترسن.
    # هر مدل رایگان جدیدی که OpenCode منتشر کنه، کافیه اینجا با یه کلید کوتاه اضافه بشه.
    # کلید کوتاه -> شناسه‌ی واقعی مدل (همونی که تو داشبورد 9Router می‌بینی)
    MODELS: dict[str, str] = {
        "mimo-v2.5": "oc/mimo-v2.5-free",
        "deepseek-v4-flash": "oc/deepseek-v4-flash-free",
    }
    # مدل پیش‌فرض
    DEFAULT_MODEL_KEY: str = os.environ.get("DEFAULT_MODEL_KEY", "mimo-v2.5")

    # --- Reasoning effort (فقط برای مدل‌های reasoning معنا داره) ---
    # هرچی effort کمتر باشه، مدل کمتر "فکر" می‌کنه قبل از جواب دادن => سریع‌تر جواب می‌ده،
    # ولی برای مسائل خیلی پیچیده ممکنه دقتش کمی کمتر بشه.
    # مقادیر مجاز (سبک OpenAI-style): "low" | "medium" | "high"
    # پیش‌فرض روی "low" گذاشته شده تا حتی با مدل‌های reasoning، جواب‌ها سریع بیان.
    AI_REASONING_EFFORT: str = os.environ.get("AI_REASONING_EFFORT", "low")
    # اگه پیام کاربر به ابزار نیاز داشته باشه (تحلیل، کد، تحقیق)، effort بالاتری استفاده
    # می‌شه چون انتخاب درست ابزار و برنامه‌ریزی چندمرحله‌ای به فکر بیشتری نیاز داره.
    AI_REASONING_EFFORT_WITH_TOOLS: str = os.environ.get("AI_REASONING_EFFORT_WITH_TOOLS", "medium")

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

    # --- تلاش مجدد برای 9Router ---
    # گاهی پروایدر رایگان "Capacity temporarily exceeded" یا 429 می‌ده. این تعداد تلاش مجدده.
    AI_MAX_RETRIES: int = int(os.environ.get("AI_MAX_RETRIES", "3"))
    AI_RETRY_DELAY: float = float(os.environ.get("AI_RETRY_DELAY", "1.0"))

    # --- مدیریت API Key های 9Router ---
    # وقتی یه کلید rate-limit بخوره، چند ثانیه کنار گذاشته می‌شه
    AI_KEY_COOLDOWN_SECONDS: int = int(os.environ.get("AI_KEY_COOLDOWN_SECONDS", "30"))

    @classmethod
    def validate(cls) -> None:
        missing = []
        if not cls.TELEGRAM_BOT_TOKEN:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not cls.AI_BASE_URL:
            missing.append("AI_BASE_URL (آدرس /v1 نمونه‌ی 9Router خودت روی Railway)")
        if not cls.AI_API_KEYS:
            missing.append("AI_API_KEYS (یا AI_API_KEY — کلید ساخته‌شده تو داشبورد 9Router)")
        if missing:
            raise RuntimeError(f"متغیرهای محیطی الزامی تنظیم نشدن: {', '.join(missing)}")
        if not cls.ALLOWED_USER_IDS:
            print("⚠️  هشدار: ALLOWED_USER_IDS خالیه یعنی هر کسی می‌تونه از ربات (و دسترسی شل!) استفاده کنه.")
        if cls.DEFAULT_MODEL_KEY not in cls.MODELS:
            print(f"⚠️  هشدار: DEFAULT_MODEL_KEY={cls.DEFAULT_MODEL_KEY!r} توی MODELS نیست.")
