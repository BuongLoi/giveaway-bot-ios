import requests
import time
import logging

logger = logging.getLogger(__name__)

def send_message(text: str, parse_mode: str = "HTML", disable_web_page_preview: bool = True) -> bool:
    """
    Gửi tin nhắn lên Telegram. Tự động xử lý lỗi 429 Retry-After.
    Nếu tin nhắn quá dài (>4096 ký tự), sẽ cắt phần đuôi.
    """
    # Import ở đây để lấy giá trị mới nhất trong quá trình mock test
    from bot.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Chưa cấu hình TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID. Bỏ qua gửi tin.")
        return False

    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    # Cắt gọn tin nhắn nếu vượt quá giới hạn của Telegram (4096)
    if len(text) > 4000:
        text = text[:4000] + "\n\n... [Đã cắt bớt do giới hạn độ dài]"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": disable_web_page_preview
    }

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(api_url, json=payload, timeout=15)
            data = response.json()

            if response.status_code == 200 and data.get("ok"):
                logger.info("Gửi tin nhắn Telegram thành công.")
                return True
            elif response.status_code == 429:
                # Xử lý Too Many Requests
                retry_after = data.get("parameters", {}).get("retry_after", 5)
                logger.warning(f"Bị giới hạn tốc độ Telegram (429). Đợi {retry_after}s trước khi thử lại...")
                time.sleep(retry_after)
            else:
                logger.error(f"Lỗi gửi Telegram: {data.get('description')}")
                # Lỗi khác thì không retry
                break
        except requests.exceptions.RequestException as e:
            logger.error(f"Lỗi kết nối Telegram API: {e}")
            time.sleep(5) # Đợi một lát rồi thử lại

    return False


def _post_with_retry(method: str, payload: dict, max_retries: int = 3) -> bool:
    """Gọi Telegram Bot API (sendPhoto/sendMessage) có xử lý 429."""
    from bot.config import TELEGRAM_BOT_TOKEN
    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    for _ in range(max_retries):
        try:
            response = requests.post(api_url, json=payload, timeout=20)
            data = response.json()
            if response.status_code == 200 and data.get("ok"):
                return True
            if response.status_code == 429:
                retry_after = data.get("parameters", {}).get("retry_after", 5)
                logger.warning(f"Telegram 429, đợi {retry_after}s...")
                time.sleep(retry_after)
                continue
            logger.error(f"Lỗi Telegram {method}: {data.get('description')}")
            return False
        except (requests.exceptions.RequestException, ValueError) as e:
            logger.error(f"Lỗi kết nối Telegram API ({method}): {e}")
            time.sleep(5)
    return False


def send_rich(caption: str, photo_url: str = "", buttons: list = None) -> bool:
    """
    Gửi thông báo đẹp: ảnh + caption HTML + nút inline [(text, url), ...].
    Nếu gửi ảnh thất bại (ảnh lỗi/không hỗ trợ) thì tự rơi về sendMessage.
    """
    from bot.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Chưa cấu hình TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID. Bỏ qua gửi tin.")
        return False

    reply_markup = None
    valid_buttons = [(t, u) for t, u in (buttons or []) if u and u.startswith("http")]
    if valid_buttons:
        reply_markup = {"inline_keyboard": [[{"text": t, "url": u}] for t, u in valid_buttons[:3]]}

    if photo_url and photo_url.startswith("http") and len(caption) <= 1024:
        payload = {"chat_id": TELEGRAM_CHAT_ID, "photo": photo_url, "caption": caption, "parse_mode": "HTML"}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        if _post_with_retry("sendPhoto", payload):
            logger.info("Gửi ảnh Telegram thành công.")
            return True
        logger.info("Gửi ảnh thất bại, chuyển sang gửi tin nhắn văn bản.")

    text = caption if len(caption) <= 4000 else caption[:4000] + "…"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML",
               "disable_web_page_preview": False}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    ok = _post_with_retry("sendMessage", payload)
    if ok:
        logger.info("Gửi tin nhắn Telegram thành công.")
    return ok
