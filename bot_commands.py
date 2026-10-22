"""
Telegram Bot Commands — Điều khiển bot trực tiếp từ Telegram.

Hỗ trợ lệnh:
  /status  — Xem trạng thái hệ thống
  /stats   — Xem thống kê thu thập
  /scan    — Kích hoạt quét ngay (chạy nền)
  /help    — Hiển thị danh sách lệnh

Chạy: python bot_commands.py
"""
import os
import sys
import subprocess
import sqlite3
import logging
import requests
import time
from datetime import datetime
from dotenv import load_dotenv
from bot.utils import get_python_executable

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("bot_commands")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DB_PATH = os.getenv("DB_PATH", "giveaways.db")

# Chỉ cho phép CHAT_ID đã cấu hình gửi lệnh (bảo mật)
ALLOWED_CHAT_IDS = {CHAT_ID}


def send_reply(chat_id: str, text: str):
    """Gửi tin nhắn phản hồi về Telegram."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }, timeout=15)


def get_db_stats() -> dict:
    """Lấy thống kê từ SQLite database."""
    stats = {"total": 0, "notified": 0, "ios": 0, "windows": 0, "sources": {}}
    if not os.path.exists(DB_PATH):
        return stats
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM giveaways")
        stats["total"] = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM giveaways WHERE notified_at IS NOT NULL")
        stats["notified"] = c.fetchone()[0]
        try:
            c.execute("SELECT COUNT(*) FROM giveaways WHERE platform = 'ios'")
            stats["ios"] = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM giveaways WHERE platform = 'windows'")
            stats["windows"] = c.fetchone()[0]
        except sqlite3.OperationalError:
            pass
        c.execute("SELECT source, COUNT(*) FROM giveaways GROUP BY source ORDER BY COUNT(*) DESC LIMIT 10")
        stats["sources"] = {row[0]: row[1] for row in c.fetchall()}
        conn.close()
    except Exception as e:
        logger.error(f"DB Error: {e}")
    return stats


def handle_command(chat_id: str, command: str):
    """Xử lý lệnh từ người dùng."""
    cmd = command.strip().lower().split()[0] if command.strip() else ""

    if cmd == "/help" or cmd == "/start":
        send_reply(chat_id, (
            "🤖 <b>Giveaway Bot — Lệnh điều khiển</b>\n\n"
            "/status — Xem trạng thái hệ thống\n"
            "/stats — Xem thống kê thu thập\n"
            "/scan — Kích hoạt quét ngay\n"
            "/help — Hiển thị trợ giúp"
        ))

    elif cmd == "/status":
        uptime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db_exists = "✅" if os.path.exists(DB_PATH) else "❌"
        stats = get_db_stats()
        send_reply(chat_id, (
            f"📡 <b>Trạng thái hệ thống</b>\n\n"
            f"🕐 Thời gian: {uptime}\n"
            f"💾 Database: {db_exists} ({stats['total']} bài)\n"
            f"🍎 iOS: {stats['ios']} | 🪟 Windows: {stats['windows']}\n"
            f"📨 Đã gửi TG: {stats['notified']}\n"
            f"🌐 Nguồn: {len(stats['sources'])} nguồn đang hoạt động"
        ))

    elif cmd == "/stats":
        stats = get_db_stats()
        if not stats["sources"]:
            send_reply(chat_id, "📊 Chưa có dữ liệu nào trong database.")
            return

        lines = ["📊 <b>Thống kê thu thập</b>\n"]
        lines.append(f"📦 Tổng: <b>{stats['total']}</b> bài (🍎 iOS: {stats['ios']} | 🪟 Win: {stats['windows']})")
        lines.append(f"📨 Đã gửi: <b>{stats['notified']}</b>\n")
        lines.append("🏆 <b>Top nguồn:</b>")
        for source, count in stats["sources"].items():
            lines.append(f"  • {source}: {count}")

        send_reply(chat_id, "\n".join(lines))

    elif cmd == "/scan":
        send_reply(chat_id, "⚡ Đang kích hoạt quét... Kết quả sẽ gửi về đây trong vài phút.")
        try:
            python_exec = get_python_executable()
            main_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
            subprocess.Popen(
                [python_exec, main_py, "--once"],
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
        except Exception as e:
            send_reply(chat_id, f"❌ Lỗi khi kích hoạt quét: {e}")

    else:
        send_reply(chat_id, "❓ Lệnh không hợp lệ. Gõ /help để xem danh sách lệnh.")


def poll_updates():
    """
    Long-polling: lắng nghe tin nhắn gửi đến bot.
    Chỉ xử lý tin nhắn từ CHAT_ID đã cấu hình.
    """
    if not BOT_TOKEN:
        logger.error("Chưa cấu hình TELEGRAM_BOT_TOKEN. Thoát.")
        sys.exit(1)

    logger.info("Bot Commands đang lắng nghe lệnh...")
    offset = 0

    while True:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
            resp = requests.get(url, params={
                "offset": offset,
                "timeout": 30,
                "allowed_updates": '["message"]'
            }, timeout=35)

            data = resp.json()
            if not data.get("ok"):
                logger.error(f"API Error: {data}")
                time.sleep(5)
                continue

            for update in data.get("result", []):
                offset = update["update_id"] + 1
                message = update.get("message", {})
                text = message.get("text", "")
                chat_id = str(message.get("chat", {}).get("id", ""))

                if not text.startswith("/"):
                    continue

                if chat_id not in ALLOWED_CHAT_IDS:
                    logger.warning(f"Từ chối lệnh từ chat_id không được phép: {chat_id}")
                    send_reply(chat_id, "🚫 Bạn không có quyền sử dụng bot này.")
                    continue

                logger.info(f"Nhận lệnh: {text} từ chat_id={chat_id}")
                handle_command(chat_id, text)

        except requests.exceptions.ReadTimeout:
            continue
        except Exception as e:
            logger.error(f"Lỗi polling: {e}")
            time.sleep(5)


if __name__ == '__main__':
    poll_updates()
