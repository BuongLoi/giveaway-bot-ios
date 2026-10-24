"""
Daily Maintenance — Chạy mỗi ngày lúc 00:00 bởi cron.
- Chỉ xóa các bài viết quá cũ (> 30 ngày) và các bài rác (confidence_score = 0 và không có code)
- Giữ lại các bài trong 30 ngày gần nhất để:
  1) App iOS / Web luôn có danh sách kèo phong phú, không bị trắng trang lúc 00:00
  2) Chống trùng lặp (không gửi lại các bài RSS cũ lên Telegram vào lúc 00:30)
"""
import sqlite3
import logging
import os

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "giveaways.db"))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("daily_reset")


def reset():
    if not os.path.exists(DB_PATH):
        return

    conn = sqlite3.connect(DB_PATH, timeout=20)
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM giveaways")
    total_before = c.fetchone()[0]

    # Xóa bài quá 30 ngày hoặc bài rác có độ tin cậy bằng 0 và không có code
    c.execute("""
        DELETE FROM giveaways
        WHERE first_seen_at < datetime('now', '-30 days')
           OR (confidence_score < 40 AND (codes IS NULL OR codes = ''))
    """)
    deleted = c.rowcount
    conn.commit()

    c.execute("VACUUM")
    conn.commit()

    c.execute("SELECT COUNT(*) FROM giveaways")
    total_after = c.fetchone()[0]
    conn.close()

    logger.info(f"Daily maintenance: da don {deleted} bai cu/rac (Con lai {total_after}/{total_before} bai hop le).")


if __name__ == "__main__":
    reset()
