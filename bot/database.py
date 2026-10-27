import sqlite3
import logging
from datetime import datetime, timezone
from bot.config import DB_PATH

logger = logging.getLogger(__name__)


def get_connection():
    """Tạo kết nối tới SQLite database (bật WAL và timeout=20s chống lỗi database is locked)."""
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=20000")
    except Exception:
        pass
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
        # v3: dữ liệu có cấu trúc (ảnh, giá gốc, hạn nhận chính xác, trạng thái)
        ("image_url", "TEXT DEFAULT ''"),
        ("worth", "TEXT DEFAULT ''"),
        ("worth_value", "REAL DEFAULT 0"),
        ("expires_at", "TEXT DEFAULT ''"),
        ("starts_at", "TEXT DEFAULT ''"),
        ("store", "TEXT DEFAULT ''"),
        ("store_url", "TEXT DEFAULT ''"),
        ("description", "TEXT DEFAULT ''"),
        ("app_id", "TEXT DEFAULT ''"),
        ("rating", "REAL DEFAULT 0"),
        ("status", "TEXT DEFAULT 'active'"),
        ("dedup_key", "TEXT DEFAULT ''"),
    ]
    for col_name, col_def in migrations:
        if col_name not in existing_cols:
            cursor.execute(f"ALTER TABLE giveaways ADD COLUMN {col_name} {col_def}")
            logger.info(f"Đã migrate thêm cột '{col_name}' vào bảng giveaways.")

    # Thêm các index tối ưu truy vấn
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_guid ON giveaways(guid)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_platform ON giveaways(platform)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_first_seen ON giveaways(first_seen_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_status ON giveaways(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_dedup ON giveaways(dedup_key)')
    conn.commit()
    conn.close()
    logger.debug("Khởi tạo SQLite Database hoàn tất.")


# Các cột v3 có thể ghi qua insert_giveaway / update_giveaway_fields
RECORD_COLUMNS = (
    "source", "canonical_url", "guid", "title", "published_at", "content_hash", "codes_hash",
    "codes", "platform", "tags", "expiry_hint", "confidence_score",
    "image_url", "worth", "worth_value", "expires_at", "starts_at", "store", "store_url",
    "description", "app_id", "rating", "status", "dedup_key",
)


def find_existing(canonical_url: str, guid: str = "", dedup_key: str = ""):
    """Tìm bản ghi đã tồn tại theo URL, GUID hoặc khóa chống trùng (cùng game/app từ nhiều nguồn)."""
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            "SELECT * FROM giveaways WHERE canonical_url = ? OR (guid = ? AND guid != '') "
            "OR (dedup_key = ? AND dedup_key != '') ORDER BY id LIMIT 1",
            (canonical_url, guid or "", dedup_key or ""),
        )
        row = c.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def insert_giveaway(record: dict) -> int:
    """Chèn bản ghi mới (chỉ lấy các cột hợp lệ). Trả về id."""
    now = datetime.now(timezone.utc).isoformat()
    cols = [k for k in RECORD_COLUMNS if k in record and record[k] is not None]
    values = [record[k] for k in cols]
    cols += ["first_seen_at", "last_seen_at"]
    values += [now, now]
    placeholders = ", ".join("?" for _ in cols)
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(f"INSERT INTO giveaways ({', '.join(cols)}) VALUES ({placeholders})", values)
        conn.commit()
        return c.lastrowid
    finally:
        conn.close()


def update_giveaway_fields(record_id: int, fields: dict):
    """Cập nhật một số cột (bỏ qua cột không hợp lệ) và làm mới last_seen_at."""
    now = datetime.now(timezone.utc).isoformat()
    safe = {k: v for k, v in (fields or {}).items() if k in RECORD_COLUMNS and v is not None}
    safe["last_seen_at"] = now
    sets = ", ".join(f"{k} = ?" for k in safe)
    conn = get_connection()
    try:
        conn.execute(f"UPDATE giveaways SET {sets} WHERE id = ?", list(safe.values()) + [record_id])
        conn.commit()
    finally:
        conn.close()


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

    record_id = row['id']
    old_codes_hash = row['codes_hash']
    was_notified = row['notified_at'] is not None

    if old_codes_hash != codes_hash:
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
        cursor.execute('''
            UPDATE giveaways
            SET last_seen_at = ?, platform = ?, tags = ?, expiry_hint = ?, confidence_score = ?
            WHERE id = ?
        ''', (now, platform, tags, expiry_hint, confidence_score, record_id))
        conn.commit()
        conn.close()
        return {'action': 'resend', 'id': record_id}
    else:
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
