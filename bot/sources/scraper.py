import urllib.robotparser
import urllib.parse
import requests
import time
import logging
from bs4 import BeautifulSoup
from typing import Optional

logger = logging.getLogger(__name__)

# Cache memory để tránh cào cùng 1 URL nhiều lần (LRU đơn giản)
_scrape_cache = {}
MAX_CACHE_SIZE = 1000

# Cache cho robotparser để không tải lại robots.txt liên tục
_robots_cache = {}

MAX_RESPONSE_SIZE = 2 * 1024 * 1024 # 2MB

def can_fetch(url: str, user_agent: str) -> bool:
    """Kiểm tra robots.txt xem URL có được phép cào không."""
    parsed_url = urllib.parse.urlparse(url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    robots_url = f"{base_url}/robots.txt"
    
    if robots_url not in _robots_cache:
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)
        try:
            rp.read()
            _robots_cache[robots_url] = rp
        except Exception as e:
            logger.warning(f"Lỗi đọc robots.txt từ {robots_url}: {e}")
            # Mặc định nếu không đọc được robots.txt thì vẫn cho phép
            return True
            
    return _robots_cache[robots_url].can_fetch(user_agent, url)

def fetch_html_content(url: str, user_agent: str = "GiveawayBot/1.0") -> Optional[str]:
    """
    Tải nội dung HTML từ URL.
    - Kiểm tra robots.txt
    - Giới hạn dung lượng 2MB
    - Trả về text sạch.
    """
    if url in _scrape_cache:
        return _scrape_cache[url]
        
    if not can_fetch(url, user_agent):
        logger.info(f"Scraper bị từ chối bởi robots.txt: {url}")
        return None
        
    headers = {'User-Agent': user_agent}
    try:
        # stream=True để không tải toàn bộ file lớn vào bộ nhớ ngay lập tức
        response = requests.get(url, headers=headers, stream=True, timeout=15, allow_redirects=True)
        response.raise_for_status()
        
        # Kiểm tra header content-length trước
        content_length = response.headers.get('Content-Length')
        if content_length and int(content_length) > MAX_RESPONSE_SIZE:
            logger.warning(f"Bỏ qua {url} do dung lượng lớn ({content_length} bytes)")
            return None
            
        content = b""
        for chunk in response.iter_content(chunk_size=8192):
            content += chunk
            if len(content) > MAX_RESPONSE_SIZE:
                logger.warning(f"Ngắt kết nối {url} vì vượt quá {MAX_RESPONSE_SIZE} bytes.")
                return None
                
        # Nếu OK, lưu vào cache
        html_content = content.decode('utf-8', errors='ignore')
        
        # Quản lý size cache
        if len(_scrape_cache) >= MAX_CACHE_SIZE:
            # Xóa item đầu tiên (cũ nhất)
            _scrape_cache.pop(next(iter(_scrape_cache)))
            
        _scrape_cache[url] = html_content
        return html_content
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Lỗi fallback scraper {url}: {e}")
        return None
