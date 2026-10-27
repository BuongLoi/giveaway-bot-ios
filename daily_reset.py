"""
Daily Maintenance — Chạy mỗi ngày lúc 00:00 bởi cron (giữ lại để tương thích crontab cũ).
Từ v3, toàn bộ logic nằm trong maintenance.py:
- Đánh dấu bài hết hạn (theo expires_at, giá App Store, tuổi bài viết)
- Chỉ xóa bài đã hết hạn > 30 ngày và bài rác (confidence < 40, không có code)
- KHÔNG xóa trắng DB, để App iOS / Web luôn có dữ liệu và không gửi lại bài cũ.
"""
import logging

from maintenance import run

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


def reset():
    run(full_cleanup=True)


if __name__ == "__main__":
    reset()
