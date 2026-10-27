import base64
import os
import pytest

pytest.importorskip("flask")
pytest.importorskip("flask_basicauth")

import web_admin
from bot.database import init_db, check_and_save_giveaway


@pytest.fixture
def client(monkeypatch, tmp_path):
    test_db = str(tmp_path / "test_web.db")
    test_env = str(tmp_path / ".env")
    monkeypatch.setattr("bot.database.DB_PATH", test_db)
    monkeypatch.setattr("web_admin.DB_PATH", test_db)
    monkeypatch.setattr("web_admin.ENV_PATH", test_env)
    web_admin.app.config["TESTING"] = True
    web_admin.app.config["BASIC_AUTH_USERNAME"] = "admin"
    web_admin.app.config["BASIC_AUTH_PASSWORD"] = "secret123"
    init_db()

    check_and_save_giveaway(
        source="appadvice",
        canonical_url="https://apps.apple.com/app/id999",
        guid="ios_1",
        title="[iOS] ProCamera [$4.99 -> Free]",
        published_at="2026-10-22",
        content_hash="h1",
        codes_hash="c1",
        confidence_score=85,
        codes="IOS9-FREE-2026",
        platform="ios",
        tags="🍎 iOS APP, 🎁 GIVEAWAY",
        expiry_hint="24 hours only"
    )
    return web_admin.app.test_client()


def _auth_header(user="admin", pw="secret123"):
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_public_endpoints_no_auth_required(client):
    r_health = client.get("/health")
    assert r_health.status_code == 200
    data = r_health.get_json()
    assert data["status"] == "ok"
    assert data["ios_giveaways"] == 1

    r_manifest = client.get("/manifest.json")
    assert r_manifest.status_code == 200
    assert r_manifest.get_json()["display"] == "standalone"

    r_sw = client.get("/sw.js")
    assert r_sw.status_code == 200


def test_protected_routes_require_auth(client):
    assert client.get("/config").status_code == 401
    assert client.get("/logs").status_code == 401
    # Trang xem danh sách giveaway (GET) mở sẵn cho iOS App / PWA
    assert client.get("/giveaways").status_code == 200
    assert client.get("/").status_code == 200


def test_giveaways_filter_and_api(client):
    headers = _auth_header()
    r_ios = client.get("/giveaways?platform=ios", headers=headers)
    assert r_ios.status_code == 200
    html = r_ios.data.decode("utf-8")
    assert "ProCamera" in html
    assert "IOS9-FREE-2026" in html

    r_win = client.get("/giveaways?platform=windows", headers=headers)
    assert r_win.status_code == 200
    assert "ProCamera" not in r_win.data.decode("utf-8")

    r_api = client.get("/api/giveaways?platform=ios", headers=headers)
    assert r_api.status_code == 200
    api_data = r_api.get_json()
    assert api_data["total"] == 1
    assert api_data["items"][0]["platform"] == "ios"
    assert "IOS9-FREE-2026" in api_data["items"][0]["code_list"]


def test_config_checkbox_saving(client):
    headers = _auth_header()
    # Khi checkbox được tick, trình duyệt gửi cả hidden "0" và checkbox "1"
    form_data = {
        "SOURCE_GOTD_IOS": ["0", "1"],
        "SOURCE_TICKCOUPON": ["0"],
        "KEYWORDS": "ios,windows",
        "ADMIN_USERNAME": "admin",
        "ADMIN_PASSWORD": "",  # Để trống không ghi đè mật khẩu cũ
    }
    resp = client.post("/config", data=form_data, headers=headers, follow_redirects=True)
    assert resp.status_code == 200

    page_html = resp.data.decode("utf-8")
    assert 'name="SOURCE_GOTD_IOS" value="1" checked' in page_html
    assert 'name="SOURCE_TICKCOUPON" value="1" checked' not in page_html


def test_api_v2_list_detail_stats(client):
    from bot.database import insert_giveaway
    insert_giveaway({"source": "epic_games", "canonical_url": "https://epic/sker", "title": "Sker Ritual",
                     "platform": "game", "confidence_score": 95, "worth": "$29.99", "worth_value": 29.99,
                     "image_url": "https://img", "store": "epic", "store_url": "https://epic/sker",
                     "expires_at": "2099-01-01T00:00:00+00:00", "status": "active"})
    insert_giveaway({"source": "epic_games", "canonical_url": "https://epic/old", "title": "Old Game",
                     "platform": "game", "confidence_score": 95, "status": "expired"})

    r = client.get("/api/v2/giveaways?platform=game")
    assert r.status_code == 200
    data = r.get_json()
    assert [i["title"] for i in data["items"]] == ["Sker Ritual"]
    item = data["items"][0]
    assert item["worth_value"] == 29.99 and item["claim_url"] == "https://epic/sker" and item["status"] == "active"

    assert client.get("/api/v2/giveaways?status=expired").get_json()["total"] == 1
    assert client.get("/api/v2/giveaways?sort=worth").get_json()["items"][0]["title"] == "Sker Ritual"
    assert client.get("/api/v2/giveaways?q=sker").get_json()["total"] == 1
    assert client.get(f"/api/v2/giveaways?ids={item['id']}").get_json()["total"] == 1

    d = client.get(f"/api/v2/giveaways/{item['id']}")
    assert d.status_code == 200 and d.get_json()["item"]["title"] == "Sker Ritual"
    assert client.get("/api/v2/giveaways/99999").status_code == 404

    s = client.get("/api/v2/stats").get_json()
    assert s["platforms"]["game"] == 1 and s["platforms"]["ios"] == 1
    assert s["total_worth"] == 29.99

    # Trang web cũ không còn hiện bài đã hết hạn
    assert "Old Game" not in client.get("/giveaways").data.decode("utf-8")
