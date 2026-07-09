"""
Tests cho C2 (double-booking race condition).

Bug gốc: booking.book_appointment() kiểm tra _confirmed_at(date, time) rồi mới
storage.add_appointment() — không transaction/unique constraint. Hai request đặt
cùng giờ gần như đồng thời có thể cùng pass check trước khi bên kia insert.

Fix: UNIQUE partial index `ux_appointments_slot` trên
appointments(date, time) WHERE status='confirmed' (Postgres) + booking.py bắt
psycopg.errors.UniqueViolation và branch theo exc.diag.constraint_name.

Môi trường dev không có DATABASE_URL (Postgres) -> các test dưới đây dùng
monkeypatch, KHÔNG cần kết nối DB thật. Xem ghi chú cuối file về giới hạn.
"""

import inspect

import psycopg
import pytest

import booking
import storage
from data import DOCTORS, DEPARTMENTS, generate_available_slots


def _pick_slot():
    """Lấy 1 (date, time, dept_code, doctor_id) hợp lệ từ lịch làm việc hiện tại."""
    slots = generate_available_slots()
    date_str = next(iter(slots))
    time_str = slots[date_str][0]
    dept_code = next(iter(DEPARTMENTS))
    doctor_id = DOCTORS[dept_code][0]["id"]
    return date_str, time_str, dept_code, doctor_id


def _make_unique_violation(constraint_name):
    """Tạo psycopg.errors.UniqueViolation thật với .diag.constraint_name giả.

    `diag` là property chỉ-đọc dựng từ `_info` truyền vào __init__ (không gán
    thẳng được), nên phải đi qua tham số `info` với key là `DiagnosticField`.
    """
    from psycopg.pq import DiagnosticField
    info = {DiagnosticField.CONSTRAINT_NAME: constraint_name.encode()}
    return psycopg.errors.UniqueViolation(
        "duplicate key value violates unique constraint", info=info)


def test_schema_has_unique_index():
    """SCHEMA_SQL (hoặc constant riêng chạy qua init_schema) phải có UNIQUE INDEX
    đúng cột (date, time), lọc WHERE status = 'confirmed'."""
    sql = storage.SCHEMA_SQL + getattr(storage, "UNIQUE_SLOT_INDEX_SQL", "")
    assert "CREATE UNIQUE INDEX" in sql
    assert "ux_appointments_slot" in sql
    assert "appointments" in sql
    assert "(date, time)" in sql.replace("  ", " ")
    assert "status = 'confirmed'" in sql


def test_unique_index_creation_is_isolated_in_init_schema():
    """Câu lệnh tạo ux_appointments_slot phải nằm trong try/except RIÊNG bên trong
    init_schema(), để 1 lỗi tạo index (vd dữ liệu trùng sẵn có) không chặn các
    bảng/index khác trong SCHEMA_SQL không bao giờ được tạo."""
    source = inspect.getsource(storage.init_schema)
    idx = source.find("UNIQUE_SLOT_INDEX_SQL")
    assert idx != -1, "init_schema() phải gọi UNIQUE_SLOT_INDEX_SQL"
    try_idx = source.rfind("try", 0, idx)
    except_idx = source.find("except", idx)
    assert try_idx != -1 and except_idx != -1, (
        "Câu lệnh tạo ux_appointments_slot phải được bọc try/except riêng"
    )


def test_init_schema_survives_unique_index_failure(monkeypatch):
    """Nếu CREATE UNIQUE INDEX fail (vd dữ liệu trùng sẵn), init_schema() vẫn phải
    hoàn tất (không raise) và đánh dấu _schema_ready — các bảng khác trong
    SCHEMA_SQL đã chạy trước đó không bị mất do lỗi này."""
    monkeypatch.setattr(storage, "USE_DB", True)
    monkeypatch.setattr(storage, "_schema_ready", False)

    executed = []

    class FakeCursor:
        def execute(self, sql, *a, **kw):
            executed.append(sql)
            if "ux_appointments_slot" in sql:
                raise Exception("duplicate key value violates unique constraint")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def commit(self):
            pass

        def rollback(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(storage, "_connect", lambda: FakeConn())

    storage.init_schema()  # không được raise

    assert storage._schema_ready is True
    assert any("CREATE TABLE IF NOT EXISTS appointments" in s for s in executed)
    assert any("ux_appointments_slot" in s for s in executed)


def test_book_appointment_catches_slot_integrity_error(monkeypatch):
    """UniqueViolation trên ux_appointments_slot -> response 'đã có người đặt',
    không để exception rò rỉ lên caller."""
    date_str, time_str, dept_code, doctor_id = _pick_slot()

    call_count = {"n": 0}

    def fake_add_appointment(appt):
        call_count["n"] += 1
        raise _make_unique_violation("ux_appointments_slot")

    monkeypatch.setattr(storage, "add_appointment", fake_add_appointment)

    # Sau khi bắt lỗi, booking gọi lại _confirmed_at để lấy bản ghi thắng race.
    winner = {"code": "SHI-WINNER", "patient_phone": "0900000000"}

    def confirmed_at_seq(*calls):
        it = iter(calls)
        def _f(d, t):
            return next(it)
        return _f

    monkeypatch.setattr(booking, "_confirmed_at",
                        confirmed_at_seq(None, winner))

    ok, payload = booking.book_appointment(
        "sess1", dept_code, doctor_id, date_str, time_str,
        patient_name="Nguyễn Văn A", patient_phone="0911111111")

    assert ok is False
    assert "error" in payload
    assert "vừa có người đặt" in payload["error"] or payload.get("duplicate") is True
    assert call_count["n"] == 1


def test_book_appointment_slot_taken_dedupe_by_phone(monkeypatch):
    """Nếu người thua race trùng SĐT với người thắng -> duplicate=True (giống
    nhánh dedupe theo SĐT hiện có, KHÔNG phải lỗi chung chung)."""
    date_str, time_str, dept_code, doctor_id = _pick_slot()

    winner = {"code": "SHI-WINNER", "patient_phone": "0911111111"}

    def confirmed_at_seq(*calls):
        it = iter(calls)
        def _f(d, t):
            return next(it)
        return _f

    monkeypatch.setattr(booking, "_confirmed_at",
                        confirmed_at_seq(None, winner))

    def fake_add_appointment(appt):
        raise _make_unique_violation("ux_appointments_slot")

    monkeypatch.setattr(storage, "add_appointment", fake_add_appointment)

    ok, payload = booking.book_appointment(
        "sess1", dept_code, doctor_id, date_str, time_str,
        patient_name="Nguyễn Văn A", patient_phone="0911111111")

    assert ok is False
    assert payload.get("duplicate") is True
    assert payload.get("existing") == winner


def test_book_appointment_retries_on_code_collision(monkeypatch):
    """UniqueViolation trên constraint KHÁC ux_appointments_slot (vd
    appointments_pkey do _generate_code() sinh trùng mã) -> KHÔNG gọi
    _confirmed_at, retry với code mới, thành công lần 2."""
    date_str, time_str, dept_code, doctor_id = _pick_slot()

    confirmed_at_calls = []
    monkeypatch.setattr(
        booking, "_confirmed_at",
        lambda d, t: confirmed_at_calls.append((d, t)) or None)

    codes_seen = []
    calls = {"n": 0}

    def fake_add_appointment(appt):
        codes_seen.append(appt["code"])
        calls["n"] += 1
        if calls["n"] == 1:
            raise _make_unique_violation("appointments_pkey")
        return None  # thành công lần 2

    monkeypatch.setattr(storage, "add_appointment", fake_add_appointment)

    ok, payload = booking.book_appointment(
        "sess1", dept_code, doctor_id, date_str, time_str,
        patient_name="Nguyễn Văn A", patient_phone="0911111111")

    assert ok is True
    assert payload["code"] == codes_seen[1]
    assert codes_seen[0] != codes_seen[1]
    assert calls["n"] == 2
    # _confirmed_at chỉ được gọi bởi book_appointment() ở bước kiểm tra slot lúc
    # đầu (KHÔNG bị gọi lại trong nhánh retry-code-collision).
    assert len(confirmed_at_calls) == 1


def test_book_appointment_gives_up_after_one_retry_on_repeated_code_collision(
        monkeypatch):
    """Nếu retry lần 2 vẫn UniqueViolation trên constraint khác slot -> trả lỗi
    hệ thống chung, không raise, không gọi _confirmed_at."""
    date_str, time_str, dept_code, doctor_id = _pick_slot()

    monkeypatch.setattr(booking, "_confirmed_at", lambda d, t: None)

    def fake_add_appointment(appt):
        raise _make_unique_violation("appointments_pkey")

    monkeypatch.setattr(storage, "add_appointment", fake_add_appointment)

    ok, payload = booking.book_appointment(
        "sess1", dept_code, doctor_id, date_str, time_str,
        patient_name="Nguyễn Văn A", patient_phone="0911111111")

    assert ok is False
    assert payload == {"error": "Lỗi hệ thống, vui lòng thử lại."}


def test_book_appointment_success_path_unchanged(monkeypatch):
    """Đường thành công (không lỗi) không bị đổi hành vi/response shape."""
    date_str, time_str, dept_code, doctor_id = _pick_slot()

    monkeypatch.setattr(booking, "_confirmed_at", lambda d, t: None)
    monkeypatch.setattr(storage, "add_appointment", lambda appt: None)

    ok, payload = booking.book_appointment(
        "sess1", dept_code, doctor_id, date_str, time_str,
        patient_name="Nguyễn Văn A", patient_phone="0911111111")

    assert ok is True
    assert payload["date"] == date_str
    assert payload["time"] == time_str
    assert payload["status"] == "confirmed"


# ---------------------------------------------------------------------------
# Integration test thật trên Postgres — CHỈ chạy nếu có DATABASE_URL khả dụng.
# Trong môi trường dev/CI hiện tại KHÔNG có DATABASE_URL -> test này bị skip.
# GHI CHÚ QUAN TRỌNG: race condition thật trên Postgres CHƯA được verify khi
# skip; các test ở trên chỉ verify qua monkeypatch (giả lập UniqueViolation) +
# review SQL của UNIQUE INDEX, KHÔNG phải chạy 2 thread thật đấu race trên DB.
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not storage.USE_DB,
                    reason="Cần DATABASE_URL trỏ tới Postgres thật để test race "
                          "condition đồng thời (2 thread cùng đặt 1 slot).")
def test_concurrent_booking_only_one_wins_real_postgres():
    import threading

    date_str, time_str, dept_code, doctor_id = _pick_slot()
    results = []

    def worker(phone):
        ok, payload = booking.book_appointment(
            f"sess-{phone}", dept_code, doctor_id, date_str, time_str,
            patient_name="Race Tester", patient_phone=phone)
        results.append(ok)

    threads = [threading.Thread(target=worker, args=(f"090000000{i}",))
              for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count(True) == 1
