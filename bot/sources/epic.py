"""Nguồn Epic Games Store: game đang miễn phí và sắp miễn phí (API JSON chính thức của store)."""
import requests
from bot.sources.base import BaseSource
from bot.config import REQUEST_TIMEOUT
from bot.enrich import parse_datetime_any, worth_to_value

EPIC_API = ("https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
            "?locale=en-US&country=US&allowCountries=US")


def _slug(el: dict) -> str:
    for mapping in (el.get("catalogNs") or {}).get("mappings") or []:
        if mapping.get("pageSlug"):
            return mapping["pageSlug"]
    for mapping in el.get("offerMappings") or []:
        if mapping.get("pageSlug"):
            return mapping["pageSlug"]
    slug = el.get("productSlug") or el.get("urlSlug") or ""
    return slug.split("/")[0] if slug else ""


def _image(el: dict) -> str:
    images = {img.get("type"): img.get("url") for img in el.get("keyImages") or []}
    for key in ("OfferImageWide", "DieselStoreFrontWide", "featuredMedia", "Thumbnail", "OfferImageTall"):
        if images.get(key):
            return images[key]
    return next(iter(images.values()), "") if images else ""


def _free_window(offers_block: list):
    """Trả về (start, end) của khuyến mãi giảm 100% đầu tiên, hoặc None."""
    for group in offers_block or []:
        for offer in group.get("promotionalOffers") or []:
            discount = (offer.get("discountSetting") or {}).get("discountPercentage")
            if discount == 0:
                return offer.get("startDate", ""), offer.get("endDate", "")
    return None


def parse_epic_response(data: dict) -> list:
    elements = (((data or {}).get("data") or {}).get("Catalog") or {}).get("searchStore", {}).get("elements") or []
    items = []
    for el in elements:
        title = (el.get("title") or "").strip()
        if not title or "mystery game" in title.lower():
            continue
        promos = el.get("promotions") or {}
        current = _free_window(promos.get("promotionalOffers"))
        upcoming = None if current else _free_window(promos.get("upcomingPromotionalOffers"))
        window = current or upcoming
        if not window:
            continue
        slug = _slug(el)
        url = f"https://store.epicgames.com/en-US/p/{slug}" if slug else "https://store.epicgames.com/en-US/free-games"
        price = ((el.get("price") or {}).get("totalPrice") or {})
        original_fmt = (price.get("fmtPrice") or {}).get("originalPrice") or ""
        original_cents = price.get("originalPrice") or 0
        worth_value = round(original_cents / (10 ** (price.get("currencyInfo") or {}).get("decimals", 2)), 2) \
            if original_cents else worth_to_value(original_fmt)
        items.append({
            "structured": True,
            "title": title,
            "link": url,
            "guid": f"epic:{el.get('id') or slug}:{window[0][:10]}",
            "published": window[0],
            "content": el.get("description") or "",
            "description": el.get("description") or "",
            "platform": "game",
            "store": "epic",
            "store_url": url,
            "image_url": _image(el),
            "worth": original_fmt if original_fmt and original_fmt not in ("0", "Free") else "",
            "worth_value": worth_value,
            "starts_at": parse_datetime_any(window[0]),
            "expires_at": parse_datetime_any(window[1]),
            "status": "active" if current else "upcoming",
            "tags": ["🎮 FREE GAME", "Epic Games"],
        })
    return items


class EpicGamesSource(BaseSource):
    def __init__(self, enabled: bool = True):
        super().__init__("epic_games", enabled)

    def fetch(self) -> list:
        if not self.enabled:
            return []
        self.logger.info("Đang tải Epic Games free promotions...")
        try:
            r = requests.get(EPIC_API, timeout=REQUEST_TIMEOUT,
                             headers={"User-Agent": "Mozilla/5.0 GiveawayHunter/3.0"})
            r.raise_for_status()
            return parse_epic_response(r.json())
        except Exception as e:
            self.logger.error(f"Lỗi tải Epic Games API: {e}")
            return []
