"""Test H6 (khoá query string bị bỏ) + H7 (cảnh báo secret/admin key mặc định)."""

from app import app


def _client():
    app.app.config["TESTING"] = True
    return app.app.test_client()


def test_admin_rejects_query_string_key():
    client = _client()
    resp = client.get(f"/api/admin/appointments?key={app.ADMIN_KEY}")
    assert resp.status_code == 401


def test_admin_accepts_header_key():
    client = _client()
    resp = client.get(
        "/api/admin/appointments",
        headers={"X-Admin-Key": app.ADMIN_KEY},
    )
    assert resp.status_code == 200


def test_admin_rejects_wrong_or_missing_key():
    client = _client()
    resp = client.get("/api/admin/appointments")
    assert resp.status_code == 401

    resp = client.get(
        "/api/admin/appointments",
        headers={"X-Admin-Key": "wrong-key"},
    )
    assert resp.status_code == 401


def test_default_key_warnings_pure_function():
    warnings = app._default_key_warnings("shi-nha-khoa-demo-key", "shi-admin-demo")
    assert len(warnings) == 2
    assert any("SECRET_KEY" in w for w in warnings)
    assert any("ADMIN_KEY" in w for w in warnings)

    warnings = app._default_key_warnings("custom-secret", "custom-admin")
    assert warnings == []
