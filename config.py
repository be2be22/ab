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

    # --- Cloudflare Workers AI ---
    # اطلاعات اکانت و توکن‌ها رو از پنل Cloudflare بگیر:
    # https://dash.cloudflare.com → My Profile → API Tokens → Create Token
    #   Permissions: Account → Workers AI → Edit
    #
    # چند توکن: اگه چندتا اکانت Cloudflare داری، می‌تونی چند توکن با کاما بذاری.
    # ربات به‌صورت round-robin بینشون می‌چرخه و اگه یکی rate-limit بخوره، میره سراغ بعدی.
    # مثال: CF_AI_TOKENS=cfut_xxx,cfut_yyy,cfut_zzz
    CF_ACCOUNT_ID: str = os.environ.get("CF_ACCOUNT_ID", "")
    # برای backward compat: اگه CF_AI_TOKEN تنظیم شده باشه، از اون استفاده می‌کنه
    CF_AI_TOKENS: list[str] = _split_csv(
        os.environ.get("CF_AI_TOKENS", "") or os.environ.get("CF_AI_TOKEN", "")
    )
    CF_AI_BASE_URL: str = os.environ.get(
        "CF_AI_BASE_URL",
        f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/v1",
    )

    # --- مدل‌های قابل انتخاب با /model و /models ---
    # این لیست فقط مدل‌هایی هستن که واقعاً روی Cloudflare کار می‌کنن (تست‌شده).
    # کلید کوتاه -> شناسه واقعی مدل
    MODELS: dict[str, str] = {
        # سریع و قدرتمند (پیشنهادی — هم سریعه هم باکیفیت)
        "llama-3.3-70b": "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
        # خیلی سریع و سبک
        "llama-3.2-3b": "@cf/meta/llama-3.2-3b-instruct",
        # reasoning (اول فکر می‌کنه بعد جواب می‌ده — کندتر ولی دقیق‌تر)
        "glm-5.2": "@cf/zai-org/glm-5.2",
        "deepseek-r1": "@cf/deepseek-ai/deepseek-r1-distill-qwen-32b",
        # تخصصی کدنویسی
        "qwen2.5-coder": "@cf/qwen/qwen2.5-coder-32b-instruct",
    }
    # مدل پیش‌فرض: glm-5.2 (reasoning — دقیق‌تر و باکیفیت‌تر از مدل‌های non-reasoning)
    DEFAULT_MODEL_KEY: str = os.environ.get("DEFAULT_MODEL_KEY", "glm-5.2")

    # --- Reasoning effort (فقط برای مدل‌های reasoning مثل glm-5.2 معنا داره) ---
    # هرچی effort کمتر باشه، مدل کمتر "فکر" می‌کنه قبل از جواب دادن => سریع‌تر جواب می‌ده،
    # ولی برای مسائل خیلی پیچیده ممکنه دقتش کمی کمتر بشه.
    # مقادیر مجاز (طبق مستندات Cloudflare/OpenAI-style): "low" | "medium" | "high"
    # پیش‌فرض روی "low" گذاشته شده تا حتی با glm-5.2، جواب‌ها سریع بیان (حتی برای «سلام»).
    CF_REASONING_EFFORT: str = os.environ.get("CF_REASONING_EFFORT", "low")
    # اگه پیام کاربر به ابزار نیاز داشته باشه (تحلیل، کد، تحقیق)، effort بالاتری استفاده
    # می‌شه چون انتخاب درست ابزار و برنامه‌ریزی چندمرحله‌ای به فکر بیشتری نیاز داره.
    CF_REASONING_EFFORT_WITH_TOOLS: str = os.environ.get("CF_REASONING_EFFORT_WITH_TOOLS", "medium")

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

    # --- مدیریت توکن‌های Cloudflare ---
    # وقتی یه توکن rate-limit بخوره، چند ثانیه کنار گذاشته می‌شه
    CF_KEY_COOLDOWN_SECONDS: int = int(os.environ.get("CF_KEY_COOLDOWN_SECONDS", "30"))

    @classmethod
    def validate(cls) -> None:
        missing = []
        if not cls.TELEGRAM_BOT_TOKEN:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not cls.CF_ACCOUNT_ID:
            missing.append("CF_ACCOUNT_ID")
        if not cls.CF_AI_TOKENS:
            missing.append("CF_AI_TOKENS (یا CF_AI_TOKEN)")
        if missing:
            raise RuntimeError(f"متغیرهای محیطی الزامی تنظیم نشدن: {', '.join(missing)}")
        if not cls.ALLOWED_USER_IDS:
            print("⚠️  هشدار: ALLOWED_USER_IDS خالیه یعنی هر کسی می‌تونه از ربات (و دسترسی شل!) استفاده کنه.")
        if cls.DEFAULT_MODEL_KEY not in cls.MODELS:
            print(f"⚠️  هشدار: DEFAULT_MODEL_KEY={cls.DEFAULT_MODEL_KEY!r} توی MODELS نیست.")
