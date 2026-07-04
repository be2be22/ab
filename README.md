# ربات ایجنت تلگرام + Cloudflare Workers AI + اجرای کد + جستجوی وب

## چیکار می‌کنه؟
- توی چت خصوصی تلگرام باهاش صحبت می‌کنی.
- برای هر کاربر، فقط **یک‌بار** سه تاپیک می‌سازه:
  - 🧠 فکرها → مراحل داخلی، reasoning و خروجی ابزارها
  - 💬 پاسخ نهایی → جواب نهایی مدل (به‌صورت زنده/استریم ادیت می‌شه)
  - 🔑 آمار و کلیدها → آمار کامل ربات و وضعیت کلیدها
- از **Cloudflare Workers AI** به‌عنوان پروایدر اصلی استفاده می‌کنه (مدل GLM-5.2 — reasoning فارسی‌زبان).
- اگه کلید NVIDIA هم تنظیم کرده باشی، اگه Cloudflare خطا بده، خودکار میره سراغ NVIDIA.
- **جستجوی وب**: ابزار `web_search` با Bing کار می‌کنه و `web_fetch` برای خوندن URL.
- **ارسال فایل**: با `send_telegram_file` می‌تونه فایل بسازه و بفرسته.

## دستورات
| دستور | کاربرد |
|---|---|
| `/start` | ساخت سه تاپیک اختصاصی و راهنمای اولیه |
| `/stats` | آمار کامل (مدل، کلیدها، uptime) |
| `/models` | لیست مدل‌های قابل انتخاب |
| `/model <name>` | تغییر مدل، مثلا `/model glm-5.2` |
| `/reset` | پاک کردن تاریخچه |
| `/export` | خروجی JSON تاریخچه |
| `/clear_keys` | پاک کردن cooldown کلیدهای NVIDIA |
| `/help` | راهنمای کامل |

## مدل‌های قابل انتخاب
- ☁️ **Cloudflare** (رایگان، پیشنهادی):
  - `glm-5.2` — GLM-5.2 (مدل reasoning فارسی، پیش‌فرض)
  - `llama-3.3-70b` — Llama 3.3 70B
  - `qwen2.5-coder-32b` — Qwen2.5 Coder
  - `mistral-7b` — Mistral 7B
  - `deepseek-r1` — DeepSeek R1 (reasoning)
- 🟢 **NVIDIA** (fallback):
  - `llama-3.1-8b` — سریع و سبک
  - `llama-3.2-90b-vision` — vision + text
  - `gemma-2-2b` — سبک

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

## ۳. متغیرهای محیطی مهم
```
TELEGRAM_BOT_TOKEN=...
ALLOWED_USER_IDS=123456789

# Cloudflare (الزامی)
CF_ACCOUNT_ID=8adae8ff813eab68018a78c71d0c54f6
CF_AI_TOKEN=cfut_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
AI_MODEL=@cf/zai-org/glm-5.2
DEFAULT_MODEL_KEY=glm-5.2

# NVIDIA (اختیاری — fallback)
NVIDIA_API_KEYS=nvapi-xxx,nvapi-yyy
NVIDIA_MODEL=meta/llama-3.1-8b-instruct

# Cloudflare retry
CF_MAX_RETRIES=3
CF_RETRY_DELAY=1.0

# Agent
SHELL_ENABLED=true
ALLOW_DANGEROUS_COMMANDS=false
STREAM_ENABLED=true
MAX_CONCURRENT_UPDATES=8
DB_PATH=/data/bot.db
```

## ۴. دیپلوی روی Railway
1. پوشه رو به یه ریپازیتوری گیت‌هاب پوش کن.
2. توی Railway → New Project → Deploy from GitHub repo → همین ریپو.
3. تب **Variables** و همه‌ی متغیرهای بالا رو با مقدار واقعی ست کن.
4. (پیشنهادی) یه **Volume** بساز و به مسیر `/data` وصل کن.
5. Deploy بزن.

## ۵. تست
توی تلگرام به ربات پیام بده. باید سه تاپیک بسازه و شروع کنه به جواب دادن.

## درباره‌ی GLM-5.2
GLM-5.2 یه مدل reasoning هست — یعنی اول به انگلیسی «فکر» می‌کنه (تو `reasoning_content`) و بعد جواب فارسی رو می‌ده (تو `content`). فکر مدل تو تاپیک «🧠 فکرها» نمایش داده می‌شه.

**نکته سرعت**: اگه سوال ساده بپرسی (سلام، شعر، توضیح)، ربات خودکار `max_tokens` رو کم می‌کنه تا reasoning سریع‌تر تموم بشه (۴-۵ ثانیه). برای سوالات پیچیده‌تر، ممکنه ۱۵-۳۰ ثانیه طول بکشه.

## نکات امنیتی
- `ALLOW_DANGEROUS_COMMANDS` رو روی `false` نگه دار.
- ابزارهای `run_shell_command` و `run_python` اجرای کد دلخواه روی کانتینر رو ممکن می‌کنن.
- توکن‌ها رو داخل کد commit نکن؛ فقط از Variables استفاده کن.
