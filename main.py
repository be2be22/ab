import time
import traceback

from config import Config
from key_manager import NvidiaKeyManager
from nvidia_client import NvidiaAgentClient
from telegram_api import TelegramAPI, split_long_text
from storage import Storage
from agent import run_agent

THOUGHTS_TOPIC_NAME = "🧠 فکرها"
ANSWER_TOPIC_NAME = "💬 پاسخ نهایی"

STATE_KEY_OFFSET = "last_update_offset"


def ensure_topics(tg: TelegramAPI, db: Storage, chat_id: int, user_id: int) -> tuple[int, int]:
    existing = db.get_topics(user_id)
    if existing:
        return existing

    thoughts_topic = tg.create_forum_topic(chat_id, THOUGHTS_TOPIC_NAME)
    answer_topic = tg.create_forum_topic(chat_id, ANSWER_TOPIC_NAME)

    thoughts_id = thoughts_topic["message_thread_id"]
    answer_id = answer_topic["message_thread_id"]

    db.save_topics(user_id, thoughts_id, answer_id)

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
    return thoughts_id, answer_id


def send_long(tg: TelegramAPI, chat_id: int, text: str, message_thread_id: int) -> None:
    for chunk in split_long_text(text):
        tg.send_message(chat_id, chunk, message_thread_id=message_thread_id)


def handle_message(tg: TelegramAPI, db: Storage, client: NvidiaAgentClient, message: dict) -> None:
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    user_id = message.get("from", {}).get("id")
    text = message.get("text")

    if not text or chat.get("type") != "private":
        return

    if Config.ALLOWED_USER_IDS and user_id not in Config.ALLOWED_USER_IDS:
        tg.send_message(chat_id, "⛔ متاسفانه اجازه استفاده از این ربات رو نداری.")
        return

    if text.strip() == "/start":
        tg.send_message(chat_id, "سلام! پیامت رو بفرست تا شروع کنیم. من دو تاپیک برات می‌سازم: یکی برای فکرهام و یکی برای پاسخ نهایی.")
        return

    thoughts_topic_id, answer_topic_id = ensure_topics(tg, db, chat_id, user_id)

    tg.send_chat_action(chat_id, "typing", message_thread_id=answer_topic_id)

    history = db.get_history(user_id, Config.MAX_HISTORY_MESSAGES)
    result = run_agent(client, history, text)

    if result.thoughts:
        send_long(tg, chat_id, "\n\n---\n\n".join(result.thoughts), thoughts_topic_id)
    else:
        tg.send_message(chat_id, "(این بار فکر خاصی ثبت نشد)", message_thread_id=thoughts_topic_id)

    send_long(tg, chat_id, result.final_answer, answer_topic_id)

    db.add_message(user_id, "user", text)
    db.add_message(user_id, "assistant", result.final_answer)
    db.trim_history(user_id, Config.MAX_HISTORY_MESSAGES)


def main() -> None:
    Config.validate()

    tg = TelegramAPI(Config.TELEGRAM_BOT_TOKEN)
    db = Storage(Config.DB_PATH)
    key_manager = NvidiaKeyManager(Config.NVIDIA_API_KEYS, Config.DEFAULT_KEY_COOLDOWN_SECONDS)
    client = NvidiaAgentClient(key_manager, Config.NVIDIA_BASE_URL, Config.NVIDIA_MODEL)

    print(f"✅ ربات روشن شد. مدل: {Config.NVIDIA_MODEL} | تعداد کلید: {key_manager.total_keys()}")

    offset_raw = db.get_state(STATE_KEY_OFFSET)
    offset = int(offset_raw) + 1 if offset_raw else None

    while True:
        try:
            updates = tg.get_updates(offset=offset, timeout=50)
        except Exception:
            print("⚠️ خطا در getUpdates:")
            traceback.print_exc()
            time.sleep(5)
            continue

        for update in updates:
            offset = update["update_id"]
            db.set_state(STATE_KEY_OFFSET, str(offset))

            message = update.get("message")
            if not message:
                continue

            try:
                handle_message(tg, db, client, message)
            except Exception:
                print("⚠️ خطا در پردازش پیام:")
                traceback.print_exc()
                chat_id = message.get("chat", {}).get("id")
                if chat_id:
                    try:
                        tg.send_message(chat_id, "⚠️ یه خطای داخلی پیش اومد، دوباره امتحان کن.")
                    except Exception:
                        pass


if __name__ == "__main__":
    print("🚀 در حال شروع ربات...")
    try:
        main()
    except Exception:
        print("❌ ربات با خطا متوقف شد:")
        traceback.print_exc()
        raise
