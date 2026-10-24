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
