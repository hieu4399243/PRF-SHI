"""Engine LLM của triage — test bằng transport GIẢ, không gọi mạng thật."""

import json
import pytest

from app import llm, triage


@pytest.fixture(autouse=True)
def _clean_llm(monkeypatch):
    """Mỗi test bắt đầu với LLM bật, cache rỗng, không có key thật."""
    monkeypatch.setenv("LLM_ENABLED", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")
    triage.clear_llm_cache()
    yield
    triage.clear_llm_cache()


def _fake_llm(monkeypatch, payload):
    """Giả lập tầng HTTP: trả về nguyên văn phản hồi kiểu OpenRouter."""
    calls = []

    def fake_post(path, body):
        calls.append(body)
        if payload is None:
            return None
        return {"choices": [{"message": {"content": json.dumps(payload)}}]}

    monkeypatch.setattr(llm, "_post", fake_post)
    return calls


def test_default_version_theo_moi_truong(monkeypatch):
    assert triage.default_version() == "llm"
    monkeypatch.setenv("LLM_ENABLED", "0")
    assert triage.default_version() == "v2"


def test_llm_tra_ve_dung_dinh_dang_classify_symptoms(monkeypatch):
    _fake_llm(monkeypatch, {
        "services": [{"code": "noi_nha", "evidence": ["nhức tận óc cả đêm"]}],
        "confidence": "high",
    })
    results = triage.classify_symptoms("cắn miếng táo mà nhức tận óc cả đêm")
    assert [r["code"] for r in results] == ["noi_nha"]
    top = results[0]
    assert top["name"] and top["desc"] and top["score"] > 0
    assert top["source"] == "llm"
    assert triage.confidence_level(results) == "high"


def test_confidence_medium_duoc_ton_trong(monkeypatch):
    _fake_llm(monkeypatch, {
        "services": [{"code": "sau_rang"}, {"code": "noi_nha"}],
        "confidence": "medium",
    })
    results = triage.classify_symptoms("răng hàm dưới khó chịu mấy hôm nay")
    assert triage.confidence_level(results) == "medium"
    assert results[0]["score"] > results[1]["score"]


def test_ma_dich_vu_model_bia_ra_bi_loai(monkeypatch):
    _fake_llm(monkeypatch, {
        "services": [{"code": "khoa_tim_mach"}, {"code": "nha_chu"}],
        "confidence": "high",
    })
    assert [r["code"] for r in triage.classify_symptoms("chảy máu chân răng")] == ["nha_chu"]


def test_model_tra_rong_thi_khong_gan_nhan(monkeypatch):
    _fake_llm(monkeypatch, {"services": [], "confidence": "low"})
    results = triage.classify_symptoms("phòng khám mở cửa mấy giờ?")
    assert results == []
    assert triage.confidence_level(results) == "low"


def test_loi_mang_thi_fallback_sang_rule_based(monkeypatch):
    _fake_llm(monkeypatch, None)  # _post trả None = timeout/HTTP lỗi
    results = triage.classify_symptoms("tôi bị sâu răng")
    assert [r["code"] for r in results][:1] == ["sau_rang"]
    assert "source" not in results[0]  # đã đi đường rule-based


def test_json_hong_thi_fallback_sang_rule_based(monkeypatch):
    monkeypatch.setattr(llm, "_post", lambda p, b: {"choices": [{"message": {"content": "xin chào"}}]})
    results = triage.classify_symptoms("tôi bị sâu răng")
    assert [r["code"] for r in results][:1] == ["sau_rang"]


def test_cache_khong_goi_api_hai_lan_cho_cung_cau(monkeypatch):
    calls = _fake_llm(monkeypatch, {
        "services": [{"code": "nha_chu"}], "confidence": "high",
    })
    triage.classify_symptoms("chảy máu chân răng khi đánh răng")
    triage.classify_symptoms("Chảy máu chân răng khi đánh răng!")  # khác hoa/dấu câu
    assert len(calls) == 1


def test_tat_llm_thi_khong_dung_toi_api(monkeypatch):
    calls = _fake_llm(monkeypatch, {"services": [{"code": "nha_chu"}], "confidence": "high"})
    monkeypatch.setenv("LLM_ENABLED", "0")
    triage.classify_symptoms("chảy máu chân răng")
    assert calls == []


def test_ep_version_v2_bo_qua_llm(monkeypatch):
    calls = _fake_llm(monkeypatch, {"services": [{"code": "nha_chu"}], "confidence": "high"})
    results = triage.classify_symptoms("tôi bị sâu răng", version="v2")
    assert calls == []
    assert [r["code"] for r in results][:1] == ["sau_rang"]


def test_prompt_chua_du_danh_muc_dich_vu():
    prompt = triage._llm_system_prompt()
    from app.data import DEPARTMENTS
    for code in DEPARTMENTS:
        assert code in prompt
    assert "không kê đơn" in prompt.lower() or "không kê đơn" in prompt


def test_status_khong_lo_api_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-bi-mat")
    assert "bi-mat" not in json.dumps(llm.status())
