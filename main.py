import base64
import json
import mimetypes
import re
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from config import Config
from key_manager import NvidiaKeyManager
from nvidia_client import NvidiaAgentClient
from telegram_api import TelegramAPI, split_long_text
from storage import Storage
from agent import run_agent

THOUGHTS_TOPIC_NAME = "🧠 فکرها"
ANSWER_TOPIC_NAME = "💬 پاسخ نهایی"
STATS_TOPIC_NAME = "🔑 آمار و کلیدها"

STATE_KEY_OFFSET = "last_update_offset"

TEXT_FILE_EXTENSIONS = {
    ".txt", ".md", ".csv", ".json", ".py", ".log", ".yaml", ".yml",
    ".xml", ".html", ".htm", ".ini", ".cfg", ".toml", ".sh", ".js",
    ".ts", ".java", ".c", ".cpp", ".go", ".rs", ".sql",
}

START_TIME = time.time()

# قفل جدا برای هر کاربر تا پیام‌های همزمانِ یک کاربر روی هم ننویسن؛
# پیام‌های کاربرهای مختلف موازی پردازش می‌شن.
_user_locks: dict[int, threading.Lock] = {}
_user_locks_guard = threading.Lock()


def _get_user_lock(user_id: int) -> threading.Lock:
    with _user_locks_guard:
        lock = _user_locks.get(user_id)
        if lock is None:
            lock = threading.Lock()
            _user_locks[user_id] = lock
        return lock


def ensure_topics(tg: TelegramAPI, db: Storage, chat_id: int, user_id: int) -> tuple[int, int, int]:
    existing = db.get_topics(user_id)
    if existing and existing[2]:
        return existing[0], existing[1], existing[2]

    if existing:
        # کاربر قدیمی که فقط دو تاپیک داره؛ فقط تاپیک آمار رو براش می‌سازیم.
        thoughts_id, answer_id, _ = existing
        stats_topic = tg.create_forum_topic(chat_id, STATS_TOPIC_NAME)
        stats_id = stats_topic["message_thread_id"]
        db.save_topics(user_id, thoughts_id, answer_id, stats_id)
        tg.send_message(
            chat_id,
            "این تاپیک وضعیت کلیدهای NVIDIA و مصرف توکن‌شون رو نشون می‌ده 🔑",
            message_thread_id=stats_id,
        )
        return thoughts_id, answer_id, stats_id

    thoughts_topic = tg.create_forum_topic(chat_id, THOUGHTS_TOPIC_NAME)
    answer_topic = tg.create_forum_topic(chat_id, ANSWER_TOPIC_NAME)
    stats_topic = tg.create_forum_topic(chat_id, STATS_TOPIC_NAME)

    thoughts_id = thoughts_topic["message_thread_id"]
    answer_id = answer_topic["message_thread_id"]
    stats_id = stats_topic["message_thread_id"]

    db.save_topics(user_id, thoughts_id, answer_id, stats_id)

    tg.send_message(
        chat_id,
        "این تاپیک برای فکرها و مراحل داخلی ایجنته 🧠",
        message_thread_id=thoughts_id,
    )
    tg.send_message(
        chat_id,
        "پاسخ‌های نهایی من اینجا میاد 💬",
        message_thread_id=answer_id,
    )
    tg.send_message(
        chat_id,
        "این تاپیک وضعیت کلیدهای NVIDIA و مصرف توکن‌شون رو نشون می‌ده 🔑",
        message_thread_id=stats_id,
    )
    return thoughts_id, answer_id, stats_id


def format_keys_stats_text(key_manager: NvidiaKeyManager, header: str = "🔑 *وضعیت کلیدهای NVIDIA*") -> str:
    lines = [header]
    active_masked = key_manager.active_key_masked()
    lines.append(f"کلیدِ در حالِ استفاده الان: `{active_masked or 'هنوز درخواستی زده نشده'}`")
    lines.append("")
    for item in key_manager.usage_snapshot():
        marker = "🟢" if item["is_active"] else ("⚪" if item["available"] else "🔴")
        line = (
            f"{marker} کلید {item['index']} (`{item['masked']}`) — "
            f"{item['requests']} درخواست — "
            f"{item['total_tokens']} توکن (ورودی {item['prompt_tokens']} / خروجی {item['completion_tokens']})"
        )
        if item["remaining_tokens"] is not None:
            line += f" — باقی‌مونده: {item['remaining_tokens']}"
        if not item["available"]:
            line += f" — 🚫 در کول‌داون ({item['cooldown_seconds']:.0f} ثانیه دیگه)"
        lines.append(line)
    return "\n".join(lines)


def send_long(tg: TelegramAPI, chat_id: int, text: str, message_thread_id: int) -> None:
    for chunk in split_long_text(text):
        tg.send_message(chat_id, chunk, message_thread_id=message_thread_id)


class TypingLoop:
    """تا وقتی ایجنت داره کار می‌کنه، هر چند ثانیه یک‌بار 'در حال نوشتن...' رو دوباره می‌فرسته."""

    def __init__(self, tg: TelegramAPI, chat_id: int, message_thread_id: int, interval: float = 4.0):
        self._tg = tg
        self._chat_id = chat_id
        self._thread_id = message_thread_id
        self._interval = interval
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop_event.is_set():
            try:
                self._tg.send_chat_action(self._chat_id, "typing", message_thread_id=self._thread_id)
            except Exception:
                pass
            self._stop_event.wait(self._interval)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop_event.set()
        self._thread.join(timeout=1)


class StreamEditor:
    """
    پاسخ نهایی رو به‌جای یک پیام کامل، به‌صورت زنده (استریم، توکن‌به‌توکن) توی تلگرام
    ادیت می‌کنه. اولین تکه‌ی متن، یه پیام جدید می‌فرسته و تکه‌های بعدی همون پیام رو
    edit می‌کنن. برای رعایت محدودیت نرخِ editMessageText تلگرام، بین ادیت‌ها حداقل
    فاصله رعایت می‌شه.

    نکته‌ی مهم: بافر بین مرحله‌های ایجنت (قبل/بعد از هر tool call) دیگه پاک نمی‌شه.
    قبلاً هر مرحله‌ی جدید بافر رو خالی می‌کرد و همین باعث می‌شد کاربر ببینه یه متن
    نوشته می‌شه، بعد پاک می‌شه و یه متن کاملاً متفاوت جاش میاد. حالا متن به‌صورت
    پیوسته رشد می‌کنه و فقط در پایان (finalize) یک‌بار با پاسخ نهاییِ تمیز جایگزین می‌شه.
    """

    def __init__(self, tg: TelegramAPI, chat_id: int, message_thread_id: int, min_interval: float):
        self._tg = tg
        self._chat_id = chat_id
        self._thread_id = message_thread_id
        self._min_interval = min_interval
        self._lock = threading.Lock()
        self._message_id: int | None = None
        self._buffer = ""
        self._last_edit = 0.0
        self._first_edit_done = False

    def add_delta(self, piece: str) -> None:
        with self._lock:
            self._buffer += piece
            now = time.time()
            # اولین ادیت زودتر انجام بشه تا کاربر سریع‌تر چیزی ببینه
            if not self._first_edit_done:
                if now - self._last_edit < Config.STREAM_FIRST_EDIT_DELAY:
                    return
            else:
                if now - self._last_edit < self._min_interval:
                    return
            text = self._buffer
            self._last_edit = now
            self._first_edit_done = True
        self._flush(text)

    def finalize(self, final_text: str) -> None:
        with self._lock:
            self._buffer = final_text
        self._flush(final_text, force=True)

    def _flush(self, text: str, force: bool = False) -> None:
        text = text.strip() or "..."
        for chunk in split_long_text(text):
            display = chunk + ("\n▌" if not force else "")
            try:
                if self._message_id is None:
                    result = self._tg.send_message(
                        self._chat_id, display, message_thread_id=self._thread_id
                    )
                    self._message_id = result["message_id"]
                else:
                    self._tg.edit_message_text(self._chat_id, self._message_id, display)
            except Exception as e:
                # اگه edit خطا بده (مثلاً پیام خیلی طولانی یا مارک‌داون نامعتبر)،
                # یه پیام جدید بفرست تا پیام نهایی از دست نره
                if self._message_id is not None and force:
                    try:
                        self._tg.send_message(
                            self._chat_id, display, message_thread_id=self._thread_id
                        )
                    except Exception:
                        pass
            break  # فعلا فقط اولین تکه رو زنده ادیت می‌کنیم؛ اگه خیلی بلند شد در finalize کامل می‌فرستیم

        if force and len(text) > 3800:
            # اگه پاسخ نهایی طولانی‌تر از یه پیام تلگرامه، بقیه‌ش رو جداگانه می‌فرستیم.
            rest = text[3800:]
            send_long(self._tg, self._chat_id, rest, self._thread_id)


def resolve_model(db: Storage, user_id: int) -> tuple[str, str]:
    """(model_key, model_id) رو برمی‌گردونه؛ اول ترجیح خود کاربر، بعد مدل پیش‌فرض."""
    model_key = db.get_user_model(user_id) or Config.DEFAULT_MODEL_KEY
    if model_key not in Config.MODELS:
        model_key = Config.DEFAULT_MODEL_KEY
    return model_key, Config.MODELS.get(model_key, Config.NVIDIA_MODEL)


def build_file_attachment_text(file_name: str, text_content: str) -> str:
    truncated = text_content[: Config.MAX_FILE_TEXT_CHARS]
    note = ""
    if len(text_content) > Config.MAX_FILE_TEXT_CHARS:
        note = f"\n...[محتوا به خاطر طول زیاد، به {Config.MAX_FILE_TEXT_CHARS} کاراکتر اول محدود شد]"
    return f"[فایل ضمیمه: {file_name}]\n```\n{truncated}{note}\n```"


def handle_command(
    tg: TelegramAPI,
    db: Storage,
    key_manager: NvidiaKeyManager,
    chat_id: int,
    user_id: int,
    thoughts_topic_id: int,
    answer_topic_id: int,
    stats_topic_id: int,
    text: str,
) -> bool:
    """اگه پیام یک دستور بود، پردازشش می‌کنه و True برمی‌گردونه؛ وگرنه False."""
    stripped = text.strip()
    lowered = stripped.lower()

    if lowered == "/stats":
        model_key, model_id = resolve_model(db, user_id)
        msg = (
            "📊 *آمار ربات*\n"
            f"- پیام‌های شما: {db.count_messages(user_id)}\n"
            f"- کل پیام‌های ثبت‌شده: {db.count_messages()}\n"
            f"- تعداد کاربران فعال: {db.count_users()}\n"
            f"- مدل فعلی شما: `{model_key}` (`{model_id}`)\n"
            f"- کلیدهای NVIDIA فعال: {key_manager.available_keys()}/{key_manager.total_keys()}\n"
            f"- زمان روشن بودن: {int((time.time() - START_TIME) // 60)} دقیقه\n\n"
            f"{format_keys_stats_text(key_manager, header='🔑 *ریز مصرف کلیدها:*')}"
        )
        tg.send_message(chat_id, msg, message_thread_id=answer_topic_id)
        return True

    if lowered == "/models":
        model_key, _ = resolve_model(db, user_id)
        lines = ["📚 *مدل‌های قابل انتخاب:*"]
        for key, model_id in Config.MODELS.items():
            marker = "✅" if key == model_key else "▫️"
            lines.append(f"{marker} `{key}` → {model_id}")
        lines.append("\nبرای تعویض: `/model <نام>` مثلا `/model llama-3.1`")
        tg.send_message(chat_id, "\n".join(lines), message_thread_id=answer_topic_id)
        return True

    if lowered.startswith("/model"):
        parts = stripped.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            tg.send_message(
                chat_id,
                "برای دیدن لیست مدل‌ها از /models استفاده کن. مثال تعویض: `/model glm-5.2`",
                message_thread_id=answer_topic_id,
            )
            return True
        key = parts[1].strip()
        if key not in Config.MODELS:
            tg.send_message(
                chat_id,
                f"❌ مدل `{key}` شناخته‌شده نیست. لیست مدل‌ها: /models",
                message_thread_id=answer_topic_id,
            )
            return True
        db.set_user_model(user_id, key)
        tg.send_message(
            chat_id,
            f"✅ مدل شما به `{key}` (`{Config.MODELS[key]}`) تغییر کرد.",
            message_thread_id=answer_topic_id,
        )
        return True

    if lowered == "/reset":
        removed = db.reset_history(user_id)
        tg.send_message(
            chat_id,
            f"🗑️ تاریخچه‌ی گفتگوی شما پاک شد ({removed} پیام حذف شد).",
            message_thread_id=answer_topic_id,
        )
        return True

    if lowered == "/export":
        history = db.get_full_history(user_id)
        payload = json.dumps(history, ensure_ascii=False, indent=2).encode("utf-8")
        tg.send_document(
            chat_id,
            filename=f"chat_history_{user_id}.json",
            content_bytes=payload,
            caption=f"تاریخچه‌ی گفتگو ({len(history)} پیام)",
            message_thread_id=answer_topic_id,
        )
        return True

    if lowered == "/clear_keys":
        # reset کردن cooldown همه‌ی کلیدها (برای مواقعی که کلیدها موقتاً سوختن)
        cleared = key_manager.reset_cooldowns()
        msg = f"🔓 cooldown همه‌ی کلیدها پاک شد.\n{cleared} کلید از حالت محدود خارج شد.\nالان {key_manager.available_keys()}/{key_manager.total_keys()} کلید فعال هست."
        tg.send_message(chat_id, msg, message_thread_id=stats_topic_id)
        return True

    if lowered == "/help":
        help_text = (
            "🤖 *راهنمای ربات*\n\n"
            "*دستورات:*\n"
            "• `/stats` - نمایش آمار کامل ربات و کلیدها\n"
            "• `/models` - لیست مدل‌های قابل انتخاب\n"
            "• `/model <name>` - تعویض مدل\n"
            "• `/reset` - پاک کردن تاریخچه\n"
            "• `/export` - خروجی JSON تاریخچه\n"
            "• `/clear_keys` - پاک کردن cooldown کلیدها (وقتی کلیدها سوختن)\n"
            "• `/help` - این راهنما\n\n"
            "*قابلیت‌ها:*\n"
            "• 📝 ارسال متن برای چت با ایجنت\n"
            "• 📷 ارسال عکس برای تحلیل تصویر\n"
            "• 📎 ارسال فایل (متنی یا باینری)\n"
            "• 🔍 جستجوی وب (به‌صورت خودکار وقتی لازم باشه)\n"
            "• 💻 اجرای کد پایتون و شل\n"
            "• 📤 ارسال فایل/عکس از طرف ربات به کاربر\n"
            "• ⚡ پاسخ استریمی زنده\n\n"
            "*تاپیک‌ها:*\n"
            "• 🧠 فکرها - مراحل فکر ایجنت\n"
            "• 💬 پاسخ نهایی - جواب نهایی\n"
            "• 🔑 آمار و کلیدها - وضعیت کلیدهای NVIDIA\n\n"
            "*مدل‌های پیشنهادی:*\n"
            "• `llama-3.1-8b` - سریع و سبک (پیش‌فرض)\n"
            "• `llama-3.2-90b-vision` - قدرتمند + vision\n\n"
            "برای سوال زمان‌مندی (قیمت، اخبار، آب‌وهوا) فقط بپرس، خودم جستجو می‌کنم!"
        )
        tg.send_message(chat_id, help_text, message_thread_id=answer_topic_id)
        return True

    return False


def _maybe_send_images_from_reply(tg: TelegramAPI, chat_id: int, message_thread_id: int, text: str) -> None:
    """اگه مدل تو خروجیش Markdown image گذاشته (![](url))، ربات خودکار عکس رو بفرسته."""
    if not Config.AUTO_SEND_IMAGES_IN_REPLY:
        return
    # الگوی ![alt](url) برای عکس‌های با پسوند jpg/jpeg/png/webp/gif
    pattern = re.compile(
        r"!\[([^\]]*)\]\((https?://[^\s)]+\.(?:jpg|jpeg|png|gif|webp)(?:\?[^\s)]*)?)\)",
        re.IGNORECASE,
    )
    matches = pattern.findall(text)
    for alt, url in matches[:5]:  # حداکثر ۵ عکس
        try:
            if url.lower().endswith(".gif") or ".gif?" in url.lower():
                tg.send_animation_by_url(chat_id, url, caption=alt or None, message_thread_id=message_thread_id)
            else:
                tg.send_photo_by_url(chat_id, url, caption=alt or None, message_thread_id=message_thread_id)
        except Exception as e:
            print(f"⚠️ ارسال عکس خودکار ناموفق: {e}")


def run_agent_and_reply(
    tg: TelegramAPI,
    db: Storage,
    key_manager: NvidiaKeyManager,
    client: NvidiaAgentClient,
    chat_id: int,
    user_id: int,
    thoughts_topic_id: int,
    answer_topic_id: int,
    stats_topic_id: int,
    user_content,
    history_text_for_db: str,
) -> None:
    model_key, model_id = resolve_model(db, user_id)
    history = db.get_history(user_id, Config.MAX_HISTORY_MESSAGES)

    def on_usage(info: dict) -> None:
        # هروقت کلید واقعاً عوض بشه (نه اولین درخواست)، توی تاپیک آمار خبر می‌دیم.
        if info.get("switched") and info.get("previous_masked_key"):
            try:
                tg.send_message(
                    chat_id,
                    f"🔁 کلید به کلید بعدی تغییر یافت: `{info.get('previous_masked_key')}` → `{info.get('masked_key')}`",
                    message_thread_id=stats_topic_id,
                )
            except Exception:
                pass

    tool_context = {"tg": tg, "chat_id": chat_id, "answer_topic_id": answer_topic_id}

    if Config.STREAM_ENABLED:
        streamer = StreamEditor(tg, chat_id, answer_topic_id, Config.STREAM_EDIT_MIN_INTERVAL)
        try:
            with TypingLoop(tg, chat_id, answer_topic_id):
                result = run_agent(
                    client,
                    history,
                    user_content,
                    model=model_id,
                    on_content_delta=streamer.add_delta,
                    on_usage=on_usage,
                    tool_context=tool_context,
                )
            streamer.finalize(result.final_answer)
        except Exception as e:
            # اگه هر خطای غیرمنتظره‌ای پیش اومد، استریم رو finalize کن و یه پیام خطا بفرست
            err_text = f"⚠️ خطای غیرمنتظره: {e}"
            print(f"⚠️ run_agent_and_reply error: {type(e).__name__}: {e}")
            traceback.print_exc()
            try:
                streamer.finalize(err_text)
            except Exception:
                try:
                    tg.send_message(chat_id, err_text, message_thread_id=answer_topic_id)
                except Exception:
                    pass
            # یه نتیجه‌ی خالی بساز تا بقیه‌ی کد کرش نکنه
            from agent import AgentResult
            result = AgentResult(thoughts=[], final_answer=err_text)
    else:
        try:
            with TypingLoop(tg, chat_id, answer_topic_id):
                result = run_agent(
                    client, history, user_content, model=model_id, on_usage=on_usage, tool_context=tool_context
                )
            send_long(tg, chat_id, result.final_answer, answer_topic_id)
        except Exception as e:
            err_text = f"⚠️ خطای غیرمنتظره: {e}"
            print(f"⚠️ run_agent_and_reply error: {type(e).__name__}: {e}")
            traceback.print_exc()
            tg.send_message(chat_id, err_text, message_thread_id=answer_topic_id)
            from agent import AgentResult
            result = AgentResult(thoughts=[], final_answer=err_text)

    # ارسال خودکار عکس‌هایی که مدل تو پاسخش گذاشته (Markdown image syntax)
    _maybe_send_images_from_reply(tg, chat_id, answer_topic_id, result.final_answer)

    if result.thoughts:
        send_long(tg, chat_id, "\n\n---\n\n".join(result.thoughts), thoughts_topic_id)
    else:
        tg.send_message(chat_id, "(این بار فکر خاصی ثبت نشد)", message_thread_id=thoughts_topic_id)

    # آمار کامل و به‌روزِ کلیدها رو بعد از هر پاسخ توی تاپیک آمار می‌فرستیم.
    try:
        tg.send_message(chat_id, format_keys_stats_text(key_manager), message_thread_id=stats_topic_id)
    except Exception:
        pass

    db.add_message(user_id, "user", history_text_for_db)
    db.add_message(user_id, "assistant", result.final_answer)
    db.trim_history(user_id, Config.MAX_HISTORY_MESSAGES)


def handle_message(tg: TelegramAPI, db: Storage, key_manager: NvidiaKeyManager, client: NvidiaAgentClient, message: dict) -> None:
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    user_id = message.get("from", {}).get("id")
    text = message.get("text")
    document = message.get("document")
    photo = message.get("photo")

    if chat.get("type") != "private":
        return
    if not (text or document or photo):
        return

    if Config.ALLOWED_USER_IDS and user_id not in Config.ALLOWED_USER_IDS:
        tg.send_message(chat_id, "⛔ متاسفانه اجازه استفاده از این ربات رو نداری.")
        return

    # هر کاربر فقط یه پیام رو در آنِ واحد پردازش می‌کنه (پیام‌های کاربرهای مختلف موازی هستن)
    with _get_user_lock(user_id):
        if text and text.strip() == "/start":
            tg.send_message(
                chat_id,
                "سلام! پیامت رو بفرست تا شروع کنیم. من سه تاپیک برات می‌سازم: یکی برای "
                "فکرهام، یکی برای پاسخ نهایی و یکی برای وضعیت کلیدها/توکن‌ها. "
                "دستورات: /stats /models /model /reset /export /help",
            )
            ensure_topics(tg, db, chat_id, user_id)
            return

        thoughts_topic_id, answer_topic_id, stats_topic_id = ensure_topics(tg, db, chat_id, user_id)

        if text and handle_command(
            tg, db, key_manager, chat_id, user_id, thoughts_topic_id, answer_topic_id, stats_topic_id, text
        ):
            return

        # --- تصویر ---
        if photo:
            largest = photo[-1]
            try:
                content_bytes, _ = tg.get_file_bytes(largest["file_id"])
            except Exception as e:
                tg.send_message(chat_id, f"⚠️ دانلود تصویر ناموفق بود: {e}", message_thread_id=answer_topic_id)
                return
            b64 = base64.b64encode(content_bytes).decode("ascii")
            caption = (message.get("caption") or "این عکس رو توضیح بده / تحلیل کن.").strip()
            user_content = [
                {"type": "text", "text": caption},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ]
            run_agent_and_reply(
                tg, db, key_manager, client, chat_id, user_id, thoughts_topic_id, answer_topic_id, stats_topic_id,
                user_content, f"[عکس ارسال شد] {caption}",
            )
            return

        # --- فایل ---
        if document:
            file_name = document.get("file_name") or "file"
            mime_type = document.get("mime_type") or mimetypes.guess_type(file_name)[0] or ""
            file_size = document.get("file_size") or 0
            if file_size > Config.MAX_DOWNLOAD_FILE_MB * 1024 * 1024:
                tg.send_message(
                    chat_id,
                    f"⚠️ فایل خیلی بزرگه (بیشتر از {Config.MAX_DOWNLOAD_FILE_MB}MB).",
                    message_thread_id=answer_topic_id,
                )
                return
            try:
                content_bytes, _ = tg.get_file_bytes(document["file_id"])
            except Exception as e:
                tg.send_message(chat_id, f"⚠️ دانلود فایل ناموفق بود: {e}", message_thread_id=answer_topic_id)
                return

            caption = (message.get("caption") or "").strip()
            ext = "." + file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""

            if mime_type.startswith("image/"):
                b64 = base64.b64encode(content_bytes).decode("ascii")
                text_prompt = caption or "این تصویر رو تحلیل کن."
                user_content = [
                    {"type": "text", "text": text_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
                ]
                db_text = f"[تصویر ضمیمه: {file_name}] {text_prompt}"
            elif ext in TEXT_FILE_EXTENSIONS or mime_type.startswith("text/"):
                text_content = content_bytes.decode("utf-8", errors="replace")
                attachment_block = build_file_attachment_text(file_name, text_content)
                user_content = f"{caption}\n\n{attachment_block}" if caption else attachment_block
                db_text = f"[فایل ضمیمه: {file_name}] {caption}"
            else:
                user_content = (
                    f"{caption}\n\n[فایل ضمیمه: {file_name} ({mime_type or 'نامشخص'}, "
                    f"{file_size} بایت) - این نوع فایل باینریه و متنش قابل نمایش مستقیم نیست. "
                    "اگه لازمه با run_shell_command یا run_python بررسیش کن."
                ).strip()
                db_text = f"[فایل باینری ضمیمه: {file_name}] {caption}"

            run_agent_and_reply(
                tg, db, key_manager, client, chat_id, user_id, thoughts_topic_id, answer_topic_id, stats_topic_id,
                user_content, db_text,
            )
            return

        # --- متن معمولی ---
        run_agent_and_reply(
            tg, db, key_manager, client, chat_id, user_id, thoughts_topic_id, answer_topic_id, stats_topic_id,
            text, text,
        )


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/health", "/"):
            body = b'{"status":"ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # لاگ‌های healthcheck رو ساکت نگه می‌داریم


def start_health_server(port: int) -> None:
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"❤️ Health endpoint روی پورت {port} در مسیر /health بالا اومد.")


def main() -> None:
    Config.validate()

    tg = TelegramAPI(Config.TELEGRAM_BOT_TOKEN)
    db = Storage(Config.DB_PATH)
    key_manager = NvidiaKeyManager(
        Config.NVIDIA_API_KEYS, Config.DEFAULT_KEY_COOLDOWN_SECONDS, Config.TOKEN_BUDGET_PER_KEY
    )
    client = NvidiaAgentClient(key_manager, Config.NVIDIA_BASE_URL, Config.NVIDIA_MODEL)

    start_health_server(Config.HEALTH_PORT)

    print(
        f"✅ ربات روشن شد. مدل پیش‌فرض: {Config.DEFAULT_MODEL_KEY} | "
        f"تعداد کلید: {key_manager.total_keys()} | Concurrency: {Config.MAX_CONCURRENT_UPDATES}"
    )

    offset_raw = db.get_state(STATE_KEY_OFFSET)
    offset = int(offset_raw) + 1 if offset_raw else None

    executor = ThreadPoolExecutor(max_workers=Config.MAX_CONCURRENT_UPDATES)

    def _process(message: dict) -> None:
        from_id = message.get("from", {}).get("id")
        try:
            handle_message(tg, db, key_manager, client, message)
            print(f"✅ پیام از {from_id} پردازش شد.")
        except Exception:
            print("⚠️ خطا در پردازش پیام:")
            traceback.print_exc()
            chat_id = message.get("chat", {}).get("id")
            if chat_id:
                try:
                    tg.send_message(chat_id, "⚠️ یه خطای داخلی پیش اومد، دوباره امتحان کن.")
                except Exception:
                    pass

    while True:
        try:
            updates = tg.get_updates(offset=offset, timeout=50)
        except Exception:
            print("⚠️ خطا در getUpdates:")
            traceback.print_exc()
            time.sleep(5)
            continue

        for update in updates:
            offset = update["update_id"] + 1
            db.set_state(STATE_KEY_OFFSET, str(update["update_id"]))

            message = update.get("message")
            if not message:
                continue

            text_preview = (message.get("text") or "[بدون متن/فایل]")[:80]
            from_id = message.get("from", {}).get("id")
            print(f"📩 پیام جدید از {from_id}: {text_preview!r}")

            executor.submit(_process, message)


if __name__ == "__main__":
    print("🚀 در حال شروع ربات...")
    try:
        main()
    except Exception:
        print("❌ ربات با خطا متوقف شد:")
        traceback.print_exc()
        raise
