import pytest
import responses
from unittest.mock import patch, MagicMock
from bot.sources.scraper import can_fetch, fetch_html_content, _robots_cache, _scrape_cache

@pytest.fixture(autouse=True)
def clear_caches():
    _robots_cache.clear()
    _scrape_cache.clear()

def test_can_fetch_allowed():
    with patch('urllib.robotparser.RobotFileParser') as MockParser:
        instance = MockParser.return_value
        instance.can_fetch.return_value = True
        
        assert can_fetch("https://example.com/page", "GiveawayBot/1.0") is True
        instance.set_url.assert_called_with("https://example.com/robots.txt")

def test_can_fetch_disallowed():
    with patch('urllib.robotparser.RobotFileParser') as MockParser:
        instance = MockParser.return_value
        instance.can_fetch.return_value = False
        
        assert can_fetch("https://example.com/page", "GiveawayBot/1.0") is False

@responses.activate
def test_fetch_html_content_success():
    url = "https://example.com/success"
    html = "<html><body>Test</body></html>"
    responses.add(responses.GET, url, body=html, status=200)
    
    with patch('bot.sources.scraper.can_fetch', return_value=True):
        content = fetch_html_content(url)
        assert content == html
        assert url in _scrape_cache # Đã được cache

@responses.activate
def test_fetch_html_content_too_large_header():
    url = "https://example.com/large_header"
    # Giả lập header báo dung lượng 3MB
    responses.add(
        responses.GET, 
        url, 
        headers={'Content-Length': str(3 * 1024 * 1024)},
        body="x" * 1024,
        status=200
    )
    
    with patch('bot.sources.scraper.can_fetch', return_value=True):
        content = fetch_html_content(url)
        assert content is None # Phải bị bỏ qua

@responses.activate
def test_fetch_html_content_too_large_stream():
    url = "https://example.com/large_stream"
    
    # Bypass requests để mô phỏng stream vượt quá giới hạn
    import requests
    class MockIterContentResponse:
        status_code = 200
        headers = {}
        def raise_for_status(self): pass
        def iter_content(self, chunk_size):
            # Tạo 300 chunk x 8KB = 2.4MB
            for _ in range(300):
                yield b"x" * 8192
                
    def mock_get(*args, **kwargs):
        return MockIterContentResponse()
        
    with patch('requests.get', side_effect=mock_get):
        with patch('bot.sources.scraper.can_fetch', return_value=True):
            content = fetch_html_content(url)
            assert content is None # Phải bị ngắt khi vượt quá giới hạn
