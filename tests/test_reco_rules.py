"""
Tests cho bộ luật gợi ý (app/reco/rules.py) + câu lý do (app/reco/reasons.py).

Toàn bộ module `rules` là hàm thuần nên test được trực tiếp bằng feature vector
dựng tay — không cần DB, không cần seed.

Ánh xạ test case: TC-REC-001 (top-3 có % ≠ 0), TC-REC-006 (lý do không thuật ngữ
kỹ thuật). Xem docs/patient-recommendation-design.md §8.3.
"""

from datetime import date

import pytest

from app.reco import features as feat
from app.reco import reasons, rules

TODAY = date(2026, 7, 30)


def _history(*visits):
    """visits: (mã dịch vụ, ngày ISO, [followup_due_date])"""
    out = []
    for i, v in enumerate(visits):
        code, day = v[0], v[1]
        due = v[2] if len(v) > 2 else None
        out.append({
            "history_id": f"h{i}", "appointment_code": f"A{i}",
            "patient_id": "u1", "patient_phone": "0900000101",
            "service_code": code, "doctor_id": "bs_tq_01",
            "treatment_date": day, "outcome": "success",
            "followup_required": bool(due), "followup_due_date": due,
            "patient_rating": None, "created_at": day + "T10:00:00",
        })
    return out


def _features(*visits, birth_year=1990):
    return feat.build(_history(*visits), {"birth_year": birth_year}, TODAY)


def _codes(scored):
    return [s["service_code"] for s in scored]


def _by_code(scored, code):
    return next((s for s in scored if s["service_code"] == code), None)


# ---------------------------------------------------------------------------
# followup_due — nha sĩ đã hẹn tái khám và ngày đó đã trôi qua
# ---------------------------------------------------------------------------
def test_followup_due_kich_hoat_khi_qua_han():
    f = _features(("kham_tong_quat", "2025-11-30", "2026-05-30"))
    sigs = rules.signals(f)
    followup = [s for s in sigs if s["reason_code"] == "followup_due"]
    assert len(followup) == 1
    assert followup[0]["service_code"] == "kham_tong_quat"


def test_followup_due_khong_kich_hoat_khi_chua_toi_han():
    f = _features(("kham_tong_quat", "2026-07-01", "2027-01-01"))
    assert not [s for s in rules.signals(f) if s["reason_code"] == "followup_due"]


def test_qua_han_cang_lau_diem_cang_cao():
    it = _features(("kham_tong_quat", "2026-01-30", "2026-06-30"))   # quá hạn 1 tháng
    lau = _features(("kham_tong_quat", "2024-06-30", "2024-12-30"))  # quá hạn ~1.5 năm
    w_it = [s for s in rules.signals(it) if s["reason_code"] == "followup_due"][0]["weight"]
    w_lau = [s for s in rules.signals(lau) if s["reason_code"] == "followup_due"][0]["weight"]
    assert w_lau > w_it
    assert w_lau <= rules.W_FOLLOWUP_MAX   # bão hoà, không tăng vô hạn


def test_followup_khong_tinh_diem_hai_lan_voi_past_treatment():
    """Cùng một sự thật ("tới hạn làm lại") không được cộng điểm hai lần cho cùng
    dịch vụ — nếu không, % phù hợp bị thổi lên."""
    f = _features(("kham_tong_quat", "2025-01-30", "2025-07-30"))
    sigs = [s for s in rules.signals(f) if s["service_code"] == "kham_tong_quat"]
    codes = {s["reason_code"] for s in sigs}
    assert "followup_due" in codes
    assert "past_treatment" not in codes


# ---------------------------------------------------------------------------
# past_treatment — dịch vụ định kỳ tới chu kỳ
# ---------------------------------------------------------------------------
def test_past_treatment_kich_hoat_khi_toi_chu_ky():
    f = _features(("tham_my", "2025-05-30"))   # chu kỳ 12 tháng, đã 14 tháng
    sigs = [s for s in rules.signals(f) if s["reason_code"] == "past_treatment"]
    assert [s["service_code"] for s in sigs] == ["tham_my"]


def test_past_treatment_khong_kich_hoat_khi_chua_toi_chu_ky():
    f = _features(("kham_tong_quat", "2026-05-30"))   # 2 tháng < chu kỳ 6
    assert not [s for s in rules.signals(f) if s["reason_code"] == "past_treatment"]


def test_past_treatment_khong_ap_cho_dich_vu_khong_dinh_ky():
    """Nội nha / nhổ răng / trồng răng không phải việc làm lại theo chu kỳ."""
    f = _features(("noi_nha", "2020-01-01"), ("nho_rang", "2019-01-01"))
    sigs = [s for s in rules.signals(f) if s["reason_code"] == "past_treatment"]
    assert sigs == []


def test_qua_chu_ky_rat_lau_duoc_cong_diem():
    vua = _features(("tham_my", "2025-06-30"))   # ~13 tháng
    lau = _features(("tham_my", "2023-06-30"))   # ~37 tháng > 1.5 chu kỳ
    w_vua = [s for s in rules.signals(vua) if s["reason_code"] == "past_treatment"][0]["weight"]
    w_lau = [s for s in rules.signals(lau) if s["reason_code"] == "past_treatment"][0]["weight"]
    assert w_lau > w_vua


# ---------------------------------------------------------------------------
# care_pathway — bước tiếp theo trong chuỗi điều trị
# ---------------------------------------------------------------------------
def test_care_pathway_noi_nha_dan_toi_phuc_hinh():
    f = _features(("noi_nha", "2026-05-30"))
    sigs = [s for s in rules.signals(f) if s["reason_code"] == "care_pathway"]
    assert [s["service_code"] for s in sigs] == ["phuc_hinh"]


def test_care_pathway_het_han_cua_so_thi_ngung_goi_y():
    """Không có cửa sổ thời gian thì một lần điều trị tủy năm 2020 sẽ gợi ý bọc
    răng sứ mãi mãi."""
    f = _features(("noi_nha", "2020-01-01"))
    assert not [s for s in rules.signals(f) if s["reason_code"] == "care_pathway"]


# ---------------------------------------------------------------------------
# similar_patients — đồng xuất hiện
# ---------------------------------------------------------------------------
def test_similar_patients_dung_ti_le_dong_xuat_hien():
    f = _features(("kham_tong_quat", "2026-06-30"))
    cooc = {"kham_tong_quat": {"sau_rang": (0.5, 6)}}
    sigs = [s for s in rules.signals(f, cooc=cooc) if s["reason_code"] == "similar_patients"]
    assert len(sigs) == 1
    assert sigs[0]["service_code"] == "sau_rang"
    assert sigs[0]["weight"] == pytest.approx(rules.W_SIMILAR_FACTOR * 0.5)
    assert sigs[0]["ctx"]["percent"] == 50


def test_similar_patients_khong_goi_y_dich_vu_da_dung():
    f = _features(("kham_tong_quat", "2026-06-30"), ("sau_rang", "2026-05-30"))
    cooc = {"kham_tong_quat": {"sau_rang": (0.9, 10)}}
    sigs = [s for s in rules.signals(f, cooc=cooc) if s["reason_code"] == "similar_patients"]
    assert sigs == []


def test_similar_patients_gop_ve_mot_tin_hieu_manh_nhat():
    """Hai dịch vụ trong lịch sử cùng dẫn tới một dịch vụ đích thì đó vẫn là MỘT
    lý do, không phải hai (nếu không thì noisy-OR cộng dồn sai)."""
    f = _features(("kham_tong_quat", "2026-06-30"), ("nha_chu", "2026-06-01"))
    cooc = {"kham_tong_quat": {"sau_rang": (0.4, 5)},
            "nha_chu": {"sau_rang": (0.8, 5)}}
    sigs = [s for s in rules.signals(f, cooc=cooc) if s["reason_code"] == "similar_patients"]
    assert len(sigs) == 1
    assert sigs[0]["ctx"]["percent"] == 80


# ---------------------------------------------------------------------------
# age_group
# ---------------------------------------------------------------------------
def test_age_group_cong_diem_cho_nhom_tuoi():
    teen = _features(("kham_tong_quat", "2026-06-30"), birth_year=2011)
    sigs = [s for s in rules.signals(teen) if s["reason_code"] == "age_group"]
    assert "chinh_nha" in [s["service_code"] for s in sigs]


def test_khong_biet_tuoi_thi_khong_co_tin_hieu_tuoi():
    f = _features(("kham_tong_quat", "2026-06-30"), birth_year=None)
    assert not [s for s in rules.signals(f) if s["reason_code"] == "age_group"]


# ---------------------------------------------------------------------------
# Gộp điểm noisy-OR
# ---------------------------------------------------------------------------
def test_nhieu_tin_hieu_thi_diem_cao_hon_mot_tin_hieu():
    """Điểm cốt lõi của noisy-OR: thêm bằng chứng phải làm tăng độ tin cậy.
    Lấy max thì không, cộng thẳng thì vượt 1.0."""
    mot = rules.score([{"service_code": "x", "weight": 0.5, "reason_code": "a", "ctx": {}}])
    hai = rules.score([{"service_code": "x", "weight": 0.5, "reason_code": "a", "ctx": {}},
                       {"service_code": "x", "weight": 0.5, "reason_code": "b", "ctx": {}}])
    assert hai[0]["confidence"] > mot[0]["confidence"]


def test_confidence_khong_bao_gio_dat_100_phan_tram():
    """Hệ thống không hứa chắc chắn 100% về một việc y tế."""
    many = [{"service_code": "x", "weight": 0.9, "reason_code": f"r{i}", "ctx": {}}
            for i in range(10)]
    assert rules.score(many)[0]["confidence"] <= rules.CONFIDENCE_CAP
    assert rules.score(many)[0]["fit_percent"] <= 95


def test_diem_duoi_nguong_bi_loai():
    weak = [{"service_code": "x", "weight": 0.1, "reason_code": "popular", "ctx": {}}]
    assert rules.score(weak) == []


def test_fit_percent_khac_0_cho_ung_vien_duoc_giu():
    """TC-REC-001: mỗi gợi ý hiển thị phải có % phù hợp ≠ 0."""
    scored = rules.score([{"service_code": "x", "weight": 0.6,
                           "reason_code": "followup_due", "ctx": {}}])
    assert scored[0]["fit_percent"] > 0


def test_thu_tu_on_dinh_khi_hoa_diem():
    """Hoà điểm phải sắp theo mã dịch vụ, nếu không eval chạy lại ra thứ tự khác."""
    sigs = [{"service_code": "b", "weight": 0.5, "reason_code": "r", "ctx": {}},
            {"service_code": "a", "weight": 0.5, "reason_code": "r", "ctx": {}}]
    assert _codes(rules.score(sigs)) == ["a", "b"]
    assert _codes(rules.score(list(reversed(sigs)))) == ["a", "b"]


def test_reason_code_hien_thi_la_tin_hieu_manh_nhat():
    sigs = [{"service_code": "x", "weight": 0.3, "reason_code": "popular", "ctx": {}},
            {"service_code": "x", "weight": 0.7, "reason_code": "followup_due", "ctx": {}}]
    assert rules.score(sigs)[0]["reason_code"] == "followup_due"


def test_giu_lai_moi_tin_hieu_cho_man_chi_tiet():
    """REC-02 hiện MỌI lý do, không chỉ lý do chính."""
    sigs = [{"service_code": "x", "weight": 0.3, "reason_code": "popular", "ctx": {}},
            {"service_code": "x", "weight": 0.7, "reason_code": "followup_due", "ctx": {}}]
    assert len(rules.score(sigs)[0]["signals"]) == 2


# ---------------------------------------------------------------------------
# urgency
# ---------------------------------------------------------------------------
def test_urgency_high_khi_bo_han_mot_ky_tai_kham():
    f = _features(("kham_tong_quat", "2025-01-30", "2025-07-30"))  # quá hạn ~12 tháng
    scored = rules.score(rules.signals(f))
    assert _by_code(scored, "kham_tong_quat")["urgency"] == "high"


def test_urgency_low_khi_diem_thap():
    sigs = [{"service_code": "x", "weight": 0.3, "reason_code": "popular", "ctx": {}}]
    assert rules.score(sigs)[0]["urgency"] == "low"


# ---------------------------------------------------------------------------
# reasons — TC-REC-006
# ---------------------------------------------------------------------------
def test_moi_reason_code_deu_co_cau_ly_do():
    for reason_code in ("followup_due", "past_treatment", "care_pathway",
                        "similar_patients", "age_group", "popular"):
        text = reasons.render({"service_code": "kham_tong_quat",
                               "reason_code": reason_code,
                               "ctx": {"months_since": 8, "cycle": 6, "percent": 50,
                                       "from_service": "noi_nha", "age_group": "adult"}})
        assert text and len(text) <= reasons.MAX_REASON_LENGTH, reason_code


def test_ly_do_khong_chua_thuat_ngu_ky_thuat():
    """TC-REC-006: người dùng thường phải đọc hiểu được."""
    for reason_code in ("followup_due", "past_treatment", "care_pathway",
                        "similar_patients", "age_group", "popular"):
        text = reasons.render({"service_code": "kham_tong_quat",
                               "reason_code": reason_code,
                               "ctx": {"months_since": 8, "cycle": 6, "percent": 50,
                                       "from_service": "noi_nha"}})
        assert not reasons.has_banned_term(text), f"{reason_code}: {text}"


def test_reason_code_la_van_co_cau_mac_dinh():
    assert reasons.render({"service_code": "x", "reason_code": "khong_ton_tai", "ctx": {}})


def test_has_banned_term_bat_duoc_thuat_ngu():
    assert reasons.has_banned_term("Điểm số của model là 0.9")
    assert reasons.has_banned_term("Dựa trên embedding của bạn")
    assert not reasons.has_banned_term("Đã 6 tháng kể từ lần khám gần nhất.")


def test_service_payload_co_thoi_luong_va_gia():
    """TC-REC-007: modal chi tiết phải hiện thời lượng + giá cơ bản."""
    payload = reasons.service_payload("kham_tong_quat")
    assert payload["duration_min"] > 0
    assert payload["price_from"] is not None
    assert payload["name"]


def test_moi_cau_template_deu_qua_duoc_bo_chan_y_te():
    """Bộ chặn `has_medical_claim` cố ý chặt — phải chắc nó không loại oan chính
    các câu template của mình, nếu không mọi lý do đều bị quay về câu mặc định."""
    for reason_code in ("followup_due", "past_treatment", "care_pathway",
                        "similar_patients", "age_group", "popular"):
        for code in ("kham_tong_quat", "noi_nha", "nha_chu", "phuc_hinh", "nha_nhi"):
            text = reasons.render({"service_code": code, "reason_code": reason_code,
                                   "ctx": {"months_since": 14, "cycle": 6, "percent": 43,
                                           "from_service": "noi_nha"}})
            assert not reasons.has_medical_claim(text), f"{reason_code}/{code}: {text}"


def test_has_medical_claim_bat_duoc_chan_doan_va_thuoc():
    assert reasons.has_medical_claim("Bạn bị viêm tủy nặng")
    assert reasons.has_medical_claim("Nên uống thuốc kháng sinh")
    assert reasons.has_medical_claim("Dịch vụ này chữa khỏi hoàn toàn")
    assert not reasons.has_medical_claim("Đã 6 tháng kể từ lần khám gần nhất.")


# ---------------------------------------------------------------------------
# reason_detail — nội dung "Tại sao AI gợi ý?" ở màn chi tiết REC-02
# ---------------------------------------------------------------------------
def test_reason_detail_mo_dau_bang_dong_du_kien_thoi_gian():
    """Wireframe REC-02 mở đầu bằng một dòng DỮ KIỆN ("Lần khám gần nhất: ... —
    đã qua 6 tháng") để bệnh nhân đối chiếu được, thay vì chỉ đọc kết luận."""
    f = _features(("kham_tong_quat", "2025-11-30", "2026-05-30"))
    item = rules.score(rules.signals(f))[0]
    detail = reasons.render_all(item, f)
    assert len(detail) >= 2
    assert "30/11/2025" in detail[0]
    assert "đã qua" in detail[0]


def test_reason_detail_uu_tien_moc_cua_chinh_dich_vu_dang_xem():
    f = _features(("kham_tong_quat", "2025-11-30", "2026-05-30"),
                  ("tham_my", "2026-07-01"))
    item = next(i for i in rules.score(rules.signals(f))
                if i["service_code"] == "kham_tong_quat")
    detail = reasons.render_all(item, f)
    assert "30/11/2025" in detail[0]          # mốc của khám tổng quát
    assert "01/07/2026" not in detail[0]      # không lấy nhầm mốc thẩm mỹ


def test_reason_detail_khong_co_features_van_chay():
    """Gọi không truyền features (vd. từ test cũ) không được vỡ."""
    item = rules.score([{"service_code": "kham_tong_quat", "weight": 0.6,
                         "reason_code": "popular", "ctx": {"percent": 40}}])[0]
    assert reasons.render_all(item)


def test_reason_detail_khong_trung_lap():
    f = _features(("kham_tong_quat", "2025-11-30", "2026-05-30"))
    item = rules.score(rules.signals(f))[0]
    detail = reasons.render_all(item, f)
    assert len(detail) == len(set(detail))


def test_dong_du_kien_khong_chua_khang_dinh_y_te():
    f = _features(("noi_nha", "2026-05-30"))
    for item in rules.score(rules.signals(f)):
        for line in reasons.render_all(item, f):
            assert not reasons.has_medical_claim(line), line
