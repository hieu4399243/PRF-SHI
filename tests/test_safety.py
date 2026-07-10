"""
Tests cho lớp an toàn (safety.py) — đảm bảo phát hiện cấp cứu / yêu cầu chẩn đoán /
human handoff hoạt động đúng cho cả câu CÓ DẤU và KHÔNG DẤU.

Bug gốc: safety.py so khớp thô trên text.lower() với pattern có dấu, nên câu
không dấu ("kho tho nang", "dot quy", "co giat"...) không kích hoạt cảnh báo 115.
"""

import json
import threading
from datetime import datetime, timezone

from app import safety
from app.triage import _normalize, _strip_accents


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


def test_audit_uses_utc_timestamp(monkeypatch, tmp_path):
    log_path = tmp_path / "audit_log.jsonl"
    monkeypatch.setattr(safety, "AUDIT_LOG_PATH", str(log_path))

    safety.audit("sid-1", "user", "xin chào")

    line = log_path.read_text(encoding="utf-8").strip()
    entry = json.loads(line)
    ts = datetime.fromisoformat(entry["ts"])
    assert ts.utcoffset() == timezone.utc.utcoffset(None)


def test_audit_rotates_when_oversized(monkeypatch, tmp_path):
    log_path = tmp_path / "audit_log.jsonl"
    old_line = json.dumps({"ts": "old", "session": "old-session", "role": "user",
                            "message": "dòng log cũ đã đầy ngưỡng xoay vòng", "meta": {}})
    log_path.write_text(old_line + "\n", encoding="utf-8")

    monkeypatch.setattr(safety, "AUDIT_LOG_PATH", str(log_path))
    monkeypatch.setattr(safety, "AUDIT_LOG_MAX_BYTES", 10)

    safety.audit("sid-2", "user", "dòng mới")

    rotated_path = log_path.with_name(log_path.name + ".1")
    assert rotated_path.exists()
    assert "old-session" in rotated_path.read_text(encoding="utf-8")

    new_content = log_path.read_text(encoding="utf-8").strip()
    assert "old-session" not in new_content
    assert json.loads(new_content)["session"] == "sid-2"


def test_audit_does_not_crash_on_unserializable_meta(monkeypatch, tmp_path):
    log_path = tmp_path / "audit_log.jsonl"
    monkeypatch.setattr(safety, "AUDIT_LOG_PATH", str(log_path))

    safety.audit("sid-3", "user", "msg", {"bad": object()})  # không raise


def test_audit_concurrent_writes_no_lost_lines(monkeypatch, tmp_path):
    log_path = tmp_path / "audit_log.jsonl"
    monkeypatch.setattr(safety, "AUDIT_LOG_PATH", str(log_path))

    n = 20
    threads = [
        threading.Thread(target=safety.audit, args=("sid-concurrent", "user", f"msg-{i}", {}))
        for i in range(n)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    total_lines = 0
    if log_path.exists():
        total_lines += len([l for l in log_path.read_text(encoding="utf-8").splitlines() if l])
    rotated_path = log_path.with_name(log_path.name + ".1")
    if rotated_path.exists():
        total_lines += len([l for l in rotated_path.read_text(encoding="utf-8").splitlines() if l])

    assert total_lines == n
