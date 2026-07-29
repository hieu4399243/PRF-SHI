"""Test H6 (khoá query string bị bỏ) + H7 (cảnh báo secret/admin key mặc định)."""

from app import main


def _client():
    main.app.config["TESTING"] = True
    return main.app.test_client()


def _login_admin(client):
    resp = client.post(
        "/api/login",
        json={"username": "admin", "password": "test123"},
    )
    assert resp.status_code == 200


def test_admin_rejects_query_string_key():
    client = _client()
    resp = client.get("/api/admin/appointments?key=legacy-key")
    assert resp.status_code == 401


def test_admin_accepts_with_jwt_cookie():
    client = _client()
    _login_admin(client)
    resp = client.get("/api/admin/appointments")
    assert resp.status_code == 200


def test_admin_rejects_wrong_or_missing_key():
    client = _client()
    resp = client.get("/api/admin/appointments")
    assert resp.status_code == 401


def test_default_key_warnings_pure_function():
    warnings = main._default_key_warnings("shi-nha-khoa-demo-key")
    assert len(warnings) == 1
    assert any("SECRET_KEY" in w for w in warnings)

    warnings = main._default_key_warnings("custom-secret")
    assert warnings == []
