"""
Tests cho lớp an toàn (safety.py) — đảm bảo phát hiện cấp cứu / yêu cầu chẩn đoán /
human handoff hoạt động đúng cho cả câu CÓ DẤU và KHÔNG DẤU.

Bug gốc: safety.py so khớp thô trên text.lower() với pattern có dấu, nên câu
không dấu ("kho tho nang", "dot quy", "co giat"...) không kích hoạt cảnh báo 115.
"""

import safety
from triage import _normalize, _strip_accents


def _to_no_accent(pattern: str) -> str:
    """Chuyển 1 pattern có dấu thành bản không dấu, dùng làm input test."""
    return _strip_accents(_normalize(pattern))


def test_check_emergency_no_accents():
    # Lấy thực tế 1 pattern có dấu từ EMERGENCY_PATTERNS hiện hành, không hardcode.
    pattern = safety.EMERGENCY_PATTERNS[0]
    no_accent_text = _to_no_accent(pattern)
    assert safety.check_emergency(no_accent_text) is True


def test_check_emergency_with_accents_still_works():
    pattern = safety.EMERGENCY_PATTERNS[0]
    assert safety.check_emergency(pattern) is True


def test_check_emergency_negative_case():
    assert safety.check_emergency("tôi muốn đặt lịch khám răng") is False


def test_is_diagnosis_request_no_accents():
    pattern = safety.DIAGNOSIS_REQUEST_PATTERNS[0]
    no_accent_text = _to_no_accent(pattern)
    assert safety.is_diagnosis_request(no_accent_text) is True


def test_is_diagnosis_request_with_accents_still_works():
    pattern = safety.DIAGNOSIS_REQUEST_PATTERNS[0]
    assert safety.is_diagnosis_request(pattern) is True


def test_needs_human_handoff_no_accents():
    pattern = safety.HANDOFF_PATTERNS[0]
    no_accent_text = _to_no_accent(pattern)
    assert safety.needs_human_handoff(no_accent_text) is True


def test_needs_human_handoff_with_accents_still_works():
    pattern = safety.HANDOFF_PATTERNS[0]
    assert safety.needs_human_handoff(pattern) is True


def test_check_emergency_pattern_with_uppercase(monkeypatch):
    """Mô phỏng pattern nạp từ Supabase (admin nhập qua dashboard): viết hoa/
    khoảng trắng thừa tùy ý, KHÔNG đảm bảo lowercase như seed hardcode."""
    monkeypatch.setattr(safety, "EMERGENCY_PATTERNS", [" Khó Thở "])
    assert safety.check_emergency("kho tho") is True
