import httpx


class TelegramAPI:
    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.file_base_url = f"https://api.telegram.org/file/bot{token}"
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

    def send_message(
        self,
        chat_id: int,
        text: str,
        message_thread_id: int | None = None,
        parse_mode: str | None = "Markdown",
    ) -> dict:
        # تلگرام محدودیت طول پیام داره؛ اگه لازم شد بیرون از این تابع تقسیم کن.
        # اگه parse_mode باعث خطای پارس بشه (مثلا مارک‌داون نامعتبر از مدل)، بدون
        # parse_mode دوباره امتحان می‌کنیم تا پیام از دست نره.
        try:
            return self._call(
                "sendMessage",
                chat_id=chat_id,
                text=text,
                message_thread_id=message_thread_id,
                parse_mode=parse_mode,
            )
        except RuntimeError as e:
            if parse_mode and "can't parse entities" in str(e).lower():
                return self._call(
                    "sendMessage",
                    chat_id=chat_id,
                    text=text,
                    message_thread_id=message_thread_id,
                )
            raise

    def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        parse_mode: str | None = "Markdown",
    ) -> dict | None:
        """برای استریم کردن پاسخ استفاده می‌شه. اگه متن تغییری نکرده باشه یا خطای
        'message is not modified' بگیریم، بی‌سروصدا نادیده می‌گیریم."""
        try:
            return self._call(
                "editMessageText",
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=parse_mode,
            )
        except RuntimeError as e:
            low = str(e).lower()
            if "message is not modified" in low:
                return None
            if parse_mode and "can't parse entities" in low:
                try:
                    return self._call(
                        "editMessageText", chat_id=chat_id, message_id=message_id, text=text
                    )
                except RuntimeError as e2:
                    if "message is not modified" in str(e2).lower():
                        return None
                    raise
            raise

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

    # --- فایل / تصویر ---
    def get_file(self, file_id: str) -> dict:
        """اطلاعات فایل (از جمله file_path) رو برمی‌گردونه."""
        return self._call("getFile", file_id=file_id)

    def download_file_bytes(self, file_path: str) -> bytes:
        resp = self._client.get(f"{self.file_base_url}/{file_path}")
        resp.raise_for_status()
        return resp.content

    def get_file_bytes(self, file_id: str) -> tuple[bytes, str]:
        """کمکی: هم متادیتا و هم بایت‌های فایل رو برمی‌گردونه -> (bytes, file_path)."""
        info = self.get_file(file_id)
        file_path = info["file_path"]
        return self.download_file_bytes(file_path), file_path

    def send_document(
        self,
        chat_id: int,
        filename: str,
        content_bytes: bytes,
        caption: str | None = None,
        message_thread_id: int | None = None,
    ) -> dict:
        params = {k: v for k, v in {
            "chat_id": chat_id,
            "caption": caption,
            "message_thread_id": message_thread_id,
        }.items() if v is not None}
        files = {"document": (filename, content_bytes)}
        resp = self._client.post(f"{self.base_url}/sendDocument", data=params, files=files)
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API error در sendDocument: {data}")
        return data["result"]


def split_long_text(text: str, limit: int = 3800) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:limit])
        text = text[limit:]
    return chunks
