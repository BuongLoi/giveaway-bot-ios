"""
Daily Reset — Chạy mỗi ngày lúc 00:00 bởi cron.
- Xóa toàn bộ dữ liệu cũ trong bảng giveaways
- Giữ lại cấu trúc bảng (không DROP)
- Ghi log số bài đã xóa
"""
import sqlite3
import logging
import os
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "giveaways.db"))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("daily_reset")

def reset():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Đếm số bài trước khi xóa
    c.execute("SELECT COUNT(*) FROM giveaways")
    total = c.fetchone()[0]

    # Xóa tất cả dữ liệu
    c.execute("DELETE FROM giveaways")
    conn.commit()

    # Thu gọn database (giải phóng dung lượng)
    c.execute("VACUUM")
    conn.commit()
    conn.close()

    logger.info(f"Daily reset: da xoa {total} bai. DB sach, san sang cho ngay moi.")

if __name__ == "__main__":
    reset()
