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

PUBLIC_PATHS = {'/', '/giveaways', '/api/giveaways', '/health', '/manifest.json', '/sw.js', '/robots.txt'}
_last_scan_ts = 0.0


@app.before_request
def require_basic_auth():
    if request.method in ('GET', 'HEAD') and (request.path in PUBLIC_PATHS or request.path.startswith('/static/')):
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

        conditions = ["(confidence_score > 0 OR (codes != '' AND codes IS NOT NULL))"]
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
