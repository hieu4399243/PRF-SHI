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


def test_role_nhan_vien_khong_duoc_coi_la_benh_nhan(monkeypatch):
    """current_patient() phải từ chối user đã đăng nhập nhưng là admin/nha sĩ."""
    for role in ("admin", "doctor"):
        monkeypatch.setattr(
            patient_api_module.auth, "resolve_user_from_token",
            lambda _t, role=role: {"id": "u9", "role": role})
        main.app.config["TESTING"] = True
        with main.app.test_request_context("/api/patient/me"):
            assert patient_api_module.current_patient() is None


def test_tai_khoan_dang_ky_role_guest_van_la_benh_nhan(monkeypatch):
    """`/api/register` tạo role='guest' — đó là bệnh nhân có tài khoản, KHÔNG phải
    khách vãng lai. Nhận nhầm thì đăng nhập xong màn gợi ý vẫn báo "khách"."""
    for role in ("patient", "guest"):
        monkeypatch.setattr(
            patient_api_module.auth, "resolve_user_from_token",
            lambda _t, role=role: {"id": "u9", "role": role})
        main.app.config["TESTING"] = True
        with main.app.test_request_context("/api/patient/me"):
            assert patient_api_module.current_patient() is not None


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


# ---------------------------------------------------------------------------
# Đăng ký: SĐT là KHOÁ ĐỊNH DANH của lịch sử điều trị
#
# `list_treatments()` gộp theo (patient_id OR patient_phone). Nên hai tài khoản
# mang cùng một SĐT = hai người đăng nhập cùng đọc được một lịch sử điều trị.
# Lỗi quan sát được trên deploy: đăng ký tài khoản mới bằng SĐT đã dùng, đăng nhập
# vào thấy nguyên lịch sử của tài khoản trước.
# ---------------------------------------------------------------------------
def _moi_truong_dang_ky(monkeypatch, *, user_theo_sdt=None, ho_so_da_ton_tai=False):
    """Giả lập tầng storage cho `/api/register` (bảng `users` không có JSON mode).

    Trả về dict sẽ nhận đúng tham số mà endpoint truyền cho `create_user_account`
    — rỗng nghĩa là KHÔNG có tài khoản nào được tạo.
    """
    da_tao = {}
    monkeypatch.setattr(main.storage, "get_user_by_phone", lambda _p: user_theo_sdt)

    def _tao_ho_so(name, phone, **kw):
        if ho_so_da_ton_tai:
            raise ValueError("Số điện thoại đã tồn tại")
        return {"id": "pt-moi", "name": name, "phone": phone}

    def _tao_user(**kw):
        da_tao.update(kw)
        return {"id": "u-moi", "username": kw["username"], "role": kw["role"]}

    monkeypatch.setattr(main.storage, "create_patient_profile", _tao_ho_so)
    monkeypatch.setattr(main.auth, "create_user_account", _tao_user)
    return da_tao


BODY = {"username": "bn999", "password": "test123", "name": "Người Mới",
        "phone": "0962043769"}


def test_khong_dang_ky_duoc_bang_sdt_da_co_tai_khoan(client, monkeypatch):
    da_tao = _moi_truong_dang_ky(
        monkeypatch, user_theo_sdt={"id": "u-cu", "username": "bn111"})

    resp = client.post("/api/register", json=BODY)
    assert resp.status_code == 409
    assert "đã có tài khoản" in resp.get_json()["error"]
    # Chặn TRƯỚC khi tạo, nếu không sẽ để lại tài khoản mồ côi.
    assert da_tao == {}


def test_khong_dang_ky_duoc_bang_sdt_da_co_ho_so(client, monkeypatch):
    """Hồ sơ có sẵn kéo theo cả lịch sử điều trị. Biết một số điện thoại KHÔNG
    chứng minh được mình là chủ số đó, nên tự nối là trao hồ sơ lâm sàng của người
    khác. Việc nối để phòng khám làm qua trang admin."""
    da_tao = _moi_truong_dang_ky(monkeypatch, ho_so_da_ton_tai=True)

    resp = client.post("/api/register", json=BODY)
    assert resp.status_code == 409
    assert "đã có hồ sơ" in resp.get_json()["error"]
    assert da_tao == {}


def test_sdt_moi_van_tao_duoc_ho_so(client, monkeypatch):
    da_tao = _moi_truong_dang_ky(monkeypatch)

    assert client.post("/api/register", json=BODY).status_code == 201
    assert da_tao["patient_id"] == "pt-moi"


def test_dang_ky_khong_sdt_van_duoc(client, monkeypatch):
    """SĐT không bắt buộc — không có thì không có hồ sơ, và cũng không đọc được
    lịch sử của ai."""
    da_tao = _moi_truong_dang_ky(monkeypatch)

    body = {k: v for k, v in BODY.items() if k != "phone"}
    assert client.post("/api/register", json=body).status_code == 201
    assert da_tao["patient_id"] is None


# ---------------------------------------------------------------------------
# GET /api/patient/appointments — trạng thái "đang chờ khám" / "đã khám"
# ---------------------------------------------------------------------------
def _dang_nhap_that(monkeypatch, user):
    """Qua `@require_auth` (đọc token thật), không qua `current_patient`."""
    monkeypatch.setattr(main.auth, "resolve_user_from_token", lambda _t: user)


def _lich_hen(code, day, status="confirmed", phone="0900000101", booked_by=None):
    storage.add_appointment({
        "code": code, "session": "s1", "patient_name": "Nguyễn Văn A",
        "patient_phone": phone, "department": "Khám tổng quát & Cạo vôi",
        "department_code": "kham_tong_quat", "doctor": "BS. An",
        "doctor_id": "bs_tq_01", "date": day, "time": "09:00",
        "created_at": day + "T08:00:00", "status": status, "reminders_sent": [],
        "booked_by_user_id": booked_by,
    })


def test_khong_thay_lich_cua_tai_khoan_khac_du_trung_sdt(client, monkeypatch):
    """Đặt hộ bằng SĐT người khác là hợp lệ — nhưng lịch đó là của NGƯỜI ĐẶT, chủ
    số điện thoại không được thấy lịch mình không đặt."""
    _lich_hen("SHI-CUATOI", "2026-08-06", booked_by="u1")
    _lich_hen("SHI-NGUOIKHAC", "2026-08-07", booked_by="u-khac")
    _dang_nhap_that(monkeypatch, {"id": "u1", "role": "guest", "username": "bn101",
                                  "phone": "0900000101"})

    rows = client.get("/api/patient/appointments").get_json()["appointments"]
    assert [a["code"] for a in rows] == ["SHI-CUATOI"]


def test_lich_cu_khong_co_dau_tai_khoan_van_nhan_theo_sdt(client, monkeypatch):
    """Lịch đặt trước khi có cột `booked_by_user_id` vẫn phải về đúng người."""
    _lich_hen("SHI-CU", "2026-08-06", booked_by=None)
    _lich_hen("SHI-CU-NGUOIKHAC", "2026-08-07", phone="0900000999", booked_by=None)
    _dang_nhap_that(monkeypatch, {"id": "u1", "role": "guest", "username": "bn101",
                                  "phone": "0900000101"})

    rows = client.get("/api/patient/appointments").get_json()["appointments"]
    assert [a["code"] for a in rows] == ["SHI-CU"]


def test_trang_thai_da_kham_den_tu_lich_su_dieu_tri(client, monkeypatch):
    """Nhãn "đã khám" phải đến từ việc nha sĩ ghi kết quả, KHÔNG suy từ ngày —
    lịch đã qua mà chưa ai ghi thì bệnh nhân chưa được coi là đã khám."""
    _lich_hen("SHI-DAKHAM", "2025-01-10")
    _lich_hen("SHI-CHUAGHI", "2025-01-11")
    storage.add_treatment({
        "history_id": "th-SHI-DAKHAM", "appointment_code": "SHI-DAKHAM",
        "patient_id": None, "patient_phone": "0900000101",
        "service_code": "kham_tong_quat", "doctor_id": "bs_tq_01",
        "treatment_date": "2025-01-10", "outcome": "success",
        "followup_required": False, "followup_due_date": None,
        "patient_rating": None, "created_at": "2025-01-10T10:00:00",
    })
    _dang_nhap_that(monkeypatch, {"id": "u1", "role": "guest", "username": "bn101",
                                  "phone": "0900000101"})

    rows = client.get("/api/patient/appointments").get_json()["appointments"]
    theo_ma = {a["code"]: a["treatment_recorded"] for a in rows}
    assert theo_ma == {"SHI-DAKHAM": True, "SHI-CHUAGHI": False}


def test_khong_muon_nhan_da_kham_cua_nguoi_khac(client, monkeypatch):
    """`list_treatments()` không tham số trả lịch sử CẢ phòng khám — lỡ gọi trần là
    mọi lịch hẹn của mọi người đều hiện "đã khám"."""
    _lich_hen("SHI-CUATOI", "2025-01-10")
    storage.add_treatment({
        "history_id": "th-nguoi-khac", "appointment_code": "SHI-CUATOI",
        "patient_id": None, "patient_phone": "0900000999",
        "service_code": "kham_tong_quat", "doctor_id": "bs_tq_01",
        "treatment_date": "2025-01-10", "outcome": "success",
        "followup_required": False, "followup_due_date": None,
        "patient_rating": None, "created_at": "2025-01-10T10:00:00",
    })
    _dang_nhap_that(monkeypatch, {"id": "u1", "role": "guest", "username": "bn101",
                                  "phone": "0900000101"})

    rows = client.get("/api/patient/appointments").get_json()["appointments"]
    assert [a["treatment_recorded"] for a in rows] == [False]


def test_khach_khong_dinh_danh_khong_doc_duoc_gi(client, monkeypatch):
    """Không có patient_id lẫn SĐT -> không được suy ra bất kỳ lượt khám nào."""
    _lich_hen("SHI-AIDO", "2025-01-10")
    storage.add_treatment({
        "history_id": "th-ai-do", "appointment_code": "SHI-AIDO",
        "patient_id": None, "patient_phone": "0900000999",
        "service_code": "kham_tong_quat", "doctor_id": "bs_tq_01",
        "treatment_date": "2025-01-10", "outcome": "success",
        "followup_required": False, "followup_due_date": None,
        "patient_rating": None, "created_at": "2025-01-10T10:00:00",
    })
    _dang_nhap_that(monkeypatch, {"id": "u1", "role": "guest", "username": "kh"})

    assert main._recorded_codes_for({"id": "u1", "role": "guest"}) == set()


def test_khong_doi_duoc_sdt_sang_so_cua_nguoi_khac(client, monkeypatch):
    """Cửa sau của cùng lỗ hổng: đăng ký bằng SĐT mới rồi sửa profile sang SĐT nạn
    nhân cũng đọc được lịch sử điều trị của họ."""
    _dang_nhap_that(monkeypatch, {"id": "u-toi", "role": "guest", "username": "bn999"})
    monkeypatch.setattr(main.storage, "get_user_by_phone",
                        lambda _p: {"id": "u-nan-nhan", "username": "bn111"})
    da_ghi = []
    monkeypatch.setattr(main.storage, "update_user_profile",
                        lambda *a, **kw: da_ghi.append(kw))

    resp = client.put("/api/profile", json={"phone": "0962043769"})
    assert resp.status_code == 409
    assert da_ghi == []


def test_van_luu_duoc_sdt_cua_chinh_minh(client, monkeypatch):
    _dang_nhap_that(monkeypatch, {"id": "u-toi", "role": "guest", "username": "bn999"})
    monkeypatch.setattr(main.storage, "get_user_by_phone",
                        lambda _p: {"id": "u-toi", "username": "bn999"})
    da_ghi = []
    monkeypatch.setattr(main.storage, "update_user_profile",
                        lambda *a, **kw: da_ghi.append(kw))

    resp = client.put("/api/profile", json={"phone": "0962043769"})
    assert resp.status_code == 200
    assert da_ghi[0]["phone"] == "0962043769"


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


# ---------------------------------------------------------------------------
# Vòng lặp dữ liệu: nha sĩ ghi kết quả -> visit_count tăng -> hết cold-start
# ---------------------------------------------------------------------------
def test_ghi_du_ba_lan_kham_thi_thoat_cold_start(client, monkeypatch):
    """Bằng chứng vòng lặp đã khép: trước khi có `POST /api/doctor/treatment`,
    không gì ghi vào `treatment_history` lúc chạy nên `visit_count` đứng yên ở 0
    và màn gợi ý cold-start vĩnh viễn, dù bệnh nhân đặt lịch bao nhiêu lần."""
    import app.doctor_api as doctor_api_module

    _login(monkeypatch)
    monkeypatch.setattr(doctor_api_module, "_get_current_doctor",
                        lambda: {"id": "u1", "role": "doctor", "doctor_id": "bs_tq_01"})
    monkeypatch.setattr(doctor_api_module, "_resolve_patient_id",
                        lambda _p: PATIENT_PROFILE_ID)

    appts = [{"code": f"SHI-{i}", "doctor_id": "bs_tq_01", "status": "confirmed",
              "date": f"2026-0{i}-10", "department_code": "kham_tong_quat",
              "patient_phone": "0900000101"} for i in (1, 2, 3)]
    monkeypatch.setattr(doctor_api_module.booking, "query_appointments",
                        lambda **kwargs: [dict(a) for a in appts])

    assert client.get("/api/patient/recommendations").get_json()["is_cold_start"] is True

    for i, appt in enumerate(appts, start=1):
        resp = client.post("/api/doctor/treatment",
                           json={"appointment_code": appt["code"]})
        assert resp.status_code == 201
        from app import reco
        reco.history.clear_cooccurrence_cache()
        body = client.get("/api/patient/recommendations").get_json()
        # Ngưỡng là 3 (COLD_START_MIN_VISITS) -> chỉ lần thứ 3 mới lật.
        assert body["is_cold_start"] is (i < 3)
        assert body["visit_count"] == i
