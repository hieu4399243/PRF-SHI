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

from app.core import storage


@pytest.fixture(autouse=True)
def _isolate_json_files(tmp_path, monkeypatch):
    """Mọi test trong file này chạy trên file JSON tạm, không đụng dữ liệu
    thật của app, và luôn ở JSON mode (không phụ thuộc DATABASE_URL máy CI)."""
    monkeypatch.setattr(storage, "USE_DB", False)
    monkeypatch.setattr(storage, "APPOINTMENTS_PATH",
                        str(tmp_path / "appointments.json"))
    monkeypatch.setattr(storage, "TOKENS_PATH", str(tmp_path / "device_tokens.json"))
    monkeypatch.setattr(storage, "TREATMENT_HISTORY_PATH",
                        str(tmp_path / "treatment_history.json"))
    monkeypatch.setattr(storage, "REC_LOG_PATH",
                        str(tmp_path / "recommendation_log.json"))
    monkeypatch.setattr(storage, "PATIENT_PREFS_PATH",
                        str(tmp_path / "patient_preference.json"))


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


def test_create_user_raises_without_db():
    with pytest.raises(storage.UserStoreUnavailableError):
        storage.create_user("u1", "user1", "hash", "guest")


def test_get_user_by_username_raises_without_db():
    with pytest.raises(storage.UserStoreUnavailableError):
        storage.get_user_by_username("user1")


def test_get_user_by_id_raises_without_db():
    with pytest.raises(storage.UserStoreUnavailableError):
        storage.get_user_by_id("u1")


def test_get_user_by_doctor_id_raises_without_db():
    with pytest.raises(storage.UserStoreUnavailableError):
        storage.get_user_by_doctor_id("bs_test_01")


# ---------------------------------------------------------------------------
# GỢI Ý DỊCH VỤ (REC-01/02) — treatment_history / recommendation_log /
# patient_preference ở JSON mode.
#
# Khác `users` (Postgres-only), 3 bảng này PHẢI chạy được ở JSON mode vì eval/
# chấm điểm engine offline — xem §14 docs/patient-recommendation-design.md.
# ---------------------------------------------------------------------------
def _treatment(history_id="h1", appointment_code="SHI-A00001", phone="0912345678",
               service_code="kham_tong_quat", treatment_date="2026-01-10",
               patient_id=None, followup_due_date=None):
    return {
        "history_id": history_id,
        "appointment_code": appointment_code,
        "patient_id": patient_id,
        "patient_phone": phone,
        "service_code": service_code,
        "doctor_id": "bs_tq_01",
        "treatment_date": treatment_date,
        "outcome": "success",
        "followup_required": bool(followup_due_date),
        "followup_due_date": followup_due_date,
        "patient_rating": 5,
        "created_at": "2026-01-10T10:00:00",
    }


def test_add_treatment_ghi_va_doc_lai():
    """Lượt điều trị ghi xuống rồi đọc lại phải giữ nguyên các field engine cần."""
    assert storage.add_treatment(_treatment(followup_due_date="2026-07-10")) is True
    rows = storage.list_treatments(patient_phone="0912345678")
    assert len(rows) == 1
    assert rows[0]["service_code"] == "kham_tong_quat"
    assert rows[0]["followup_required"] is True
    assert rows[0]["followup_due_date"] == "2026-07-10"


def test_add_treatment_idempotent_theo_appointment_code():
    """Chạy lại backfill không được nhân đôi lịch sử của cùng một lịch hẹn."""
    assert storage.add_treatment(_treatment(history_id="h1")) is True
    assert storage.add_treatment(_treatment(history_id="h2")) is False
    assert len(storage.list_treatments()) == 1


def test_add_treatment_idempotent_theo_history_id():
    """Dữ liệu seed demo không gắn lịch hẹn (appointment_code=None) -> phải dedupe
    theo history_id, nếu không chạy lại script seed sẽ nhân đôi lịch sử."""
    rec = _treatment(history_id="th-demo-1", appointment_code=None)
    assert storage.add_treatment(rec) is True
    assert storage.add_treatment(dict(rec)) is False
    assert len(storage.list_treatments()) == 1


def test_list_treatments_moi_nhat_truoc():
    storage.add_treatment(_treatment(history_id="h1", appointment_code="A1",
                                     treatment_date="2025-05-01"))
    storage.add_treatment(_treatment(history_id="h2", appointment_code="A2",
                                     treatment_date="2026-03-01"))
    dates = [r["treatment_date"] for r in storage.list_treatments()]
    assert dates == ["2026-03-01", "2025-05-01"]


def test_list_treatments_gop_theo_id_hoac_phone():
    """patient_id VÀ patient_phone là quan hệ OR: bệnh nhân đặt lịch qua chatbot
    trước khi có tài khoản (chỉ SĐT) rồi mới tạo tài khoản (có id) — cả hai đều là
    lịch sử của cùng một người, thiếu OR là mất nửa lịch sử."""
    storage.add_treatment(_treatment(history_id="h1", appointment_code="A1",
                                     phone="0912345678", patient_id=None))
    storage.add_treatment(_treatment(history_id="h2", appointment_code="A2",
                                     phone=None, patient_id="u1"))
    rows = storage.list_treatments(patient_id="u1", patient_phone="0912345678")
    assert len(rows) == 2


def test_list_treatments_gioi_han_limit():
    for i in range(5):
        storage.add_treatment(_treatment(history_id=f"h{i}", appointment_code=f"A{i}",
                                         treatment_date=f"2026-0{i + 1}-01"))
    assert len(storage.list_treatments(limit=3)) == 3


def _rec_log(rec_log_id="r1", patient_id="u1"):
    return {
        "rec_log_id": rec_log_id,
        "patient_id": patient_id,
        "generated_at": "2026-07-30T10:00:00",
        "trigger": "booking_page",
        "model_version": "rules-v1",
        "is_cold_start": False,
        "recommendations": [
            {"rank": 1, "service_code": "kham_tong_quat", "confidence": 0.91,
             "reason_code": "followup_due"},
        ],
        "latency_ms": 12,
        "feature_snapshot": {"age_group": "adult", "time_since_last": 240},
    }


def test_rec_log_ghi_va_doc_lai_giu_nguyen_jsonb():
    storage.add_rec_log(_rec_log())
    entry = storage.get_rec_log("r1")
    assert entry["recommendations"][0]["confidence"] == 0.91
    assert entry["feature_snapshot"]["age_group"] == "adult"


def test_rec_log_khong_ton_tai_tra_none():
    assert storage.get_rec_log("khong-co") is None


def test_set_rec_log_action_khong_ghi_de_hanh_dong_cu():
    """Một lượt gợi ý có đúng MỘT hành động quyết định. Bấm 2 lần (hoặc 2 tab)
    không được biến 'book' thành 'view_detail' — thứ tự request tới không đảm bảo,
    ghi đè sẽ làm sai chỉ số CTR/NDCG@3."""
    storage.add_rec_log(_rec_log())
    assert storage.set_rec_log_action("r1", "book", "kham_tong_quat", 1) is True
    assert storage.set_rec_log_action("r1", "view_detail", "sau_rang", 2) is False
    entry = storage.get_rec_log("r1")
    assert entry["patient_action"] == "book"
    assert entry["patient_acted_service_code"] == "kham_tong_quat"
    assert entry["patient_acted_rank"] == 1


def test_set_rec_log_action_log_khong_ton_tai():
    assert storage.set_rec_log_action("khong-co", "book") is False


def test_rec_log_json_mode_gioi_han_so_dong(monkeypatch):
    """JSON mode phải chặn file log phình vô hạn."""
    monkeypatch.setattr(storage, "_RECLOG_JSON_MAX", 3)
    for i in range(6):
        storage.add_rec_log(_rec_log(rec_log_id=f"r{i}"))
    assert storage.get_rec_log("r0") is None      # dòng cũ nhất đã bị loại
    assert storage.get_rec_log("r5") is not None


def test_prefs_benh_nhan_chua_co_ban_ghi():
    """Chưa có bản ghi -> vẫn trả dict đủ khoá, không phải None (tránh AttributeError
    ở tầng engine)."""
    prefs = storage.get_patient_preference("u-moi")
    assert prefs["dismissed_service_codes"] == []
    assert prefs["service_ratings"] == {}


def test_dismiss_luu_ben_va_khong_trung():
    """TC-REC-004: dịch vụ đã "Không quan tâm" không được xuất hiện lại lần sau
    -> phải lưu bền, và bấm 2 lần không nhân đôi."""
    storage.add_dismissed_service("u1", "tham_my")
    storage.add_dismissed_service("u1", "tham_my")
    storage.add_dismissed_service("u1", "chinh_nha")
    assert storage.get_patient_preference("u1")["dismissed_service_codes"] == [
        "tham_my", "chinh_nha"]


def test_dismiss_tach_biet_giua_cac_benh_nhan():
    storage.add_dismissed_service("u1", "tham_my")
    assert storage.get_patient_preference("u2")["dismissed_service_codes"] == []


def test_reset_dismissed():
    """TC-REC-005: empty state có link reset preferences."""
    storage.add_dismissed_service("u1", "tham_my")
    assert storage.reset_dismissed_services("u1") is True
    assert storage.get_patient_preference("u1")["dismissed_service_codes"] == []


def test_reset_dismissed_benh_nhan_chua_co_ban_ghi():
    assert storage.reset_dismissed_services("u-moi") is False


def test_cac_ham_goi_y_bo_qua_patient_id_rong():
    """patient_id rỗng (khách chưa đăng nhập) không được làm hỏng storage."""
    assert storage.add_dismissed_service("", "tham_my") == []
    assert storage.reset_dismissed_services(None) is False
    assert storage.get_patient_preference(None)["dismissed_service_codes"] == []
