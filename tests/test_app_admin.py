"""Test H6 (khoá query string bị bỏ) + H7 (cảnh báo secret/admin key mặc định)."""

import uuid

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


def test_admin_doctors_requires_auth():
    client = _client()
    resp = client.get("/api/admin/doctors")
    assert resp.status_code == 401


def test_admin_patient_create_and_update():
    client = _client()
    _login_admin(client)
    suffix = uuid.uuid4().hex[:6]
    phone_1 = f"0988{suffix}"
    phone_2 = f"0977{suffix}"

    create_resp = client.post(
        "/api/admin/patients",
        json={
            "name": "Nguyen Van B",
            "phone": phone_1,
            "email": f"b_{suffix}@example.com",
            "address": "HCM",
            "notes": "test note",
        },
    )
    assert create_resp.status_code == 201
    body = create_resp.get_json()
    assert body["ok"] is True
    patient_id = body["patient"]["id"]

    list_resp = client.get("/api/admin/patients")
    assert list_resp.status_code == 200
    patients = list_resp.get_json()["patients"]
    assert any(p["id"] == patient_id for p in patients)

    update_resp = client.put(
        f"/api/admin/patients/{patient_id}",
        json={
            "name": "Nguyen Van B Updated",
            "phone": phone_2,
        },
    )
    assert update_resp.status_code == 200
    updated = update_resp.get_json()["patient"]
    assert updated["name"] == "Nguyen Van B Updated"
    assert updated["phone"] == phone_2


def test_admin_doctor_create_and_update():
    client = _client()
    _login_admin(client)

    meta = client.get("/api/admin/meta").get_json()
    dept_code = meta["departments"][0]["code"]
    doctor_id = f"bs_test_{uuid.uuid4().hex[:8]}"

    create_resp = client.post(
        "/api/admin/doctors",
        json={
            "id": doctor_id,
            "name": "BS. Test Admin",
            "service_code": dept_code,
            "phone": "0900000111",
            "email": "bs_test_admin@shi.local",
        },
    )
    assert create_resp.status_code == 201

    update_resp = client.put(
        f"/api/admin/doctors/{doctor_id}",
        json={
            "name": "BS. Test Admin Updated",
            "service_code": dept_code,
            "phone": "0900000222",
        },
    )
    assert update_resp.status_code == 200
    updated = update_resp.get_json()["doctor"]
    assert updated["name"] == "BS. Test Admin Updated"
    assert updated["phone"] == "0900000222"


def test_default_key_warnings_pure_function():
    warnings = main._default_key_warnings("shi-nha-khoa-demo-key")
    assert len(warnings) == 1
    assert any("SECRET_KEY" in w for w in warnings)

    warnings = main._default_key_warnings("custom-secret")
    assert warnings == []
