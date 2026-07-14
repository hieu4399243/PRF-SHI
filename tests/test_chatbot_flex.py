"""Các bước đặt lịch phải chấp nhận CÂU TRẢ LỜI TỰ DO, không chỉ đúng value của nút.

Bug gốc: đang ở bước chọn bác sĩ, gõ bất cứ thứ gì khác id bác sĩ đều bị lặp lại
"Bạn chọn giúp mình một bác sĩ ở các nút bên trên nhé."
"""

import pytest

from app import chatbot, booking, nlu, triage


@pytest.fixture
def sid(request):
    """Phiên đã đi tới bước PICK_DOCTOR của dịch vụ Chỉnh nha (2 bác sĩ)."""
    s = f"flex-{request.node.name}"
    chatbot.start(s)
    chatbot.handle_message(s, "tôi muốn niềng răng")
    resp = chatbot.handle_message(s, "yes")
    assert resp["state"] == "PICK_DOCTOR"
    return s


# --- Bước chọn bác sĩ -------------------------------------------------------
def test_chon_bac_si_bang_ten_rieng(sid):
    resp = chatbot.handle_message(sid, "cho tôi gặp bác sĩ Hải")
    assert resp["state"] == "PICK_DATE"
    assert chatbot.get_session(sid)["doctor_id"] == "bs_cn_02"


def test_ai_cung_duoc_thi_bot_xep_giup(sid):
    resp = chatbot.handle_message(sid, "bác sĩ nào cũng được")
    assert resp["state"] == "PICK_DATE"
    assert chatbot.get_session(sid)["doctor_id"]  # đã tự chọn, không bắt chọn lại


def test_doi_dich_vu_ngay_giua_buoc_chon_bac_si(sid):
    resp = chatbot.handle_message(sid, "thôi tôi muốn đổi dịch vụ")
    assert resp["state"] == "TRIAGE"


def test_trieu_chung_moi_thi_de_nghi_doi_dich_vu(sid):
    resp = chatbot.handle_message(sid, "à mà tôi bị chảy máu chân răng nữa")
    assert resp["state"] == "CONFIRM_DEPT"
    assert chatbot.get_session(sid)["dept_code"] == "nha_chu"


def test_go_linh_tinh_van_duoc_huong_dan_va_giu_nut(sid):
    resp = chatbot.handle_message(sid, "asdfgh")
    assert resp["state"] == "PICK_DOCTOR"
    assert len(resp["options"]) >= 2  # vẫn hiện lại danh sách bác sĩ để bấm


# --- Bước chọn ngày / giờ ---------------------------------------------------
def _den_buoc_chon_ngay(sid):
    chatbot.handle_message(sid, "ai cũng được")


def test_chon_ngay_bang_ngon_ngu_tu_nhien(sid):
    _den_buoc_chon_ngay(sid)
    resp = chatbot.handle_message(sid, "mai")
    assert resp["state"] == "PICK_TIME"
    assert chatbot.get_session(sid)["date"] == booking.get_available_dates()[0]


def test_chon_gio_bang_9h(sid):
    _den_buoc_chon_ngay(sid)
    chatbot.handle_message(sid, "sớm nhất")
    resp = chatbot.handle_message(sid, "9h")
    assert resp["state"] == "ASK_NAME"
    assert chatbot.get_session(sid)["time"] == "09:00"


def test_buoi_chieu_thi_thu_hep_danh_sach_gio(sid):
    _den_buoc_chon_ngay(sid)
    chatbot.handle_message(sid, "mai")
    resp = chatbot.handle_message(sid, "buổi chiều")
    assert resp["state"] == "PICK_TIME"
    assert all(o["value"] >= "12:00" for o in resp["options"])


def test_quay_lai_tu_buoc_chon_gio(sid):
    _den_buoc_chon_ngay(sid)
    chatbot.handle_message(sid, "thứ 5")
    resp = chatbot.handle_message(sid, "quay lại")
    assert resp["state"] == "PICK_DATE"


def test_hoi_thong_tin_dich_vu_giua_luc_dat_lich(sid):
    _den_buoc_chon_ngay(sid)
    resp = chatbot.handle_message(sid, "nội nha là khám gì")
    assert resp["state"] == "CONFIRM_DEPT"
    assert "tủy" in resp["reply"].lower()


def test_parser_ngay_giu_dau_gach_cheo():
    """_normalize() xóa dấu câu -> '20/7' từng bị hiểu thành '20 7' và parse hỏng."""
    dates = booking.get_available_dates()
    target = next(d for d in dates if d.endswith("-20"))
    assert nlu.match_date("20/7", dates) == target
    assert nlu.match_time("9:30", booking.get_available_times(dates[0])) == "09:30"


def test_ten_bac_si_mo_ho_thi_khong_doan_bua():
    docs = [{"id": "a", "name": "BS. Nguyễn Văn An"}, {"id": "b", "name": "BS. Trần Văn An"}]
    assert nlu.match_doctor("bác sĩ An", docs) is None  # 2 người trùng tên -> hỏi lại


# --- Hỏi về DANH SÁCH bác sĩ, và gọi tên bác sĩ của dịch vụ khác ------------
@pytest.fixture
def sid_sau_rang(request):
    """Phiên ở bước PICK_DOCTOR của Trám răng / Sâu răng — dịch vụ chỉ có 1 bác sĩ."""
    s = f"doc-{request.node.name}"
    chatbot.start(s)
    chatbot.handle_message(s, "tôi bị sâu răng")
    assert chatbot.handle_message(s, "yes")["state"] == "PICK_DOCTOR"
    return s


def test_hoi_co_bac_si_khac_khong_thi_phai_tra_loi(sid_sau_rang):
    """Bug gốc: hỏi "có bác sĩ khác không" chỉ nhận lại hướng dẫn chọn, không có câu trả lời."""
    resp = chatbot.handle_message(sid_sau_rang, "có bác sĩ khác không")
    assert resp["state"] == "PICK_DOCTOR"
    assert "chỉ có <b>một bác sĩ</b>" in resp["reply"]
    assert "Lê Minh Châu" in resp["reply"]


def test_liet_ke_du_bac_si_khi_dich_vu_co_nhieu_nguoi(sid):
    resp = chatbot.handle_message(sid, "có mấy bác sĩ")  # sid = Chỉnh nha, 2 bác sĩ
    assert "2 bác sĩ" in resp["reply"]
    assert "Đỗ Thị Giang" in resp["reply"] and "Ngô Văn Hải" in resp["reply"]


def test_bac_si_thuoc_dich_vu_khac_thi_bao_ro(sid_sau_rang):
    """BS. Nguyễn Văn An có thật, nhưng phụ trách Khám tổng quát -> phải nói ra."""
    resp = chatbot.handle_message(sid_sau_rang, "bác sĩ Nguyễn Văn An")
    assert resp["state"] == "CONFIRM_DEPT"
    assert "Khám tổng quát" in resp["reply"]
    # Chưa được đổi dịch vụ khi người dùng CHƯA đồng ý.
    assert chatbot.get_session(sid_sau_rang)["dept_code"] == "sau_rang"


def test_dong_y_doi_thi_xep_luon_dung_bac_si_do(sid_sau_rang):
    chatbot.handle_message(sid_sau_rang, "bác sĩ Nguyễn Văn An")
    resp = chatbot.handle_message(sid_sau_rang, "yes")
    sess = chatbot.get_session(sid_sau_rang)
    assert resp["state"] == "PICK_DATE"          # không bắt chọn lại bác sĩ
    assert sess["dept_code"] == "kham_tong_quat"
    assert sess["doctor_id"] == "bs_tq_01"


def test_tu_choi_doi_thi_giu_nguyen_dich_vu_cu(sid_sau_rang):
    chatbot.handle_message(sid_sau_rang, "bác sĩ Nguyễn Văn An")
    resp = chatbot.handle_message(sid_sau_rang, "no")
    sess = chatbot.get_session(sid_sau_rang)
    assert resp["state"] == "PICK_DOCTOR"
    assert sess["dept_code"] == "sau_rang"       # giữ đúng dịch vụ đang đặt
    assert sess["pending_dept_code"] is None
    assert sess["pending_doctor_id"] is None


def test_ten_bac_si_khong_ton_tai_thi_bao_khong_tim_thay(sid_sau_rang):
    resp = chatbot.handle_message(sid_sau_rang, "tôi muốn gặp bác sĩ Long Nhật")
    assert resp["state"] == "PICK_DOCTOR"
    assert "không tìm thấy" in resp["reply"].lower()


# --- Ý ĐỊNH DỪNG: "thôi tôi không bị nữa" ----------------------------------
def _den_confirm_dept(s):
    """Bot hỏi 'dịch vụ nào?' với 2 ứng viên (độ tin cậy medium)."""
    chatbot.start(s)
    resp = chatbot.handle_message(s, "tôi bị đau răng")
    assert resp["state"] == "CONFIRM_DEPT"
    return s


@pytest.mark.parametrize("msg", [
    "tôi không bị nữa",
    "thôi tôi hết đau rồi",
    "khỏi rồi",
    "thôi không đặt nữa",
    "để hôm khác",
    "thôi",
])
def test_muon_dung_thi_bot_phai_chot_hoi_thoai(msg):
    """Bug gốc: gõ "tôi không bị nữa" chỉ nhận lại "vui lòng chọn một dịch vụ"."""
    s = _den_confirm_dept(f"stop-{msg}")
    resp = chatbot.handle_message(s, msg)
    assert resp["state"] == "DONE"
    assert "làm lại" in resp["reply"]


def test_dung_vi_da_khoi_thi_van_dan_do_di_kham_neu_tai_phat():
    s = _den_confirm_dept("stop-recovered")
    resp = chatbot.handle_message(s, "tôi không bị nữa")
    assert "đỡ hơn" in resp["reply"]
    assert "quay lại" in resp["reply"] or "kéo dài" in resp["reply"]


def test_dung_duoc_o_giua_luong_dat_lich(sid):
    chatbot.handle_message(sid, "ai cũng được")   # -> PICK_DATE
    resp = chatbot.handle_message(sid, "thôi không đặt nữa")
    assert resp["state"] == "DONE"


def test_ask_name_khong_bi_cuop_luot_boi_y_dinh_dung(sid):
    """"Thôi" cũng là tên người — ở ASK_NAME phải hiểu là TÊN, không phải ý định dừng."""
    chatbot.handle_message(sid, "ai cũng được")
    chatbot.handle_message(sid, "mai")
    chatbot.handle_message(sid, "9h")             # -> ASK_NAME
    resp = chatbot.handle_message(sid, "Thôi")
    assert resp["state"] == "ASK_PHONE"
    assert chatbot.get_session(sid)["patient_name"] == "Thôi"


# --- CONFIRM_DEPT phải hiểu câu trả lời tự do ------------------------------
@pytest.mark.parametrize("msg", ["ừ", "ok", "đồng ý", "vâng", "đúng rồi", "chốt"])
def test_dong_y_bang_tu_ngu_tu_nhien(msg):
    chatbot.start("aff")
    chatbot.handle_message("aff", "tôi bị sâu răng")   # high -> bot hỏi yes/no
    resp = chatbot.handle_message("aff", msg)
    assert resp["state"] == "PICK_DOCTOR"


@pytest.mark.parametrize("msg", ["không phải", "sai rồi", "không đúng"])
def test_tu_choi_bang_tu_ngu_tu_nhien(msg):
    chatbot.start("den")
    chatbot.handle_message("den", "tôi bị sâu răng")
    resp = chatbot.handle_message("den", msg)
    assert resp["state"] == "TRIAGE"


def test_dong_y_mo_ho_thi_hien_lai_nut_chu_khong_doan_bua():
    """2 ứng viên ngang điểm -> "ừ" là đồng ý với cái nào? Phải hỏi lại, kèm nút."""
    s = _den_confirm_dept("amb")
    resp = chatbot.handle_message(s, "ừ")
    assert resp["state"] == "CONFIRM_DEPT"
    assert len(resp["options"]) >= 2


def test_mo_ta_them_trieu_chung_o_confirm_dept_thi_triage_lai():
    s = _den_confirm_dept("retriage")
    resp = chatbot.handle_message(s, "răng tôi chảy máu chân răng nữa")
    assert resp["state"] == "CONFIRM_DEPT"
    assert "Nha chu" in resp["reply"]


# --- Mất phiên (server restart / hết TTL / nhiều worker) --------------------
def test_mat_phien_thi_khong_nuot_tin_nhan_cua_nguoi_dung():
    """SESSIONS là in-memory: restart -> phiên về GREET. Tin nhắn triệu chứng
    của người dùng phải được triage, không bị thay bằng mỗi lời chào."""
    chatbot.start("lost")
    chatbot.handle_message("lost", "tôi bị sâu răng")
    chatbot.SESSIONS.clear()                       # giả lập server restart

    resp = chatbot.handle_message("lost", "tôi bị chảy máu chân răng")
    assert resp["state"] == "CONFIRM_DEPT"
    assert "Nha chu" in resp["reply"]


def test_mat_phien_va_cau_khong_hieu_thi_van_chao_lai():
    chatbot.start("lost2")
    chatbot.SESSIONS.clear()
    resp = chatbot.handle_message("lost2", "ừ")
    assert "Xin chào" in resp["reply"]


# --- Hỏi về DANH MỤC dịch vụ ----------------------------------------------
@pytest.mark.parametrize("msg", [
    "còn dịch vụ nào khác không",
    "phòng khám có những dịch vụ nào",
    "tôi muốn xem các dịch vụ",
])
def test_hoi_danh_muc_dich_vu_thi_phai_liet_ke(msg):
    """Bug gốc: hỏi "còn dịch vụ nào khác không" chỉ nhận lại "vui lòng chọn một dịch vụ"."""
    from app.data import DEPARTMENTS
    s = _den_confirm_dept(f"cat-{msg}")
    resp = chatbot.handle_message(s, msg)
    assert resp["state"] == "CONFIRM_DEPT"
    assert f"{len(DEPARTMENTS)} nhóm dịch vụ" in resp["reply"]
    # Phải chọn được NGAY từ danh mục vừa liệt kê.
    assert len(resp["options"]) >= len(DEPARTMENTS)


def test_hoi_danh_muc_giua_luc_dat_lich(sid):
    chatbot.handle_message(sid, "ai cũng được")     # -> PICK_DATE
    resp = chatbot.handle_message(sid, "còn dịch vụ nào khác không")
    assert "nhóm dịch vụ" in resp["reply"]


def test_hoi_danh_muc_khac_voi_doi_dich_vu(sid):
    """"đổi dịch vụ" -> mô tả lại; "còn dịch vụ nào khác" -> liệt kê. Đừng nhầm."""
    resp = chatbot.handle_message(sid, "tôi muốn đổi dịch vụ")
    assert resp["state"] == "TRIAGE"


# --- Câu hỏi thông tin viết kiểu chat --------------------------------------
@pytest.mark.parametrize("msg,expect", [
    ("trám răng là cái g", "sau_rang"),      # viết tắt "g" = "gì"
    ("trám răng là cái gì", "sau_rang"),
    ("niềng răng là j", "chinh_nha"),        # viết tắt "j" = "gì"
    ("tẩy trắng răng là sao", "tham_my"),
])
def test_hoi_thong_tin_kieu_viet_tat(msg, expect):
    assert triage.info_question_service(msg) == expect


@pytest.mark.parametrize("msg", ["tôi bị sâu răng", "răng tôi ê buốt khi ăn ngọt"])
def test_cau_mo_ta_trieu_chung_khong_bi_hieu_thanh_cau_hoi(msg):
    """Nới mẫu câu hỏi không được cướp lượt của câu mô tả triệu chứng."""
    assert triage.is_info_question(msg) is False


def test_hoi_dich_vu_la_gi_giua_buoc_chon_bac_si(sid_sau_rang):
    resp = chatbot.handle_message(sid_sau_rang, "trám răng là cái g")
    assert resp["state"] == "CONFIRM_DEPT"
    assert "trám lại" in resp["reply"] or "lỗ sâu" in resp["reply"]
    # Bấm "Đặt lịch" sau đó phải quay lại đúng bước chọn bác sĩ.
    assert chatbot.handle_message(sid_sau_rang, "yes")["state"] == "PICK_DOCTOR"
