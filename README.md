# ربات ایجنت تلگرام + Cloudflare Workers AI

## چیکار می‌کنه؟
- توی چت خصوصی تلگرام باهاش صحبت می‌کنی.
- برای هر کاربر، فقط **یک‌بار** سه تاپیک می‌سازه:
  - 🧠 فکرها → مراحل داخلی، reasoning و خروجی ابزارها
  - 💬 پاسخ نهایی → جواب نهایی مدل (به‌صورت زنده/استریم ادیت می‌شه)
  - 🔑 آمار و توکن‌ها → آمار کامل ربات و وضعیت توکن‌های Cloudflare
- از **Cloudflare Workers AI** استفاده می‌کنه (رایگان، سریع، پایدار).
- **پشتیبانی از چند توکن**: اگه چندتا اکانت Cloudflare داری، می‌تونی چند توکن بذاری.
- **جستجوی وب**: ابزار `web_search` با Bing کار می‌کنه و `web_fetch` برای خوندن URL.
- **ارسال فایل**: با `send_telegram_file` می‌تونه فایل بسازه و بفرسته.

## دستورات
| دستور | کاربرد |
|---|---|
| `/start` | ساخت سه تاپیک اختصاصی و راهنمای اولیه |
| `/stats` | آمار کامل (مدل، توکن‌ها، uptime) |
| `/models` | لیست مدل‌های قابل انتخاب |
| `/model <name>` | تغییر مدل، مثلا `/model glm-5.2` |
| `/reset` | پاک کردن تاریخچه |
| `/export` | خروجی JSON تاریخچه |
| `/clear_tokens` | پاک کردن cooldown توکن‌ها |
| `/help` | راهنمای کامل |

## مدل‌های قابل انتخاب
- `llama-3.3-70b` — سریع + باکیفیت + فارسی خوب (**پیش‌فرض**)
- `llama-3.2-3b` — خیلی سریع و سبک
- `glm-5.2` — reasoning (اول فکر می‌کنه بعد جواب می‌ده — دقیق‌تر ولی کندتر)
- `deepseek-r1` — reasoning (مشابه glm-5.2)
- `qwen2.5-coder` — تخصصی کدنویسی

## ۱. ساخت ربات تلگرام
1. با [@BotFather](https://t.me/BotFather) چت کن، `/newbot` بزن و توکن رو بگیر.
2. آیدی عددی خودت رو از [@userinfobot](https://t.me/userinfobot) بگیر.

> ⚠️ **حتما `ALLOWED_USER_IDS` رو پر کن.** ربات دسترسی اجرای شل/پایتون داره!

## ۲. گرفتن توکن Cloudflare Workers AI
1. وارد [dash.cloudflare.com](https://dash.cloudflare.com) بشو
2. بالا سمت راست، روی آواتارت کلیک کن → **My Profile**
3. برو به **API Tokens** → **Create Token** → **Create Custom Token**
4. تنظیمات:
   - **Permissions**: `Account` → `Workers AI` → `Edit`
   - **Account Resources**: `Include` → اکانتت
5. **Create Token** رو بزن و توکن رو کپی کن
6. Account ID رو از داشبورد Cloudflare (سمت راست، پایین) بگیر

## ۳. اضافه کردن چند توکن Cloudflare
اگه چندتا اکانت Cloudflare داری، می‌تونی چند توکن بذاری:
1. برای هر اکانت، یه توکن بساز (مرحله‌ی ۲)
2. همه‌ی توکن‌ها رو با کاما تو `CF_AI_TOKENS` بذار:
   ```
   CF_AI_TOKENS=cfut_xxx,cfut_yyy,cfut_zzz
   ```
3. ربات به‌صورت **sticky** بینشون می‌چرخه:
   - همون توکنی که کار می‌کنه رو نگه می‌داره
   - اگه یکی rate-limit بخوره، خودکار میره سراغ بعدی
   - تو تاپیک «🔑 آمار و توکن‌ها» می‌تونی ببینی کدوم توکن فعال هست
   - با `/clear_tokens` می‌تونی cooldown همه رو پاک کنی

**نکته**: همه‌ی توکن‌ها باید مربوط به **همون Account ID** باشن. اگه اکانت‌های مختلف داری، باید Account ID اون اکانتی که توکن‌ها رو ازش ساختی بذاری.

## ۴. متغیرهای محیطی مهم
```
TELEGRAM_BOT_TOKEN=...
ALLOWED_USER_IDS=123456789

# Cloudflare (الزامی)
CF_ACCOUNT_ID=8adae8ff813eab68018a78c71d0c54f6
CF_AI_TOKENS=cfut_xxx,cfut_yyy
DEFAULT_MODEL_KEY=llama-3.3-70b

# Cloudflare retry
CF_MAX_RETRIES=3
CF_RETRY_DELAY=1.0
CF_KEY_COOLDOWN_SECONDS=30

# Agent
SHELL_ENABLED=true
ALLOW_DANGEROUS_COMMANDS=false
STREAM_ENABLED=true
MAX_CONCURRENT_UPDATES=8
DB_PATH=/data/bot.db
```

## ۵. دیپلوی روی Railway
1. پوشه رو به یه ریپازیتوری گیت‌هاب پوش کن.
2. توی Railway → New Project → Deploy from GitHub repo → همین ریپو.
3. تب **Variables** و همه‌ی متغیرهای بالا رو با مقدار واقعی ست کن.
4. (پیشنهادی) یه **Volume** بساز و به مسیر `/data` وصل کن.
5. Deploy بزن.

## ۶. تست
توی تلگرام به ربات پیام بده. باید سه تاپیک بسازه و شروع کنه به جواب دادن.

## درباره‌ی سرعت
- مدل پیش‌فرض `llama-3.3-70b` سریع‌ترین و باکیفیت‌ترین گزینه‌ست (۱-۳ ثانیه).
- اگه دقت بیشتری خواستی، از `/model glm-5.2` استفاده کن (ولی کندتره — ۵-۱۵ ثانیه).
- برای سوالات ساده (سلام، شعر)، ربات خودکار `max_tokens` رو کم می‌کنه تا سریع‌تر جواب بده.

## نکات امنیتی
- `ALLOW_DANGEROUS_COMMANDS` رو روی `false` نگه دار.
- ابزارهای `run_shell_command` و `run_python` اجرای کد دلخواه روی کانتینر رو ممکن می‌کنن.
- توکن‌ها رو داخل کد commit نکن؛ فقط از Variables استفاده کن.
