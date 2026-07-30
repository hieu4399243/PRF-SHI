"""
Tests cho engine gợi ý end-to-end (app/reco/__init__.py) — bộ lọc an toàn,
cold-start, empty state, và ghi log.

Chạy ở JSON mode với file tạm nên không đụng dữ liệu thật.

Ánh xạ test case TC-F2: TC-REC-001 (top-3), TC-REC-002 (cold-start vẫn đủ 3),
TC-REC-004 (dismiss vĩnh viễn), TC-REC-005 (empty state).
"""

from datetime import date

import pytest

from app import reco
from app.core import storage

TODAY = date(2026, 7, 30)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "USE_DB", False)
    monkeypatch.setattr(storage, "APPOINTMENTS_PATH", str(tmp_path / "appt.json"))
    monkeypatch.setattr(storage, "TREATMENT_HISTORY_PATH", str(tmp_path / "th.json"))
    monkeypatch.setattr(storage, "REC_LOG_PATH", str(tmp_path / "rl.json"))
    monkeypatch.setattr(storage, "PATIENT_PREFS_PATH", str(tmp_path / "pp.json"))
    reco.history.clear_cooccurrence_cache()
    yield
    reco.history.clear_cooccurrence_cache()


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


def _recommend(**kwargs):
    kwargs.setdefault("today", TODAY)
    kwargs.setdefault("use_llm", False)   # eval/test luôn dùng template
    kwargs.setdefault("log", False)
    return reco.recommend(**kwargs)


def _codes(result):
    return [i["service_code"] for i in result["items"]]


# ---------------------------------------------------------------------------
# Cold-start — TC-REC-002
# ---------------------------------------------------------------------------
def test_cold_start_khi_it_hon_3_luot():
    _visit("0911", "kham_tong_quat", "2026-06-30")
    _visit("0922", "sau_rang", "2026-05-30")
    result = _recommend(patient_phone="0911")
    assert result["is_cold_start"] is True
    assert result["cold_start_note"]


def test_cold_start_van_tra_du_3_goi_y():
    """TC-REC-002: 'vẫn trả về đủ 3 gợi ý; không trả về lỗi'."""
    for phone, code in [("0922", "sau_rang"), ("0933", "nha_chu"),
                        ("0944", "kham_tong_quat"), ("0955", "tham_my")]:
        _visit(phone, code, "2026-05-30")
    _visit("0911", "kham_tong_quat", "2026-06-30")
    result = _recommend(patient_phone="0911")
    assert result["is_cold_start"] is True
    assert len(result["items"]) == 3


def test_cold_start_khong_hien_phan_tram():
    """% ở cold-start đến từ độ phổ biến chung, không phải mức phù hợp cá nhân —
    hiện lên sẽ gây hiểu sai. Wireframe state 4 chỉ hiện thời lượng + giá."""
    for phone in ("0922", "0933", "0944"):
        _visit(phone, "sau_rang", "2026-05-30")
    _visit("0911", "kham_tong_quat", "2026-06-30")
    result = _recommend(patient_phone="0911")
    assert all(i["fit_percent"] is None for i in result["items"])
    assert all(i["duration_min"] > 0 for i in result["items"])


def test_khong_cold_start_khi_du_3_luot():
    _visit("0911", "kham_tong_quat", "2025-11-30", due="2026-05-30")
    _visit("0911", "nha_chu", "2024-06-30")
    _visit("0911", "tham_my", "2024-01-30")
    result = _recommend(patient_phone="0911")
    assert result["is_cold_start"] is False
    assert result["items"][0]["fit_percent"] > 0


def test_ho_so_hoan_toan_rong_khong_loi():
    result = _recommend(patient_phone="0999")
    assert result["is_cold_start"] is True
    assert result["visit_count"] == 0
    assert isinstance(result["items"], list)


# ---------------------------------------------------------------------------
# Bộ lọc an toàn — SEQ 4.5
# ---------------------------------------------------------------------------
def _ho_so_day_du(phone="0911"):
    """3 lượt điều trị -> vượt ngưỡng cold-start."""
    _visit(phone, "kham_tong_quat", "2025-11-30", due="2026-05-30")
    _visit(phone, "nha_chu", "2024-06-30")
    _visit(phone, "tham_my", "2024-01-30")


def test_dich_vu_da_bo_qua_khong_xuat_hien_lai():
    """TC-REC-004: 'lần sau không xuất hiện'."""
    _ho_so_day_du()
    before = _recommend(patient_phone="0911", patient_id="u1")
    assert "kham_tong_quat" in _codes(before)

    storage.add_dismissed_service("u1", "kham_tong_quat")
    after = _recommend(patient_phone="0911", patient_id="u1")
    assert "kham_tong_quat" not in _codes(after)


def test_dich_vu_da_co_lich_hen_sap_toi_bi_loai():
    _ho_so_day_du()
    storage.add_appointment({
        "code": "SHI-UP01", "session": "s", "patient_name": "A",
        "patient_phone": "0911", "department": "Khám tổng quát",
        "department_code": "kham_tong_quat", "doctor": "BS", "doctor_id": "bs_tq_01",
        "date": "2026-08-10", "time": "09:00", "created_at": "2026-07-01T00:00:00",
        "status": "confirmed",
    })
    assert "kham_tong_quat" not in _codes(_recommend(patient_phone="0911"))


def test_lich_hen_da_qua_khong_lam_loai_goi_y():
    _ho_so_day_du()
    storage.add_appointment({
        "code": "SHI-OLD1", "session": "s", "patient_name": "A",
        "patient_phone": "0911", "department": "Khám tổng quát",
        "department_code": "kham_tong_quat", "doctor": "BS", "doctor_id": "bs_tq_01",
        "date": "2026-01-10", "time": "09:00", "created_at": "2026-01-01T00:00:00",
        "status": "confirmed",
    })
    assert "kham_tong_quat" in _codes(_recommend(patient_phone="0911"))


def test_dich_vu_khong_dinh_ky_da_lam_thi_khong_goi_y_lai():
    """Đã điều trị tủy rồi thì không gợi ý điều trị tủy nữa."""
    _visit("0911", "noi_nha", "2026-05-30")
    _visit("0911", "kham_tong_quat", "2025-11-30")
    _visit("0911", "nha_chu", "2024-06-30")
    assert "noi_nha" not in _codes(_recommend(patient_phone="0911"))


def test_dich_vu_dinh_ky_chua_toi_chu_ky_thi_khong_goi_y():
    _visit("0911", "kham_tong_quat", "2026-06-30")   # 1 tháng < chu kỳ 6
    _visit("0911", "nha_chu", "2024-06-30")
    _visit("0911", "tham_my", "2024-01-30")
    assert "kham_tong_quat" not in _codes(_recommend(patient_phone="0911"))


def test_nha_khoa_tre_em_khong_goi_y_cho_nguoi_lon():
    _ho_so_day_du()
    result = _recommend(patient_phone="0911", profile={"birth_year": 1990})
    assert "nha_nhi" not in _codes(result)


def test_nha_khoa_tre_em_khong_goi_y_khi_khong_biet_tuoi():
    """Thiếu năm sinh + dịch vụ chỉ dành cho một nhóm tuổi -> không gợi ý. Nếu
    không, bệnh nhân chưa khai tuổi sẽ thấy 'Nha khoa trẻ em'."""
    _ho_so_day_du()
    result = _recommend(patient_phone="0911", profile={"birth_year": None})
    assert "nha_nhi" not in _codes(result)


def test_chinh_nha_khong_goi_y_cho_tre_em():
    _visit("0911", "nha_nhi", "2025-11-30", due="2026-05-30")
    _visit("0911", "nha_nhi", "2024-11-30")
    _visit("0911", "nha_nhi", "2023-11-30")
    result = _recommend(patient_phone="0911", profile={"birth_year": 2018})
    assert "chinh_nha" not in _codes(result)
    assert "nha_nhi" in _codes(result)


# ---------------------------------------------------------------------------
# Empty state — TC-REC-005
# ---------------------------------------------------------------------------
def test_empty_state_khi_bo_qua_het():
    _ho_so_day_du()
    from app.core.catalog import DEPARTMENTS
    for code in DEPARTMENTS:
        storage.add_dismissed_service("u1", code)
    result = _recommend(patient_phone="0911", patient_id="u1")
    assert result["items"] == []
    assert result["empty_reason"] == "all_dismissed"
    assert "Không còn gợi ý phù hợp" in result["empty_text"]


def test_reset_dismissed_lam_goi_y_tro_lai():
    _ho_so_day_du()
    from app.core.catalog import DEPARTMENTS
    for code in DEPARTMENTS:
        storage.add_dismissed_service("u1", code)
    assert _recommend(patient_phone="0911", patient_id="u1")["items"] == []
    storage.reset_dismissed_services("u1")
    assert _recommend(patient_phone="0911", patient_id="u1")["items"]


# ---------------------------------------------------------------------------
# Hình dạng kết quả — TC-REC-001
# ---------------------------------------------------------------------------
def test_toi_da_3_goi_y():
    _ho_so_day_du()
    assert len(_recommend(patient_phone="0911")["items"]) <= 3


def test_moi_goi_y_du_truong_de_render_card():
    _ho_so_day_du()
    for item in _recommend(patient_phone="0911")["items"]:
        for field in ("service_code", "name", "desc", "duration_min", "rank",
                      "reason_code", "reason_text", "reason_detail", "urgency"):
            assert field in item, field
        assert item["reason_text"]
        assert isinstance(item["reason_detail"], list) and item["reason_detail"]


def test_phan_tram_giam_dan_theo_thu_hang():
    """% phù hợp phải giảm dần, nếu không UI trông như lỗi (card #1 55%, #2 88%)."""
    _ho_so_day_du()
    items = _recommend(patient_phone="0911")["items"]
    fits = [i["fit_percent"] for i in items if i["fit_percent"] is not None]
    assert fits == sorted(fits, reverse=True)


def test_card_bu_khong_bao_gio_xep_tren_card_ca_nhan_hoa():
    _visit("0911", "kham_tong_quat", "2025-01-30", due="2025-07-30")
    _visit("0911", "nha_chu", "2024-06-30")
    _visit("0911", "tham_my", "2024-01-30")
    for phone in ("0922", "0933", "0944"):
        _visit(phone, "sau_rang", "2026-05-30")
    items = _recommend(patient_phone="0911")["items"]
    fillers = [i["rank"] for i in items if i.get("is_filler")]
    real = [i["rank"] for i in items if not i.get("is_filler")]
    assert not real or not fillers or min(fillers) > max(real)


def test_rank_lien_tuc_tu_1():
    _ho_so_day_du()
    items = _recommend(patient_phone="0911")["items"]
    assert [i["rank"] for i in items] == list(range(1, len(items) + 1))


def test_khong_tra_signals_ra_ngoai_qua_api_payload():
    """`signals` là nội bộ engine; patient_api phải lọc bỏ (test ở test_patient_api)."""
    _ho_so_day_du()
    assert "signals" in _recommend(patient_phone="0911")["items"][0]


# ---------------------------------------------------------------------------
# Gộp lịch sử theo id + SĐT
# ---------------------------------------------------------------------------
def test_gop_lich_su_truoc_va_sau_khi_co_tai_khoan():
    """Lịch đặt qua chatbot (chỉ SĐT) và lịch sau khi có tài khoản (có id) là của
    cùng một người — nếu không gộp thì bệnh nhân bị coi là cold-start oan."""
    _visit("0911", "kham_tong_quat", "2025-11-30", due="2026-05-30")
    _visit(None, "nha_chu", "2024-06-30", patient_id="u1")
    _visit(None, "tham_my", "2024-01-30", patient_id="u1")
    result = _recommend(patient_phone="0911", patient_id="u1")
    assert result["visit_count"] == 3
    assert result["is_cold_start"] is False


# ---------------------------------------------------------------------------
# Log
# ---------------------------------------------------------------------------
def test_ghi_recommendation_log():
    _ho_so_day_du()
    result = reco.recommend(patient_phone="0911", patient_id="u1", today=TODAY,
                            use_llm=False, log=True)
    entry = storage.get_rec_log(result["rec_log_id"])
    assert entry is not None
    assert entry["patient_id"] == "u1"
    assert entry["model_version"] == reco.MODEL_VERSION
    assert len(entry["recommendations"]) == len(result["items"])
    assert entry["feature_snapshot"]["visit_count"] == 3


def test_log_khong_chua_lich_su_dieu_tri_chi_tiet():
    """feature_snapshot là dữ liệu phân tích giữ lâu — không nhân bản cả hồ sơ
    điều trị của bệnh nhân vào đó."""
    _ho_so_day_du()
    result = reco.recommend(patient_phone="0911", patient_id="u1", today=TODAY,
                            use_llm=False, log=True)
    snap = storage.get_rec_log(result["rec_log_id"])["feature_snapshot"]
    assert "last_by_service" not in snap
    assert "category_distribution" not in snap


def test_loi_ghi_log_khong_lam_sap_goi_y(monkeypatch):
    """Log là dữ liệu phân tích, không phải nghiệp vụ: storage lỗi thì bệnh nhân
    vẫn phải thấy gợi ý."""
    _ho_so_day_du()

    def _boom(_entry):
        raise RuntimeError("DB sập")

    monkeypatch.setattr(storage, "add_rec_log", _boom)
    result = reco.recommend(patient_phone="0911", patient_id="u1", today=TODAY,
                            use_llm=False, log=True)
    assert result["items"]


def test_khong_ghi_log_khi_khong_co_tai_khoan():
    """Khách chưa đăng nhập -> không có patient_id -> không ghi log rác."""
    _ho_so_day_du()
    result = reco.recommend(patient_phone="0911", today=TODAY, use_llm=False, log=True)
    assert storage.get_rec_log(result["rec_log_id"]) is None


def test_trigger_la_bi_quy_ve_mac_dinh():
    _ho_so_day_du()
    result = reco.recommend(patient_phone="0911", patient_id="u1", trigger="hack",
                            today=TODAY, use_llm=False, log=True)
    assert storage.get_rec_log(result["rec_log_id"])["trigger"] == "booking_page"


def test_trigger_chatbot_duoc_ghi_nhan():
    """Chatbot là một trigger chính thức của luồng gợi ý (enum trong ER)."""
    _ho_so_day_du()
    result = reco.recommend(patient_phone="0911", patient_id="u1", trigger="chatbot",
                            today=TODAY, use_llm=False, log=True)
    assert storage.get_rec_log(result["rec_log_id"])["trigger"] == "chatbot"


def test_record_action_ghi_vao_log():
    _ho_so_day_du()
    result = reco.recommend(patient_phone="0911", patient_id="u1", today=TODAY,
                            use_llm=False, log=True)
    assert reco.record_action(result["rec_log_id"], "book", "kham_tong_quat", 1)
    assert storage.get_rec_log(result["rec_log_id"])["patient_action"] == "book"


# ---------------------------------------------------------------------------
# Dữ liệu rác
# ---------------------------------------------------------------------------
def test_bo_qua_lich_su_co_ma_dich_vu_khong_con_ton_tai():
    """Dữ liệu còn sót từ phiên bản đa khoa cũ không được thành gợi ý."""
    _visit("0911", "ho_hap", "2025-01-30")
    _visit("0911", "tieu_hoa", "2025-02-30" if False else "2025-02-28")
    _visit("0911", "kham_tong_quat", "2025-11-30", due="2026-05-30")
    result = _recommend(patient_phone="0911")
    assert result["visit_count"] == 1        # 2 bản ghi rác bị loại khỏi lịch sử
    assert "ho_hap" not in _codes(result)
    assert "tieu_hoa" not in _codes(result)


# ---------------------------------------------------------------------------
# Khách chưa đăng nhập — không có định danh
# ---------------------------------------------------------------------------
def test_khong_co_dinh_danh_thi_lich_su_rong_khong_phai_lich_su_ca_phong_kham():
    """`storage.list_treatments()` không tham số trả TOÀN BỘ bảng (cố ý, để dựng
    bảng đồng xuất hiện). `history.recent()` là API theo-từng-bệnh-nhân nên phải
    chặn: không có id lẫn SĐT -> rỗng. Thiếu chốt này, khách chưa đăng nhập nhận
    lịch sử của cả phòng khám làm của mình."""
    _ho_so_day_du("0911")
    _ho_so_day_du("0922")
    assert reco.history.recent() == []
    assert reco.history.recent(patient_id=None, patient_phone=None) == []
    # nhưng tầng storage vẫn trả toàn bộ khi cần cho thống kê chung
    assert len(storage.list_treatments()) == 6


def test_khach_luon_cold_start_du_he_thong_co_nhieu_du_lieu():
    _ho_so_day_du("0911")
    _ho_so_day_du("0922")
    result = _recommend()
    assert result["visit_count"] == 0
    assert result["is_cold_start"] is True
    assert len(result["items"]) == 3      # vẫn đủ 3 (dịch vụ phổ biến)
