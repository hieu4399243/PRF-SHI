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


# ---------------------------------------------------------------------------
# POST /api/doctor/treatment — mắt xích appointments -> treatment_history
# ---------------------------------------------------------------------------
APPT = {"code": "SHI-1", "doctor_id": "bs_sr_01", "status": "confirmed",
        "date": "2026-07-01", "department_code": "sau_rang",
        "patient_phone": "0900000101"}


def _as_doctor(monkeypatch, doctor_id="bs_sr_01"):
    monkeypatch.setattr(doctor_api_module, "_get_current_doctor",
                        lambda: {"id": "u1", "role": "doctor", "doctor_id": doctor_id})


def _with_appt(monkeypatch, appt=None, added=True):
    """Giả lập 1 lịch hẹn + bắt bản ghi mà endpoint ghi xuống storage."""
    monkeypatch.setattr(doctor_api_module.booking, "query_appointments",
                        lambda **kwargs: [dict(appt or APPT)])
    monkeypatch.setattr(doctor_api_module, "_resolve_patient_id", lambda _p: "p-1")
    ghi = {}

    def _fake_add(rec):
        ghi.update(rec)
        return added

    monkeypatch.setattr(doctor_api_module.storage, "add_treatment", _fake_add)
    return ghi


def test_ghi_nhan_dieu_tri_can_dang_nhap():
    assert _client().post("/api/doctor/treatment", json={}).status_code == 401


def test_ghi_nhan_dieu_tri_thanh_cong(monkeypatch):
    _as_doctor(monkeypatch)
    ghi = _with_appt(monkeypatch)

    resp = _client().post("/api/doctor/treatment",
                          json={"appointment_code": "SHI-1", "outcome": "success"})
    assert resp.status_code == 201
    assert ghi["service_code"] == "sau_rang"
    assert ghi["treatment_date"] == "2026-07-01"
    assert ghi["patient_phone"] == "0900000101"
    assert ghi["patient_id"] == "p-1"
    # Cùng quy ước id với backfill -> không tạo bản ghi trùng cho cùng lịch hẹn.
    assert ghi["history_id"] == "th-SHI-1"


def test_khong_ghi_duoc_lich_hen_cua_nha_si_khac(monkeypatch):
    """Chốt chặn quan trọng nhất: lịch sử điều trị lái thẳng vào gợi ý y tế."""
    _as_doctor(monkeypatch, doctor_id="bs_nn_01")
    ghi = _with_appt(monkeypatch)

    resp = _client().post("/api/doctor/treatment", json={"appointment_code": "SHI-1"})
    assert resp.status_code == 403
    assert ghi == {}


def test_khong_ghi_duoc_lich_hen_da_huy(monkeypatch):
    _as_doctor(monkeypatch)
    _with_appt(monkeypatch, {**APPT, "status": "cancelled"})

    resp = _client().post("/api/doctor/treatment", json={"appointment_code": "SHI-1"})
    assert resp.status_code == 400


def test_khong_ghi_duoc_lich_hen_chua_toi_ngay(monkeypatch):
    _as_doctor(monkeypatch)
    _with_appt(monkeypatch, {**APPT, "date": "2099-01-01"})

    resp = _client().post("/api/doctor/treatment", json={"appointment_code": "SHI-1"})
    assert resp.status_code == 400
    assert "chưa tới ngày" in resp.get_json()["error"]


def test_hen_tai_kham_bat_buoc_co_ngay(monkeypatch):
    """`followup_required` là CHỈ ĐỊNH của nha sĩ — không tự suy ngày từ chu kỳ."""
    _as_doctor(monkeypatch)
    _with_appt(monkeypatch)

    resp = _client().post("/api/doctor/treatment",
                          json={"appointment_code": "SHI-1", "followup_required": True})
    assert resp.status_code == 400
    assert "followup_due_date" in resp.get_json()["error"]


def test_hen_tai_kham_ghi_dung_ngay(monkeypatch):
    _as_doctor(monkeypatch)
    ghi = _with_appt(monkeypatch)

    resp = _client().post("/api/doctor/treatment",
                          json={"appointment_code": "SHI-1", "followup_required": True,
                                "followup_due_date": "2027-01-05"})
    assert resp.status_code == 201
    assert ghi["followup_required"] is True
    assert ghi["followup_due_date"] == "2027-01-05"


def test_ngay_tai_kham_sai_dinh_dang(monkeypatch):
    _as_doctor(monkeypatch)
    _with_appt(monkeypatch)

    resp = _client().post("/api/doctor/treatment",
                          json={"appointment_code": "SHI-1", "followup_required": True,
                                "followup_due_date": "05/01/2027"})
    assert resp.status_code == 400


def test_outcome_khong_hop_le(monkeypatch):
    _as_doctor(monkeypatch)
    _with_appt(monkeypatch)

    resp = _client().post("/api/doctor/treatment",
                          json={"appointment_code": "SHI-1", "outcome": "xong_roi"})
    assert resp.status_code == 400


def test_rating_ngoai_khoang(monkeypatch):
    _as_doctor(monkeypatch)
    _with_appt(monkeypatch)

    resp = _client().post("/api/doctor/treatment",
                          json={"appointment_code": "SHI-1", "patient_rating": 9})
    assert resp.status_code == 400


def test_ghi_nhan_hai_lan_tra_409(monkeypatch):
    _as_doctor(monkeypatch)
    _with_appt(monkeypatch, added=False)

    resp = _client().post("/api/doctor/treatment", json={"appointment_code": "SHI-1"})
    assert resp.status_code == 409


def test_lich_hen_khong_ton_tai(monkeypatch):
    _as_doctor(monkeypatch)
    _with_appt(monkeypatch)

    resp = _client().post("/api/doctor/treatment", json={"appointment_code": "SHI-999"})
    assert resp.status_code == 404


def test_danh_dau_lich_da_ghi_ket_qua(monkeypatch):
    """Dashboard phải biết lịch nào đã ghi, nếu không nha sĩ bấm lại chỉ nhận 409."""
    _as_doctor(monkeypatch)
    monkeypatch.setattr(doctor_api_module.booking, "query_appointments",
                        lambda **kwargs: [dict(APPT), {**APPT, "code": "SHI-2"}])
    monkeypatch.setattr(doctor_api_module.storage, "list_treatments",
                        lambda: [{"appointment_code": "SHI-1"}])

    body = _client().get("/api/doctor/appointments").get_json()
    da_ghi = {a["code"]: a["treatment_recorded"] for a in body["appointments"]}
    assert da_ghi == {"SHI-1": True, "SHI-2": False}


def test_khong_hien_nut_cho_ma_khoa_da_bo(monkeypatch):
    """Lịch hẹn cũ mang mã khoa từ thời phòng khám đa khoa (`ho_hap`, `tieu_hoa`)
    không ghi kết quả được. Nút phải TẮT sẵn thay vì bấm rồi mới nhận 400 —
    đây là lỗi nha sĩ gặp trên dashboard."""
    _as_doctor(monkeypatch)
    monkeypatch.setattr(doctor_api_module.booking, "query_appointments",
                        lambda **kwargs: [dict(APPT),
                                          {**APPT, "code": "SHI-9", "department_code": "ho_hap"}])
    monkeypatch.setattr(doctor_api_module.storage, "list_treatments", lambda: [])

    body = _client().get("/api/doctor/appointments").get_json()
    theo_ma = {a["code"]: (a["can_record_treatment"], a["record_blocker"])
               for a in body["appointments"]}
    assert theo_ma == {"SHI-1": (True, None), "SHI-9": (False, "dich_vu_da_bo")}


def test_co_can_record_khop_voi_endpoint(monkeypatch):
    """Cờ trên bảng và chốt chặn của endpoint phải cùng một bộ luật — lệch nhau
    thì nút lại mời bấm một việc bị từ chối."""
    _as_doctor(monkeypatch)
    cases = [
        ({**APPT, "code": "C1", "status": "cancelled"}, "chua_xac_nhan", 400),
        ({**APPT, "code": "C2", "date": "2099-01-01"}, "chua_toi_ngay", 400),
        ({**APPT, "code": "C3", "department_code": "ho_hap"}, "dich_vu_da_bo", 400),
        ({**APPT, "code": "C4", "doctor_id": "bs_khac"}, "khong_phai_cua_ban", 403),
    ]
    for appt, blocker, http in cases:
        _with_appt(monkeypatch, appt)
        monkeypatch.setattr(doctor_api_module.storage, "list_treatments", lambda: [])
        client = _client()

        row = client.get("/api/doctor/appointments").get_json()["appointments"][0]
        assert row["can_record_treatment"] is False
        assert row["record_blocker"] == blocker

        resp = client.post("/api/doctor/treatment", json={"appointment_code": appt["code"]})
        assert resp.status_code == http


def test_lich_lam_viec_mang_theo_co_ghi_ket_qua(monkeypatch):
    """Nha sĩ ghi kết quả ngay tại slot vừa khám xong, nên slot phải mang đủ cờ —
    không thì tab lịch làm việc chỉ xem được, phải sang tab khác dò mã lịch."""
    _as_doctor(monkeypatch)
    monkeypatch.setattr(doctor_api_module.booking, "doctor_day_schedule",
                        lambda doctor_id, date_str: [
                            {"time": "08:00", "appt": dict(APPT)},
                            {"time": "08:30", "appt": {**APPT, "code": "SHI-2"}},
                            {"time": "09:00", "appt": None},
                        ])
    monkeypatch.setattr(doctor_api_module.storage, "list_treatments",
                        lambda: [{"appointment_code": "SHI-1"}])

    slots = _client().get("/api/doctor/schedule?date=2026-07-01").get_json()["slots"]
    assert slots[0]["appt"]["treatment_recorded"] is True
    assert slots[0]["appt"]["can_record_treatment"] is False
    assert slots[1]["appt"]["can_record_treatment"] is True
    assert slots[2]["appt"] is None


# ---------------------------------------------------------------------------
# Lượt điều trị thuộc bệnh án AI — tài khoản đã đặt lịch, không phải SĐT
# ---------------------------------------------------------------------------
def test_ho_so_lay_theo_tai_khoan_dat_lich(monkeypatch):
    """SĐT trên lịch hẹn là số người dùng TỰ GÕ và đặt hộ là hợp lệ, nên suy chủ
    nhân từ SĐT làm ca khám chui vào bệnh án chủ số đó (ca SHI-ELBICD thật)."""
    monkeypatch.setattr(doctor_api_module.storage, "get_user_by_id",
                        lambda uid: {"id": uid, "patient_id": "pt-cua-toi"})
    monkeypatch.setattr(doctor_api_module, "_resolve_patient_id",
                        lambda _p: "pt-cua-chu-so-dien-thoai")

    appt = {**APPT, "booked_by_user_id": "u-toi", "patient_phone": "0900000999"}
    assert doctor_api_module._patient_id_of_appointment(appt) == "pt-cua-toi"


def test_tai_khoan_chua_co_ho_so_thi_khong_doan_theo_sdt(monkeypatch):
    """Đã biết tài khoản rồi thì SĐT hết quyền nói lịch này của ai — kể cả khi tài
    khoản đó chưa có hồ sơ bệnh nhân."""
    monkeypatch.setattr(doctor_api_module.storage, "get_user_by_id",
                        lambda uid: {"id": uid, "patient_id": None})
    monkeypatch.setattr(doctor_api_module, "_resolve_patient_id",
                        lambda _p: "pt-cua-chu-so-dien-thoai")

    appt = {**APPT, "booked_by_user_id": "u-toi"}
    assert doctor_api_module._patient_id_of_appointment(appt) is None


def test_lich_cua_khach_van_neo_theo_sdt(monkeypatch):
    """Khách chưa đăng nhập: SĐT là định danh DUY NHẤT tồn tại, và không có tài
    khoản nào để gán nhầm."""
    monkeypatch.setattr(doctor_api_module, "_resolve_patient_id", lambda _p: "pt-khach")

    assert doctor_api_module._patient_id_of_appointment(dict(APPT)) == "pt-khach"


# ---------------------------------------------------------------------------
# GET /api/doctor/patient — hồ sơ + gợi ý phía nha sĩ (trigger dentist_view)
# ---------------------------------------------------------------------------
def _fake_reco(monkeypatch, captured=None):
    def _recommend(**kwargs):
        if captured is not None:
            captured.update(kwargs)
        return {"items": [{"service_code": "sau_rang", "name": "Trám răng", "rank": 1,
                           "signals": [{"w": 0.9}], "fit_percent": 82,
                           "urgency": "high", "reason_text": "lý do"}],
                "is_cold_start": False, "empty_reason": None, "cold_start_note": None,
                "empty_text": None, "visit_count": 3}
    monkeypatch.setattr(doctor_api_module.reco, "recommend", _recommend)


def test_ho_so_benh_nhan_can_dang_nhap():
    assert _client().get("/api/doctor/patient?phone=0900000101").status_code == 401


def test_ho_so_benh_nhan_can_sdt(monkeypatch):
    _as_doctor(monkeypatch)
    assert _client().get("/api/doctor/patient").status_code == 400


def test_khong_xem_duoc_benh_nhan_khong_phai_cua_minh(monkeypatch):
    """Endpoint nhận SĐT từ client, nên không chặn thì nó thành cửa tra cứu toàn
    bộ bệnh nhân của phòng khám bằng cách dò số."""
    _as_doctor(monkeypatch)
    monkeypatch.setattr(doctor_api_module.booking, "query_appointments",
                        lambda **kwargs: [])

    resp = _client().get("/api/doctor/patient?phone=0900000999")
    assert resp.status_code == 403


def test_ho_so_benh_nhan_tra_lich_su_va_goi_y(monkeypatch):
    _as_doctor(monkeypatch)
    monkeypatch.setattr(doctor_api_module.booking, "query_appointments",
                        lambda **kwargs: [dict(APPT)])
    monkeypatch.setattr(doctor_api_module, "_resolve_patient_id", lambda _p: "p-1")
    monkeypatch.setattr(doctor_api_module.storage, "get_patient_clinical",
                        lambda pid: {"name": "Nguyễn Văn A", "birth_year": 1990,
                                     "allergies": []})
    monkeypatch.setattr(doctor_api_module.reco.history, "recent",
                        lambda **kwargs: [{"treatment_date": "2026-07-01",
                                           "service_code": "sau_rang",
                                           "doctor_id": "bs_sr_01",
                                           "outcome": "success"}])
    captured = {}
    _fake_reco(monkeypatch, captured)

    body = _client().get("/api/doctor/patient?phone=0900000101").get_json()

    assert body["patient"]["name"] == "Nguyễn Văn A"
    assert body["visit_count"] == 1
    assert body["treatments"][0]["service_name"] == "Trám răng / Sâu răng"
    assert captured["trigger"] == "dentist_view"
    assert captured["patient_phone"] == "0900000101"
    assert body["recommendations"]["items"][0]["service_code"] == "sau_rang"


def test_ho_so_khong_lo_trong_so_noi_bo(monkeypatch):
    """`signals` là trọng số của bộ luật, không phải thông tin lâm sàng — giữ đúng
    ranh giới mà /api/patient/recommendations đã đặt."""
    _as_doctor(monkeypatch)
    monkeypatch.setattr(doctor_api_module.booking, "query_appointments",
                        lambda **kwargs: [dict(APPT)])
    monkeypatch.setattr(doctor_api_module, "_resolve_patient_id", lambda _p: None)
    monkeypatch.setattr(doctor_api_module.reco.history, "recent", lambda **kwargs: [])
    _fake_reco(monkeypatch)

    body = _client().get("/api/doctor/patient?phone=0900000101").get_json()
    assert "signals" not in body["recommendations"]["items"][0]
