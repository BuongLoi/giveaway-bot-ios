"""
Bảo trì định kỳ (v3) — chạy mỗi giờ bởi cron:
1. Bài 'upcoming' đã tới giờ bắt đầu  -> 'active'.
2. Bài có expires_at đã qua           -> 'expired'.
3. Xác minh lại giá app iOS/macOS qua iTunes Lookup: nếu giá > 0 -> 'expired'.
4. Bài RSS không có hạn rõ ràng: iOS không có App ID > 3 ngày, còn lại > 7 ngày -> 'expired'.
5. Xóa bài hết hạn > 30 ngày, bài rác (confidence < 40, không có code).
"""
import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.database import get_connection, init_db  # noqa: E402
from bot.enrich import itunes_lookup  # noqa: E402

logger = logging.getLogger("maintenance")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def run(full_cleanup: bool = False) -> dict:
    init_db()
    now = datetime.now(timezone.utc)
    now_iso = _iso(now)
    stats = {"activated": 0, "expired_by_date": 0, "expired_by_price": 0, "expired_by_age": 0, "deleted": 0}

    conn = get_connection()
    c = conn.cursor()

    c.execute("UPDATE giveaways SET status='active' WHERE status='upcoming' AND starts_at != '' AND starts_at <= ?",
              (now_iso,))
    stats["activated"] = c.rowcount

    c.execute("UPDATE giveaways SET status='expired' WHERE status IN ('active','upcoming') "
              "AND expires_at != '' AND expires_at IS NOT NULL AND expires_at < ?", (now_iso,))
    stats["expired_by_date"] = c.rowcount
    conn.commit()

    # Xác minh lại giá App Store
    c.execute("SELECT id, app_id FROM giveaways WHERE status='active' AND app_id != '' AND app_id IS NOT NULL "
              "AND first_seen_at >= ?", (_iso(now - timedelta(days=21)),))
    rows = c.fetchall()
    if rows:
        info = itunes_lookup([r["app_id"] for r in rows])
        for r in rows:
            app = info.get(str(r["app_id"]))
            price = (app or {}).get("price")
            if isinstance(price, (int, float)) and price > 0:
                c.execute("UPDATE giveaways SET status='expired' WHERE id=?", (r["id"],))
                stats["expired_by_price"] += 1
        conn.commit()

    # Bài không có hạn rõ ràng: hết hạn theo tuổi
    c.execute("UPDATE giveaways SET status='expired' WHERE status='active' AND (expires_at = '' OR expires_at IS NULL) "
              "AND platform IN ('ios','macos') AND (app_id = '' OR app_id IS NULL) AND first_seen_at < ?",
              (_iso(now - timedelta(days=3)),))
    stats["expired_by_age"] += c.rowcount
    c.execute("UPDATE giveaways SET status='expired' WHERE status='active' AND (expires_at = '' OR expires_at IS NULL) "
              "AND first_seen_at < ?", (_iso(now - timedelta(days=7)),))
    stats["expired_by_age"] += c.rowcount
    conn.commit()

    # Dọn dẹp
    c.execute("""
        DELETE FROM giveaways
        WHERE (status = 'expired' AND first_seen_at < ?)
           OR (confidence_score < 40 AND (codes IS NULL OR codes = ''))
    """, (_iso(now - timedelta(days=30)),))
    stats["deleted"] = c.rowcount
    conn.commit()

    if full_cleanup:
        c.execute("VACUUM")
    conn.close()

    logger.info(f"Maintenance: {stats}")
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="Chạy thêm VACUUM (dùng cho lịch hằng ngày).")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    run(full_cleanup=args.full)
