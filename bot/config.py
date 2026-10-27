import os
from dotenv import load_dotenv

# Tải biến môi trường từ file .env (nếu có)
load_dotenv()

# Cấu hình Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


# Cấu hình Sources (mặc định bật)
def is_enabled(env_var_name: str, default: bool = True) -> bool:
    val = os.getenv(env_var_name)
    if val is None or val.strip() == "":
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


SOURCES_CONFIG = {
    # ── Chuyên giveaway phần mềm Windows / PC ──
    "sharewareonsale": is_enabled("SOURCE_SHAREWAREONSALE"),
    "giveawayoftheday": is_enabled("SOURCE_GIVEAWAYOFTHEDAY"),
    "tickcoupon": is_enabled("SOURCE_TICKCOUPON"),
    # ── Chuyên iOS / iPadOS / macOS (Apps Gone Free & Promo Codes) ──
    "gotd_ios": is_enabled("SOURCE_GOTD_IOS"),
    "gotd_mac": is_enabled("SOURCE_GOTD_MAC"),
    "9to5toys_apps": is_enabled("SOURCE_9TO5TOYS_APPS"),
    "idownloadblog": is_enabled("SOURCE_IDOWNLOADBLOG"),
    # ── Trang tin công nghệ lớn ──
    "ghacks": is_enabled("SOURCE_GHACKS"),
    "betanews": is_enabled("SOURCE_BETANEWS"),
    "softpedia": is_enabled("SOURCE_SOFTPEDIA"),
    "digitaltrends": is_enabled("SOURCE_DIGITALTRENDS"),
    "makeuseof": is_enabled("SOURCE_MAKEUSEOF"),
    # ── Cộng đồng & diễn đàn ──
    "nsane_deals": is_enabled("SOURCE_NSANE_DEALS"),
    "comss": is_enabled("SOURCE_COMSS"),
    "itsfoss": is_enabled("SOURCE_ITSFOSS"),
    "freeappsforme": is_enabled("SOURCE_FREEAPPSFORME"),
    "geckoandfly": is_enabled("SOURCE_GECKOANDFLY"),
    # ── Game & Reddit (Multireddit iOS + PC) ──
    "steam_newreleases": is_enabled("SOURCE_STEAM_NEWRELEASES", default=False),
    "reddit_rss": is_enabled("SOURCE_REDDIT_RSS"),
    # ── v3: API có cấu trúc (ảnh, giá gốc, hạn nhận chính xác) ──
    "epic_games": is_enabled("SOURCE_EPIC_GAMES"),
    "gamerpower": is_enabled("SOURCE_GAMERPOWER"),
}

# Danh sách biến môi trường nguồn để đồng bộ với Web Admin UI
SOURCE_ENV_KEYS = [
    "SOURCE_SHAREWAREONSALE",
    "SOURCE_GIVEAWAYOFTHEDAY",
    "SOURCE_TICKCOUPON",
    "SOURCE_GOTD_IOS",
    "SOURCE_GOTD_MAC",
    "SOURCE_9TO5TOYS_APPS",
    "SOURCE_IDOWNLOADBLOG",
    "SOURCE_GHACKS",
    "SOURCE_BETANEWS",
    "SOURCE_SOFTPEDIA",
    "SOURCE_DIGITALTRENDS",
    "SOURCE_MAKEUSEOF",
    "SOURCE_NSANE_DEALS",
    "SOURCE_COMSS",
    "SOURCE_ITSFOSS",
    "SOURCE_FREEAPPSFORME",
    "SOURCE_GECKOANDFLY",
    "SOURCE_STEAM_NEWRELEASES",
    "SOURCE_REDDIT_RSS",
    "SOURCE_EPIC_GAMES",
    "SOURCE_GAMERPOWER",
]

# v3: chỉ gửi Telegram cho các nền tảng này (để trống = tất cả). Vd: "ios,windows,game,macos"
_tg_platforms = os.getenv("TELEGRAM_PLATFORMS", "")
TELEGRAM_PLATFORMS = [p.strip().lower() for p in _tg_platforms.split(",") if p.strip()]

# Đường dẫn Database
DB_PATH = os.getenv("DB_PATH", "giveaways.db")

# Từ khóa lọc (nếu trống thì không lọc)
_keywords_str = os.getenv("KEYWORDS", "")
KEYWORDS = [k.strip().lower() for k in _keywords_str.split(",") if k.strip()] if _keywords_str.strip() else []

# Từ khóa loại trừ (bài chứa những từ này sẽ bị bỏ qua)
_neg_keywords_str = os.getenv("NEGATIVE_KEYWORDS", "")
NEGATIVE_KEYWORDS = [k.strip().lower() for k in _neg_keywords_str.split(",") if k.strip()] if _neg_keywords_str.strip() else []

# Điểm tin cậy tối thiểu (0 = gửi tất cả, 50 = chỉ gửi bài có code/deal đáng tin)
try:
    MIN_CONFIDENCE_SCORE = int(os.getenv("MIN_CONFIDENCE_SCORE", "0"))
except ValueError:
    MIN_CONFIDENCE_SCORE = 0

# Fallback Scraping
ENABLE_FALLBACK_SCRAPER = is_enabled("ENABLE_FALLBACK_SCRAPER", default=True)

# Reddit PRAW Config
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "python:me.buongloi.giveawaybot:v2.0")

# Telethon Config
ENABLE_TELETHON_LISTENER = is_enabled("ENABLE_TELETHON_LISTENER", default=False)
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
_channels_str = os.getenv("TELETHON_CHANNELS", "")
TELETHON_CHANNELS = [c.strip() for c in _channels_str.split(",") if c.strip()]

# Cấu hình Timeout & Retry
REQUEST_TIMEOUT = 15  # giây
MAX_RETRIES = 3
