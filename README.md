# ربات ایجنت تلگرام + 9Router (OpenCode Free)

## چیکار می‌کنه؟
- توی چت خصوصی تلگرام باهاش صحبت می‌کنی.
- برای هر کاربر، فقط **یک‌بار** سه تاپیک می‌سازه:
  - 🧠 فکرها → مراحل داخلی، reasoning و خروجی ابزارها
  - 💬 پاسخ نهایی → جواب نهایی مدل (به‌صورت زنده/استریم ادیت می‌شه)
  - 🔑 آمار و توکن‌ها → آمار کامل ربات و وضعیت API Key های 9Router
- از **9Router** (اندپوینت سازگار با OpenAI که خودت روی Railway دیپلوی می‌کنی) و پروایدر رایگان **OpenCode Free** استفاده می‌کنه.
- **پشتیبانی از چند API Key**: اگه چند کلید از داشبورد 9Router داری، می‌تونی چند تا بذاری.
- **جستجوی وب**: ابزار `web_search` با Bing کار می‌کنه و `web_fetch` برای خوندن URL.
- **ارسال فایل**: با `send_telegram_file` می‌تونه فایل بسازه و بفرسته.

## دستورات
| دستور | کاربرد |
|---|---|
| `/start` | ساخت سه تاپیک اختصاصی و راهنمای اولیه |
| `/stats` | آمار کامل (مدل، توکن‌ها، uptime) |
| `/models` | لیست مدل‌های قابل انتخاب |
| `/model <n>` | تغییر مدل، مثلا `/model deepseek-v4-flash` |
| `/reset` | پاک کردن تاریخچه |
| `/export` | خروجی JSON تاریخچه |
| `/clear_tokens` | پاک کردن cooldown کلیدها |
| `/help` | راهنمای کامل |

## مدل‌های قابل انتخاب
مدل‌های پیش‌فرض تعریف‌شده در `config.py` (پروایدر OpenCode Free، از طریق 9Router):
- `mimo-v2.5` → `oc/mimo-v2.5-free` (**پیش‌فرض** — سریع و باکیفیت، reasoning)
- `deepseek-v4-flash` → `oc/deepseek-v4-flash-free` (سریع‌تر)

> هر مدل رایگان جدیدی که تیم OpenCode منتشر کنه، کافیه یک خط به دیکشنری `MODELS` در `config.py` اضافه کنی (کلید کوتاه دلخواه ← شناسه‌ی دقیق مدل که در داشبورد 9Router می‌بینی).

## ۱. ساخت ربات تلگرام
1. با [@BotFather](https://t.me/BotFather) چت کن، `/newbot` بزن و توکن رو بگیر.
2. آیدی عددی خودت رو از [@userinfobot](https://t.me/userinfobot) بگیر.

> ⚠️ **حتما `ALLOWED_USER_IDS` رو پر کن.** ربات دسترسی اجرای شل/پایتون داره!

## ۲. دیپلوی 9Router روی Railway و فعال‌سازی OpenCode Free
1. با قالب رسمی، 9Router رو روی Railway دیپلوی کن: `https://railway.com/deploy/9router`
   - در تنظیمات دیپلوی، مقدار `INITIAL_PASSWORD` (پسورد ورود به داشبورد 9Router) رو تعیین کن.
2. بعد از اتمام دیپلوی، آدرس عمومی که Railway ساخته (چیزی شبیه `https://xxxx.up.railway.app`) رو باز کن و با `INITIAL_PASSWORD` وارد داشبورد شو.
3. در داشبورد، بخش **Providers** → پروایدر **OpenCode Free** رو Connect کن (نیازی به احراز هویت نداره).
4. در بخش **API Keys**، یک کلید بساز — همین کلید بعداً در متغیر `AI_API_KEYS` استفاده می‌شه.
5. آدرس نهایی که در ربات استفاده می‌کنی: `https://<your-railway-domain>.up.railway.app/v1`

## ۳. اضافه کردن چند API Key (اختیاری)
اگه چند کلید از 9Router داری (مثلا برای توزیع بار یا چند اکانت):
1. برای هر کدوم یه API Key از داشبورد 9Router بساز.
2. همه رو با کاما تو `AI_API_KEYS` بذار:
   ```
   AI_API_KEYS=key_xxx,key_yyy,key_zzz
   ```
3. ربات به‌صورت **sticky** بینشون می‌چرخه:
   - همون کلیدی که کار می‌کنه رو نگه می‌داره
   - اگه یکی rate-limit بخوره، خودکار میره سراغ بعدی
   - تو تاپیک «🔑 آمار و توکن‌ها» می‌تونی ببینی کدوم کلید فعاله
   - با `/clear_tokens` می‌تونی cooldown همه رو پاک کنی

## ۴. متغیرهای محیطی مهم
```
TELEGRAM_BOT_TOKEN=...
ALLOWED_USER_IDS=123456789

# 9Router (الزامی)
AI_BASE_URL=https://<your-railway-domain>.up.railway.app/v1
AI_API_KEYS=key_xxx,key_yyy
DEFAULT_MODEL_KEY=mimo-v2.5

# 9Router retry
AI_MAX_RETRIES=3
AI_RETRY_DELAY=1.0
AI_KEY_COOLDOWN_SECONDS=30

# Agent
SHELL_ENABLED=true
ALLOW_DANGEROUS_COMMANDS=false
STREAM_ENABLED=true
MAX_CONCURRENT_UPDATES=8
DB_PATH=/data/bot.db
```

## ۵. دیپلوی ربات روی Railway
1. پوشه رو به یه ریپازیتوری گیت‌هاب پوش کن.
2. توی Railway → New Project → Deploy from GitHub repo → همین ریپو.
3. تب **Variables** و همه‌ی متغیرهای بالا رو با مقدار واقعی ست کن.
4. (پیشنهادی) یه **Volume** بساز و به مسیر `/data` وصل کن.
5. Deploy بزن.

> نکته: این سرویس ربات (main.py) با سرویس 9Router یه پروژه‌ی جدا روی Railway‌ست. یعنی دو تا سرویس داری: یکی 9Router (گیت‌وی مدل‌ها) و یکی همین ربات که بهش وصل می‌شه.

## ۶. تست
توی تلگرام به ربات پیام بده. باید سه تاپیک بسازه و شروع کنه به جواب دادن.

می‌تونی قبل از دیپلوی ربات، اتصال 9Router رو مستقل تست کنی:
```bash
curl -X POST "https://<your-railway-domain>.up.railway.app/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "model": "oc/mimo-v2.5-free",
    "messages": [{"role": "user", "content": "سلام"}]
  }'
```

## درباره‌ی سرعت
- مدل پیش‌فرض `mimo-v2.5` سریع و باکیفیته.
- برای پاسخ سریع‌تر روی سوالات ساده، از `/model deepseek-v4-flash` استفاده کن.
- برای سوالات ساده (سلام، شعر)، ربات خودکار `max_tokens` رو کم می‌کنه تا سریع‌تر جواب بده.

## نکات امنیتی
- `ALLOW_DANGEROUS_COMMANDS` رو روی `false` نگه دار.
- ابزارهای `run_shell_command` و `run_python` اجرای کد دلخواه روی کانتینر رو ممکن می‌کنن.
- API Key ها و توکن‌ها رو داخل کد commit نکن؛ فقط از Variables استفاده کن.
- چون 9Router روی یه آدرس عمومی Railway در دسترسه، پسورد داشبورد و API Key ها رو قوی نگه دار.
