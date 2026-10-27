from datetime import datetime, timedelta, timezone

import pytest

from bot.database import init_db, find_existing, get_connection
from bot.enrich import parse_worth, parse_expiry, extract_app_store_id, make_dedup_key, app_info_to_fields
from bot.sources.epic import parse_epic_response
from bot.sources.gamerpower import parse_gamerpower_response


def _iso(dt):
    return dt.replace(microsecond=0).isoformat()


NOW = datetime.now(timezone.utc)

EPIC_SAMPLE = {"data": {"Catalog": {"searchStore": {"elements": [
    {
        "title": "Sker Ritual", "id": "abc", "description": "Co-op horror FPS",
        "catalogNs": {"mappings": [{"pageSlug": "sker-ritual"}]},
        "keyImages": [{"type": "OfferImageWide", "url": "https://cdn.epic/sker.jpg"}],
        "price": {"totalPrice": {"originalPrice": 2999, "currencyInfo": {"decimals": 2},
                                 "fmtPrice": {"originalPrice": "$29.99"}}},
        "promotions": {"promotionalOffers": [{"promotionalOffers": [{
            "startDate": _iso(NOW - timedelta(days=1)), "endDate": _iso(NOW + timedelta(days=6)),
            "discountSetting": {"discountPercentage": 0}}]}], "upcomingPromotionalOffers": []},
    },
    {
        "title": "Future Game", "id": "def", "productSlug": "future-game",
        "keyImages": [], "price": {},
        "promotions": {"promotionalOffers": [], "upcomingPromotionalOffers": [{"promotionalOffers": [{
            "startDate": _iso(NOW + timedelta(days=6)), "endDate": _iso(NOW + timedelta(days=13)),
            "discountSetting": {"discountPercentage": 0}}]}]},
    },
    {"title": "Mystery Game", "promotions": {}},
    {"title": "Paid Game 50% off", "promotions": {"promotionalOffers": [{"promotionalOffers": [{
        "startDate": "", "endDate": "", "discountSetting": {"discountPercentage": 50}}]}]}},
]}}}}


def test_parse_epic():
    items = parse_epic_response(EPIC_SAMPLE)
    assert [i["title"] for i in items] == ["Sker Ritual", "Future Game"]
    sker, future = items
    assert sker["status"] == "active" and future["status"] == "upcoming"
    assert sker["worth"] == "$29.99" and sker["worth_value"] == 29.99
    assert sker["link"] == "https://store.epicgames.com/en-US/p/sker-ritual"
    assert sker["image_url"] == "https://cdn.epic/sker.jpg"
    assert sker["expires_at"] > _iso(NOW)


def test_parse_gamerpower():
    data = [
        {"id": 1, "title": "Ancient Evil (IndieGala) Giveaway", "worth": "$4.99", "platforms": "PC, DRM-Free",
         "end_date": "2026-12-30 23:59:00", "image": "https://gp/img.jpg", "open_giveaway_url": "https://gp/open/1",
         "gamerpower_url": "https://gp/1", "status": "Active", "type": "Game", "description": "d", "instructions": "i"},
        {"id": 2, "title": "Mobile thing", "worth": "N/A", "platforms": "iOS", "end_date": "N/A",
         "open_giveaway_url": "https://gp/open/2", "status": "Active", "type": "Game"},
        {"id": 3, "title": "Old", "platforms": "PC", "open_giveaway_url": "x", "status": "Expired"},
    ]
    items = parse_gamerpower_response(data)
    assert len(items) == 2
    assert items[0]["platform"] == "game" and items[0]["store"] == "indiegala"
    assert items[0]["expires_at"].startswith("2026-12-30T23:59:00")
    assert items[0]["worth_value"] == 4.99
    assert items[1]["platform"] == "ios" and items[1]["worth"] == "" and items[1]["expires_at"] == ""


def test_enrich_helpers():
    assert parse_worth("[iOS] ProCamera [$4.99 -> Free]") == ("$4.99", 4.99)
    assert parse_worth("PicPost – Now FREE! (Was $1.99)")[1] == 1.99
    assert parse_worth("Nothing here") == ("", 0.0)

    base = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    assert parse_expiry("48 hours left", base) == "2026-10-29T12:00:00+00:00"
    assert parse_expiry("expires October 31, 2026", base) == "2026-10-31T23:59:00+00:00"
    assert parse_expiry("until Nov 2", base) == "2026-11-02T23:59:00+00:00"
    assert parse_expiry("limited time", base) == ""

    assert extract_app_store_id("https://apps.apple.com/us/app/procamera/id694647259?mt=8") == "694647259"
    assert extract_app_store_id("no link") == ""

    assert make_dedup_key("game", "Sker Ritual (Epic Games) Giveaway") == make_dedup_key("game", "Sker Ritual")
    assert make_dedup_key("ios", "Anything", "123456") == "app:123456"
    assert make_dedup_key("windows", "Some App") == ""

    assert app_info_to_fields({"price": 2.99, "kind": "software"})["status"] == "expired"
    assert "status" not in app_info_to_fields({"price": 0.0, "kind": "mac-software"})
    assert app_info_to_fields({"price": 0.0, "kind": "mac-software"})["platform"] == "macos"


@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    db = str(tmp_path / "v3.db")
    monkeypatch.setattr("bot.database.DB_PATH", db)
    init_db()
    return db


def test_pipeline_structured_dedup_and_activation(temp_db, monkeypatch):
    import main
    sent = []
    monkeypatch.setattr(main, "send_rich", lambda caption, photo="", buttons=None: sent.append((caption, photo, buttons)) or True)
    monkeypatch.setattr(main.time, "sleep", lambda s: None)
    monkeypatch.setattr(main, "TELEGRAM_PLATFORMS", [])

    sker, future = parse_epic_response(EPIC_SAMPLE)
    main.process_giveaway("epic_games", sker, dry_run=False, backfill=False)
    main.process_giveaway("epic_games", future, dry_run=False, backfill=False)
    assert len(sent) == 1  # upcoming không gửi
    caption, photo, buttons = sent[0]
    assert "<s>$29.99</s>" in caption and "MIỄN PHÍ" in caption and "Hết hạn" in caption
    assert photo == "https://cdn.epic/sker.jpg"
    assert buttons[0][1] == "https://store.epicgames.com/en-US/p/sker-ritual"

    # Cùng game từ GamerPower -> bị chống trùng theo tên
    gp = parse_gamerpower_response([{"id": 9, "title": "Sker Ritual (Epic Games) Giveaway", "platforms": "PC, Epic Games Store",
                                     "open_giveaway_url": "https://gp/open/9", "gamerpower_url": "https://gp/9",
                                     "status": "Active", "type": "Game", "end_date": "N/A", "worth": "$29.99"}])[0]
    main.process_giveaway("gamerpower", gp, dry_run=False, backfill=False)
    assert len(sent) == 1
    conn = get_connection()
    assert conn.execute("SELECT COUNT(*) FROM giveaways").fetchone()[0] == 2
    conn.close()

    # Future game chuyển sang active -> gửi thông báo
    future_active = dict(future, status="active")
    main.process_giveaway("epic_games", future_active, dry_run=False, backfill=False)
    assert len(sent) == 2
    row = find_existing(future["link"])
    assert row["status"] == "active" and row["notified_at"]


def test_pipeline_platform_filter(temp_db, monkeypatch):
    import main
    sent = []
    monkeypatch.setattr(main, "send_rich", lambda *a, **k: sent.append(a) or True)
    monkeypatch.setattr(main, "TELEGRAM_PLATFORMS", ["ios"])
    sker, _ = parse_epic_response(EPIC_SAMPLE)
    main.process_giveaway("epic_games", sker, dry_run=False, backfill=False)
    assert sent == []
    assert find_existing(sker["link"])["notified_at"]  # đánh dấu đã xử lý, không lặp lại


def test_maintenance_expiry(temp_db, monkeypatch):
    import maintenance
    from bot.database import insert_giveaway
    monkeypatch.setattr(maintenance, "itunes_lookup", lambda ids: {"555555": {"price": 1.99}})
    base = {"source": "t", "title": "x", "confidence_score": 80, "platform": "game"}
    insert_giveaway(dict(base, canonical_url="u1", expires_at=_iso(NOW - timedelta(hours=1))))
    insert_giveaway(dict(base, canonical_url="u2", expires_at=_iso(NOW + timedelta(days=2))))
    insert_giveaway(dict(base, canonical_url="u3", platform="ios", app_id="555555"))
    insert_giveaway(dict(base, canonical_url="u4", status="upcoming", starts_at=_iso(NOW - timedelta(minutes=5)),
                         expires_at=_iso(NOW + timedelta(days=5))))
    stats = maintenance.run()
    assert stats["expired_by_date"] == 1 and stats["expired_by_price"] == 1 and stats["activated"] == 1
    statuses = {r["canonical_url"]: r["status"] for r in get_connection().execute("SELECT canonical_url, status FROM giveaways")}
    assert statuses == {"u1": "expired", "u2": "active", "u3": "expired", "u4": "active"}
