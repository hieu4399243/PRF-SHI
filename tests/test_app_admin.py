"""Test H6 (khoá query string bị bỏ) + H7 (cảnh báo secret/admin key mặc định)."""

from app import main
from app.core import storage


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


def test_login_hides_db_config_details_when_unavailable(monkeypatch):
    def _boom(username):
        raise storage.UserStoreUnavailableError(
            "User accounts cần DATABASE_URL (Postgres) — không hỗ trợ JSON-file mode."
        )

    monkeypatch.setattr(main.storage, "get_user_by_username", _boom)
    client = _client()
    resp = client.post("/api/login", json={"username": "admin", "password": "test123"})
    assert resp.status_code == 500
    body = resp.get_data(as_text=True)
    assert "DATABASE_URL" not in body
    assert "Postgres" not in body


def test_register_rejects_admin_role():
    client = _client()
    resp = client.post(
        "/api/register",
        json={"username": "u1", "password": "123456", "role": "admin"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "Role không hợp lệ"


def test_register_rejects_missing_doctor_id_for_doctor_role():
    client = _client()
    resp = client.post(
        "/api/register",
        json={"username": "u2", "password": "123456", "role": "doctor"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "doctor_id không hợp lệ"


def test_register_rejects_invalid_doctor_id(monkeypatch):
    monkeypatch.setattr(main.booking, "all_doctors", lambda: [{"id": "bs_real_01"}])
    client = _client()
    resp = client.post(
        "/api/register",
        json={"username": "u3", "password": "123456", "role": "doctor", "doctor_id": "khong-ton-tai"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "doctor_id không hợp lệ"


def test_register_allows_guest_role():
    client = _client()
    resp = client.post(
        "/api/register",
        json={"username": "u4", "password": "123456", "role": "guest"},
    )
    assert resp.status_code != 400 or resp.get_json().get("error") != "Role không hợp lệ"


def test_register_allows_valid_unclaimed_doctor_id(monkeypatch):
    monkeypatch.setattr(main.booking, "all_doctors", lambda: [{"id": "bs_real_01"}])
    monkeypatch.setattr(main.storage, "get_user_by_doctor_id", lambda doctor_id: None)
    client = _client()
    resp = client.post(
        "/api/register",
        json={"username": "u5", "password": "123456", "role": "doctor", "doctor_id": "bs_real_01"},
    )
    assert resp.get_json().get("error") != "doctor_id không hợp lệ"


def test_register_rejects_claimed_doctor_id(monkeypatch):
    monkeypatch.setattr(main.booking, "all_doctors", lambda: [{"id": "bs_real_01"}])
    monkeypatch.setattr(
        main.storage, "get_user_by_doctor_id",
        lambda doctor_id: {"id": "existing-user", "doctor_id": "bs_real_01"},
    )
    client = _client()
    resp = client.post(
        "/api/register",
        json={"username": "u6", "password": "123456", "role": "doctor", "doctor_id": "bs_real_01"},
    )
    assert resp.status_code == 409
    assert resp.get_json()["error"] == "doctor_id đã được đăng ký"


def test_default_key_warnings_pure_function():
    warnings = main._default_key_warnings("shi-nha-khoa-demo-key")
    assert len(warnings) == 1
    assert any("SECRET_KEY" in w for w in warnings)

    warnings = main._default_key_warnings("custom-secret")
    assert warnings == []
