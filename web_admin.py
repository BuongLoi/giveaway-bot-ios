import os
import time
import subprocess
import sqlite3
import logging
from datetime import datetime, timezone
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response
from flask_basicauth import BasicAuth
from dotenv import set_key, load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

# Load .env để lấy ADMIN_USERNAME và ADMIN_PASSWORD
load_dotenv()

from bot.config import DB_PATH, SOURCE_ENV_KEYS
from bot.database import init_db
from bot.utils import get_python_executable
from bot.extractor import get_platform_badge

app = Flask(__name__)
app.secret_key = os.getenv("TELEGRAM_BOT_TOKEN") or "giveaway-bot-secret-key"

app.config['BASIC_AUTH_USERNAME'] = os.getenv('ADMIN_USERNAME', 'admin')
app.config['BASIC_AUTH_PASSWORD'] = os.getenv('ADMIN_PASSWORD', 'changeme123')
app.config['BASIC_AUTH_FORCE'] = False


class SecureBasicAuth(BasicAuth):
    """Mở rộng BasicAuth: hỗ trợ cả plaintext và hashed password (werkzeug)."""
    def check_credentials(self, username, password):
        correct_username = self.app.config['BASIC_AUTH_USERNAME']
        stored_password = self.app.config['BASIC_AUTH_PASSWORD']

        if username != correct_username:
            return False

        if stored_password.startswith(('pbkdf2:', 'scrypt:')):
            return check_password_hash(stored_password, password)

        return password == stored_password


basic_auth = SecureBasicAuth(app)

PUBLIC_PATHS = {'/', '/giveaways', '/api/giveaways', '/health', '/manifest.json', '/sw.js', '/robots.txt',
                '/api/v2/giveaways', '/api/v2/stats'}
_last_scan_ts = 0.0


@app.before_request
def require_basic_auth():
    if request.method in ('GET', 'HEAD') and (
            request.path in PUBLIC_PATHS or request.path.startswith('/static/')
            or request.path.startswith('/api/v2/')):
        return None
    if request.method == 'POST' and request.path == '/action/scan':
        return None
    if not basic_auth.authenticate():
        return basic_auth.challenge()


@app.context_processor
def utility_processor():
    return dict(get_platform_badge=get_platform_badge)


ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cron.log")

logger = logging.getLogger(__name__)

try:
    init_db()
except Exception as e:
    logger.warning(f"Không thể khởi tạo DB lúc khởi động Web: {e}")


# ─── Database Helpers ────────────────────────────────────────────────

def get_db():
    """Tạo kết nối SQLite tái sử dụng."""
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn


def get_db_stats():
    """Lấy thống kê tổng hợp cho Dashboard (chỉ tính các bài hợp lệ)."""
    stats = {
        "total": 0,
        "notified": 0,
        "with_codes": 0,
        "ios_count": 0,
        "windows_count": 0,
        "sources": [],
        "platforms": {},
        "recent": []
    }
    if not os.path.exists(DB_PATH):
        return stats
    try:
        init_db()
        conn = get_db()
        c = conn.cursor()

        valid_filter = "WHERE (confidence_score > 0 OR (codes != '' AND codes IS NOT NULL))"

        c.execute(f"SELECT COUNT(*) FROM giveaways {valid_filter}")
        stats["total"] = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM giveaways WHERE notified_at IS NOT NULL")
        stats["notified"] = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM giveaways WHERE (codes != '' AND codes IS NOT NULL) OR (codes_hash != '' AND codes_hash IS NOT NULL)")
        stats["with_codes"] = c.fetchone()[0]

        c.execute(f"SELECT COUNT(*) FROM giveaways {valid_filter} AND platform = 'ios'")
        stats["ios_count"] = c.fetchone()[0]

        c.execute(f"SELECT COUNT(*) FROM giveaways {valid_filter} AND platform = 'windows'")
        stats["windows_count"] = c.fetchone()[0]

        c.execute(f"SELECT platform, COUNT(*) FROM giveaways {valid_filter} GROUP BY platform")
        stats["platforms"] = {row[0] or "other": row[1] for row in c.fetchall()}

        c.execute(f"SELECT source, COUNT(*) FROM giveaways {valid_filter} GROUP BY source ORDER BY COUNT(*) DESC LIMIT 8")
        stats["sources"] = c.fetchall()

        c.execute(f"""
            SELECT id, source, title, canonical_url, confidence_score,
                   codes, codes_hash, platform, tags, expiry_hint, first_seen_at
            FROM giveaways
            {valid_filter}
            ORDER BY first_seen_at DESC LIMIT 12
        """)
        stats["recent"] = [dict(row) for row in c.fetchall()]

        conn.close()
    except Exception as e:
        logger.error(f"DB Error: {e}")
    return stats


def query_giveaways(search: str = "", platform: str = "", page: int = 1, per_page: int = 20):
    """Truy vấn danh sách giveaways có bộ lọc nền tảng + từ khóa + phân trang."""
    items = []
    total = 0
    offset = (max(1, page) - 1) * per_page

    if not os.path.exists(DB_PATH):
        return items, total

    try:
        init_db()
        conn = get_db()
        c = conn.cursor()

        conditions = ["(confidence_score > 0 OR (codes != '' AND codes IS NOT NULL))",
                      "COALESCE(status, 'active') != 'expired'"]
        params = []

        if search:
            like = f"%{search}%"
            conditions.append("(title LIKE ? OR source LIKE ? OR codes LIKE ? OR tags LIKE ?)")
            params.extend([like, like, like, like])

        if platform == "has_code":
            conditions.append("((codes != '' AND codes IS NOT NULL) OR (codes_hash != '' AND codes_hash IS NOT NULL))")
        elif platform in ("ios", "windows", "macos", "android", "game", "other"):
            conditions.append("platform = ?")
            params.append(platform)

        where_clause = f"WHERE {' AND '.join(conditions)}"

        c.execute(f"SELECT COUNT(*) FROM giveaways {where_clause}", params)
        total = c.fetchone()[0]

        c.execute(f"""
            SELECT id, source, title, canonical_url, confidence_score,
                   codes, codes_hash, platform, tags, expiry_hint, first_seen_at, notified_at
            FROM giveaways
            {where_clause}
            ORDER BY first_seen_at DESC
            LIMIT ? OFFSET ?
        """, params + [per_page, offset])

        items = [dict(row) for row in c.fetchall()]
        conn.close()
    except Exception as e:
        logger.error(f"DB Query Error: {e}")

    return items, total


# ─── Routes ──────────────────────────────────────────────────────────

@app.route('/')
def index():
    stats = get_db_stats()
    return render_template('index.html', stats=stats)


@app.route('/giveaways')
def giveaways():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('q', '').strip()
    platform = request.args.get('platform', '').strip().lower()
    per_page = 20

    items, total = query_giveaways(search=search, platform=platform, page=page, per_page=per_page)
    total_pages = max(1, (total + per_page - 1) // per_page)

    return render_template(
        'giveaways.html',
        items=items,
        page=page,
        total_pages=total_pages,
        total=total,
        search=search,
        platform=platform
    )


@app.route('/api/giveaways')
def api_giveaways():
    page = request.args.get('page', 1, type=int)
    per_page = min(100, max(1, request.args.get('per_page', 25, type=int)))
    search = request.args.get('q', '').strip()
    platform = request.args.get('platform', '').strip().lower()

    items, total = query_giveaways(search=search, platform=platform, page=page, per_page=per_page)
    for item in items:
        item["platform_badge"] = get_platform_badge(item.get("platform", "other"))
        item["code_list"] = [c.strip() for c in (item.get("codes") or "").split(",") if c.strip()]

    return jsonify({
        "status": "ok",
        "page": page,
        "per_page": per_page,
        "total": total,
        "platform": platform or "all",
        "items": items
    })


# ─── API v2 (App iOS native) ─────────────────────────────────────────

V2_COLUMNS = ("id, source, title, canonical_url, store_url, platform, image_url, worth, worth_value, "
              "expires_at, starts_at, status, codes, tags, description, rating, store, app_id, "
              "confidence_score, first_seen_at")
V2_PLATFORMS = ("ios", "windows", "macos", "android", "game", "other")
V2_VALID = "(confidence_score > 0 OR (codes != '' AND codes IS NOT NULL))"


def _serialize_v2(row: dict) -> dict:
    claim_url = row.get("store_url") or row.get("canonical_url") or ""
    return {
        "id": row["id"],
        "title": row.get("title") or "",
        "source": row.get("source") or "",
        "url": row.get("canonical_url") or "",
        "claim_url": claim_url,
        "platform": row.get("platform") or "other",
        "platform_badge": get_platform_badge(row.get("platform") or "other"),
        "image_url": row.get("image_url") or "",
        "worth": row.get("worth") or "",
        "worth_value": float(row.get("worth_value") or 0),
        "expires_at": row.get("expires_at") or None,
        "starts_at": row.get("starts_at") or None,
        "status": row.get("status") or "active",
        "codes": [c.strip() for c in (row.get("codes") or "").split(",") if c.strip()],
        "tags": [t.strip() for t in (row.get("tags") or "").split(",") if t.strip()],
        "description": (row.get("description") or "")[:800],
        "rating": float(row.get("rating") or 0),
        "store": row.get("store") or "",
        "app_id": row.get("app_id") or "",
        "confidence": int(row.get("confidence_score") or 0),
        "first_seen_at": row.get("first_seen_at") or "",
    }


def query_v2(params) -> tuple:
    page = max(1, params.get('page', 1, type=int))
    per_page = min(100, max(1, params.get('per_page', 30, type=int)))
    platform = (params.get('platform') or '').strip().lower()
    status = (params.get('status') or 'active').strip().lower()
    sort = (params.get('sort') or 'new').strip().lower()
    search = (params.get('q') or '').strip()
    since = (params.get('since') or '').strip()
    ids = [i for i in (params.get('ids') or '').split(',') if i.strip().isdigit()][:200]

    conditions, args = [V2_VALID], []
    if ids:
        conditions.append(f"id IN ({','.join('?' for _ in ids)})")
        args.extend(int(i) for i in ids)
    else:
        if status in ('active', 'upcoming', 'expired'):
            conditions.append("COALESCE(status, 'active') = ?")
            args.append(status)
        elif status == 'ending':
            conditions.append("COALESCE(status, 'active') = 'active' AND expires_at != '' AND expires_at IS NOT NULL "
                              "AND expires_at <= ?")
            args.append(datetime.fromtimestamp(time.time() + 48 * 3600, tz=timezone.utc).replace(microsecond=0).isoformat())
        if platform in V2_PLATFORMS:
            conditions.append("platform = ?")
            args.append(platform)
        elif platform == 'has_code':
            conditions.append("codes != '' AND codes IS NOT NULL")
        if search:
            like = f"%{search}%"
            conditions.append("(title LIKE ? OR description LIKE ? OR source LIKE ? OR store LIKE ?)")
            args.extend([like] * 4)
        if since:
            conditions.append("first_seen_at > ?")
            args.append(since)

    order = {
        'ending': "CASE WHEN expires_at = '' OR expires_at IS NULL THEN 1 ELSE 0 END, expires_at ASC",
        'worth': "worth_value DESC, first_seen_at DESC",
    }.get(sort, "first_seen_at DESC")

    where = " AND ".join(conditions)
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute(f"SELECT COUNT(*) FROM giveaways WHERE {where}", args)
        total = c.fetchone()[0]
        c.execute(f"SELECT {V2_COLUMNS} FROM giveaways WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?",
                  args + [per_page, (page - 1) * per_page])
        items = [_serialize_v2(dict(r)) for r in c.fetchall()]
    finally:
        conn.close()
    return items, total, page, per_page


@app.route('/api/v2/giveaways')
def api_v2_giveaways():
    try:
        init_db()
        items, total, page, per_page = query_v2(request.args)
    except Exception as e:
        logger.error(f"API v2 error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    return jsonify({
        "status": "ok", "page": page, "per_page": per_page, "total": total,
        "has_more": page * per_page < total, "items": items,
        "server_time": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    })


@app.route('/api/v2/giveaways/<int:item_id>')
def api_v2_giveaway_detail(item_id: int):
    conn = get_db()
    try:
        row = conn.execute(f"SELECT {V2_COLUMNS} FROM giveaways WHERE id = ?", (item_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return jsonify({"status": "error", "message": "not found"}), 404
    return jsonify({"status": "ok", "item": _serialize_v2(dict(row))})


@app.route('/api/v2/stats')
def api_v2_stats():
    result = {"status": "ok", "platforms": {}, "active_total": 0, "total_worth": 0.0,
              "ending_soon": 0, "upcoming": 0, "last_scan_at": None}
    try:
        init_db()
        conn = get_db()
        c = conn.cursor()
        active = f"{V2_VALID} AND COALESCE(status, 'active') = 'active'"
        c.execute(f"SELECT platform, COUNT(*), COALESCE(SUM(worth_value), 0) FROM giveaways WHERE {active} GROUP BY platform")
        for platform, count, worth in c.fetchall():
            result["platforms"][platform or "other"] = count
            result["active_total"] += count
            result["total_worth"] += float(worth or 0)
        result["total_worth"] = round(result["total_worth"], 2)
        soon = datetime.fromtimestamp(time.time() + 48 * 3600, tz=timezone.utc).replace(microsecond=0).isoformat()
        c.execute(f"SELECT COUNT(*) FROM giveaways WHERE {active} AND expires_at != '' AND expires_at <= ?", (soon,))
        result["ending_soon"] = c.fetchone()[0]
        c.execute(f"SELECT COUNT(*) FROM giveaways WHERE {V2_VALID} AND status = 'upcoming'")
        result["upcoming"] = c.fetchone()[0]
        c.execute("SELECT MAX(last_seen_at) FROM giveaways")
        result["last_scan_at"] = c.fetchone()[0]
        conn.close()
    except Exception as e:
        logger.error(f"API v2 stats error: {e}")
        result["status"] = "error"
    return jsonify(result)


@app.route('/config', methods=['GET', 'POST'])
def config():
    if request.method == 'POST':
        text_fields = [
            'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'KEYWORDS', 'NEGATIVE_KEYWORDS',
            'MIN_CONFIDENCE_SCORE', 'ENABLE_FALLBACK_SCRAPER',
            'REDDIT_CLIENT_ID', 'REDDIT_CLIENT_SECRET',
            'ENABLE_TELETHON_LISTENER', 'TELEGRAM_API_ID', 'TELEGRAM_API_HASH',
            'TELETHON_CHANNELS', 'ADMIN_USERNAME', 'ADMIN_PASSWORD',
        ]
        for field in text_fields:
            val = request.form.get(field)
            if val is not None:
                val = val.strip()
                if field == 'ADMIN_PASSWORD':
                    if not val:
                        continue
                    if not val.startswith(('pbkdf2:', 'scrypt:')):
                        val = generate_password_hash(val)
                set_key(ENV_PATH, field, val)

        for source_key in SOURCE_ENV_KEYS:
            values = request.form.getlist(source_key)
            if values:
                is_checked = '1' in values
                set_key(ENV_PATH, source_key, '1' if is_checked else '0')

        load_dotenv(ENV_PATH, override=True)
        if request.form.get('ADMIN_USERNAME', '').strip():
            app.config['BASIC_AUTH_USERNAME'] = request.form.get('ADMIN_USERNAME').strip()
        if request.form.get('ADMIN_PASSWORD', '').strip():
            app.config['BASIC_AUTH_PASSWORD'] = os.getenv('ADMIN_PASSWORD', app.config['BASIC_AUTH_PASSWORD'])
        flash("Cấu hình đã được lưu thành công!", "success")
        return redirect(url_for('config'))

    current_env = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    current_env[k.strip()] = v.strip().strip("'\"")

    return render_template('config.html', env=current_env)


@app.route('/logs')
def logs():
    log_content = "Không tìm thấy file cron.log — Bot chưa chạy lần nào hoặc chưa cấu hình cron job."
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()[-200:]
            log_content = "".join(lines)
    return render_template('logs.html', log_content=log_content)


@app.route('/action/scan', methods=['POST'])
def action_scan():
    """Kích hoạt quét nền có giới hạn tần suất (cooldown 45s) để dùng mượt từ App iOS."""
    global _last_scan_ts
    now = time.time()
    wants_json = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '')

    if now - _last_scan_ts < 45:
        wait_sec = int(45 - (now - _last_scan_ts))
        msg = f"Hệ thống đang quét rồi, vui lòng đợi {wait_sec}s nữa."
        if wants_json:
            return jsonify({"status": "cooldown", "message": msg})
        flash(msg, "success")
        return redirect(request.referrer or url_for('giveaways'))

    try:
        _last_scan_ts = now
        python_exec = get_python_executable()
        base_dir = os.path.dirname(os.path.abspath(__file__))
        main_py = os.path.join(base_dir, "main.py")
        with open(LOG_PATH, "a", encoding="utf-8") as log_file:
            subprocess.Popen(
                [python_exec, main_py, "--once"],
                cwd=base_dir,
                stdout=log_file,
                stderr=log_file
            )
        msg = "⚡ Đã kích hoạt quét nguồn mới! Kéo xuống để làm mới sau vài giây."
        if wants_json:
            return jsonify({"status": "ok", "message": msg})
        flash(msg, "success")
    except Exception as e:
        err_msg = f"Lỗi khi kích hoạt quét: {e}"
        if wants_json:
            return jsonify({"status": "error", "message": err_msg}), 500
        flash(err_msg, "danger")
    return redirect(request.referrer or url_for('giveaways'))


@app.route('/robots.txt')
def robots_txt():
    return Response("User-agent: *\nDisallow: /config\nDisallow: /logs\n", mimetype='text/plain')


@app.route('/manifest.json')
def manifest():
    return jsonify({
        "name": "Giveaway Hunter — iOS & PC",
        "short_name": "GiveawayBot",
        "description": "Săn phần mềm bản quyền Windows, macOS & ứng dụng iOS miễn phí hàng ngày.",
        "start_url": "/giveaways",
        "display": "standalone",
        "background_color": "#0f172a",
        "theme_color": "#0f172a",
        "orientation": "portrait-primary",
        "icons": [
            {
                "src": "/static/app-icon.svg",
                "sizes": "512x512",
                "type": "image/svg+xml",
                "purpose": "any maskable"
            }
        ]
    })


@app.route('/sw.js')
def service_worker():
    sw_code = """
self.addEventListener('install', (e) => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', (e) => {});
"""
    return Response(sw_code.strip(), mimetype='application/javascript')


@app.route('/health')
def health():
    db_ok = os.path.exists(DB_PATH)
    stats = get_db_stats() if db_ok else {}
    return jsonify({
        "status": "ok",
        "db_exists": db_ok,
        "total_giveaways": stats.get("total", 0),
        "ios_giveaways": stats.get("ios_count", 0),
        "windows_giveaways": stats.get("windows_count", 0),
        "timestamp": datetime.now(timezone.utc).isoformat()
    })


if __name__ == '__main__':
    port = int(os.getenv("WEB_PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
