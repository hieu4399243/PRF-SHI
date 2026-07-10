"""Test M3 (MAX_CONTENT_LENGTH) + M7 (validate session id) + M8 (rate limit)."""

import json

from app import app


def _client():
    app.app.config["TESTING"] = True
    return app.app.test_client()


def test_oversized_body_rejected():
    client = _client()
    big_message = "a" * (app.app.config["MAX_CONTENT_LENGTH"] + 1024)
    resp = client.post(
        "/api/chat",
        data=json.dumps({"message": big_message}),
        content_type="application/json",
    )
    assert resp.status_code == 413


def test_normal_body_accepted():
    client = _client()
    resp = client.post(
        "/api/chat",
        data=json.dumps({"message": "xin chao"}),
        content_type="application/json",
    )
    assert resp.status_code != 413


def test_resolve_sid_rejects_malformed_client_session():
    client = _client()
    resp = client.post(
        "/api/start",
        data=json.dumps({"session": "not-a-valid-uuid"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.get_json()["session"] != "not-a-valid-uuid"


def test_resolve_sid_accepts_valid_uuid4_hex():
    client = _client()
    valid_sid = "0123456789abcdef0123456789abcdef"
    resp = client.post(
        "/api/start",
        data=json.dumps({"session": valid_sid}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.get_json()["session"] == valid_sid


def test_resolve_sid_rejects_non_string_session():
    client = _client()

    resp = client.post(
        "/api/start",
        data=json.dumps({"session": 123}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["session"] != 123
    assert isinstance(body["session"], str)

    resp2 = client.post(
        "/api/start",
        data=json.dumps({"session": [1, 2, 3]}),
        content_type="application/json",
    )
    assert resp2.status_code == 200
    body2 = resp2.get_json()
    assert body2["session"] != [1, 2, 3]
    assert isinstance(body2["session"], str)


def test_rate_limit_blocks_after_threshold(monkeypatch):
    monkeypatch.setattr(app, "_RATE_LIMIT", 3)
    client = _client()

    for _ in range(3):
        resp = client.post(
            "/api/start",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 200

    resp = client.post(
        "/api/start",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert resp.status_code == 429


def test_rate_limit_applies_to_admin_routes(monkeypatch):
    monkeypatch.setattr(app, "_RATE_LIMIT", 3)
    client = _client()

    for _ in range(3):
        resp = client.get(
            "/api/admin/meta",
            headers={"X-Admin-Key": app.ADMIN_KEY},
        )
        assert resp.status_code == 200

    resp = client.get(
        "/api/admin/meta",
        headers={"X-Admin-Key": app.ADMIN_KEY},
    )
    assert resp.status_code == 429
