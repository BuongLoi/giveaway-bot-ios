import time
import xml.etree.ElementTree as ET
import requests
from bot.sources.base import BaseSource
from bot.config import REQUEST_TIMEOUT, REDDIT_USER_AGENT

try:
    import feedparser
except ImportError:
    feedparser = None


def _parse_feed_fallback(xml_bytes: bytes) -> list:
    """
    Fallback parser bằng xml.etree.ElementTree (Standard Library)
    hỗ trợ cả RSS 2.0 (<item>) và Atom (<entry>) khi chưa cài đặt feedparser.
    """
    entries = []
    root = ET.fromstring(xml_bytes)

    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or link).strip()
        published = (item.findtext("pubDate") or "").strip()
        content = (
            item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded")
            or item.findtext("description")
            or ""
        )
        entries.append({
            "title": title,
            "link": link,
            "guid": guid,
            "published": published,
            "content": content,
        })

    if entries:
        return entries

    atom_ns = "{http://www.w3.org/2005/Atom}"
    for entry in root.findall(f".//{atom_ns}entry"):
        title = (entry.findtext(f"{atom_ns}title") or "").strip()
        link = ""
        link_el = entry.find(f"{atom_ns}link")
        if link_el is not None:
            link = link_el.attrib.get("href", "").strip()
        guid = (entry.findtext(f"{atom_ns}id") or link).strip()
        published = (
            entry.findtext(f"{atom_ns}published")
            or entry.findtext(f"{atom_ns}updated")
            or ""
        ).strip()
        content = (
            entry.findtext(f"{atom_ns}content")
            or entry.findtext(f"{atom_ns}summary")
            or ""
        )
        entries.append({
            "title": title,
            "link": link,
            "guid": guid,
            "published": published,
            "content": content,
        })

    return entries


class RSSSource(BaseSource):
    def __init__(self, name: str, feed_url: str, enabled: bool = True):
        super().__init__(name, enabled)
        self.feed_url = feed_url

    def fetch(self) -> list:
        if not self.enabled:
            self.logger.debug("Source bị tắt, bỏ qua.")
            return []

        self.logger.info(f"Đang tải RSS từ {self.feed_url}")
        results = []
        is_reddit = "reddit.com" in self.feed_url.lower()

        if is_reddit:
            # Nghỉ ngắn và dùng User-Agent chuẩn Reddit API để tránh lỗi 429 Too Many Requests
            time.sleep(2.5)
            headers = {'User-Agent': REDDIT_USER_AGENT or 'python:me.buongloi.giveawaybot:v2.1 (by /u/BuongLoi)'}
        else:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) GiveawayBot/2.1'}

        try:
            response = requests.get(self.feed_url, headers=headers, timeout=REQUEST_TIMEOUT)
            if response.status_code == 429 and is_reddit:
                self.logger.warning(f"Reddit trả về 429 cho {self.feed_url}, đợi 6s rồi thử lại...")
                time.sleep(6)
                response = requests.get(self.feed_url, headers=headers, timeout=REQUEST_TIMEOUT)

            response.raise_for_status()

            if feedparser is not None:
                feed = feedparser.parse(response.content)
                for entry in feed.entries:
                    title = getattr(entry, 'title', '')
                    link = getattr(entry, 'link', '')
                    guid = getattr(entry, 'id', link)
                    published = getattr(entry, 'published', getattr(entry, 'updated', ''))

                    content = ""
                    if hasattr(entry, 'content'):
                        content = entry.content[0].value
                    elif hasattr(entry, 'summary'):
                        content = entry.summary
                    elif hasattr(entry, 'description'):
                        content = entry.description

                    results.append({
                        'title': title,
                        'link': link,
                        'guid': guid,
                        'published': published,
                        'content': content
                    })
            else:
                results = _parse_feed_fallback(response.content)

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Lỗi tải RSS {self.feed_url}: {e}")
        except Exception as e:
            self.logger.error(f"Lỗi phân tích RSS {self.feed_url}: {e}")

        return results
