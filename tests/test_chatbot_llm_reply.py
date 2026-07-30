"""Ở các nhánh bộ luật BÓ TAY, chatbot phải trả lời bằng LLM thay vì đọc template.

Bug gốc (quan sát trên demo): "tôi đang ăn cơm mà thấy không ngon" -> "Mình chưa rõ
triệu chứng của bạn."; hỏi lại "bạn có chắc không" -> "Bạn vui lòng chọn một dịch vụ
ở các nút bên trên." Đúng luật nhưng đọc như cây quyết định.

Test KHÔNG gọi API thật: monkeypatch `app.triage.llm.chat_json` (cổng ra duy nhất).
"""

import pytest

from app import chatbot
from app.chatbot import llm_reply


@pytest.fixture
def llm_on(monkeypatch):
    """Bật LLM và thay cổng ra bằng hàm giả — trả về list các prompt đã gửi đi."""
    monkeypatch.setenv("LLM_ENABLED", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("CHAT_LLM_REPLY", "1")
    # Triage vẫn phải chạy rule-based: bài test này đo LỚP CÂU CHỮ, không đo phân loại.
    monkeypatch.setattr("app.triage.engine.classify_with_llm", lambda text: None)

    sent = []

    def fake(system, user, **kwargs):
        sent.append(user)
        return {"reply": "Mình hiểu rồi, bạn kể thêm giúp mình nhé."}

    monkeypatch.setattr(llm_reply.llm, "chat_json", fake)
    return sent


def _reply_of(sid, msg):
    return chatbot.handle_message(sid, msg)["reply"]


# Câu bộ luật v2 KHÔNG nhận ra (dùng làm đầu vào cho nhánh fallback).
# Lưu ý: chính câu trên demo — "tôi đang ăn cơm mà thấy không ngon" — lại bị v2
# chấm 1 điểm cho Sâu răng vì "cơm" bỏ dấu trùng từ khoá "cộm"; test tái hiện ca
# demo đó phải chạy bằng engine LLM, xem test_ca_demo_* bên dưới.
UNKNOWN = "hôm nay trời đẹp nhỉ"


# --- Hai ca hỏng trên demo --------------------------------------------------
def test_cau_khong_hieu_o_triage_duoc_llm_tra_loi(llm_on):
    chatbot.start("s1")
    resp = chatbot.handle_message("s1", UNKNOWN)
    assert resp["state"] == "TRIAGE"                  # bước không đổi
    assert "chưa rõ triệu chứng" not in resp["reply"]  # không còn template cứng
    assert resp["reply"] == "Mình hiểu rồi, bạn kể thêm giúp mình nhé."


def test_ca_demo_an_com_khong_ngon(llm_on, monkeypatch):
    """Tái hiện đúng lượt hỏng trên demo: engine LLM bảo "không khớp dịch vụ nào"."""
    monkeypatch.setattr("app.triage.engine.classify_with_llm", lambda text: [])
    chatbot.start("demo")
    resp = chatbot.handle_message("demo", "tôi đang ăn cơm mà thấy không ngon")
    assert resp["state"] == "TRIAGE"
    assert "chưa rõ triệu chứng" not in resp["reply"]


def test_hoi_lai_o_confirm_dept_duoc_llm_tra_loi(llm_on):
    chatbot.start("s2")
    chatbot.handle_message("s2", "tôi bị sâu răng")   # -> CONFIRM_DEPT (yes/no)
    resp = chatbot.handle_message("s2", "bạn có chắc không")
    assert resp["state"] == "CONFIRM_DEPT"
    assert "vui lòng chọn một dịch vụ" not in resp["reply"]
    assert len(resp["options"]) >= 2                  # nút vẫn còn nguyên


def test_cau_tai_khang_dinh_dich_vu_van_deo_disclaimer(llm_on):
    """Câu LLM ở CONFIRM_DEPT là câu tái khẳng định gợi ý -> phải kèm disclaimer."""
    chatbot.start("s2b")
    chatbot.handle_message("s2b", "tôi bị sâu răng")
    resp = chatbot.handle_message("s2b", "bạn có chắc không")
    assert "không chẩn đoán bệnh" in resp["reply"]


def test_llm_khong_duoc_doi_state_va_options(llm_on):
    """Bất biến của cả lớp này: LLM chỉ đổi CÂU CHỮ."""
    chatbot.start("s3")
    chatbot.handle_message("s3", "tôi muốn niềng răng")
    chatbot.handle_message("s3", "yes")               # -> PICK_DOCTOR
    resp = chatbot.handle_message("s3", "hôm nay trời đẹp nhỉ")
    assert resp["state"] == "PICK_DOCTOR"
    assert [o["value"] for o in resp["options"]]      # vẫn là danh sách bác sĩ


# --- Ngữ cảnh gửi cho LLM ---------------------------------------------------
def test_prompt_kem_dich_vu_dang_de_xuat_va_luot_truoc(llm_on):
    chatbot.start("s4")
    chatbot.handle_message("s4", "tôi bị sâu răng")
    chatbot.handle_message("s4", "bạn có chắc không")
    prompt = llm_on[-1]
    assert "Trám răng / Sâu răng" in prompt            # biết đang nói về dịch vụ nào
    assert "tôi bị sâu răng" in prompt                 # biết "chắc" là chắc về cái gì
    assert "BỆNH NHÂN VỪA NÓI: bạn có chắc không" in prompt


def test_prompt_kem_danh_sach_bac_si_that(llm_on):
    chatbot.start("s5")
    chatbot.handle_message("s5", "tôi muốn niềng răng")
    chatbot.handle_message("s5", "yes")
    chatbot.handle_message("s5", "hôm nay trời đẹp nhỉ")
    assert "Đỗ Thị Giang" in llm_on[-1] and "Ngô Văn Hải" in llm_on[-1]


def test_khong_luu_ten_va_sdt_vao_ngu_canh():
    """user_turns là ngữ cảnh gửi ra OpenRouter -> không được chứa PII."""
    chatbot.start("s6")
    chatbot.handle_message("s6", "tôi bị sâu răng")
    chatbot.handle_message("s6", "yes")
    chatbot.handle_message("s6", "ai cũng được")
    chatbot.handle_message("s6", "mai")
    chatbot.handle_message("s6", "9h")                # -> ASK_NAME
    chatbot.handle_message("s6", "Trần Minh Hiếu")
    chatbot.handle_message("s6", "0912345678")
    turns = chatbot.get_session("s6")["user_turns"]
    assert "Trần Minh Hiếu" not in turns and "0912345678" not in turns


# --- Fallback: hỏng chỗ nào cũng phải quay về template ----------------------
def test_llm_tat_thi_giu_nguyen_template(monkeypatch):
    monkeypatch.setenv("CHAT_LLM_REPLY", "0")
    chatbot.start("off")
    assert "chưa rõ triệu chứng" in _reply_of("off", UNKNOWN)


def test_llm_loi_thi_giu_nguyen_template(llm_on, monkeypatch):
    monkeypatch.setattr(llm_reply.llm, "chat_json", lambda *a, **k: None)
    chatbot.start("err")
    assert "chưa rõ triệu chứng" in _reply_of("err", UNKNOWN)


@pytest.mark.parametrize("bad", [
    "Bạn bị viêm tủy rồi, cần điều trị ngay.",        # chẩn đoán
    "Bạn uống thuốc giảm đau trước nhé.",             # kê đơn
    "Dịch vụ này khoảng 500k thôi bạn.",              # giá bịa
    "Mai 9h còn trống, mình giữ chỗ nhé.",            # lịch bịa
    "Bạn gọi 0912345678 để được hỗ trợ.",             # SĐT bịa
    "Mô hình của mình chấm điểm ra dịch vụ này.",     # lộ kỹ thuật
    "<script>alert(1)</script>",                      # thẻ HTML lạ
    "x" * 500,                                        # dài lê thê
    "",
    None,
])
def test_cau_vi_pham_bi_loai_va_quay_ve_template(llm_on, monkeypatch, bad):
    monkeypatch.setattr(llm_reply.llm, "chat_json", lambda *a, **k: {"reply": bad})
    chatbot.start("guard")
    assert "chưa rõ triệu chứng" in _reply_of("guard", UNKNOWN)


# --- Các lối đi tất định KHÔNG được giao cho LLM ----------------------------
def test_cap_cuu_van_di_duong_guardrail(llm_on):
    chatbot.start("emg")
    resp = chatbot.handle_message("emg", "tôi bị sưng mặt lan và khó nuốt")
    assert "115" in resp["reply"]
    assert not llm_on                                  # chưa hề gọi LLM


def test_yeu_cau_chan_doan_o_triage_dung_cau_tu_choi_chuan(llm_on):
    chatbot.start("diag")
    resp = chatbot.handle_message("diag", "tôi bị bệnh gì vậy bác")
    assert "không thể chẩn đoán" in resp["reply"]
    assert not llm_on


def test_buoc_chon_ngay_gio_khong_dung_llm(llm_on):
    """PICK_DATE/PICK_TIME nêu lịch trống thật -> giữ 100% template."""
    chatbot.start("sched")
    chatbot.handle_message("sched", "tôi bị sâu răng")
    chatbot.handle_message("sched", "yes")
    chatbot.handle_message("sched", "ai cũng được")   # -> PICK_DATE
    resp = chatbot.handle_message("sched", "hôm nay trời đẹp nhỉ")
    assert "chưa nhận ra ngày" in resp["reply"]
    assert not llm_on


# --- Không được cướp lượt của các nhánh bộ luật ĐÃ hiểu đúng ----------------
def test_luat_hieu_duoc_thi_khong_goi_llm(llm_on):
    chatbot.start("rule")
    resp = chatbot.handle_message("rule", "tôi bị sâu răng")
    assert "Trám răng / Sâu răng" in resp["reply"]
    assert chatbot.handle_message("rule", "yes")["state"] == "PICK_DOCTOR"
    assert not llm_on
