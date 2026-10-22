import re
from typing import List, Tuple
from bs4 import BeautifulSoup

# Patterns nhận diện key
# 1. Các khối chữ/số cách nhau bởi dấu gạch ngang (e.g. XXXX-XXXX-XXXX, XXXX-XXXX-XXXX-XXXX, XXXXX-XXXXX-XXXXX)
KEY_PATTERN = re.compile(r'\b(?:[A-Z0-9]{3,8}[-]){2,5}[A-Z0-9]{3,8}\b', re.IGNORECASE)
# 2. Chuỗi Alphanumeric liên tiếp dài (10-30 ký tự, chứa cả chữ và số)
ALNUM_PATTERN = re.compile(r'\b(?=.*[A-Z])(?=.*[0-9])[A-Z0-9]{10,30}\b', re.IGNORECASE)

# Patterns loại trừ False Positive
EXCLUSION_PATTERNS = [
    re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.IGNORECASE),  # UUID
    re.compile(r'^https?://', re.IGNORECASE),  # URL
    re.compile(r'\b[0-9a-f]{40}\b', re.IGNORECASE),  # Git SHA-1
    re.compile(r'\b[0-9a-f]{64}\b', re.IGNORECASE),  # SHA-256
    re.compile(r'\b[0-9a-f]{32}\b', re.IGNORECASE),  # MD5
    re.compile(r'^\d{4}-\d{2}-\d{2}', re.IGNORECASE),  # Date YYYY-MM-DD
    re.compile(r'^\d{3,4}x\d{3,4}', re.IGNORECASE),  # Resolution 1920x1080
    re.compile(r'^\d{3,4}p\d{2,3}fps$', re.IGNORECASE),  # Video format 1080p60fps
    re.compile(r'^(?:windows|iphone|android|macos|version|update|release|build|directx|geforce|radeon)[a-z0-9-]*$', re.IGNORECASE),
]

# Từ khóa tăng điểm tin cậy quanh mã code
CONTEXT_KEYWORDS = [
    'key', 'license', 'licence', 'serial', 'activation', 'code',
    'redeem', 'promo', 'coupon', 'voucher', 'registration', 'giveaway',
    'код', 'лицензия', 'промокод', 'ключ'
]

# Nguồn chuyên biệt 100% là giveaway/freebie
DEDICATED_GIVEAWAY_SOURCES = {
    'sharewareonsale', 'giveawayoftheday', 'tickcoupon',
    'gotd_ios', 'gotd_mac', 'freeappsforme', 'nsane_deals',
    'reddit_ios', 'reddit_pc',
    'reddit_apphookup', 'reddit_efreebies', 'reddit_giveaways',
    'reddit_freegamefindings', 'reddit_promocode'
}

# Regex kiểm tra tín hiệu Giveaway trên Tiêu đề cho các trang báo công nghệ tổng hợp
TITLE_GIVEAWAY_REGEX = re.compile(
    r'(?:\bfree\b|\bfreebies?\b|\bgiveaways?\b|\b100%\s*off\b|'
    r'\bpromo\s*codes?\b|\blicense\s*keys?\b|\bcoupons?\b|\bredeem\b|'
    r'->\s*free|→\s*free|\$0(?:\.00)?\b|'
    r'бесплатно|раздача|лицензия|промокод|miễn\s+phí)',
    re.IGNORECASE
)

# Mẫu giá giảm về 0 đặc trưng trên r/AppHookup, GiveawayOfTheDay iOS, 9to5Toys (vd: [$4.99 -> Free], ($2.99 → Free))
PRICE_FREE_PATTERN = re.compile(
    r'(?:\d+(?:\.\d{1,2})?\s*(?:->|→|--?>|to)\s*(?:free|\$0(?:\.00)?))|'
    r'(?:100%\s*off)|'
    r'(?:apps?\s+gone\s+free)|'
    r'(?:deals\s+and\s+freebies)|'
    r'(?:\[free\])',
    re.IGNORECASE
)

# Mẫu nhận diện bài đã hết hạn ngay trên tiêu đề
EXPIRED_TITLE_REGEX = re.compile(
    r'(?:\*expired\*|\[expired\]|\(expired\)|\[ended\]|\bexpired\s*:)',
    re.IGNORECASE
)


def extract_text_from_html(html_content: str) -> str:
    """Loại bỏ thẻ script, style, code blocks và trả về text sạch."""
    if not html_content:
        return ""
    soup = BeautifulSoup(html_content, 'html.parser')
    for element in soup(["script", "style", "code", "pre"]):
        element.extract()
    return soup.get_text(separator=' ')


def _extract_code_tags_text(html_content: str) -> List[str]:
    """
    Trích xuất riêng nội dung ngắn nằm trong thẻ <code>, <pre>, <kbd>
    vì nhiều trang giveaway đặt License Key trong <code>XXXX-XXXX-XXXX</code>.
    """
    if not html_content or ('<' not in html_content):
        return []
    soup = BeautifulSoup(html_content, 'html.parser')
    candidates = []
    for tag in soup.find_all(["code", "pre", "kbd"]):
        txt = tag.get_text(separator=' ').strip()
        if 8 <= len(txt) <= 120:
            candidates.append(txt)
    return candidates


def is_excluded(text: str) -> bool:
    """Kiểm tra xem chuỗi có thuộc dạng loại trừ (UUID, Hash, URL, từ ghép thường...) hay không."""
    if not text:
        return True
    for pattern in EXCLUSION_PATTERNS:
        if pattern.search(text):
            return True

    # Nếu là chuỗi liền không có dấu gạch ngang, yêu cầu phải có ít nhất 2 chữ IN HOA
    # và không có chữ thường để tránh bắt nhầm tên riêng/từ tiếng Anh có số (vd: Glasscribe1, kiririn51...)
    if '-' not in text:
        if any(c.islower() for c in text):
            return True
        upper_count = sum(1 for c in text if c.isupper())
        if upper_count < 2:
            return True

    # Nếu có dấu gạch ngang (vd: word-word-123), loại bỏ nếu chứa chữ thường (slug URL / tên bài)
    if '-' in text:
        if any(c.islower() for c in text):
            return True

    return False


def calculate_confidence(code: str, full_text: str) -> int:
    """
    Tính điểm tin cậy dựa vào ngữ cảnh.
    Tìm vị trí của code, quét xung quanh (trước và sau ~150 ký tự) xem có từ khóa liên quan không.
    """
    score = 0
    idx = full_text.find(code)
    if idx != -1:
        start_idx = max(0, idx - 150)
        end_idx = min(len(full_text), idx + len(code) + 150)
        context_str = full_text[start_idx:end_idx].lower()

        for kw in CONTEXT_KEYWORDS:
            if kw in context_str:
                score += 50
                break  # Chỉ tính 1 lần nếu có bất kỳ từ nào
    return score


def extract_codes(html_content: str) -> Tuple[List[str], int]:
    """
    Trích xuất các đoạn mã nghi ngờ từ nội dung HTML (bao gồm cả text thường và thẻ <code> ngắn).
    Trả về danh sách code và điểm tin cậy cao nhất.
    """
    clean_text = extract_text_from_html(html_content)
    code_tag_texts = _extract_code_tags_text(html_content)

    full_search_text = clean_text
    if code_tag_texts:
        full_search_text = f"{clean_text} {' '.join(code_tag_texts)}"

    found_codes = []

    # 1. Tìm kiếm định dạng XXXX-XXXX-XXXX
    for m in KEY_PATTERN.findall(full_search_text):
        if not is_excluded(m) and m not in found_codes:
            found_codes.append(m)

    # 2. Tìm kiếm định dạng Alphanumeric liền (chữ IN HOA + số)
    for m in ALNUM_PATTERN.findall(full_search_text):
        if not is_excluded(m) and m not in found_codes:
            found_codes.append(m)

    max_score = 0
    for code in found_codes:
        score = calculate_confidence(code, full_search_text)
        max_score = max(max_score, score)

    return list(set(found_codes)), max_score


def is_relevant_giveaway(title: str, content_text: str, source: str = "", codes: List[str] = None) -> bool:
    """
    Kiểm tra bài viết có thực sự là bài Giveaway / Free App / Deal miễn phí hay không.
    - Với nguồn chuyên giveaway (SharewareOnSale, GOTD, TickCoupon, r/AppHookup...): luôn hợp lệ.
    - Với trang báo công nghệ tổng hợp (Ghacks, BetaNews, iDownloadBlog...): bắt buộc Tiêu đề phải có
      từ khóa giveaway/freebie hoặc trích xuất được mã code hợp lệ.
    """
    title_str = title or ""
    if EXPIRED_TITLE_REGEX.search(title_str):
        return False

    if codes:
        return True

    source_lower = (source or "").lower()
    if source_lower in DEDICATED_GIVEAWAY_SOURCES:
        return True

    combined = f"{title_str} {(content_text or '')[:400]}"

    if PRICE_FREE_PATTERN.search(combined):
        return True

    if TITLE_GIVEAWAY_REGEX.search(title_str):
        return True

    return False


def evaluate_article_confidence(
    title: str,
    content_text: str,
    codes: List[str],
    code_score: int,
    link: str = "",
    source: str = ""
) -> int:
    """
    Đánh giá độ tin cậy tổng thể (0 - 100) của bài Giveaway (hỗ trợ cả phần mềm có key và App iOS miễn phí trực tiếp).
    """
    score = code_score
    combined = f"{title} {content_text}".lower()
    link_lower = (link or "").lower()
    source_lower = (source or "").lower()

    if codes:
        has_dashed_key = any('-' in c for c in codes)
        if has_dashed_key and score >= 50:
            score = max(score, 85)
        elif has_dashed_key:
            score = max(score, 45)

    # Nếu là deal giảm giá 100% / Apps Gone Free (đặc thù của iOS App Store & r/AppHookup)
    if PRICE_FREE_PATTERN.search(combined):
        score = max(score, 80)

    # Nếu đến từ nguồn iOS/Mac GiveawayOfTheDay hoặc link App Store miễn phí
    if source_lower in ("gotd_ios", "gotd_mac"):
        score = max(score, 85)
    elif ("apps.apple.com" in link_lower or "apps.apple.com" in combined) and TITLE_GIVEAWAY_REGEX.search(combined):
        score = max(score, 75)

    # Nếu đến từ nguồn chuyên giveaway uy tín và tiêu đề có chữ free / giveaway / license
    if source_lower in DEDICATED_GIVEAWAY_SOURCES and TITLE_GIVEAWAY_REGEX.search(title or ""):
        score = max(score, 70)

    return min(100, score)


# ─── Nhận diện Nền tảng (Windows / iOS / macOS / Android / Game) ────

PLATFORM_RULES = [
    ("ios", [
        "[ios", "/ios]", "ios/", "ios /", "[iphone", "[ipad", "[watchos", "[apple",
        "for ios", "on ios", "for iphone", "for ipad", "ios app", "iphone app", "ipad app",
        "ios game", "apps gone free", "app store", "apps.apple.com", "itunes.apple.com",
        "iphone.giveawayoftheday.com"
    ]),
    ("macos", [
        "[mac", "/mac]", "macos", "[osx]", "for mac", "mac app", "mac.giveawayoftheday.com"
    ]),
    ("windows", [
        "[windows", "/windows", "windows/", "[win]", "[pc]", "for windows", "for pc",
        "windows 10", "windows 11", "win10", "win11", ".exe", "microsoft store"
    ]),
    ("android", [
        "[android", "/android", "android/", "google play", "play.google.com",
        "for android", "android app", "android.giveawayoftheday.com", ".apk"
    ]),
    ("game", [
        "[steam", "[epic", "[gog", "[itch.io", "steam free", "epic games", "free game",
        "store.steampowered.com", "gog.com"
    ]),
]

IOS_SOURCES = {"gotd_ios", "idownloadblog", "reddit_iosgaming", "appadvice", "toucharcade"}
MAC_SOURCES = {"gotd_mac"}
GAME_SOURCES = {"steam_newreleases", "reddit_freegamefindings"}


def detect_platform(title: str, content_text: str = "", link: str = "", source: str = "") -> str:
    """
    Nhận diện nền tảng chính của bài giveaway:
    Trả về một trong: 'ios', 'windows', 'macos', 'android', 'game', 'other'.
    """
    source_lower = (source or "").lower()
    title_lower = (title or "").lower()
    link_lower = (link or "").lower()
    combined_lower = f"{title_lower} {link_lower} {(content_text or '')[:600].lower()}"

    # 1. Nguồn chuyên biệt cố định nền tảng
    if source_lower == "gotd_ios":
        return "ios"
    if source_lower == "gotd_mac":
        return "macos"

    # 2. Kiểm tra ngay trên tiêu đề + link (chính xác nhất)
    title_and_link = f"{title_lower} {link_lower}"
    for platform, keywords in PLATFORM_RULES:
        for kw in keywords:
            if kw in title_and_link:
                return platform

    # 3. Kiểm tra theo nhóm nguồn
    if source_lower in IOS_SOURCES:
        return "ios"
    if source_lower in MAC_SOURCES:
        return "macos"
    if source_lower in GAME_SOURCES:
        return "game"

    # 4. Kiểm tra trong đoạn đầu nội dung
    for platform, keywords in PLATFORM_RULES:
        for kw in keywords:
            if kw in combined_lower:
                return platform

    # Mặc định các nguồn phần mềm PC truyền thống là windows
    if source_lower in {"sharewareonsale", "giveawayoftheday", "tickcoupon", "comss", "nsane_deals"}:
        return "windows"

    return "other"


PLATFORM_BADGES = {
    "ios": "🍎 iOS",
    "macos": "🍏 macOS",
    "windows": "🪟 Windows",
    "android": "🤖 Android",
    "game": "🎮 Game",
    "other": "📦 Phần mềm",
}


def get_platform_badge(platform: str) -> str:
    """Trả về nhãn hiển thị kèm icon cho nền tảng."""
    return PLATFORM_BADGES.get((platform or "other").lower(), "📦 Phần mềm")


# ─── #5: Phân loại bài viết tự động ────────────────────────────────

TAG_RULES = [
    {
        "tag": "🍎 iOS APP",
        "keywords": ["[ios", "apps gone free", "apps.apple.com", "iphone.giveawayoftheday", "for iphone", "for ipad", "ios app"],
    },
    {
        "tag": "🎫 FREE LICENSE",
        "keywords": ["free license", "license key", "license code", "full version free",
                     "registration code", "giveaway license", "activation key", "бесплатная лицензия"],
    },
    {
        "tag": "🏷️ COUPON",
        "keywords": ["coupon", "discount code", "promo code", "% off", "deal",
                     "voucher", "промокод", "скидка"],
    },
    {
        "tag": "🎁 GIVEAWAY",
        "keywords": ["giveaway", "give away", "free copy", "free download", "-> free", "→ free",
                     "раздача", "бесплатно"],
    },
    {
        "tag": "🆓 OPEN SOURCE",
        "keywords": ["open source", "open-source", "github.com", "gitlab.com", "foss",
                     "mit license", "gpl", "apache license"],
    },
    {
        "tag": "🎮 FREE GAME",
        "keywords": ["free game", "free on steam", "free on epic", "epic games free",
                     "steam free", "100% off steam", "бесплатная игра"],
    },
]


def classify_giveaway(title: str, content_text: str) -> list:
    """
    Phân loại bài viết dựa trên từ khóa.
    Trả về danh sách các tag phù hợp. Ví dụ: ['🍎 iOS APP', '🎁 GIVEAWAY']
    """
    combined = f"{title} {content_text}".lower()
    tags = []
    for rule in TAG_RULES:
        for keyword in rule["keywords"]:
            if keyword in combined:
                tags.append(rule["tag"])
                break
    return tags


# ─── #18: Phát hiện thời hạn hết hạn ──────────────────────────────

EXPIRY_PATTERNS = [
    re.compile(r'expires?\s+(?:on\s+)?(\w+\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2})', re.IGNORECASE),
    re.compile(r'valid\s+(?:until|till)\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', re.IGNORECASE),
    re.compile(r'ends?\s+(?:on\s+)?(\w+\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2})', re.IGNORECASE),
    re.compile(r'until\s+([A-Z][a-z]{2,8}\s+\d{1,2}(?:,?\s+\d{4})?)', re.IGNORECASE),
    re.compile(r'(\d+)\s*(?:hours?|hrs?|h)\s*(?:only|left|remaining)', re.IGNORECASE),
    re.compile(r'(\d+)\s*(?:days?|d)\s*(?:only|left|remaining)', re.IGNORECASE),
    re.compile(r'limited\s*time', re.IGNORECASE),
]


def detect_expiry_hint(title: str, content_text: str) -> str:
    """
    Phát hiện gợi ý về thời hạn hết hạn từ tiêu đề và nội dung.
    """
    combined = f"{title} {content_text}"
    for pattern in EXPIRY_PATTERNS:
        match = pattern.search(combined)
        if match:
            return match.group(0).strip()
    return ""
