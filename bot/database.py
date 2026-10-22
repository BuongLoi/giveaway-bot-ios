import sqlite3
import logging
from datetime import datetime, timezone
from bot.config import DB_PATH

logger = logging.getLogger(__name__)


def get_connection():
    """Tạo kết nối tới SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Khởi tạo bảng cơ sở dữ liệu và tự động migrate cột mới nếu chưa tồn tại."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS giveaways (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            canonical_url TEXT NOT NULL,
            guid TEXT,
            title TEXT,
            published_at TEXT,
            content_hash TEXT,
            codes_hash TEXT,
            codes TEXT DEFAULT '',
            platform TEXT DEFAULT 'other',
            tags TEXT DEFAULT '',
            expiry_hint TEXT DEFAULT '',
            confidence_score INTEGER DEFAULT 0,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            notified_at TEXT,
            UNIQUE(canonical_url)
        )
    ''')

    # Auto-migration an toàn cho DB cũ chưa có các cột mới
    cursor.execute("PRAGMA table_info(giveaways)")
    existing_cols = {row["name"] for row in cursor.fetchall()}
    migrations = [
        ("codes", "TEXT DEFAULT ''"),
        ("platform", "TEXT DEFAULT 'other'"),
        ("tags", "TEXT DEFAULT ''"),
        ("expiry_hint", "TEXT DEFAULT ''"),
    ]
    for col_name, col_def in migrations:
        if col_name not in existing_cols:
            cursor.execute(f"ALTER TABLE giveaways ADD COLUMN {col_name} {col_def}")
            logger.info(f"Đã migrate thêm cột '{col_name}' vào bảng giveaways.")

    # Thêm các index tối ưu truy vấn
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_guid ON giveaways(guid)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_platform ON giveaways(platform)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_first_seen ON giveaways(first_seen_at DESC)')
    conn.commit()
    conn.close()
    logger.debug("Khởi tạo SQLite Database hoàn tất.")


def check_and_save_giveaway(
    source: str,
    canonical_url: str,
    guid: str,
    title: str,
    published_at: str,
    content_hash: str,
    codes_hash: str,
    confidence_score: int,
    codes: str = "",
    platform: str = "other",
    tags: str = "",
    expiry_hint: str = ""
) -> dict:
    """
    Kiểm tra xem bài đăng đã tồn tại và có thay đổi gì không.
    Trả về một dict mô tả hành động cần làm:
    - action: 'new' (mới), 'update' (có cập nhật code), 'resend' (chưa gửi TG), 'skip' (đã có, không đổi).
    - id: ID của bản ghi.
    """
    conn = get_connection()
    cursor = conn.cursor()

    now = datetime.now(timezone.utc).isoformat()

    # Tìm kiếm theo canonical_url hoặc guid
    cursor.execute('SELECT * FROM giveaways WHERE canonical_url = ? OR guid = ?', (canonical_url, guid))
    row = cursor.fetchone()

    if not row:
        # Bản ghi mới
        cursor.execute('''
            INSERT INTO giveaways 
            (source, canonical_url, guid, title, published_at, content_hash, codes_hash,
             codes, platform, tags, expiry_hint, confidence_score, first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            source, canonical_url, guid, title, str(published_at or ""),
            content_hash, codes_hash, codes, platform, tags, expiry_hint,
            confidence_score, now, now
        ))
        conn.commit()
        record_id = cursor.lastrowid
        conn.close()
        return {'action': 'new', 'id': record_id}

    # Nếu bản ghi đã tồn tại, kiểm tra sự thay đổi codes_hash
    record_id = row['id']
    old_codes_hash = row['codes_hash']
    was_notified = row['notified_at'] is not None

    if old_codes_hash != codes_hash:
        # Có sự thay đổi về code
        cursor.execute('''
            UPDATE giveaways 
            SET title = ?, codes_hash = ?, codes = ?, content_hash = ?,
                platform = ?, tags = ?, expiry_hint = ?, confidence_score = ?, last_seen_at = ?
            WHERE id = ?
        ''', (title, codes_hash, codes, content_hash, platform, tags, expiry_hint, confidence_score, now, record_id))
        conn.commit()
        conn.close()
        return {'action': 'update', 'id': record_id}
    elif not was_notified:
        # Bài đã lưu DB nhưng chưa từng gửi Telegram (ví dụ: từ dry-run hoặc lỗi gửi)
        cursor.execute('''
            UPDATE giveaways
            SET last_seen_at = ?, platform = ?, tags = ?, expiry_hint = ?, confidence_score = ?
            WHERE id = ?
        ''', (now, platform, tags, expiry_hint, confidence_score, record_id))
        conn.commit()
        conn.close()
        return {'action': 'resend', 'id': record_id}
    else:
        # Đã gửi rồi và không có thay đổi -> bỏ qua
        cursor.execute('UPDATE giveaways SET last_seen_at = ? WHERE id = ?', (now, record_id))
        conn.commit()
        conn.close()
        return {'action': 'skip', 'id': record_id}


def mark_as_notified(record_id: int):
    """Đánh dấu bản ghi đã được thông báo lên Telegram."""
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    cursor.execute('UPDATE giveaways SET notified_at = ? WHERE id = ?', (now, record_id))
    conn.commit()
    conn.close()
