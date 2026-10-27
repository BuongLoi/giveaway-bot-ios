"""
Làm giàu dữ liệu giveaway (v3):
- Lấy App Store ID và tra iTunes Lookup API: icon, giá hiện tại, rating, thể loại.
  => Xác minh app iOS/macOS CÒN miễn phí thật hay đã hết hạn.
- Trích giá gốc ("$4.99 -> Free", "worth $29.95").
- Chuyển gợi ý thời hạn dạng chữ thành thời điểm ISO-8601 (UTC).
- Lấy ảnh đại diện (og:image / <img> đầu tiên).
- Sinh khóa chống trùng (cùng game/app xuất hiện ở nhiều nguồn).
"""
import re
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, Optional, Tuple

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

ITUNES_LOOKUP_URL = "https://itunes.apple.com/lookup"
HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; GiveawayHunter/3.0)"}

APP_ID_PATTERN = re.compile(r'(?:apps|itunes)\.apple\.com/[^\s"\'<>]*?/?id(\d{6,12})', re.IGNORECASE)

# "$4.99 -> Free", "$29.99 → Lifetime", "(Was $1.99)", "CA$5.69 → Free", "worth $19.95"
WORTH_PATTERNS = [
    re.compile(r'([A-Z]{0,3}\$\s?\d{1,4}(?:[.,]\d{1,2})?)\s*(?:->|→|--?>|to)\s*(?:free|\$0|lifetime)', re.IGNORECASE),
    re.compile(r'\bwas\s+([A-Z]{0,3}\$\s?\d{1,4}(?:[.,]\d{1,2})?)', re.IGNORECASE),
    re.compile(r'\b(?:worth|regular(?:ly)?|normally|reg\.?|value[sd]?\s+at)\s*:?\s*([A-Z]{0,3}\$\s?\d{1,4}(?:[.,]\d{1,2})?)', re.IGNORECASE),
    re.compile(r'(\d{1,4}(?:[.,]\d{1,2})?\s?(?:USD|EUR|€))\b', re.IGNORECASE),
]

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


# ─── Giá trị / giá gốc ──────────────────────────────────────────────

def parse_worth(text: str) -> Tuple[str, float]:
    """Trả về (chuỗi giá gốc hiển thị, giá trị số). ("", 0) nếu không tìm thấy."""
    if not text:
        return "", 0.0
    for pattern in WORTH_PATTERNS:
        m = pattern.search(text)
        if m:
            raw = m.group(1).strip()
            return raw, worth_to_value(raw)
    return "", 0.0


def worth_to_value(raw: str) -> float:
    if not raw:
        return 0.0
    m = re.search(r'(\d{1,5}(?:[.,]\d{1,2})?)', raw)
    if not m:
        return 0.0
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return 0.0


# ─── Thời hạn ───────────────────────────────────────────────────────

def _to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def parse_datetime_any(value: str) -> str:
    """Chuẩn hóa các dạng ngày phổ biến ("2026-10-30 23:59:00", ISO 'Z', ...) thành ISO UTC. "" nếu không hợp lệ."""
    if not value or str(value).strip().upper() in ("N/A", "NONE", "NULL"):
        return ""
    s = str(value).strip().replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.fromisoformat(s) if fmt is None else datetime.strptime(s, fmt)
            return _to_iso(dt)
        except ValueError:
            continue
    return ""


def parse_expiry(hint: str, now: Optional[datetime] = None) -> str:
    """Chuyển gợi ý thời hạn (vd 'expires October 31, 2026', '48 hours left', 'until Oct 31') thành ISO UTC."""
    if not hint:
        return ""
    now = now or datetime.now(timezone.utc)
    text = hint.lower()

    m = re.search(r'(\d{1,3})\s*(?:hours?|hrs?|h)\b', text)
    if m:
        return _to_iso(now + timedelta(hours=int(m.group(1))))
    m = re.search(r'(\d{1,2})\s*(?:days?|d)\b', text)
    if m:
        return _to_iso(now + timedelta(days=int(m.group(1))))

    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', text)
    if m:
        try:
            return _to_iso(datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), 23, 59))
        except ValueError:
            return ""

    m = re.search(r'([a-z]{3})[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?', text)
    if m and m.group(1) in MONTHS:
        year = int(m.group(3)) if m.group(3) else now.year
        try:
            dt = datetime(year, MONTHS[m.group(1)], int(m.group(2)), 23, 59, tzinfo=timezone.utc)
        except ValueError:
            return ""
        if not m.group(3) and dt < now - timedelta(days=30):
            dt = dt.replace(year=year + 1)
        return _to_iso(dt)

    m = re.search(r'(\d{1,2})[/.](\d{1,2})[/.](\d{2,4})', text)
    if m:
        year = int(m.group(3))
        year = year + 2000 if year < 100 else year
        try:
            return _to_iso(datetime(year, int(m.group(1)), int(m.group(2)), 23, 59))
        except ValueError:
            try:
                return _to_iso(datetime(year, int(m.group(2)), int(m.group(1)), 23, 59))
            except ValueError:
                return ""
    return ""


# ─── App Store / iTunes Lookup ──────────────────────────────────────

def extract_app_store_id(*texts: str) -> str:
    for t in texts:
        if not t:
            continue
        m = APP_ID_PATTERN.search(t)
        if m:
            return m.group(1)
    return ""


def itunes_lookup(app_ids: Iterable[str], country: str = "us") -> Dict[str, dict]:
    """Tra cứu theo lô (tối đa 150 id/request). Trả về {app_id: info}."""
    ids = [str(i) for i in dict.fromkeys(app_ids) if i]
    result: Dict[str, dict] = {}
    for start in range(0, len(ids), 150):
        chunk = ids[start:start + 150]
        try:
            r = requests.get(ITUNES_LOOKUP_URL, params={"id": ",".join(chunk), "country": country},
                             headers=HTTP_HEADERS, timeout=15)
            r.raise_for_status()
            for app in r.json().get("results", []):
                track_id = str(app.get("trackId", ""))
                if track_id:
                    result[track_id] = app
        except Exception as e:
            logger.warning(f"iTunes lookup lỗi ({len(chunk)} id): {e}")
    return result


def app_info_to_fields(app: dict) -> dict:
    """Chuyển kết quả iTunes thành các cột DB."""
    kind = (app.get("kind") or "").lower()
    price = app.get("price")
    fields = {
        "image_url": app.get("artworkUrl512") or app.get("artworkUrl100") or "",
        "store": "appstore",
        "store_url": app.get("trackViewUrl", "").split("?")[0],
        "description": (app.get("description") or "")[:800],
        "rating": round(float(app.get("averageUserRating") or 0), 1),
        "platform": "macos" if kind == "mac-software" else "ios",
    }
    if isinstance(price, (int, float)) and price > 0:
        fields["status"] = "expired"
    return fields


# ─── Ảnh đại diện ───────────────────────────────────────────────────

def extract_image(html: str) -> str:
    if not html or "<" not in html:
        return ""
    try:
        soup = BeautifulSoup(html, "html.parser")
        for attr in ("og:image", "twitter:image"):
            tag = soup.find("meta", attrs={"property": attr}) or soup.find("meta", attrs={"name": attr})
            if tag and tag.get("content", "").startswith("http"):
                return tag["content"]
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or ""
            if src.startswith("http") and not any(x in src.lower() for x in ("avatar", "emoji", "pixel", "logo", ".gif", "badge")):
                return src
    except Exception:
        pass
    return ""


# ─── Chống trùng ────────────────────────────────────────────────────

_NOISE = re.compile(
    r'\((?:steam|epic(?: games)?|gog|itch\.io|indiegala|prime gaming|ubisoft|origin|ea app|drm-free)[^)]*\)'
    r'|\b(?:giveaway|free|key|game|for pc|on steam|on epic games?)\b',
    re.IGNORECASE,
)


def normalize_title(title: str) -> str:
    t = _NOISE.sub(" ", title or "")
    t = re.sub(r'[^a-z0-9]+', '', t.lower())
    return t


def make_dedup_key(platform: str, title: str, app_id: str = "") -> str:
    if app_id:
        return f"app:{app_id}"
    if platform == "game":
        norm = normalize_title(title)
        if len(norm) >= 4:
            return f"game:{norm}"
    return ""
