import pytest
from bot.extractor import (
    extract_codes, is_excluded, calculate_confidence, extract_text_from_html,
    detect_platform, is_relevant_giveaway, evaluate_article_confidence
)


def test_extract_text_from_html():
    html = "<p>Some text</p><script>alert(1);</script><code>test-code</code>"
    text = extract_text_from_html(html)
    assert "Some text" in text
    assert "alert(1)" not in text
    assert "test-code" not in text


def test_is_excluded():
    assert is_excluded("550e8400-e29b-41d4-a716-446655440000")  # UUID
    assert is_excluded("https://google.com")
    assert is_excluded("0123456789abcdef0123456789abcdef01234567")  # Git sha
    assert is_excluded("2026-10-22")  # Date
    assert is_excluded("1920x1080p60")  # Resolution
    assert is_excluded("iphone15pro2026")  # Lowercase word + number
    assert is_excluded("some-lowercase-slug-123")  # URL slug
    assert not is_excluded("AAAA-BBBB-CCCC")


def test_extract_codes_valid():
    html = "<div>Here is your serial: AAAA-BBBB-CCCC-DDDD, enjoy!</div>"
    codes, score = extract_codes(html)
    assert "AAAA-BBBB-CCCC-DDDD" in codes
    assert score == 50  # Vì có từ khóa "serial"


def test_extract_codes_inside_code_tag():
    html = "<p>Use this license key: <code>WIN9-PRO8-KEY7-FREE</code> to activate.</p>"
    codes, score = extract_codes(html)
    assert "WIN9-PRO8-KEY7-FREE" in codes
    assert score == 50


def test_extract_codes_no_context():
    html = "<div>Take this: AAAA-BBBB-CCCC-DDDD, enjoy!</div>"
    codes, score = extract_codes(html)
    assert "AAAA-BBBB-CCCC-DDDD" in codes
    assert score == 0  # Không có từ khóa liên quan


def test_extract_codes_alnum():
    html = "<div>Activation key: 1A2B3C4D5E6F7G8H9I0J, grab it fast!</div>"
    codes, score = extract_codes(html)
    assert "1A2B3C4D5E6F7G8H9I0J" in codes
    assert score == 50


def test_detect_platform_ios_and_windows():
    assert detect_platform("[iOS] [$4.99 -> Free] ProCamera App", "", "https://apps.apple.com/app/id123", "reddit_apphookup") == "ios"
    assert detect_platform("Daily Apps Gone Free", "Best iPhone apps today", "https://appadvice.com/post", "appadvice") == "ios"
    assert detect_platform("IObit Uninstaller Pro 14 Free License Key [Windows]", "", "", "tickcoupon") == "windows"
    assert detect_platform("[Steam] (Game) Metro 2033 Redux Free", "", "https://store.steampowered.com/app/1", "reddit_freegamefindings") == "game"


def test_is_relevant_giveaway_and_confidence():
    # Bài báo tin tức thông thường trên trang công nghệ -> phải bị loại
    assert not is_relevant_giveaway("Apple announces new MacBook Pro M4", "Full review of hardware specs", "digitaltrends", [])

    # Bài đã hết hạn (*EXPIRED*) -> phải bị loại
    assert not is_relevant_giveaway("*EXPIRED* Math Middle & High School PRO", "Free iOS app", "gotd_ios", [])

    # Bài Apps Gone Free trên iOS -> phải được nhận và có điểm tin cậy cao dù không có serial text
    title = "[iOS] [AdGuard Pro] [$9.99 -> Free] [Lifetime AdBlocker for iPhone & iPad]"
    text = "Download free on the App Store: https://apps.apple.com/us/app/id1126386264"
    assert is_relevant_giveaway(title, text, "reddit_apphookup", [])
    score = evaluate_article_confidence(title, text, [], 0, "https://apps.apple.com/us/app/id1126386264", "reddit_apphookup")
    assert score >= 80
