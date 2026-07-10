"""
Tests cho M2 (JSON atomic write + khoá chống race đọc-sửa-ghi) và M6 (chống
trùng code / trùng slot ở JSON mode).

Bug gốc (M2): `_json_save()` ghi trực tiếp đè file (không atomic) — process
chết giữa chừng làm hỏng toàn bộ file JSON; nhiều thao tác đọc-sửa-ghi JSON
đồng thời (add_appointment, set_reminder_sent, set_status, add_token,
remove_token) không có khoá -> mất cập nhật khi race.

Bug gốc (M6): `storage.add_appointment()` (JSON mode) chỉ `append` thẳng,
không kiểm tra trùng `code` LẪN trùng slot `(doctor_id, date, time)` — 2
request đặt cùng bác sĩ/cùng giờ gần như đồng thời có thể cùng insert thành
công (race mà UNIQUE INDEX `ux_appointments_doctor_slot` chặn ở Postgres,
JSON mode không có tầng DB tương đương).

Môi trường dev không có DATABASE_URL -> mọi test dưới đây monkeypatch
`storage.USE_DB = False` và trỏ APPOINTMENTS_PATH/TOKENS_PATH vào file tạm để
không đụng dữ liệu thật.
"""

import concurrent.futures
import json
import os
import threading

import pytest

import storage


@pytest.fixture(autouse=True)
def _isolate_json_files(tmp_path, monkeypatch):
    """Mọi test trong file này chạy trên file JSON tạm, không đụng dữ liệu
    thật của app, và luôn ở JSON mode (không phụ thuộc DATABASE_URL máy CI)."""
    monkeypatch.setattr(storage, "USE_DB", False)
    monkeypatch.setattr(storage, "APPOINTMENTS_PATH",
                        str(tmp_path / "appointments.json"))
    monkeypatch.setattr(storage, "TOKENS_PATH", str(tmp_path / "device_tokens.json"))


def _appt(code, doctor_id="d1", date="2026-08-01", time="09:00",
          status="confirmed", phone="0900000000"):
    return {
        "code": code,
        "session": "sess1",
        "patient_name": "Khách",
        "patient_phone": phone,
        "department": "Khoa A",
        "department_code": "kA",
        "doctor": "BS A",
        "doctor_id": doctor_id,
        "date": date,
        "time": time,
        "created_at": "2026-07-10T00:00:00",
        "status": status,
    }


# ---------------------------------------------------------------------------
# M2 — atomic write
# ---------------------------------------------------------------------------
def test_json_save_is_atomic(tmp_path):
    target = tmp_path / "data.json"
    big_data = {"items": list(range(5000))}

    storage._json_save(str(target), big_data)

    tmp_file = f"{target}.tmp"
    assert not os.path.exists(tmp_file)
    with open(target, encoding="utf-8") as f:
        assert json.load(f) == big_data


def test_json_save_replaces_existing_file_fully(tmp_path):
    target = tmp_path / "data.json"
    storage._json_save(str(target), {"v": 1})
    storage._json_save(str(target), {"v": 2})
    with open(target, encoding="utf-8") as f:
        assert json.load(f) == {"v": 2}


# ---------------------------------------------------------------------------
# M6 — trùng code / trùng slot
# ---------------------------------------------------------------------------
def test_add_appointment_json_detects_duplicate_code():
    storage.add_appointment(_appt("SHI-DUP", doctor_id="d1", time="09:00"))
    with pytest.raises(storage.DuplicateCodeError):
        storage.add_appointment(_appt("SHI-DUP", doctor_id="d2", time="10:00"))


def test_add_appointment_json_detects_slot_collision():
    first = _appt("SHI-A", doctor_id="d1", date="2026-08-01", time="09:00",
                  status="confirmed")
    storage.add_appointment(first)

    second = _appt("SHI-B", doctor_id="d1", date="2026-08-01", time="09:00",
                   status="confirmed")
    with pytest.raises(storage.SlotTakenError) as exc_info:
        storage.add_appointment(second)

    assert exc_info.value.existing["code"] == "SHI-A"


def test_add_appointment_json_allows_different_doctor_same_slot():
    storage.add_appointment(_appt("SHI-A", doctor_id="d1", date="2026-08-01",
                                  time="09:00", status="confirmed"))
    # Không raise: khác doctor_id, cùng (date, time).
    storage.add_appointment(_appt("SHI-B", doctor_id="d2", date="2026-08-01",
                                  time="09:00", status="confirmed"))

    assert len(storage.list_appointments()) == 2


def test_add_appointment_json_allows_cancelled_to_share_slot():
    """Lịch 'cancelled' không chặn slot mới — khớp semantics UNIQUE INDEX
    Postgres (WHERE status='confirmed')."""
    storage.add_appointment(_appt("SHI-A", doctor_id="d1", date="2026-08-01",
                                  time="09:00", status="cancelled"))
    storage.add_appointment(_appt("SHI-B", doctor_id="d1", date="2026-08-01",
                                  time="09:00", status="confirmed"))
    assert len(storage.list_appointments()) == 2


def test_json_operations_thread_safe():
    n = 20

    def worker(i):
        storage.add_appointment(_appt(f"SHI-{i:03d}", doctor_id=f"d{i}",
                                      date="2026-08-01", time=f"{9 + i % 8}:00"))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(storage.list_appointments()) == n


def test_concurrent_same_slot_only_one_succeeds():
    n = 10
    results = []
    results_lock = threading.Lock()

    def worker(i):
        try:
            storage.add_appointment(_appt(f"SHI-RACE-{i:03d}", doctor_id="d1",
                                          date="2026-08-01", time="09:00",
                                          status="confirmed"))
            outcome = "ok"
        except storage.SlotTakenError:
            outcome = "slot_taken"
        with results_lock:
            results.append(outcome)

    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:
        list(pool.map(worker, range(n)))

    assert results.count("ok") == 1
    assert results.count("slot_taken") == n - 1


# ---------------------------------------------------------------------------
# M5 (phần storage) — remove_token
# ---------------------------------------------------------------------------
def test_remove_token_json_mode():
    storage.add_token("sess1", "ExponentPushToken[abc]")
    storage.add_token("sess1", "ExponentPushToken[def]")

    storage.remove_token("ExponentPushToken[abc]")

    assert storage.get_tokens("sess1") == ["ExponentPushToken[def]"]


def test_remove_token_json_mode_no_such_token_is_noop():
    storage.add_token("sess1", "ExponentPushToken[abc]")
    storage.remove_token("ExponentPushToken[does-not-exist]")
    assert storage.get_tokens("sess1") == ["ExponentPushToken[abc]"]


def test_add_token_and_remove_token_thread_safe():
    known_token = "ExponentPushToken[known]"
    storage.add_token("sess1", known_token)

    n = 20

    def add_worker(i):
        storage.add_token("sess1", f"ExponentPushToken[t{i:03d}]")

    def remove_worker():
        storage.remove_token(known_token)

    threads = [threading.Thread(target=add_worker, args=(i,)) for i in range(n)]
    threads.append(threading.Thread(target=remove_worker))
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    tokens = storage.get_tokens("sess1")
    assert known_token not in tokens
    assert len(tokens) == n
