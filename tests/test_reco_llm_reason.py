"""
Tests cho lớp LLM viết lý do gợi ý (app/reco/llm_reason.py).

Đây là chỗ RỦI RO NHẤT của tính năng: dự án cố tình cho LLM viết `reason_text`
(sai lệch D1 so với SEQ 5.3), nên phải chứng minh được hai điều:

  1. LLM KHÔNG BAO GIỜ đổi được `service_code` / `confidence` / `rank` / `urgency`
     -> một ảo giác của mô hình không thể đổi nội dung gợi ý y tế.
  2. Mọi đường lỗi (tắt, timeout, JSON hỏng, câu vi phạm) đều quay về template.

Không test nào ở đây gọi mạng thật — `llm.chat_json` luôn bị monkeypatch.
"""

import pytest

from app.reco import llm_reason


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    llm_reason.clear_cache()
    monkeypatch.setenv("REC_LLM_REASON", "1")
    # Coi như đã cấu hình API key (không gọi mạng vì chat_json bị thay).
    monkeypatch.setattr(llm_reason.llm, "is_enabled", lambda: True)
    yield
    llm_reason.clear_cache()


def _items():
    return [
        {"service_code": "kham_tong_quat", "confidence": 0.91, "rank": 1,
         "urgency": "high", "reason_text": "Đã 8 tháng kể từ lần khám gần nhất.",
         "reason_source": "template"},
        {"service_code": "sau_rang", "confidence": 0.42, "rank": 2,
         "urgency": "low", "reason_text": "50% bệnh nhân tương tự đã dùng dịch vụ này.",
         "reason_source": "template"},
    ]


def _fake_llm(monkeypatch, payload):
    calls = []

    def _chat_json(system, user, max_tokens=None, temperature=None):
        calls.append({"system": system, "user": user, "temperature": temperature})
        return payload

    monkeypatch.setattr(llm_reason.llm, "chat_json", _chat_json)
    return calls


# ---------------------------------------------------------------------------
# Đường thành công
# ---------------------------------------------------------------------------
def test_viet_lai_cau_ly_do(monkeypatch):
    _fake_llm(monkeypatch, {"reasons": [
        {"i": 0, "text": "Bạn nên ghé kiểm tra định kỳ, đã 8 tháng rồi nhé."},
        {"i": 1, "text": "Nhiều người có hồ sơ giống bạn cũng chọn dịch vụ này."},
    ]})
    items = llm_reason.polish(_items())
    assert items[0]["reason_text"] == "Bạn nên ghé kiểm tra định kỳ, đã 8 tháng rồi nhé."
    assert items[0]["reason_source"] == "llm"


def test_khong_doi_thu_hang_va_diem_so(monkeypatch):
    """RÀNG BUỘC BẤT BIẾN: LLM chỉ được đổi câu chữ."""
    _fake_llm(monkeypatch, {"reasons": [
        {"i": 0, "text": "Câu mới hoàn toàn cho mục một."},
        {"i": 1, "text": "Câu mới hoàn toàn cho mục hai."},
    ]})
    before = _items()
    after = llm_reason.polish(_items())
    for b, a in zip(before, after):
        assert a["service_code"] == b["service_code"]
        assert a["confidence"] == b["confidence"]
        assert a["rank"] == b["rank"]
        assert a["urgency"] == b["urgency"]


def test_cache_theo_cau_template_khong_goi_lai_llm(monkeypatch):
    calls = _fake_llm(monkeypatch, {"reasons": [
        {"i": 0, "text": "Bạn nên ghé kiểm tra định kỳ, đã 8 tháng rồi nhé."},
        {"i": 1, "text": "Nhiều người có hồ sơ giống bạn cũng chọn dịch vụ này."},
    ]})
    llm_reason.polish(_items())
    llm_reason.polish(_items())
    assert len(calls) == 1


def test_cache_khong_khoa_theo_benh_nhan(monkeypatch):
    """Cache khoá theo CÂU template nên không chứa dữ liệu định danh, và bệnh nhân
    khác có cùng lý do vẫn dùng lại được (giữ SLA khi bật LLM)."""
    calls = _fake_llm(monkeypatch, {"reasons": [
        {"i": 0, "text": "Bạn nên ghé kiểm tra định kỳ, đã 8 tháng rồi nhé."},
        {"i": 1, "text": "Nhiều người có hồ sơ giống bạn cũng chọn dịch vụ này."},
    ]})
    llm_reason.polish(_items())
    other_patient = _items()
    llm_reason.polish(other_patient)
    assert len(calls) == 1
    assert other_patient[0]["reason_source"] == "llm-cache"


# ---------------------------------------------------------------------------
# Đường lỗi — luôn phải quay về template
# ---------------------------------------------------------------------------
def test_tat_bang_bien_moi_truong(monkeypatch):
    monkeypatch.setenv("REC_LLM_REASON", "0")
    calls = _fake_llm(monkeypatch, {"reasons": [{"i": 0, "text": "Câu mới."}]})
    items = llm_reason.polish(_items())
    assert calls == []
    assert items[0]["reason_text"] == "Đã 8 tháng kể từ lần khám gần nhất."


def test_khong_co_api_key_thi_giu_template(monkeypatch):
    monkeypatch.setattr(llm_reason.llm, "is_enabled", lambda: False)
    items = llm_reason.polish(_items())
    assert items[0]["reason_source"] == "template"


def test_llm_loi_hoac_timeout_giu_template(monkeypatch):
    _fake_llm(monkeypatch, None)   # llm.chat_json trả None khi lỗi/timeout
    items = llm_reason.polish(_items())
    assert items[0]["reason_text"] == "Đã 8 tháng kể từ lần khám gần nhất."


def test_json_sai_dinh_dang_giu_template(monkeypatch):
    _fake_llm(monkeypatch, {"khong_phai_reasons": []})
    items = llm_reason.polish(_items())
    assert items[0]["reason_source"] == "template"


def test_thieu_mot_muc_thi_chi_muc_do_giu_template(monkeypatch):
    _fake_llm(monkeypatch, {"reasons": [{"i": 0, "text": "Câu mới cho mục một nhé."}]})
    items = llm_reason.polish(_items())
    assert items[0]["reason_source"] == "llm"
    assert items[1]["reason_source"] == "template"
    assert items[1]["reason_text"] == "50% bệnh nhân tương tự đã dùng dịch vụ này."


def test_loai_cau_chua_thuat_ngu_ky_thuat(monkeypatch):
    """TC-REC-006 — LLM rất dễ nhắc tới 'mô hình'/'điểm số'."""
    _fake_llm(monkeypatch, {"reasons": [
        {"i": 0, "text": "Mô hình AI cho điểm số cao với dịch vụ này."},
    ]})
    items = llm_reason.polish(_items())
    assert items[0]["reason_source"] == "template"


def test_loai_cau_qua_dai(monkeypatch):
    _fake_llm(monkeypatch, {"reasons": [{"i": 0, "text": "A" * 300}]})
    assert llm_reason.polish(_items())[0]["reason_source"] == "template"


def test_loai_cau_rong(monkeypatch):
    _fake_llm(monkeypatch, {"reasons": [{"i": 0, "text": "   "}]})
    assert llm_reason.polish(_items())[0]["reason_source"] == "template"


def test_loai_cau_chua_so_dien_thoai(monkeypatch):
    """Số điện thoại trong câu lý do = LLM bịa hoặc rò dữ liệu."""
    _fake_llm(monkeypatch, {"reasons": [
        {"i": 0, "text": "Gọi 0912345678 để đặt lịch kiểm tra định kỳ nhé."},
    ]})
    assert llm_reason.polish(_items())[0]["reason_source"] == "template"


def test_loai_cau_mang_tinh_chan_doan(monkeypatch):
    """Bộ chặn nội dung của dự án được áp lên ĐẦU RA của LLM, không chỉ đầu vào."""
    _fake_llm(monkeypatch, {"reasons": [
        {"i": 0, "text": "Bạn bị viêm tủy, cần uống thuốc kháng sinh ngay."},
    ]})
    assert llm_reason.polish(_items())[0]["reason_source"] == "template"


def test_khong_luu_cache_cau_bi_loai(monkeypatch):
    """Câu vi phạm không được vào cache, nếu không nó sẽ được dùng lại mãi."""
    _fake_llm(monkeypatch, {"reasons": [
        {"i": 0, "text": "Điểm số của model rất cao."},
    ]})
    llm_reason.polish(_items())
    calls = _fake_llm(monkeypatch, {"reasons": [
        {"i": 0, "text": "Câu hợp lệ đã sửa lại rồi nhé."},
    ]})
    items = llm_reason.polish(_items())
    assert len(calls) == 1
    assert items[0]["reason_source"] == "llm"


def test_danh_sach_rong_khong_goi_llm(monkeypatch):
    calls = _fake_llm(monkeypatch, {"reasons": []})
    assert llm_reason.polish([]) == []
    assert calls == []


def test_index_khong_hop_le_khong_lam_sap(monkeypatch):
    _fake_llm(monkeypatch, {"reasons": [
        {"i": "khong-phai-so", "text": "Câu mới."},
        {"i": 99, "text": "Câu ngoài phạm vi."},
        "chuoi-rac",
    ]})
    items = llm_reason.polish(_items())
    assert all(i["reason_source"] == "template" for i in items)


def test_prompt_khong_chua_du_lieu_dinh_danh_benh_nhan(monkeypatch):
    """Prompt chỉ được chứa câu template + tên dịch vụ (ngữ cảnh).

    KHÔNG được chứa dữ liệu định danh bệnh nhân (tên, SĐT, mã tài khoản) và cũng
    không cần điểm số — LLM không được biết để không thể bàn về nó."""
    calls = _fake_llm(monkeypatch, {"reasons": [{"i": 0, "text": "Câu mới hợp lệ."}]})
    items = _items()
    items[0].update(patient_id="u-benh-nhan-1", patient_phone="0900000101")
    llm_reason.polish(items)
    sent = calls[0]["user"]
    assert "u-benh-nhan-1" not in sent
    assert "0900000101" not in sent
    assert "0.91" not in sent
    assert "0.42" not in sent


def test_loai_cau_khang_dinh_benh(monkeypatch):
    _fake_llm(monkeypatch, {"reasons": [
        {"i": 0, "text": "Bạn đang bị nhiễm trùng, nên xử lý sớm."},
    ]})
    assert llm_reason.polish(_items())[0]["reason_source"] == "template"


def test_loai_cau_hua_ket_qua_dieu_tri(monkeypatch):
    _fake_llm(monkeypatch, {"reasons": [
        {"i": 0, "text": "Dịch vụ này chữa khỏi hoàn toàn cho bạn."},
    ]})
    assert llm_reason.polish(_items())[0]["reason_source"] == "template"


def test_loai_cau_noi_ve_dich_vu_khac(monkeypatch):
    """Lỗi quan sát được trên dữ liệu thật: gợi ý "Nha chu" bị LLM viết lại thành
    "bạn nên kiểm tra răng định kỳ" — tức nói về "Khám tổng quát". Card sẽ có tiêu
    đề một dịch vụ mà lý do nói về dịch vụ khác."""
    items = [{"service_code": "nha_chu", "name": "Nha chu (Nướu / Lợi)",
              "confidence": 0.65, "rank": 1, "urgency": "medium",
              "reason_text": "Bạn từng dùng dịch vụ này 2 năm trước.",
              "reason_source": "template"}]
    _fake_llm(monkeypatch, {"reasons": [
        {"i": 0, "text": "Đã 2 năm rồi, bạn nên đi khám tổng quát lại nhé."},
    ]})
    assert llm_reason.polish(items)[0]["reason_source"] == "template"


def test_giu_cau_dung_dich_vu_cua_minh(monkeypatch):
    """Ngược lại: nhắc tên CHÍNH dịch vụ đó thì hợp lệ."""
    items = [{"service_code": "nha_chu", "name": "Nha chu (Nướu / Lợi)",
              "confidence": 0.65, "rank": 1, "urgency": "medium",
              "reason_text": "Bạn từng dùng dịch vụ này 2 năm trước.",
              "reason_source": "template"}]
    _fake_llm(monkeypatch, {"reasons": [
        {"i": 0, "text": "Đã 2 năm kể từ lần chăm sóc nha chu gần nhất của bạn."},
    ]})
    assert llm_reason.polish(items)[0]["reason_source"] == "llm"


def test_ten_dich_vu_duoc_gui_lam_ngu_canh(monkeypatch):
    """Không gửi tên dịch vụ thì LLM không biết đang nói về gì và sẽ tự bịa."""
    calls = _fake_llm(monkeypatch, {"reasons": [{"i": 0, "text": "Câu mới hợp lệ."}]})
    llm_reason.polish([{"service_code": "nha_chu", "name": "Nha chu (Nướu / Lợi)",
                        "reason_text": "Bạn từng dùng dịch vụ này 2 năm trước.",
                        "reason_source": "template"}])
    assert "[Nha chu (Nướu / Lợi)]" in calls[0]["user"]


def test_cache_khong_dung_chung_giua_hai_dich_vu(monkeypatch):
    """Hai dịch vụ có thể sinh CÙNG câu template; câu đã viết lại gắn với ngữ cảnh
    dịch vụ nên dùng chung sẽ nói sai dịch vụ."""
    same = "Bạn từng dùng dịch vụ này 2 năm trước."
    a = [{"service_code": "nha_chu", "name": "Nha chu (Nướu / Lợi)",
          "reason_text": same, "reason_source": "template"}]
    b = [{"service_code": "tham_my", "name": "Nha khoa thẩm mỹ",
          "reason_text": same, "reason_source": "template"}]
    calls = _fake_llm(monkeypatch, {"reasons": [{"i": 0, "text": "Câu mới hợp lệ nhé."}]})
    llm_reason.polish(a)
    llm_reason.polish(b)
    assert len(calls) == 2   # không lấy cache của dịch vụ khác


def test_cho_phep_nhac_dich_vu_ma_ly_do_tham_chieu(monkeypatch):
    """Lý do `care_pathway` BUỘC phải nhắc dịch vụ trước đó ("Sau khi nội nha...").
    Không miễn trừ thì luật này luôn bị loại oan và mất hẳn phần LLM."""
    items = [{"service_code": "phuc_hinh", "name": "Phục hình / Trồng răng",
              "reason_text": "Sau khi nội nha, bước tiếp theo thường là dịch vụ này.",
              "reason_source": "template",
              "signals": [{"service_code": "phuc_hinh", "reason_code": "care_pathway",
                           "ctx": {"from_service": "noi_nha"}}]}]
    _fake_llm(monkeypatch, {"reasons": [
        {"i": 0, "text": "Sau điều trị nội nha, bạn thường cần phục hình lại răng."},
    ]})
    assert llm_reason.polish(items)[0]["reason_source"] == "llm"


def test_van_loai_dich_vu_khong_duoc_tham_chieu(monkeypatch):
    """Miễn trừ chỉ áp cho dịch vụ mà tín hiệu tham chiếu, không phải mọi dịch vụ."""
    items = [{"service_code": "phuc_hinh", "name": "Phục hình / Trồng răng",
              "reason_text": "Sau khi nội nha, bước tiếp theo thường là dịch vụ này.",
              "reason_source": "template",
              "signals": [{"service_code": "phuc_hinh", "reason_code": "care_pathway",
                           "ctx": {"from_service": "noi_nha"}}]}]
    _fake_llm(monkeypatch, {"reasons": [
        {"i": 0, "text": "Bạn nên niềng răng chỉnh nha cho đều hơn nhé."},
    ]})
    assert llm_reason.polish(items)[0]["reason_source"] == "template"


def test_dung_temperature_cao_hon_0_khi_viet_cau(monkeypatch):
    """Sinh văn bản với temperature=0 cho ra câu rập khuôn. `reason_text` không
    tham gia xếp hạng nên nâng temperature vẫn giữ được tính tái lập của gợi ý."""
    calls = _fake_llm(monkeypatch, {"reasons": [{"i": 0, "text": "Câu mới hợp lệ."}]})
    llm_reason.polish(_items())
    assert calls[0]["temperature"] == llm_reason.TEMPERATURE
    assert 0 < llm_reason.TEMPERATURE <= 0.7


def test_prompt_co_vi_du_few_shot(monkeypatch):
    """Zero-shot chỉ có luật, model không biết văn phong mong muốn."""
    calls = _fake_llm(monkeypatch, {"reasons": [{"i": 0, "text": "Câu mới hợp lệ."}]})
    llm_reason.polish(_items())
    assert "VÍ DỤ" in calls[0]["system"]
    assert calls[0]["system"].count("ra  :") >= 3
