"""
Tests cho patient_api — phân quyền, cách ly dữ liệu giữa các bệnh nhân, và hợp
đồng JSON mà patient.html dựa vào.

Trọng tâm bảo mật: KHÔNG endpoint nào được nhận `patient_id` từ client. Nếu nhận,
bệnh nhân A đổi một tham số là đọc được lịch sử khám của bệnh nhân B.

Ánh xạ test case TC-F2: TC-REC-003 (đặt lịch từ gợi ý, dịch vụ chọn sẵn),
TC-REC-004 (dismiss), TC-REC-005 (reset).
"""

import pytest

from app import main, patient_api as patient_api_module
from app.core import storage

# Tài khoản đăng nhập (`users`) và hồ sơ bệnh nhân (`patients`) là HAI thực thể,
# nối qua `users.patient_id`. Tuổi/dị ứng nằm ở hồ sơ, không nằm ở tài khoản.
PATIENT_PROFILE_ID = "p-benh-nhan-1"
PATIENT = {"id": "u-benh-nhan-1", "username": "bn101", "role": "patient",
           "patient_id": PATIENT_PROFILE_ID, "phone": "0900000101"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "USE_DB", False)
    monkeypatch.setattr(storage, "APPOINTMENTS_PATH", str(tmp_path / "appt.json"))
    monkeypatch.setattr(storage, "TREATMENT_HISTORY_PATH", str(tmp_path / "th.json"))
    monkeypatch.setattr(storage, "REC_LOG_PATH", str(tmp_path / "rl.json"))
    monkeypatch.setattr(storage, "PATIENT_PREFS_PATH", str(tmp_path / "pp.json"))
    monkeypatch.setattr(storage, "PATIENTS_PATH", str(tmp_path / "patients.json"))
    storage._json_save(str(tmp_path / "patients.json"), [{
        "id": PATIENT_PROFILE_ID, "name": "Nguyễn Văn A", "phone": "0900000101",
        "email": None, "address": None, "notes": None, "birth_year": 1990,
        "allergies": [], "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
    }])
    from app import reco
    reco.history.clear_cooccurrence_cache()
    monkeypatch.setenv("REC_LLM_REASON", "0")   # test không gọi mạng
    main.app.config["TESTING"] = True
    return main.app.test_client()


def _login(monkeypatch, user=PATIENT):
    monkeypatch.setattr(patient_api_module, "current_patient", lambda: user)


def _visit(phone, code, day, due=None, patient_id=None, n=[0]):
    n[0] += 1
    storage.add_treatment({
        "history_id": f"h{n[0]}", "appointment_code": f"A{n[0]}",
        "patient_id": patient_id, "patient_phone": phone,
        "service_code": code, "doctor_id": "bs_tq_01",
        "treatment_date": day, "outcome": "success",
        "followup_required": bool(due), "followup_due_date": due,
        "patient_rating": None, "created_at": day + "T10:00:00",
    })


def _ho_so(phone="0900000101"):
    _visit(phone, "kham_tong_quat", "2025-11-30", due="2026-05-30")
    _visit(phone, "nha_chu", "2024-06-30")
    _visit(phone, "tham_my", "2024-01-30")


# ---------------------------------------------------------------------------
# Phân quyền
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("path", [
    "/api/patient/me",
    "/api/patient/history",
    "/api/patient/recommendations",
])
def test_khach_chua_dang_nhap_van_xem_duoc(client, path):
    """Khách vẫn vào được trang gợi ý (và vẫn đặt lịch qua widget chatbot)."""
    resp = client.get(path)
    assert resp.status_code == 200
    assert resp.get_json()["is_guest"] is True


def test_khach_khong_thay_lich_su_hay_lich_hen_cua_bat_ky_ai(client):
    """Điểm mấu chốt của chế độ khách: mở cửa cho xem gợi ý KHÔNG được kéo theo
    việc lộ dữ liệu. Khách không có định danh -> không có gì để trả."""
    _ho_so("0900000101")
    storage.add_appointment({
        "code": "SHI-X1", "session": "s", "patient_name": "Ai đó",
        "patient_phone": "0900000101", "department": "Khám tổng quát",
        "department_code": "kham_tong_quat", "doctor": "BS", "doctor_id": "bs_tq_01",
        "date": "2026-08-10", "time": "09:00",
        "created_at": "2026-07-01T00:00:00", "status": "confirmed",
    })
    assert client.get("/api/patient/history").get_json()["count"] == 0
    assert client.get("/api/patient/me").get_json()["full_name"] is None


def test_khach_luon_roi_vao_cold_start(client):
    """Chưa biết là ai -> không cá nhân hoá được -> dịch vụ phổ biến, không hiện %."""
    _ho_so("0900000101")
    d = client.get("/api/patient/recommendations").get_json()
    assert d["is_cold_start"] is True
    assert d["visit_count"] == 0
    assert all(i["fit_percent"] is None for i in d["items"])


def test_khach_bo_qua_goi_y_thi_khong_luu_ben(client):
    """Không có tài khoản để gắn lựa chọn -> API vẫn nhận nhưng không lưu, và UI
    dựa vào `dismissed = None` để chỉ ẩn card trong phiên hiện tại."""
    resp = client.post("/api/patient/recommendations/action",
                       json={"action": "dismiss", "service_code": "tham_my"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["is_guest"] is True
    assert body["dismissed"] is None


def test_khach_khong_reset_duoc(client):
    """Không có gì để reset -> giữ nguyên yêu cầu đăng nhập."""
    assert client.post("/api/patient/recommendations/reset").status_code == 401


def test_man_goi_y_mo_duoc_ca_khi_chua_dang_nhap(client):
    """Khách vào thẳng màn gợi ý được, và widget chat nằm ngay trong trang đó."""
    resp = client.get("/recommendations")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "Gợi ý điều trị" in html
    assert "chatPanel" in html


def test_role_khac_khong_duoc_coi_la_benh_nhan(monkeypatch):
    """current_patient() phải từ chối cả user đã đăng nhập nhưng role khác."""
    for role in ("admin", "doctor", "guest"):
        monkeypatch.setattr(
            patient_api_module.auth, "resolve_user_from_token",
            lambda _t, role=role: {"id": "u9", "role": role})
        main.app.config["TESTING"] = True
        with main.app.test_request_context("/api/patient/me"):
            assert patient_api_module.current_patient() is None


# ---------------------------------------------------------------------------
# Cách ly dữ liệu giữa các bệnh nhân
# ---------------------------------------------------------------------------
def test_khong_doc_duoc_lich_su_benh_nhan_khac(client, monkeypatch):
    _ho_so("0900000101")
    _visit("0900000999", "noi_nha", "2025-03-30")
    _login(monkeypatch)

    data = client.get("/api/patient/history").get_json()
    assert data["count"] == 3
    assert "Nội nha (Điều trị tủy)" not in [r["service_name"] for r in data["history"]]


def test_khong_the_truyen_patient_id_qua_query(client, monkeypatch):
    """Đổi tham số không được làm lệch định danh — định danh chỉ đến từ token."""
    _ho_so("0900000101")
    _visit("0900000999", "noi_nha", "2025-03-30")
    _login(monkeypatch)

    a = client.get("/api/patient/history").get_json()
    b = client.get("/api/patient/history?patient_id=u-khac"
                   "&patient_phone=0900000999").get_json()
    assert a == b






# ---------------------------------------------------------------------------
# /me và /history
# ---------------------------------------------------------------------------
def test_me_tra_ten_va_so_luot(client, monkeypatch):
    _ho_so()
    _login(monkeypatch)
    data = client.get("/api/patient/me").get_json()
    assert data["full_name"] == "Nguyễn Văn A"   # lấy từ patients.name
    assert data["visit_count"] == 3
    assert data["has_history"] is True


def test_history_du_cot_theo_AC_PAT01(client, monkeypatch):
    """AC PAT-01: bảng lịch sử gồm ngày, dịch vụ, bác sĩ, trạng thái."""
    _ho_so()
    _login(monkeypatch)
    row = client.get("/api/patient/history").get_json()["history"][0]
    for field in ("date", "service_name", "doctor", "outcome"):
        assert field in row
    assert row["doctor"].startswith("BS.")


def test_history_rong_van_tra_200(client, monkeypatch):
    """AC PAT-01: 'Empty lịch sử vẫn cho vào gợi ý (cold-start)'."""
    _login(monkeypatch)
    data = client.get("/api/patient/history").get_json()
    assert data == {"history": [], "count": 0, "is_guest": False}


# ---------------------------------------------------------------------------
# /recommendations
# ---------------------------------------------------------------------------
def test_recommendations_tra_toi_da_3_muc(client, monkeypatch):
    _ho_so()
    _login(monkeypatch)
    data = client.get("/api/patient/recommendations").get_json()
    assert len(data["items"]) <= 3
    assert data["model_version"]
    assert data["rec_log_id"]


def test_recommendations_khong_ro_ri_signals_ra_client(client, monkeypatch):
    """`signals` là nội bộ engine (trọng số từng luật) — không gửi ra ngoài."""
    _ho_so()
    _login(monkeypatch)
    for item in client.get("/api/patient/recommendations").get_json()["items"]:
        assert "signals" not in item
        assert item["reason_text"]
        assert isinstance(item["reason_detail"], list)


def test_recommendations_co_du_du_lieu_cho_modal_REC02(client, monkeypatch):
    """REC-02 mở modal không cần gọi API lần hai (TC-REC-007)."""
    _ho_so()
    _login(monkeypatch)
    item = client.get("/api/patient/recommendations").get_json()["items"][0]
    for field in ("desc", "duration_min", "price_from", "reason_detail", "doctors"):
        assert field in item


def test_trigger_chatbot_duoc_chap_nhan(client, monkeypatch):
    _ho_so()
    _login(monkeypatch)
    resp = client.get("/api/patient/recommendations?trigger=chatbot")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /recommendations/action
# ---------------------------------------------------------------------------
def test_action_khong_hop_le_bi_tu_choi(client, monkeypatch):
    _login(monkeypatch)
    resp = client.post("/api/patient/recommendations/action",
                       json={"action": "xoa_het_du_lieu"})
    assert resp.status_code == 400


def test_action_dismiss_luu_ben(client, monkeypatch):
    """TC-REC-004: lần sau dịch vụ đó không xuất hiện nữa."""
    _ho_so()
    _login(monkeypatch)
    before = client.get("/api/patient/recommendations").get_json()
    code = before["items"][0]["service_code"]

    resp = client.post("/api/patient/recommendations/action",
                       json={"action": "dismiss", "service_code": code,
                             "rec_log_id": before["rec_log_id"], "rank": 1})
    assert resp.status_code == 200
    assert code in resp.get_json()["dismissed"]

    after = client.get("/api/patient/recommendations").get_json()
    assert code not in [i["service_code"] for i in after["items"]]


def test_action_dismiss_can_service_code(client, monkeypatch):
    _login(monkeypatch)
    resp = client.post("/api/patient/recommendations/action",
                       json={"action": "dismiss"})
    assert resp.status_code == 400


def test_action_tu_choi_service_code_khong_ton_tai(client, monkeypatch):
    """Mã dịch vụ bịa không được ghi vào patient_preference."""
    _login(monkeypatch)
    resp = client.post("/api/patient/recommendations/action",
                       json={"action": "dismiss", "service_code": "dich_vu_bia"})
    assert resp.status_code == 400
    assert storage.get_patient_preference(PATIENT_PROFILE_ID)["dismissed_service_codes"] == []


def test_action_book_ghi_vao_log(client, monkeypatch):
    _ho_so()
    _login(monkeypatch)
    data = client.get("/api/patient/recommendations").get_json()
    client.post("/api/patient/recommendations/action",
                json={"action": "book", "service_code": data["items"][0]["service_code"],
                      "rec_log_id": data["rec_log_id"], "rank": 1})
    entry = storage.get_rec_log(data["rec_log_id"])
    assert entry["patient_action"] == "book"
    assert entry["patient_acted_rank"] == 1


def test_action_skip_all_khong_can_service_code(client, monkeypatch):
    """AC SMMG-65: 'bỏ qua tất cả để tự chọn dịch vụ'."""
    _ho_so()
    _login(monkeypatch)
    data = client.get("/api/patient/recommendations").get_json()
    resp = client.post("/api/patient/recommendations/action",
                       json={"action": "skip_all", "rec_log_id": data["rec_log_id"]})
    assert resp.status_code == 200
    assert storage.get_rec_log(data["rec_log_id"])["patient_action"] == "skip_all"


def test_reset_dismissed(client, monkeypatch):
    """TC-REC-005: link reset ở empty state."""
    _ho_so()
    _login(monkeypatch)
    storage.add_dismissed_service(PATIENT_PROFILE_ID, "kham_tong_quat")
    assert client.post("/api/patient/recommendations/reset").status_code == 200
    assert storage.get_patient_preference(PATIENT_PROFILE_ID)["dismissed_service_codes"] == []


# ---------------------------------------------------------------------------
# TC-REC-003 — đặt lịch từ gợi ý, dịch vụ đã chọn sẵn
# ---------------------------------------------------------------------------
def test_start_voi_service_vao_thang_buoc_chon_bac_si(client):
    """'Booking flow mở với dịch vụ được pre-selected; không cần chọn lại dịch vụ.'"""
    resp = client.post("/api/start", json={"service": "chinh_nha"})
    data = resp.get_json()
    assert data["state"] == "PICK_DOCTOR"
    assert "Chỉnh nha" in data["reply"]
    assert data["options"]


def test_start_khong_co_service_van_vao_triage(client):
    data = client.post("/api/start", json={}).get_json()
    assert data["state"] == "TRIAGE"


def test_start_voi_service_la_quay_ve_loi_chao(client):
    """Card gợi ý trong tab cũ có thể mang mã dịch vụ đã bị xoá khỏi danh mục —
    phải quay về lời chào, không phải lỗi 500."""
    data = client.post("/api/start", json={"service": "dich_vu_khong_ton_tai"}).get_json()
    assert data["state"] == "TRIAGE"
