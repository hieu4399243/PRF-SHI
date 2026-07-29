"""Test doctor API: chỉ xem dữ liệu của chính bác sĩ đăng nhập."""

from app import main
import app.doctor_api as doctor_api_module


def _client():
    main.app.config["TESTING"] = True
    return main.app.test_client()


def test_doctor_meta_requires_login():
    client = _client()
    resp = client.get("/api/doctor/meta")
    assert resp.status_code == 401


def test_doctor_schedule_requires_date(monkeypatch):
    client = _client()

    monkeypatch.setattr(
        doctor_api_module,
        "_get_current_doctor",
        lambda: {"id": "u1", "role": "doctor", "doctor_id": "bs_sr_01"},
    )

    resp = client.get("/api/doctor/schedule")
    assert resp.status_code == 400
    assert "date" in resp.get_json()["error"]


def test_doctor_appointments_force_current_doctor(monkeypatch):
    client = _client()

    monkeypatch.setattr(
        doctor_api_module,
        "_get_current_doctor",
        lambda: {"id": "u1", "role": "doctor", "doctor_id": "bs_sr_01"},
    )

    captured = {}

    def _fake_query_appointments(**kwargs):
        captured.update(kwargs)
        return [{"code": "SHI-1", "doctor_id": kwargs.get("doctor_id"), "status": "confirmed"}]

    monkeypatch.setattr(doctor_api_module.booking, "query_appointments", _fake_query_appointments)

    resp = client.get("/api/doctor/appointments?doctor_id=bs_other&status=confirmed")
    assert resp.status_code == 200
    body = resp.get_json()

    assert captured["doctor_id"] == "bs_sr_01"
    assert captured["status"] == "confirmed"
    assert body["count"] == 1
    assert body["appointments"][0]["doctor_id"] == "bs_sr_01"


def test_doctor_meta_summary_scoped(monkeypatch):
    client = _client()

    monkeypatch.setattr(
        doctor_api_module,
        "_get_current_doctor",
        lambda: {"id": "u1", "role": "doctor", "doctor_id": "bs_sr_01"},
    )

    monkeypatch.setattr(
        doctor_api_module.booking,
        "query_appointments",
        lambda **kwargs: [
            {"status": "confirmed", "date": "2026-07-30"},
            {"status": "confirmed", "date": "2026-08-01"},
            {"status": "cancelled", "date": "2026-07-31"},
        ],
    )
    monkeypatch.setattr(
        doctor_api_module.booking,
        "all_doctors",
        lambda: [
            {
                "id": "bs_sr_01",
                "name": "BS. Lê Minh Châu",
                "dept_code": "sau_rang",
                "dept_name": "Trám răng / Sâu răng",
            }
        ],
    )
    monkeypatch.setattr(doctor_api_module.booking, "get_available_dates", lambda: ["2026-07-30"])

    resp = client.get("/api/doctor/meta")
    assert resp.status_code == 200
    body = resp.get_json()

    assert body["doctor"]["id"] == "bs_sr_01"
    assert body["summary"] == {"total": 3, "confirmed": 2, "cancelled": 1}
    assert body["dates"] == ["2026-08-01", "2026-07-31", "2026-07-30"]
