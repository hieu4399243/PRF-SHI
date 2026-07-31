"""Chuyển tiếp sang nhân viên thật — CB-05 / SMMG-52.

Bốn acceptance criteria của story:
  1. chatbot nhận ra khi không giải quyết được và CHỦ ĐỘNG đề xuất chuyển tiếp;
  2. bệnh nhân yêu cầu gặp nhân viên bất cứ lúc nào;
  3. toàn bộ lịch sử chat được chuyển kèm cho nhân viên tiếp nhận;
  4. ngoài giờ làm việc thì ghi nhận yêu cầu và hẹn callback.

Bug gốc kèm theo: state HANDOFF không có handler nên lượt kế tiếp rơi vào nhánh
`else` của router và bệnh nhân đang chờ người thật bị chào lại như phiên mới.
"""

from datetime import datetime

import pytest

from app import chatbot
from app.chatbot import llm_reply
from app.chatbot.steps import handoff_step
from app.core import storage


@pytest.fixture(autouse=True)
def json_store(tmp_path, monkeypatch):
    """Ghi handoff vào file tạm — test không được đụng dữ liệu thật."""
    monkeypatch.setattr(storage, "USE_DB", False)
    monkeypatch.setattr(storage, "HANDOFF_PATH", str(tmp_path / "handoff.json"))


# Sau khi chuyển tiếp, bot còn xin tên+SĐT nên state là HANDOFF_ASK_CONTACT rồi
# mới về HANDOFF. Cả hai đều nghĩa là "đã chuyển sang nhân viên".
IN_HANDOFF = {"HANDOFF", "HANDOFF_ASK_CONTACT"}


def _last_handoff():
    items = storage.list_handoffs()
    assert items, "chưa có yêu cầu chuyển tiếp nào được ghi"
    return items[0]


# --- AC2: bệnh nhân yêu cầu gặp nhân viên ----------------------------------
@pytest.mark.parametrize("msg", [
    "cho tôi gặp nhân viên",
    "tôi muốn nói chuyện với người thật",
    "cho tôi gặp tư vấn viên",
])
def test_yeu_cau_gap_nguoi_that_thi_tao_ban_ghi(msg):
    chatbot.start(f"ho-{msg}")
    resp = chatbot.handle_message(f"ho-{msg}", msg)
    assert resp["state"] in IN_HANDOFF
    assert _last_handoff()["reason"] == handoff_step.PATIENT_REQUEST


# Bug thật: bản đầu chỉ liệt kê 7 từ khoá, nên "tôi cần gặp y tá" lọt qua CẢ hai
# lớp và bot đáp "mình không có chức năng hẹn gặp y tá" — đúng chữ, sai nghiệp vụ.
# AC là "yêu cầu gặp nhân viên BẤT CỨ LÚC NÀO", không phải "gặp đúng vài chức danh".
@pytest.mark.parametrize("msg", [
    "tôi cần gặp y tá",
    "cho tôi gặp lễ tân",
    "gọi giúp tôi người phụ trách",
    "cho tôi gặp trợ lý nha khoa",
    "tôi muốn gặp quản lý",
    "có ai đó không",
    "tôi muốn phàn nàn về bác sĩ",     # có "bác sĩ" nhưng là khiếu nại
])
def test_moi_cach_goi_con_nguoi_deu_chuyen_tiep(msg):
    from app.triage import safety
    assert safety.needs_human_handoff(msg), "lớp từ khoá phải bắt được (chạy cả khi LLM tắt)"
    chatbot.start(f"hu-{msg}")
    assert chatbot.handle_message(f"hu-{msg}", msg)["state"] in IN_HANDOFF


@pytest.mark.parametrize("msg", [
    "Tôi cần gặp bác sĩ",
    "tôi cần gặp bác sĩ để biết chi tiết hơn",
    "cho tôi gặp nha sĩ",
])
def test_gap_bac_si_van_la_dat_lich_chu_khong_chuyen_tiep(msg):
    """Ngoại lệ DUY NHẤT của quy tắc trên — xem llm_reply._CLINICIAN_WORDS."""
    chatbot.start(f"bs-{msg}")
    assert chatbot.handle_message(f"bs-{msg}", msg)["state"] != "HANDOFF"


def test_yeu_cau_duoc_o_giua_luong_dat_lich():
    """"Bất cứ lúc nào" — kể cả khi đang chọn ngày giờ."""
    chatbot.start("ho-mid")
    chatbot.handle_message("ho-mid", "tôi bị sâu răng")
    chatbot.handle_message("ho-mid", "yes")
    resp = chatbot.handle_message("ho-mid", "cho tôi gặp nhân viên")
    assert resp["state"] in IN_HANDOFF


# --- Bug: HANDOFF nuốt lượt ------------------------------------------------
def test_dang_cho_nhan_vien_thi_khong_bi_chao_lai():
    """Bug gốc: gõ tiếp khi đang chờ -> bot trả về "Xin chào 👋" như phiên mới."""
    chatbot.start("ho-wait")
    chatbot.handle_message("ho-wait", "cho tôi gặp nhân viên")
    chatbot.handle_message("ho-wait", "Minh Hiếu - 0912345678")
    resp = chatbot.handle_message("ho-wait", "tôi chờ được bao lâu")
    assert resp["state"] == "HANDOFF"
    assert "Xin chào" not in resp["reply"]


# Bug 2 của cùng luồng: sửa xong "bị chào lại" thì MỌI tin nhắn lúc chờ đều nhận
# chung một câu "đã ghi nhận thêm nội dung". Bệnh nhân hỏi "có ai đó hỗ trợ không"
# — vẫn đúng câu họ đã hỏi lúc đầu — mà nhận lại câu đó thì nghe như bot coi lời
# cầu cứu là một mẩu thông tin để lưu trữ, và KHÔNG trả lời câu hỏi.
@pytest.mark.parametrize("msg", [
    "có ai đó hỗ trợ không",
    "có ai không",
    "bao lâu nữa vậy",
    "sao lâu thế",
    "đến lượt tôi chưa",
])
def test_hoi_lai_luc_cho_thi_bao_tinh_trang_that(msg, monkeypatch):
    # Ghim giờ làm việc: để trôi theo giờ hệ thống thì test đỏ/xanh tuỳ lúc chạy.
    monkeypatch.setattr("app.chatbot.steps.handoff_step.is_working_time",
                        lambda when: True)
    chatbot.start("ho-status")
    chatbot.handle_message("ho-status", "tôi cần gặp người")
    chatbot.handle_message("ho-status", "Minh Hiếu - 0912345678")
    resp = chatbot.handle_message("ho-status", msg)
    assert resp["state"] == "HANDOFF"
    assert "ghi nhận thêm nội dung" not in resp["reply"]
    assert "đang chờ nhân viên" in resp["reply"]
    assert _last_handoff()["code"] in resp["reply"]   # có mã để đối chiếu


def test_ke_them_thong_tin_thi_van_la_ghi_nhan():
    """Phân biệt cho đúng: kể thêm triệu chứng KHÁC với hỏi lại về tình trạng."""
    chatbot.start("ho-info")
    chatbot.handle_message("ho-info", "tôi cần gặp người")
    chatbot.handle_message("ho-info", "Minh Hiếu - 0912345678")
    resp = chatbot.handle_message("ho-info", "à mà răng tôi còn chảy máu chân răng nữa")
    assert "ghi nhận thêm nội dung" in resp["reply"]


def test_nhan_vien_da_nhan_thi_khong_bao_dang_cho_nua(monkeypatch):
    """Nói "chờ chút nhé" khi đã có người nhận là nói sai -> phải đọc lại bản ghi."""
    monkeypatch.setattr("app.chatbot.steps.handoff_step.is_working_time",
                        lambda when: True)
    chatbot.start("ho-handled")
    chatbot.handle_message("ho-handled", "tôi cần gặp người")
    chatbot.handle_message("ho-handled", "Minh Hiếu - 0912345678")
    storage.set_handoff_handled(_last_handoff()["code"], handled_by="admin")
    resp = chatbot.handle_message("ho-handled", "có ai đó hỗ trợ không")
    assert "đã tiếp nhận" in resp["reply"]
    assert "đang chờ nhân viên" not in resp["reply"]


def test_ngoai_gio_hoi_lai_thi_nhac_moc_goi_lai(monkeypatch):
    monkeypatch.setattr("app.chatbot.steps.handoff_step.is_working_time",
                        lambda when: False)
    monkeypatch.setattr("app.chatbot.steps.handoff_step.next_working_time",
                        lambda when: datetime(2026, 8, 3, 8, 0))
    chatbot.start("ho-off-status")
    chatbot.handle_message("ho-off-status", "tôi cần gặp người")
    chatbot.handle_message("ho-off-status", "Minh Hiếu - 0912345678")
    resp = chatbot.handle_message("ho-off-status", "có ai đó hỗ trợ không")
    assert "03/08" in resp["reply"] and "gọi lại" in resp["reply"]


def test_lam_lai_van_thoat_duoc_khoi_handoff():
    chatbot.start("ho-reset")
    chatbot.handle_message("ho-reset", "cho tôi gặp nhân viên")
    resp = chatbot.handle_message("ho-reset", "làm lại")
    assert resp["state"] == "TRIAGE"


def test_khong_tao_yeu_cau_trung_khi_dang_cho():
    chatbot.start("ho-dup")
    chatbot.handle_message("ho-dup", "cho tôi gặp nhân viên")
    chatbot.handle_message("ho-dup", "cho tôi gặp nhân viên nhanh lên")
    assert len(storage.list_handoffs()) == 1


# --- AC3: toàn bộ lịch sử chat đi kèm --------------------------------------
def test_transcript_kem_theo_ca_hai_phia():
    chatbot.start("ho-tr")
    chatbot.handle_message("ho-tr", "tôi bị chảy máu chân răng")
    chatbot.handle_message("ho-tr", "cho tôi gặp nhân viên")
    transcript = _last_handoff()["transcript"]
    roles = {t["role"] for t in transcript}
    assert roles == {"user", "bot"}
    assert any("chảy máu chân răng" in t["message"] for t in transcript)


def test_cau_go_them_sau_khi_cho_cung_vao_transcript():
    """Nhân viên tiếp nhận phải đọc được cả những gì bệnh nhân nói lúc chờ."""
    chatbot.start("ho-more")
    chatbot.handle_message("ho-more", "cho tôi gặp nhân viên")
    chatbot.handle_message("ho-more", "Minh Hiếu - 0912345678")
    chatbot.handle_message("ho-more", "răng tôi đau từ hôm qua")
    transcript = _last_handoff()["transcript"]
    assert any("đau từ hôm qua" in t["message"] for t in transcript)


def test_transcript_khong_lo_so_dien_thoai():
    """Transcript lấy từ audit log nên PII phải đã bị ẩn (Nghị định 13/2023)."""
    chatbot.start("ho-pii")
    chatbot.handle_message("ho-pii", "gọi tôi số 0912345678 nhé")
    chatbot.handle_message("ho-pii", "cho tôi gặp nhân viên")
    dump = str(_last_handoff()["transcript"])
    assert "0912345678" not in dump


# --- AC4: ngoài giờ làm việc -----------------------------------------------
def test_ngoai_gio_thi_hen_goi_lai_va_xin_sdt(monkeypatch):
    monkeypatch.setattr("app.chatbot.steps.handoff_step.is_working_time",
                        lambda when: False)
    monkeypatch.setattr("app.chatbot.steps.handoff_step.next_working_time",
                        lambda when: datetime(2026, 8, 3, 8, 0))
    chatbot.start("ho-off")
    resp = chatbot.handle_message("ho-off", "cho tôi gặp nhân viên")
    assert "ngoài giờ làm việc" in resp["reply"]
    assert "03/08" in resp["reply"] and "08:00" in resp["reply"]
    assert "chờ trong giây lát" not in resp["reply"]  # không hứa suông khi vắng người
    assert resp["state"] == "HANDOFF_ASK_CONTACT"     # chưa có SĐT -> hỏi
    entry = _last_handoff()
    assert entry["within_hours"] is False
    assert entry["callback_at"].startswith("2026-08-03T08:00")


def test_ngoai_gio_nhan_duoc_sdt_goi_lai(monkeypatch):
    monkeypatch.setattr("app.chatbot.steps.handoff_step.is_working_time",
                        lambda when: False)
    chatbot.start("ho-phone")
    chatbot.handle_message("ho-phone", "cho tôi gặp nhân viên")
    resp = chatbot.handle_message("ho-phone", "0912345678")
    assert resp["state"] == "HANDOFF"
    assert _last_handoff()["patient_phone"] == "0912345678"


def test_sdt_sai_dinh_dang_thi_hoi_lai(monkeypatch):
    monkeypatch.setattr("app.chatbot.steps.handoff_step.is_working_time",
                        lambda when: False)
    chatbot.start("ho-badphone")
    chatbot.handle_message("ho-badphone", "cho tôi gặp nhân viên")
    resp = chatbot.handle_message("ho-badphone", "123")
    assert resp["state"] == "HANDOFF_ASK_CONTACT"
    assert "chưa đọc được số điện thoại" in resp["reply"]


def test_trong_gio_thi_khong_hen_goi_lai(monkeypatch):
    monkeypatch.setattr("app.chatbot.steps.handoff_step.is_working_time",
                        lambda when: True)
    chatbot.start("ho-on")
    resp = chatbot.handle_message("ho-on", "cho tôi gặp nhân viên")
    assert "chuyển bạn tới" in resp["reply"]
    assert _last_handoff()["callback_at"] is None


# --- Liên hệ: nhân viên phải gọi lại được --------------------------------
# Lỗ hổng thật: TRONG GIỜ làm việc bot không hề xin số, nên yêu cầu tới tay nhân
# viên với cột SĐT trống — khung chat này không có phía nhân viên trả lời trực
# tiếp, họ chỉ đọc ở /admin/handoff rồi gọi ra ngoài. Không có số = bệnh nhân
# ngồi chờ một cuộc gọi không bao giờ đến.
def test_trong_gio_van_phai_xin_lien_he(monkeypatch):
    monkeypatch.setattr("app.chatbot.steps.handoff_step.is_working_time",
                        lambda when: True)
    chatbot.start("ho-contact")
    resp = chatbot.handle_message("ho-contact", "cho tôi gặp nhân viên")
    assert resp["state"] == "HANDOFF_ASK_CONTACT"
    assert "số điện thoại" in resp["reply"]


@pytest.mark.parametrize("msg,name,phone", [
    ("Minh Hiếu - 0912345678", "Minh Hiếu", "0912345678"),
    ("tôi là Trần Minh Hiếu, sđt 0912345678", "Trần Minh Hiếu", "0912345678"),
    ("Anh Tuấn 0987654321", "Anh Tuấn", "0987654321"),
    ("0912345678", "", "0912345678"),
])
def test_tach_duoc_ten_va_sdt_trong_mot_luot(msg, name, phone):
    """Bug: bản đầu có "minh" trong danh sách từ nhiễu -> "Minh Hiếu" thành "Hiếu"."""
    from app.chatbot.steps.handoff_step import _parse_contact
    assert _parse_contact(msg) == (name, phone)


def test_lien_he_duoc_ghi_vao_ban_ghi_cho_nhan_vien():
    chatbot.start("ho-save")
    chatbot.handle_message("ho-save", "cho tôi gặp nhân viên")
    chatbot.handle_message("ho-save", "Minh Hiếu - 0912345678")
    entry = _last_handoff()
    assert entry["patient_name"] == "Minh Hiếu"
    assert entry["patient_phone"] == "0912345678"


# Bug: người ta hay gõ TÊN trước rồi mới tới SỐ ở lượt sau. Bản đầu vứt luôn cái
# tên đó, nên bệnh nhân "đã nhập tên rồi" mà cột Bệnh nhân ở trang nhân viên vẫn trống.
def test_nhap_ten_va_sdt_o_HAI_luot_thi_van_giu_duoc_ten():
    chatbot.start("ho-2turn")
    chatbot.handle_message("ho-2turn", "cho tôi gặp nhân viên")
    resp = chatbot.handle_message("ho-2turn", "Trần Minh Hiếu")
    assert resp["state"] == "HANDOFF_ASK_CONTACT"
    assert "Trần Minh Hiếu" in resp["reply"]        # xác nhận đã nhận được tên
    chatbot.handle_message("ho-2turn", "0912345678")
    entry = _last_handoff()
    assert entry["patient_name"] == "Trần Minh Hiếu"
    assert entry["patient_phone"] == "0912345678"


@pytest.mark.parametrize("text,is_name", [
    ("Trần Minh Hiếu", True),
    ("Hiếu", True),
    ("giờ tôi phải làm gì", False),      # câu hỏi, không phải tên
    ("sao lâu thế?", False),
    ("abc 123", False),                  # có số -> không phải tên
    ("tôi bị đau răng từ mấy hôm nay rồi bạn ạ", False),   # quá dài
])
def test_khong_nhan_nham_cau_hoi_thanh_ten(text, is_name):
    """Đoán nhầm thì nhân viên gọi điện gặp "Giờ Tôi Phải Làm Gì"."""
    from app.chatbot.steps.handoff_step import _looks_like_name
    assert _looks_like_name(text) is is_name


# Bug: lượt nhập liên hệ được ghi bằng nhãn ẩn PII, mà hàm nối transcript cũng
# cập nhật `last_message` -> cột "Câu cuối" ở trang nhân viên hiện "[LIÊN HỆ ĐÃ ẨN]"
# thay vì câu bệnh nhân thật sự nói.
def test_cau_cuoi_khong_bi_de_boi_nhan_an_pii():
    chatbot.start("ho-last")
    chatbot.handle_message("ho-last", "răng tôi đau nhức mấy hôm nay")
    chatbot.handle_message("ho-last", "cho tôi gặp nhân viên")
    chatbot.handle_message("ho-last", "Minh Hiếu - 0912345678")
    entry = _last_handoff()
    assert entry["last_message"] == "cho tôi gặp nhân viên"
    # Transcript VẪN phải có dấu vết lượt đó, chỉ là đã ẩn nội dung.
    assert any("[LIÊN HỆ ĐÃ ẨN]" in t["message"] for t in entry["transcript"])
    assert "0912345678" not in str(entry["transcript"])


def test_hoi_gi_o_buoc_xin_lien_he_thi_giai_thich_chu_khong_bao_sai_dinh_dang():
    chatbot.start("ho-why")
    chatbot.handle_message("ho-why", "cho tôi gặp nhân viên")
    resp = chatbot.handle_message("ho-why", "giờ tôi phải làm gì")
    assert "chưa đọc được số điện thoại" not in resp["reply"]
    assert "liên hệ với bạn" in resp["reply"]


def test_tu_choi_de_lai_so_thi_van_giu_yeu_cau():
    chatbot.start("ho-nophone")
    chatbot.handle_message("ho-nophone", "cho tôi gặp nhân viên")
    resp = chatbot.handle_message("ho-nophone", "thôi")
    assert resp["state"] == "HANDOFF"
    assert _last_handoff()["status"] == "new"       # yêu cầu KHÔNG bị huỷ


def test_bao_ro_nhan_vien_se_goi_vao_so_nao(monkeypatch):
    """"sao tôi biết để liên hệ" — trả lời sẵn trước khi họ phải hỏi."""
    monkeypatch.setattr("app.chatbot.steps.handoff_step.is_working_time",
                        lambda when: True)
    chatbot.start("ho-note")
    chatbot.handle_message("ho-note", "cho tôi gặp nhân viên")
    chatbot.handle_message("ho-note", "Minh Hiếu - 0912345678")
    resp = chatbot.handle_message("ho-note", "sao tôi biết để liên hệ")
    assert "0912345678" in resp["reply"]


def test_chua_co_so_ma_hoi_lien_he_thi_xin_lai():
    chatbot.start("ho-renew")
    chatbot.handle_message("ho-renew", "cho tôi gặp nhân viên")
    chatbot.handle_message("ho-renew", "thôi")                # bỏ qua lần 1
    resp = chatbot.handle_message("ho-renew", "sao tôi biết để liên hệ")
    assert resp["state"] == "HANDOFF_ASK_CONTACT"


# --- AC1: chatbot CHỦ ĐỘNG đề xuất khi bó tay ------------------------------
def _den_loi_de_nghi(sid):
    """Gõ đủ số lượt bó tay để bot tự đề nghị chuyển tiếp."""
    chatbot.start(sid)
    for _ in range(llm_reply.STUCK_LIMIT):
        resp = chatbot.handle_message(sid, "hôm nay trời đẹp nhỉ")
    assert resp["state"] == "HANDOFF_OFFER"
    return resp


def test_bo_tay_nhieu_luot_thi_DE_NGHI_chu_khong_tu_chuyen():
    """AC ghi "chủ động ĐỀ XUẤT" — suy đoán của bot thì phải hỏi, không tự đẩy đi.

    Backstop này tất định nên chạy được cả khi LLM tắt.
    """
    resp = _den_loi_de_nghi("ho-stuck")
    assert "chưa hỗ trợ được" in resp["reply"]
    assert len(resp["options"]) == 2
    assert storage.list_handoffs() == []  # chưa tạo yêu cầu nào khi chưa đồng ý


def test_dong_y_loi_de_nghi_thi_moi_tao_yeu_cau():
    _den_loi_de_nghi("ho-offer-yes")
    resp = chatbot.handle_message("ho-offer-yes", "yes")
    assert resp["state"] in IN_HANDOFF
    assert _last_handoff()["reason"] == handoff_step.BOT_STUCK


def test_tu_choi_loi_de_nghi_thi_quay_lai_buoc_cu():
    _den_loi_de_nghi("ho-offer-no")
    resp = chatbot.handle_message("ho-offer-no", "no")
    assert resp["state"] == "TRIAGE"
    assert storage.list_handoffs() == []
    # Và không được hỏi lại ngay ở lượt kế tiếp.
    assert chatbot.handle_message("ho-offer-no", "tôi bị sâu răng")["state"] == "CONFIRM_DEPT"


def test_lo_loi_de_nghi_ma_noi_tiep_viec_minh_thi_khong_bi_ep_tra_loi():
    _den_loi_de_nghi("ho-offer-skip")
    resp = chatbot.handle_message("ho-offer-skip", "tôi bị chảy máu chân răng")
    assert resp["state"] == "CONFIRM_DEPT"
    assert "Nha chu" in resp["reply"]


def test_yeu_cau_ro_rang_thi_chuyen_luon_khong_hoi_lai():
    """Bệnh nhân đã nói rõ ý -> hỏi "có chắc không" chỉ làm người đang bực thêm bực."""
    chatbot.start("ho-direct")
    assert chatbot.handle_message("ho-direct", "cho tôi gặp nhân viên")["state"] in IN_HANDOFF


def test_hoi_thoai_nhich_duoc_thi_xoa_bo_dem_bo_tay():
    """Một lượt lạc đề giữa chừng không được cộng dồn mãi thành handoff."""
    chatbot.start("ho-reset-stuck")
    chatbot.handle_message("ho-reset-stuck", "hôm nay trời đẹp nhỉ")
    chatbot.handle_message("ho-reset-stuck", "tôi bị sâu răng")   # -> CONFIRM_DEPT
    assert chatbot.get_session("ho-reset-stuck")["stuck_turns"] == 0


def test_llm_bao_can_nguoi_that_thi_chuyen_ngay(monkeypatch):
    """Lớp ngữ nghĩa: câu không có từ khoá nào trong HANDOFF_PATTERNS."""
    monkeypatch.setenv("LLM_ENABLED", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("CHAT_LLM_REPLY", "1")
    monkeypatch.setattr("app.triage.engine.classify_with_llm", lambda text: None)
    monkeypatch.setattr(llm_reply.llm, "chat_json",
                        lambda *a, **k: {"reply": "", "handoff": True})

    msg = "nói mãi mà chả đâu vào đâu"
    from app.triage import safety
    assert safety.needs_human_handoff(msg) is False   # từ khoá KHÔNG bắt được

    chatbot.start("ho-llm")
    resp = chatbot.handle_message("ho-llm", msg)
    assert resp["state"] in IN_HANDOFF
    assert _last_handoff()["reason"] == handoff_step.PATIENT_REQUEST


def test_llm_tat_van_chuyen_duoc_bang_tu_khoa(monkeypatch):
    """Đường thoát sang người thật không được phụ thuộc API bên thứ ba."""
    monkeypatch.setenv("CHAT_LLM_REPLY", "0")
    chatbot.start("ho-nollm")
    assert chatbot.handle_message("ho-nollm", "cho tôi gặp nhân viên")["state"] in IN_HANDOFF


# --- Fail-safe -------------------------------------------------------------
def test_storage_hong_van_tra_loi_duoc_benh_nhan(monkeypatch):
    """Mất bản ghi còn hơn mất luôn câu trả lời cho người đang cần giúp."""
    def boom(entry):
        raise RuntimeError("DB down")
    monkeypatch.setattr(storage, "add_handoff", boom)
    chatbot.start("ho-err")
    resp = chatbot.handle_message("ho-err", "cho tôi gặp nhân viên")
    assert resp["state"] in IN_HANDOFF
    assert "nhân viên" in resp["reply"]


# --- Giờ trực của phòng khám ------------------------------------------------
# Bug thật: giờ trực từng được suy từ WORK_SLOTS (10 slot => "đóng cửa lúc
# 10:30"), nên nhắn lúc 10:38 sáng thứ 6 — giờ hành chính bình thường — bị báo
# "ngoài giờ làm việc". Hai khái niệm này phải tách: WORK_SLOTS là mốc bắt đầu
# ca khám, giờ trực là khoảng lễ tân nghe máy và luôn rộng hơn.
def test_gio_hanh_chinh_khong_bi_coi_la_ngoai_gio():
    from app.core import catalog
    assert catalog.is_working_time(datetime(2026, 7, 31, 10, 38)) is True
    assert catalog.is_working_time(datetime(2026, 7, 31, 17, 0)) is True


def test_nghi_trua_cung_la_ngoai_gio():
    from app.core import catalog
    noon = datetime(2026, 7, 31, 12, 30)
    assert catalog.is_working_time(noon) is False
    assert catalog.next_working_time(noon) == datetime(2026, 7, 31, 13, 30)


def test_het_gio_chieu_thi_hen_sang_hom_sau():
    from app.core import catalog
    assert catalog.next_working_time(datetime(2026, 7, 31, 18, 0)) \
        == datetime(2026, 8, 1, 8, 0)


def test_mac_dinh_lam_ca_tuan_ke_ca_chu_nhat():
    from app.core import catalog
    assert catalog.clinic_closed_days() == set()
    assert catalog.is_working_time(datetime(2026, 8, 2, 9, 0)) is True   # Chủ nhật


def test_doi_gio_truc_bang_bien_moi_truong(monkeypatch):
    from app.core import catalog
    monkeypatch.setenv("CLINIC_HOURS", "09:00-17:00")
    monkeypatch.setenv("CLINIC_CLOSED_DAYS", "6")
    assert catalog.is_working_time(datetime(2026, 7, 31, 8, 30)) is False
    assert catalog.is_working_time(datetime(2026, 7, 31, 12, 30)) is True
    # Chủ nhật nghỉ -> hẹn sang Thứ 2.
    assert catalog.next_working_time(datetime(2026, 8, 2, 10, 0)) \
        == datetime(2026, 8, 3, 9, 0)


@pytest.mark.parametrize("bad", ["tám giờ tới trưa", "08:00", "", "25:00-26:00"])
def test_cau_hinh_gio_hong_thi_ve_mac_dinh_chu_khong_sap(monkeypatch, bad):
    """Một biến môi trường gõ sai không được phép làm chatbot y tế chết."""
    from app.core import catalog
    monkeypatch.setenv("CLINIC_HOURS", bad)
    assert catalog.clinic_periods() == [(8 * 60, 12 * 60), (13 * 60 + 30, 17 * 60 + 30)]


# --- API cho nhân viên (AC3: nhân viên phải đọc được) ----------------------
@pytest.fixture
def admin_client(monkeypatch):
    """Client đã qua cửa admin.

    Không đăng nhập thật: `/api/login` cần `DATABASE_URL`, mà fixture `json_store`
    ở trên đã tắt DB để test không ghi vào Supabase. Phần xác thực của các
    endpoint này chỉ là `_check_admin()` dùng chung với mọi endpoint admin khác
    (đã có test riêng); ở đây cần kiểm tra LOGIC list/detail/tiếp nhận.
    """
    from app import admin_api, main
    monkeypatch.setattr(admin_api, "_check_admin", lambda: True)
    monkeypatch.setattr(admin_api.auth, "resolve_user_from_token",
                        lambda token: {"username": "admin", "role": "admin"})
    main.app.config["TESTING"] = True
    return main.app.test_client()


def _seed_one():
    chatbot.start("ho-api")
    chatbot.handle_message("ho-api", "tôi bị sâu răng")
    chatbot.handle_message("ho-api", "cho tôi gặp nhân viên")
    return _last_handoff()["code"]


def test_api_liet_ke_va_dem_viec_can_lam(admin_client):
    code = _seed_one()
    data = admin_client.get("/api/admin/handoffs?status=new").get_json()
    assert data["new_count"] >= 1
    assert any(h["code"] == code for h in data["handoffs"])


def test_api_chi_tiet_kem_transcript(admin_client):
    code = _seed_one()
    data = admin_client.get(f"/api/admin/handoffs/{code}").get_json()
    assert data["ok"] is True
    assert any("sâu răng" in t["message"] for t in data["handoff"]["transcript"])


def test_api_tiep_nhan_mot_lan_duy_nhat(admin_client):
    """Hai nhân viên cùng bấm -> người đầu tiên là người tiếp nhận, không ghi đè."""
    code = _seed_one()
    client = admin_client
    assert client.post(f"/api/admin/handoffs/{code}/handled").status_code == 200
    assert client.post(f"/api/admin/handoffs/{code}/handled").status_code == 409
    assert storage.get_handoff(code)["status"] == "handled"


def test_api_ma_khong_ton_tai_tra_404(admin_client):
    assert admin_client.get("/api/admin/handoffs/HO-KHONGCO").status_code == 404


def test_api_can_dang_nhap_admin():
    from app import main
    main.app.config["TESTING"] = True
    assert main.app.test_client().get("/api/admin/handoffs").status_code == 401
