import httpx


class TelegramAPI:
    def __init__(self, token: str):
        self.base_url = f"https://api.telegram.org/bot{token}"
        self._client = httpx.Client(timeout=65.0)

    def _call(self, method: str, **params) -> dict:
        params = {k: v for k, v in params.items() if v is not None}
        resp = self._client.post(f"{self.base_url}/{method}", json=params)
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API error در {method}: {data}")
        return data["result"]

    def get_updates(self, offset: int | None = None, timeout: int = 50) -> list[dict]:
        return self._call("getUpdates", offset=offset, timeout=timeout, allowed_updates=["message"])

    def send_message(self, chat_id: int, text: str, message_thread_id: int | None = None) -> dict:
        # تلگرام محدودیت طول پیام داره؛ اگه لازم شد بیرون از این تابع تقسیم کن
        return self._call(
            "sendMessage",
            chat_id=chat_id,
            text=text,
            message_thread_id=message_thread_id,
        )

    def send_chat_action(self, chat_id: int, action: str = "typing", message_thread_id: int | None = None) -> dict:
        return self._call(
            "sendChatAction",
            chat_id=chat_id,
            action=action,
            message_thread_id=message_thread_id,
        )

    def create_forum_topic(self, chat_id: int, name: str) -> dict:
        """تاپیک جدید می‌سازه (حالا هم توی گروه، هم توی چت خصوصی پشتیبانی می‌شه). خروجی شامل message_thread_id هست."""
        return self._call("createForumTopic", chat_id=chat_id, name=name)


def split_long_text(text: str, limit: int = 3800) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:limit])
        text = text[limit:]
    return chunks
