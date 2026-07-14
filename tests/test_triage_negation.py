"""Triage phải hiểu PHỦ ĐỊNH: "tôi không bị đau răng" không phải là triệu chứng đau răng."""

import pytest

from app import triage, chatbot


@pytest.mark.parametrize("text", [
    "tôi không bị đau răng",
    "toi khong bi dau rang",          # gõ thiếu dấu
    "răng tôi không bị sâu",
    "tôi không bị chảy máu chân răng",
    "tôi chưa bị sâu răng bao giờ",
])
def test_phu_dinh_khong_tinh_diem(text):
    assert triage.classify_symptoms(text) == []
    assert triage.negated_matches(text), "phải ghi nhận là dịch vụ BỊ PHỦ ĐỊNH"


@pytest.mark.parametrize("text,expected", [
    # "không" đứng SAU = từ để hỏi, KHÔNG phải phủ định.
    ("kiểm tra xem có sâu răng không", "sau_rang"),
    # "không" thuộc mệnh đề khác, không phủ định triệu chứng đứng trước nó.
    ("Răng tôi đau dữ dội, nhức cả đêm không ngủ được", "noi_nha"),
    ("Nhức răng từng cơn, uống thuốc giảm đau không đỡ", "noi_nha"),
])
def test_khong_phu_dinh_nham(text, expected):
    results = triage.classify_symptoms(text)
    assert results and results[0]["code"] == expected


def test_lien_tu_doi_lap_chan_pham_vi_phu_dinh():
    """"không bị A NHƯNG bị B" -> B vẫn được tính, A thì không."""
    results = triage.classify_symptoms("tôi không bị sâu răng nhưng bị chảy máu chân răng")
    assert [r["code"] for r in results] == ["nha_chu"]
    assert [n["code"] for n in triage.negated_matches(
        "tôi không bị sâu răng nhưng bị chảy máu chân răng")] == ["sau_rang"]


def test_phu_dinh_khong_kich_hoat_dental_followup():
    assert triage.mentions_dental_discomfort("răng tôi đau") is True
    assert triage.mentions_dental_discomfort("răng tôi không đau") is False


def test_bot_khong_goi_y_dich_vu_vua_bi_phu_dinh():
    """Bug gốc: gõ "tôi không bị đau răng" mà bot vẫn hiện dịch vụ Sâu răng/Nội nha."""
    chatbot.start("neg-1")
    resp = chatbot.handle_message("neg-1", "tôi không bị đau răng")
    labels = " ".join(o["label"] for o in resp["options"])
    assert "Trám răng" not in labels and "Nội nha" not in labels
    assert "không" in resp["reply"].lower()


def test_cau_khong_lien_quan_rang_mieng():
    chatbot.start("neg-2")
    resp = chatbot.handle_message("neg-2", "tôi không bị đau bụng")
    assert resp["state"] == "TRIAGE"
    assert resp["options"] == []
