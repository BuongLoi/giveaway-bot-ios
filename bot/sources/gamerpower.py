"""
Nguồn GamerPower API: tổng hợp game miễn phí trên Steam, GOG, Epic, Prime Gaming,
itch.io, Ubisoft, IndieGala, Android, iOS... kèm giá gốc, ảnh và hạn nhận.
Tài liệu: https://www.gamerpower.com/api-read
"""
import requests
from bot.sources.base import BaseSource
from bot.config import REQUEST_TIMEOUT
from bot.enrich import parse_datetime_any, worth_to_value

GAMERPOWER_API = "https://www.gamerpower.com/api/giveaways"

STORE_KEYWORDS = [
    ("steam", "steam"), ("epic", "epic"), ("gog", "gog"), ("prime", "prime"),
    ("itch", "itch"), ("ubisoft", "ubisoft"), ("indiegala", "indiegala"),
    ("origin", "ea"), ("ea app", "ea"), ("battle.net", "battlenet"),
    ("ios", "appstore"), ("android", "googleplay"), ("xbox", "xbox"), ("playstation", "playstation"),
]


def _platform_and_store(platforms: str, title: str):
    text = f"{platforms} {title}".lower()
    store = next((s for kw, s in STORE_KEYWORDS if kw in text), "")
    p = (platforms or "").lower()
    if "ios" in p and "pc" not in p:
        return "ios", store or "appstore"
    if "android" in p and "pc" not in p:
        return "android", store or "googleplay"
    return "game", store


def parse_gamerpower_response(data: list) -> list:
    items = []
    if not isinstance(data, list):
        return items
    for g in data:
        if (g.get("status") or "Active").lower() != "active":
            continue
        title = (g.get("title") or "").strip()
        url = g.get("open_giveaway_url") or g.get("gamerpower_url") or ""
        if not title or not url:
            continue
        platform, store = _platform_and_store(g.get("platforms", ""), title)
        worth = g.get("worth") or ""
        description = (g.get("description") or "").strip()
        instructions = (g.get("instructions") or "").strip()
        items.append({
            "structured": True,
            "title": title,
            "link": g.get("gamerpower_url") or url,
            "guid": f"gamerpower:{g.get('id')}",
            "published": g.get("published_date", ""),
            "content": f"{description}\n{instructions}",
            "description": (description + ("\n\nCách nhận:\n" + instructions if instructions else ""))[:800],
            "platform": platform,
            "store": store,
            "store_url": url,
            "image_url": g.get("image") or g.get("thumbnail") or "",
            "worth": worth if worth and worth.upper() != "N/A" else "",
            "worth_value": worth_to_value(worth) if worth and worth.upper() != "N/A" else 0.0,
            "starts_at": "",
            "expires_at": parse_datetime_any(g.get("end_date", "")),
            "status": "active",
            "tags": ["🎮 FREE GAME"] if (g.get("type") or "").lower() == "game" else ["🎁 GIVEAWAY"],
        })
    return items


class GamerPowerSource(BaseSource):
    def __init__(self, enabled: bool = True, giveaway_type: str = "game"):
        super().__init__("gamerpower", enabled)
        self.giveaway_type = giveaway_type

    def fetch(self) -> list:
        if not self.enabled:
            return []
        self.logger.info("Đang tải GamerPower giveaways...")
        try:
            r = requests.get(GAMERPOWER_API, params={"type": self.giveaway_type, "sort-by": "date"},
                             timeout=REQUEST_TIMEOUT, headers={"User-Agent": "Mozilla/5.0 GiveawayHunter/3.0"})
            if r.status_code == 201:  # API trả 201 khi không có giveaway nào
                return []
            r.raise_for_status()
            return parse_gamerpower_response(r.json())
        except Exception as e:
            self.logger.error(f"Lỗi tải GamerPower API: {e}")
            return []
