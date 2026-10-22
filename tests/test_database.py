import pytest
import os
import sqlite3
from bot.database import init_db, check_and_save_giveaway, mark_as_notified, get_connection


@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    test_db = "test_giveaways.db"
    monkeypatch.setattr("bot.database.DB_PATH", test_db)
    init_db()
    yield
    if os.path.exists(test_db):
        os.remove(test_db)


def test_check_and_save_new():
    result = check_and_save_giveaway(
        "test", "https://test.com", "guid1", "Title", "2026-01-01",
        "hash1", "codes1", 80, codes="AAAA-BBBB-CCCC", platform="ios", tags="🍎 iOS APP"
    )
    assert result['action'] == 'new'
    assert result['id'] > 0

    conn = get_connection()
    row = conn.execute("SELECT * FROM giveaways WHERE id = ?", (result['id'],)).fetchone()
    conn.close()
    assert row['codes'] == "AAAA-BBBB-CCCC"
    assert row['platform'] == "ios"
    assert row['tags'] == "🍎 iOS APP"


def test_check_and_save_resend_when_not_notified():
    # Insert new nhưng chưa mark_as_notified
    check_and_save_giveaway(
        "test", "https://test.com", "guid1", "Title", "2026-01-01", "hash1", "codes1", 0
    )
    # Quét lại khi chưa gửi TG -> phải trả về 'resend'
    result = check_and_save_giveaway(
        "test", "https://test.com", "guid1", "Title", "2026-01-01", "hash1", "codes1", 0
    )
    assert result['action'] == 'resend'


def test_check_and_save_skip():
    # Insert new và đánh dấu đã gửi thông báo
    first = check_and_save_giveaway(
        "test", "https://test.com", "guid1", "Title", "2026-01-01", "hash1", "codes1", 0
    )
    mark_as_notified(first['id'])

    # Check again with same codes_hash -> phải trả về 'skip'
    result = check_and_save_giveaway(
        "test", "https://test.com", "guid1", "Title", "2026-01-01", "hash2", "codes1", 0
    )
    assert result['action'] == 'skip'


def test_check_and_save_update():
    # Insert new
    first = check_and_save_giveaway(
        "test", "https://test.com", "guid1", "Title", "2026-01-01", "hash1", "codes1", 0
    )
    mark_as_notified(first['id'])

    # Check again with different codes_hash -> phải trả về 'update'
    result = check_and_save_giveaway(
        "test", "https://test.com", "guid1", "Title", "2026-01-01",
        "hash2", "codes2", 50, codes="NEW1-NEW2-NEW3"
    )
    assert result['action'] == 'update'
