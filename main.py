import argparse
import re
import sqlite3
import time
import logging
from datetime import datetime, timedelta, timezone

from bot.config import (
    SOURCES_CONFIG, KEYWORDS, NEGATIVE_KEYWORDS, MIN_CONFIDENCE_SCORE,
    REDDIT_CLIENT_ID, ENABLE_FALLBACK_SCRAPER, TELEGRAM_PLATFORMS
)
from bot.utils import setup_logging, generate_hash, escape_html
from bot.database import (
    init_db, mark_as_notified, find_existing, insert_giveaway, update_giveaway_fields
)
from bot.extractor import (
    extract_codes, extract_text_from_html, classify_giveaway,
    detect_expiry_hint, detect_platform, get_platform_badge,
    is_relevant_giveaway, evaluate_article_confidence
)
from bot.enrich import (
    parse_worth, parse_expiry, extract_app_store_id, itunes_lookup, app_info_to_fields,
    extract_image, make_dedup_key
)
from bot.telegram import send_rich
from bot.sources.rss import RSSSource
from bot.sources.scraper import fetch_html_content
from bot.sources.reddit import RedditAPI
from bot.sources.epic import EpicGamesSource
from bot.sources.gamerpower import GamerPowerSource

logger = logging.getLogger(__name__)

VN_TZ = timezone(timedelta(hours=7))

STORE_DOMAINS = [
    ("apps.apple.com", "appstore"), ("itunes.apple.com", "appstore"),
    ("store.steampowered.com", "steam"), ("epicgames.com", "epic"), ("gog.com", "gog"),
    ("play.google.com", "googleplay"), ("itch.io", "itch"), ("microsoft.com", "microsoft"),
]

STORE_LABELS = {
    "appstore": "App Store", "steam": "Steam", "epic": "Epic Games", "gog": "GOG",
    "googleplay": "Google Play", "itch": "itch.io", "prime": "Prime Gaming", "ubisoft": "Ubisoft",
    "indiegala": "IndieGala", "microsoft": "Microsoft Store", "ea": "EA App",
}

REDDIT_MULTI = "AppHookup+iphoneapps+macapps+iosgaming+FreeGameFindings+Freegamestuff+eFreebies+giveaways"


def get_all_sources():
    """Tạo danh sách các nguồn cấp dữ liệu (Windows + iOS + macOS + Game)."""
    sources = [
        # ── v3: API có cấu trúc (độ chính xác cao nhất, có ảnh + hạn nhận) ──
        EpicGamesSource(SOURCES_CONFIG.get("epic_games", True)),
        GamerPowerSource(SOURCES_CONFIG.get("gamerpower", True)),

        # ── Nguồn chuyên giveaway phần mềm Windows / PC ──
        RSSSource("sharewareonsale", "https://sharewareonsale.com/feed", SOURCES_CONFIG.get("sharewareonsale", True)),
        RSSSource("giveawayoftheday", "https://www.giveawayoftheday.com/feed/", SOURCES_CONFIG.get("giveawayoftheday", True)),
        RSSSource("tickcoupon", "https://tickcoupon.com/feed/", SOURCES_CONFIG.get("tickcoupon", True)),

        # ── Nguồn chuyên iOS / iPadOS / macOS (Apps Gone Free & Deals) ──
        RSSSource("gotd_ios", "https://iphone.giveawayoftheday.com/feed/", SOURCES_CONFIG.get("gotd_ios", True)),
        RSSSource("gotd_mac", "https://mac.giveawayoftheday.com/feed/", SOURCES_CONFIG.get("gotd_mac", True)),
        RSSSource("9to5toys_apps", "https://9to5toys.com/guides/apps/feed/", SOURCES_CONFIG.get("9to5toys_apps", True)),
        RSSSource("idownloadblog", "https://www.idownloadblog.com/feed/", SOURCES_CONFIG.get("idownloadblog", True)),

        # ── Trang tin công nghệ lớn (đăng giveaway + deals thường xuyên) ──
        RSSSource("ghacks", "https://www.ghacks.net/feed/", SOURCES_CONFIG.get("ghacks", True)),
        RSSSource("betanews", "https://betanews.com/feed/", SOURCES_CONFIG.get("betanews", True)),
        RSSSource("softpedia", "https://www.softpedia.com/backend.xml", SOURCES_CONFIG.get("softpedia", True)),
        RSSSource("digitaltrends", "https://www.digitaltrends.com/computing/feed/", SOURCES_CONFIG.get("digitaltrends", True)),
        RSSSource("makeuseof", "https://makeuseof.com/feed/", SOURCES_CONFIG.get("makeuseof", True)),

        # ── Cộng đồng & diễn đàn ──
        RSSSource("nsane_deals", "https://nsaneforums.com/forum/48-promotions-and-deals.xml/", SOURCES_CONFIG.get("nsane_deals", True)),
        RSSSource("comss", "https://www.comss.ru/rss.php", SOURCES_CONFIG.get("comss", True)),
        RSSSource("itsfoss", "https://itsfoss.com/feed/", SOURCES_CONFIG.get("itsfoss", True)),
        RSSSource("freeappsforme", "https://freeappsforme.com/feed/", SOURCES_CONFIG.get("freeappsforme", True)),
        RSSSource("geckoandfly", "https://www.geckoandfly.com/feed/", SOURCES_CONFIG.get("geckoandfly", True)),

        # ── Game mới phát hành (mặc định tắt vì không phải game miễn phí) ──
        RSSSource("steam_newreleases", "https://store.steampowered.com/feeds/newreleases.xml", SOURCES_CONFIG.get("steam_newreleases", False)),
    ]

    reddit_enabled = SOURCES_CONFIG.get("reddit_rss", True)
    if REDDIT_CLIENT_ID:
        for sub in REDDIT_MULTI.split("+"):
            sources.append(RedditAPI(f"reddit_{sub.lower()}", sub, reddit_enabled))
    else:
        # Gộp tất cả subreddit vào 1 request duy nhất để tránh lỗi 429 Too Many Requests
        sources.append(RSSSource(
            "reddit",
            f"https://www.reddit.com/r/{REDDIT_MULTI}/new.rss?limit=100",
            reddit_enabled
        ))

    return sources


def contains_keywords(text: str) -> bool:
    if not KEYWORDS:
        return True
    text_lower = text.lower()
    for kw in KEYWORDS:
        if kw in text_lower:
            return True
    return False


def contains_negative_keywords(text: str) -> bool:
    if not NEGATIVE_KEYWORDS:
        return False
    text_lower = text.lower()
    for kw in NEGATIVE_KEYWORDS:
        if kw in text_lower:
            return True
    return False


# ─── Helpers ────────────────────────────────────────────────────────

_HREF_PATTERN = re.compile(r'href=["\'](https?://[^"\']+)["\']', re.IGNORECASE)


def find_external_link(content_html: str) -> str:
    """Lấy link ngoài đầu tiên (không phải reddit/imgur) trong bài Reddit, thường là link App Store/Steam."""
    for url in _HREF_PATTERN.findall(content_html or ""):
        low = url.lower()
        if not any(d in low for d in ("reddit.com", "redd.it", "imgur.com", "redditmedia.com", "redditstatic.com")):
            return url.replace("&amp;", "&")
    return ""


def store_from_url(url: str) -> str:
    low = (url or "").lower()
    for domain, store in STORE_DOMAINS:
        if domain in low:
            return store
    return ""


def is_past(iso_value: str) -> bool:
    if not iso_value:
        return False
    try:
        return datetime.fromisoformat(iso_value) < datetime.now(timezone.utc)
    except ValueError:
        return False


def format_expiry_vn(iso_value: str) -> str:
    """'30/10 23:59 (còn 2 ngày 3 giờ)' theo giờ Việt Nam."""
    try:
        dt = datetime.fromisoformat(iso_value)
    except (TypeError, ValueError):
        return ""
    remaining = dt - datetime.now(timezone.utc)
    local = dt.astimezone(VN_TZ).strftime("%d/%m %H:%M")
    secs = int(remaining.total_seconds())
    if secs <= 0:
        return f"{local} (đã hết hạn)"
    days, rem = divmod(secs, 86400)
    hours = rem // 3600
    left = f"{days} ngày {hours} giờ" if days else f"{hours} giờ {(rem % 3600) // 60} phút"
    return f"{local} (còn {left})"


def build_caption(rec: dict) -> str:
    title = escape_html(rec.get("title", ""))
    platform = rec.get("platform", "other")
    parts = [get_platform_badge(platform)]
    store_label = STORE_LABELS.get(rec.get("store", ""), "")
    if store_label:
        parts.append(f"🏪 {store_label}")
    if rec.get("rating"):
        parts.append(f"⭐ {rec['rating']}")

    lines = [f"🎁 <b>{title}</b>", " • ".join(parts), ""]
    if rec.get("worth"):
        lines.append(f"💰 <s>{escape_html(rec['worth'])}</s> → <b>MIỄN PHÍ</b>")
    else:
        lines.append("💰 <b>MIỄN PHÍ</b>")
    if rec.get("expires_at"):
        lines.append(f"⏰ Hết hạn: <b>{escape_html(format_expiry_vn(rec['expires_at']))}</b>")
    elif rec.get("expiry_hint"):
        lines.append(f"⏰ Thời hạn: <i>{escape_html(rec['expiry_hint'])}</i>")

    codes = [c.strip() for c in (rec.get("codes") or "").split(",") if c.strip()]
    if codes:
        lines.append("")
        lines.append("🔑 <b>License / Code:</b>")
        lines.extend(f"<code>{escape_html(c)}</code>" for c in codes[:5])

    desc = (rec.get("description") or "").strip().replace("\n", " ")
    if desc:
        lines.append("")
        lines.append(f"📝 <i>{escape_html(desc[:220])}{'…' if len(desc) > 220 else ''}</i>")

    lines.append("")
    lines.append(f"🌍 Nguồn: {escape_html(rec.get('source', ''))}")
    caption = "\n".join(lines)
    return caption[:1024] if len(caption) > 1024 else caption


def notify(rec: dict, dry_run: bool) -> bool:
    """Gửi thông báo Telegram cho một bản ghi đang active. Trả về True nếu đã xử lý (gửi hoặc bị lọc)."""
    platform = (rec.get("platform") or "other").lower()
    if TELEGRAM_PLATFORMS and platform not in TELEGRAM_PLATFORMS:
        logger.info(f"[{rec.get('source')}] Bỏ qua Telegram vì nền tảng '{platform}' không nằm trong TELEGRAM_PLATFORMS.")
        mark_as_notified(rec["id"])
        return True

    caption = build_caption(rec)
    claim_url = rec.get("store_url") or rec.get("canonical_url")
    buttons = [("🎁 Nhận ngay", claim_url)]
    if rec.get("canonical_url") and rec.get("canonical_url") != claim_url:
        buttons.append(("📄 Xem bài gốc", rec["canonical_url"]))

    if dry_run:
        logger.info(f"[DRY-RUN] Sẽ gửi Telegram: {rec.get('title')}")
        return True

    success = send_rich(caption, rec.get("image_url", ""), buttons)
    if success:
        mark_as_notified(rec["id"])
    time.sleep(3)
    return success


def _confidence_ok(rec: dict) -> bool:
    return MIN_CONFIDENCE_SCORE <= 0 or (rec.get("confidence_score") or 0) >= MIN_CONFIDENCE_SCORE \
        or bool(rec.get("codes"))


# ─── Pipeline xử lý 1 bài ───────────────────────────────────────────

def process_giveaway(source_name: str, item: dict, dry_run: bool, backfill: bool):
    title = (item.get('title') or '').strip()
    link = (item.get('link') or '').strip()
    guid = item.get('guid') or link
    published = item.get('published', '')
    content_html = item.get('content', '') or ''
    structured = bool(item.get('structured'))

    if not title or not link:
        return

    # 1) Chống trùng sớm (rẻ): theo URL, GUID, App Store ID hoặc tên game
    pre_app_id = item.get('app_id') or extract_app_store_id(link, content_html)
    pre_platform = item.get('platform') or detect_platform(title, "", link, source_name)
    pre_dedup = make_dedup_key(pre_platform, title, pre_app_id)
    existing = find_existing(link, guid, pre_dedup)

    if existing:
        updates = {}
        if structured:
            for key in ("status", "expires_at", "starts_at", "image_url", "worth", "worth_value", "store_url"):
                val = item.get(key)
                if val not in (None, "", 0) and val != existing.get(key):
                    updates[key] = val
        update_giveaway_fields(existing["id"], updates)
        merged = {**existing, **updates}
        if not merged.get("notified_at") and merged.get("status", "active") == "active" and _confidence_ok(merged):
            logger.info(f"[{source_name}] RESEND/ACTIVATE - {title}")
            if backfill:
                mark_as_notified(existing["id"])
            else:
                notify(merged, dry_run)
        return

    # 2) Lọc nội dung (chỉ áp dụng cho nguồn RSS không cấu trúc)
    clean_text = extract_text_from_html(content_html)
    codes, code_confidence = extract_codes(content_html)
    full_html = ""

    if not structured:
        if not contains_keywords(clean_text) and not contains_keywords(title):
            return
        if contains_negative_keywords(clean_text) or contains_negative_keywords(title):
            return
        if not is_relevant_giveaway(title, clean_text, source_name, codes):
            logger.debug(f"[{source_name}] Bỏ qua vì không phải bài giveaway/freebie: {title}")
            return

        skip_scrape_domains = ("reddit.com", "nsaneforums.com")
        if len(codes) == 0 and ENABLE_FALLBACK_SCRAPER and len(clean_text) < 300 \
                and not any(d in link.lower() for d in skip_scrape_domains):
            logger.info(f"[{source_name}] RSS thiếu nội dung/code, thử cào HTML gốc: {link}")
            full_html = fetch_html_content(link) or ""
            if full_html:
                clean_text = extract_text_from_html(full_html)
                codes, code_confidence = extract_codes(full_html)

    platform = item.get('platform') or detect_platform(title, clean_text, link, source_name)
    tags = list(dict.fromkeys(classify_giveaway(title, clean_text) + list(item.get('tags') or [])))
    expiry_hint = detect_expiry_hint(title, clean_text)

    if structured:
        confidence = 95
    else:
        confidence = evaluate_article_confidence(title, clean_text, codes, code_confidence, link, source_name)
        if confidence == 0 and not codes:
            return
        if MIN_CONFIDENCE_SCORE > 0 and confidence < MIN_CONFIDENCE_SCORE and not codes:
            logger.debug(f"[{source_name}] Bỏ qua vì confidence ({confidence}) < MIN ({MIN_CONFIDENCE_SCORE}): {title}")
            return

    # 3) Làm giàu dữ liệu
    worth = item.get('worth') or ""
    worth_value = item.get('worth_value') or 0.0
    if not worth:
        worth, worth_value = parse_worth(f"{title} {clean_text[:600]}")

    external = item.get('store_url') or (find_external_link(content_html) if "reddit" in source_name else "")
    app_id = pre_app_id or extract_app_store_id(external, full_html)
    store_url = external or ""
    record = {
        "source": source_name,
        "canonical_url": link,
        "guid": guid,
        "title": title,
        "published_at": str(published or ""),
        "content_hash": generate_hash(clean_text),
        "codes_hash": generate_hash(",".join(sorted(codes))),
        "codes": ", ".join(sorted(codes)),
        "platform": platform,
        "tags": ", ".join(tags),
        "expiry_hint": expiry_hint,
        "confidence_score": confidence,
        "image_url": item.get('image_url') or extract_image(content_html) or extract_image(full_html),
        "worth": worth,
        "worth_value": worth_value,
        "expires_at": item.get('expires_at') or parse_expiry(expiry_hint),
        "starts_at": item.get('starts_at') or "",
        "store": item.get('store') or store_from_url(store_url or link),
        "store_url": store_url,
        "description": (item.get('description') or clean_text[:600]).strip(),
        "app_id": app_id,
        "rating": 0.0,
        "status": item.get('status') or "active",
    }

    if app_id:
        info = itunes_lookup([app_id]).get(app_id)
        if info:
            fields = app_info_to_fields(info)
            record.update({k: v for k, v in fields.items() if v not in ("", None) or k == "status"})
            if fields.get("status") == "expired":
                logger.info(f"[{source_name}] App {app_id} hiện đã có giá {info.get('formattedPrice')}, đánh dấu hết hạn: {title}")

    if record["status"] == "active" and is_past(record["expires_at"]):
        record["status"] = "expired"
    record["dedup_key"] = make_dedup_key(record["platform"], title, app_id)

    try:
        record["id"] = insert_giveaway(record)
    except sqlite3.IntegrityError:
        logger.debug(f"[{source_name}] Trùng URL khi chèn, bỏ qua: {title}")
        return

    logger.info(f"[{source_name}] [{record['platform'].upper()}] NEW ({record['status']}) - {title} - "
                f"Codes: {len(codes)} - Confidence: {confidence} - Worth: {worth or '-'} - Exp: {record['expires_at'] or '-'}")

    if backfill:
        mark_as_notified(record["id"])
        return

    if record["status"] == "active":
        notify(record, dry_run)


def main():
    parser = argparse.ArgumentParser(description="Giveaway Bot - Thu thập code & app miễn phí (Windows, iOS, macOS, Game).")
    parser.add_argument("--once", action="store_true", help="Chạy một lần rồi thoát (dành cho cronjob).")
    parser.add_argument("--dry-run", action="store_true", help="Không gửi Telegram, chỉ in ra log.")
    parser.add_argument("--source", type=str, help="Chỉ chạy một nguồn cụ thể để debug (vd: epic_games, gamerpower, reddit).")
    parser.add_argument("--verbose", action="store_true", help="Bật log DEBUG.")
    parser.add_argument("--backfill", action="store_true", help="Nạp dữ liệu cũ vào DB nhưng không gửi thông báo.")

    args = parser.parse_args()

    setup_logging(args.verbose)
    init_db()

    sources = get_all_sources()

    if args.source:
        sources = [s for s in sources if s.name.lower() == args.source.lower()]
        if not sources:
            logger.error(f"Không tìm thấy nguồn: {args.source}")
            return

    logger.info(f"Bắt đầu chạy Giveaway Bot. Dry-run: {args.dry_run}, Backfill: {args.backfill}")

    while True:
        for source in sources:
            if not source.enabled and not args.source:
                continue

            logger.info(f"Đang quét nguồn: {source.name}...")
            try:
                items = source.fetch()
                for item in items:
                    try:
                        process_giveaway(source.name, item, args.dry_run, args.backfill)
                    except Exception as e:
                        logger.exception(f"Lỗi xử lý bài '{item.get('title', '')}' từ {source.name}: {e}")
            except Exception as e:
                logger.error(f"Lỗi không xác định khi quét nguồn {source.name}: {e}")

        if args.once:
            logger.info("Hoàn thành chế độ chạy một lần (--once).")
            break

        logger.info("Đã quét xong tất cả các nguồn. Đợi 30 phút...")
        time.sleep(1800)


if __name__ == "__main__":
    main()
