import argparse
import time
import logging
from bot.config import (
    SOURCES_CONFIG, KEYWORDS, NEGATIVE_KEYWORDS, MIN_CONFIDENCE_SCORE,
    REDDIT_CLIENT_ID, ENABLE_FALLBACK_SCRAPER
)
from bot.utils import setup_logging, generate_hash, escape_html
from bot.database import init_db, check_and_save_giveaway, mark_as_notified
from bot.extractor import (
    extract_codes, extract_text_from_html, classify_giveaway,
    detect_expiry_hint, detect_platform, get_platform_badge,
    is_relevant_giveaway, evaluate_article_confidence
)
from bot.telegram import send_message
from bot.sources.rss import RSSSource
from bot.sources.scraper import fetch_html_content
from bot.sources.reddit import RedditAPI

logger = logging.getLogger(__name__)


def get_all_sources():
    """Tạo danh sách các nguồn cấp dữ liệu (Windows + iOS + macOS + Game)."""
    sources = [
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
        RSSSource("makeuseof", "https://www.makeuseof.com/feed/", SOURCES_CONFIG.get("makeuseof", True)),

        # ── Cộng đồng & diễn đàn ──
        RSSSource("nsane_deals", "https://nsaneforums.com/forum/48-promotions-and-deals.xml/", SOURCES_CONFIG.get("nsane_deals", True)),
        RSSSource("comss", "https://www.comss.ru/rss.php", SOURCES_CONFIG.get("comss", True)),
        RSSSource("itsfoss", "https://itsfoss.com/feed/", SOURCES_CONFIG.get("itsfoss", True)),
        RSSSource("freeappsforme", "https://freeappsforme.com/feed/", SOURCES_CONFIG.get("freeappsforme", True)),
        RSSSource("geckoandfly", "https://www.geckoandfly.com/feed/", SOURCES_CONFIG.get("geckoandfly", True)),

        # ── Game miễn phí ──
        RSSSource("steam_newreleases", "https://store.steampowered.com/feeds/newreleases.xml", SOURCES_CONFIG.get("steam_newreleases", True)),
    ]

    # Reddit: Nếu có REDDIT_CLIENT_ID thì dùng PRAW, nếu không dùng Multireddit RSS (chống lỗi 429)
    reddit_enabled = SOURCES_CONFIG.get("reddit_rss", True)
    if REDDIT_CLIENT_ID:
        for sub in ['AppHookup', 'iphoneapps', 'iosgaming', 'macapps', 'FreeGameFindings', 'eFreebies', 'giveaways', 'software', 'PromoCode']:
            sources.append(RedditAPI(f"reddit_{sub.lower()}", sub, reddit_enabled))
    else:
        sources.append(RSSSource(
            "reddit_ios",
            "https://www.reddit.com/r/AppHookup+iphoneapps+iosgaming+macapps/new.rss",
            reddit_enabled
        ))
        sources.append(RSSSource(
            "reddit_pc",
            "https://www.reddit.com/r/FreeGameFindings+eFreebies+giveaways+PromoCode+software/new.rss",
            reddit_enabled
        ))

    return sources


def contains_keywords(text: str) -> bool:
    """Kiểm tra nếu bài viết chứa bất kỳ từ khóa nào được yêu cầu."""
    if not KEYWORDS:
        return True  # Không cấu hình từ khóa -> lấy hết

    text_lower = text.lower()
    for kw in KEYWORDS:
        if kw in text_lower:
            return True
    return False


def contains_negative_keywords(text: str) -> bool:
    """Kiểm tra nếu bài viết chứa từ khóa loại trừ (sẽ bị bỏ qua)."""
    if not NEGATIVE_KEYWORDS:
        return False
    text_lower = text.lower()
    for kw in NEGATIVE_KEYWORDS:
        if kw in text_lower:
            return True
    return False


def process_giveaway(source_name: str, item: dict, dry_run: bool, backfill: bool):
    title = item.get('title', '').strip()
    link = item.get('link', '').strip()
    guid = item.get('guid', link)
    published = item.get('published', '')
    content_html = item.get('content', '')

    if not title or not link:
        return

    # Rút trích text sạch
    clean_text = extract_text_from_html(content_html)

    # Trích xuất mã code
    codes, code_confidence = extract_codes(content_html)

    # Lọc theo keyword cấu hình
    if not contains_keywords(clean_text) and not contains_keywords(title):
        logger.debug(f"[{source_name}] Bỏ qua vì không chứa từ khóa cấu hình: {title}")
        return

    # Lọc theo negative keywords (loại trừ bài không liên quan)
    if contains_negative_keywords(clean_text) or contains_negative_keywords(title):
        logger.debug(f"[{source_name}] Bỏ qua vì chứa từ khóa loại trừ: {title}")
        return

    # Lọc độ liên quan: bỏ qua các bài báo tin tức thông thường không phải giveaway/free app
    if not is_relevant_giveaway(title, clean_text, source_name, codes):
        logger.debug(f"[{source_name}] Bỏ qua vì không phải bài giveaway/freebie: {title}")
        return

    # Phase 2: Fallback Scraper nếu không có code, nội dung RSS ngắn (< 300 char) và không phải trang Reddit
    if len(codes) == 0 and ENABLE_FALLBACK_SCRAPER and len(clean_text) < 300 and "reddit.com" not in link.lower():
        logger.info(f"[{source_name}] RSS thiếu nội dung/code, thử cào HTML gốc: {link}")
        full_html = fetch_html_content(link)
        if full_html:
            clean_text = extract_text_from_html(full_html)
            codes, code_confidence = extract_codes(full_html)

    # Phân loại nền tảng, nhãn, thời hạn & điểm tin cậy tổng hợp
    platform = detect_platform(title, clean_text, link, source_name)
    tags = classify_giveaway(title, clean_text)
    expiry = detect_expiry_hint(title, clean_text)
    confidence = evaluate_article_confidence(title, clean_text, codes, code_confidence, link, source_name)

    sorted_codes = sorted(codes)
    codes_str = ", ".join(sorted_codes)
    tags_str = ", ".join(tags)
    content_hash = generate_hash(clean_text)
    codes_hash = generate_hash(",".join(sorted_codes))

    # Lưu vào database
    db_result = check_and_save_giveaway(
        source=source_name,
        canonical_url=link,
        guid=guid,
        title=title,
        published_at=published,
        content_hash=content_hash,
        codes_hash=codes_hash,
        confidence_score=confidence,
        codes=codes_str,
        platform=platform,
        tags=tags_str,
        expiry_hint=expiry
    )

    action = db_result['action']
    record_id = db_result['id']

    if action == 'skip':
        logger.debug(f"[{source_name}] Không có cập nhật: {title}")
        return

    logger.info(f"[{source_name}] [{platform.upper()}] {action.upper()} - {title} - Codes: {len(codes)} - Confidence: {confidence}")

    # Nếu chạy chế độ backfill, đánh dấu đã xử lý để lần chạy sau không gửi bù hàng loạt
    if backfill:
        mark_as_notified(record_id)
        return

    # Lọc theo điểm tin cậy tối thiểu
    if MIN_CONFIDENCE_SCORE > 0 and confidence < MIN_CONFIDENCE_SCORE:
        logger.debug(f"[{source_name}] Bỏ qua gửi TG vì confidence ({confidence}) < MIN ({MIN_CONFIDENCE_SCORE}): {title}")
        return

    # Gửi Telegram
    platform_badge = get_platform_badge(platform)
    safe_title = escape_html(title)
    safe_link = escape_html(link)

    all_badges = [platform_badge] + [t for t in tags if t != platform_badge]
    tag_line = " • ".join(all_badges)

    message = f"🎁 <b>{safe_title}</b>\n"
    if tag_line:
        message += f"🏷️ {tag_line}\n"
    message += f"\n🌍 <b>Nguồn:</b> {escape_html(source_name)}\n"
    message += f"🔗 <a href='{safe_link}'>Mở trang nhận / Tải về</a>\n\n"

    if sorted_codes:
        message += "🔑 <b>Code thu thập được:</b>\n"
        for c in sorted_codes:
            message += f"<code>{escape_html(c)}</code>\n"

        if confidence < 50:
            message += "\n<i>⚠️ Lưu ý: Chuỗi trên có thể chứa code, nhưng độ tin cậy không cao.</i>\n"
    elif platform == "ios":
        message += "<i>📱 Ứng dụng/Game iOS đang miễn phí trực tiếp trên App Store hoặc nhận trong bài viết.</i>\n"
    else:
        message += "<i>ℹ️ Nhận bản quyền / tải miễn phí trực tiếp qua đường link bài viết.</i>\n"

    if expiry:
        message += f"\n⏰ <b>Thời hạn:</b> <i>{escape_html(expiry)}</i>\n"

    if not dry_run:
        success = send_message(message)
        if success:
            mark_as_notified(record_id)
        time.sleep(3)
    else:
        logger.info(f"[DRY-RUN] Sẽ gửi tin nhắn cho: {title}")


def main():
    parser = argparse.ArgumentParser(description="Giveaway Bot - Thu thập code & app miễn phí (Windows, iOS, macOS, Game).")
    parser.add_argument("--once", action="store_true", help="Chạy một lần rồi thoát (dành cho cronjob).")
    parser.add_argument("--dry-run", action="store_true", help="Không gửi Telegram, chỉ in ra log.")
    parser.add_argument("--source", type=str, help="Chỉ chạy một nguồn cụ thể để debug (vd: gotd_ios, reddit_ios).")
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
                    process_giveaway(source.name, item, args.dry_run, args.backfill)
            except Exception as e:
                logger.error(f"Lỗi không xác định khi quét nguồn {source.name}: {e}")

        if args.once:
            logger.info("Hoàn thành chế độ chạy một lần (--once).")
            break

        logger.info("Đã quét xong tất cả các nguồn. Đợi 30 phút...")
        time.sleep(1800)


if __name__ == "__main__":
    main()
