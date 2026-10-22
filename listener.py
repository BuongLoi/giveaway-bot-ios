import asyncio
import logging
import sys
from datetime import datetime, timezone
import argparse

# Thiết lập logging trước tiên
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("listener")

try:
    from telethon import TelegramClient, events
except ImportError:
    logger.error("Thư viện telethon chưa được cài đặt. Vui lòng chạy: pip install telethon")
    sys.exit(1)

from bot.config import (
    ENABLE_TELETHON_LISTENER,
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH,
    TELETHON_CHANNELS,
    KEYWORDS,
    NEGATIVE_KEYWORDS,
    MIN_CONFIDENCE_SCORE
)
from bot.database import init_db, check_and_save_giveaway, mark_as_notified
from bot.extractor import (
    extract_codes, classify_giveaway, detect_expiry_hint,
    detect_platform, get_platform_badge, evaluate_article_confidence
)
from bot.utils import generate_hash, escape_html
from bot.telegram import send_message


def contains_keywords(text: str) -> bool:
    if not KEYWORDS:
        return True
    text_lower = text.lower()
    for kw in KEYWORDS:
        if kw in text_lower:
            return True
    return False


def contains_negative_keywords(text: str) -> bool:
    if not NEGATIVE_KEYWORDS:
        return False
    text_lower = text.lower()
    for kw in NEGATIVE_KEYWORDS:
        if kw in text_lower:
            return True
    return False


async def main(dry_run: bool):
    if not ENABLE_TELETHON_LISTENER:
        logger.error("Telethon Listener đang bị TẮT trong file .env (ENABLE_TELETHON_LISTENER=0).")
        sys.exit(1)  # Exit 1 để systemd Restart=on-failure không restart vô hạn

    if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
        logger.error("Thiếu TELEGRAM_API_ID hoặc TELEGRAM_API_HASH trong .env.")
        sys.exit(1)

    if not TELETHON_CHANNELS:
        logger.warning("Không có channel nào được cấu hình trong TELETHON_CHANNELS. Bot sẽ không lắng nghe gì cả.")

    # Khởi tạo DB
    init_db()

    logger.info("Đang khởi tạo Telethon Client...")
    client = TelegramClient('giveaway_listener', TELEGRAM_API_ID, TELEGRAM_API_HASH)

    @client.on(events.NewMessage(chats=TELETHON_CHANNELS))
    async def handler(event):
        chat = await event.get_chat()
        chat_title = getattr(chat, 'title', chat.username or str(chat.id))

        # Lấy văn bản từ tin nhắn (caption nếu là media)
        text = event.message.message or ""
        if not text:
            return

        logger.info(f"Nhận tin nhắn mới từ {chat_title}")

        if not contains_keywords(text) or contains_negative_keywords(text):
            logger.debug("Bỏ qua tin nhắn do bộ lọc từ khóa.")
            return

        # Giả lập guid từ id tin nhắn để chống trùng
        guid = f"telethon_{chat.id}_{event.message.id}"
        canonical_url = f"https://t.me/c/{chat.id}/{event.message.id}"

        codes, code_confidence = extract_codes(text)

        # Chỉ xử lý nếu tìm thấy code để tránh rác DB từ các tin nhắn chat bình thường
        if not codes:
            logger.debug(f"[{chat_title}] Không tìm thấy mã code trong tin nhắn.")
            return

        first_line = text.strip().splitlines()[0][:80] if text.strip() else f"Chia sẻ từ {chat_title}"
        title = f"[{chat_title}] {first_line}"
        platform = detect_platform(title, text, canonical_url, f"telegram_{chat_title}")
        tags = classify_giveaway(title, text)
        expiry = detect_expiry_hint(title, text)
        confidence = evaluate_article_confidence(title, text, codes, code_confidence, canonical_url, "telegram")

        sorted_codes = sorted(codes)
        codes_str = ", ".join(sorted_codes)
        tags_str = ", ".join(tags)
        content_hash = generate_hash(text)
        codes_hash = generate_hash(",".join(sorted_codes))
        published_at = event.message.date.isoformat() if event.message.date else datetime.now(timezone.utc).isoformat()

        # Lưu vào SQLite
        db_result = check_and_save_giveaway(
            source=f"Telegram ({chat_title})",
            canonical_url=canonical_url,
            guid=guid,
            title=title,
            published_at=published_at,
            content_hash=content_hash,
            codes_hash=codes_hash,
            confidence_score=confidence,
            codes=codes_str,
            platform=platform,
            tags=tags_str,
            expiry_hint=expiry
        )

        action = db_result['action']
        record_id = db_result['id']

        if action == 'skip':
            return

        if MIN_CONFIDENCE_SCORE > 0 and confidence < MIN_CONFIDENCE_SCORE:
            logger.debug(f"[{chat_title}] Bỏ qua gửi TG vì confidence ({confidence}) < MIN ({MIN_CONFIDENCE_SCORE})")
            return

        logger.info(f"[{chat_title}] Đã phát hiện code mới! Đang gửi Telegram Bot...")

        platform_badge = get_platform_badge(platform)
        safe_title = escape_html(title)
        message = f"🎁 <b>{safe_title}</b>\n"
        message += f"🏷️ {platform_badge}\n\n"
        message += f"🌍 <b>Nguồn:</b> Telegram ({escape_html(chat_title)})\n\n"

        message += "🔑 <b>Code thu thập được:</b>\n"
        for c in sorted_codes:
            message += f"<code>{escape_html(c)}</code>\n"

        if confidence < 50:
            message += "\n<i>⚠️ Lưu ý: Độ tin cậy thấp, hãy kiểm tra kỹ.</i>\n"

        if expiry:
            message += f"\n⏰ <b>Thời hạn:</b> <i>{escape_html(expiry)}</i>\n"

        if not dry_run:
            success = send_message(message)
            if success:
                mark_as_notified(record_id)
        else:
            logger.info(f"[DRY-RUN] Sẽ gửi tin nhắn: {sorted_codes}")

    logger.info(f"Bắt đầu lắng nghe tin nhắn từ: {TELETHON_CHANNELS}")
    await client.start()
    await client.run_until_disconnected()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Giveaway Bot - Telethon Listener")
    parser.add_argument("--dry-run", action="store_true", help="Không gửi Telegram, chỉ in log.")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.dry_run))
    except KeyboardInterrupt:
        logger.info("Đã dừng Listener.")
