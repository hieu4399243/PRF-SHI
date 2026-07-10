"""
Tests cho C4 (`/api/ics/<code>` không xác thực -> lộ dữ liệu sức khỏe).

Bug gốc:
  - `download_ics` gọi `booking.get_appointment(code)` mà không so khớp
    session sở hữu -> ai biết/đoán được `code` cũng tải được thông tin
    lịch hẹn (tên, dịch vụ khám...).
  - `booking._generate_code()` dùng `random.choices` (không phải CSPRNG)
    -> mã dễ đoán/dò hơn cần thiết.

Fix:
  - `download_ics` so `appt["session"]` với `resolve_sid()` hiện tại, không
    khớp hoặc không tồn tại -> 404 đồng nhất (chống enumeration).
  - `_generate_code()` dùng `secrets.choice`.
"""

import string

from app import app as app_module
from app import booking


def _fake_appointment(code, session_id):
    return {
        "code": code,
        "session": session_id,
        "patient_name": "Khách",
        "patient_phone": "0900000000",
        "department": "Nha khoa tổng quát",
        "department_code": "nkq",
        "doctor": "BS. Test",
        "doctor_id": "d1",
        "date": "2026-08-01",
        "time": "09:00",
        "created_at": "2026-07-09T00:00:00",
        "status": "confirmed",
    }


def test_generate_code_uses_secrets(monkeypatch):
    calls = []

    def fake_choice(seq):
        calls.append(seq)
        return "A"

    monkeypatch.setattr(booking.secrets, "choice", fake_choice)

    code = booking._generate_code()

    assert len(calls) == 6
    alphabet = string.ascii_uppercase + string.digits
    assert all(seq == alphabet for seq in calls)
    assert code == "SHI-AAAAAA"


def test_ics_requires_ownership(monkeypatch):
    code = "SHI-OWNER1"
    appt = _fake_appointment(code, session_id="alice")
    monkeypatch.setattr(booking, "get_appointment", lambda c: appt if c == code else None)

    client = app_module.app.test_client()
    with client.session_transaction() as sess:
        sess["sid"] = "bob"

    resp = client.get(f"/api/ics/{code}")

    assert resp.status_code == 404


def test_ics_allows_owner(monkeypatch):
    code = "SHI-OWNER2"
    appt = _fake_appointment(code, session_id="alice")
    monkeypatch.setattr(booking, "get_appointment", lambda c: appt if c == code else None)

    client = app_module.app.test_client()
    with client.session_transaction() as sess:
        sess["sid"] = "alice"

    resp = client.get(f"/api/ics/{code}")

    assert resp.status_code == 200
    assert resp.content_type.startswith("text/calendar")


def test_ics_unknown_code_returns_404(monkeypatch):
    monkeypatch.setattr(booking, "get_appointment", lambda c: None)

    client = app_module.app.test_client()
    with client.session_transaction() as sess:
        sess["sid"] = "alice"

    resp = client.get("/api/ics/SHI-NOPE00")

    assert resp.status_code == 404
