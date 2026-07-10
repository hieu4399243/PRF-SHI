"""
Tests cho C2 (double-booking race condition) + H1 (khoá trùng giờ theo bác sĩ).

Bug gốc (C2): booking.book_appointment() kiểm tra _confirmed_at(date, time) rồi
mới storage.add_appointment() — không transaction/unique constraint. Hai request
đặt cùng giờ gần như đồng thời có thể cùng pass check trước khi bên kia insert.

Fix (C2): UNIQUE partial index `ux_appointments_slot` trên
appointments(date, time) WHERE status='confirmed' (Postgres) + booking.py bắt
psycopg.errors.UniqueViolation và branch theo exc.diag.constraint_name.

Bug gốc (H1): khoá trùng giờ ở trên chỉ tính (date, time) — coi cả phòng khám
là 1 ghế. Đặt bác sĩ A giờ X chặn luôn bác sĩ B giờ X dù 2 bác sĩ khác nhau.

Fix (H1): đổi khoá + index sang (doctor_id, date, time) — index đổi tên thành
`ux_appointments_doctor_slot`, `_confirmed_at` nhận thêm tham số `doctor_id`.

Môi trường dev không có DATABASE_URL (Postgres) -> các test dưới đây dùng
monkeypatch, KHÔNG cần kết nối DB thật. Xem ghi chú cuối file về giới hạn.
"""

import inspect

import psycopg
import pytest

from app import booking
from app import storage
from app.data import DOCTORS, DEPARTMENTS, generate_available_slots


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


def test_schema_uses_doctor_scoped_index():
    """UNIQUE INDEX phải khoá theo (doctor_id, date, time), KHÔNG chỉ (date,
    time) — 2 bác sĩ khác nhau đặt cùng giờ không được coi là trùng."""
    sql = storage.SCHEMA_SQL + getattr(storage, "UNIQUE_SLOT_INDEX_SQL", "")
    assert "CREATE UNIQUE INDEX" in sql
    assert "ux_appointments_doctor_slot" in sql
    assert "appointments" in sql
    assert "(doctor_id, date, time)" in sql.replace("  ", " ")
    assert "status = 'confirmed'" in sql


def test_old_slot_index_dropped_after_new_index_created():
    """Index cũ `ux_appointments_slot` phải bị DROP (fail-safe: SAU khi index
    mới đã CREATE xong, không phải trước) — 2 lệnh execute() riêng biệt, không
    gộp chung 1 chuỗi SQL (psycopg3 không đảm bảo multi-statement)."""
    create_sql = storage.UNIQUE_SLOT_INDEX_SQL
    drop_sql = storage.DROP_OLD_SLOT_INDEX_SQL
    assert "ux_appointments_doctor_slot" in create_sql
    assert "DROP INDEX IF EXISTS ux_appointments_slot" in drop_sql
    # Không phải cùng 1 hằng số/chuỗi SQL (2 execute() riêng biệt).
    assert create_sql is not drop_sql

    source = inspect.getsource(storage.init_schema)
    create_idx = source.find("cur.execute(UNIQUE_SLOT_INDEX_SQL)")
    drop_idx = source.find("cur.execute(DROP_OLD_SLOT_INDEX_SQL)")
    assert create_idx != -1 and drop_idx != -1, (
        "CREATE và DROP phải là 2 cur.execute() riêng biệt, không gộp 1 chuỗi SQL"
    )
    assert create_idx < drop_idx, (
        "CREATE index mới phải đứng TRƯỚC DROP index cũ trong init_schema()"
    )


def test_unique_index_creation_is_isolated_in_init_schema():
    """Câu lệnh tạo ux_appointments_doctor_slot phải nằm trong try/except RIÊNG
    bên trong init_schema(), để 1 lỗi tạo index (vd dữ liệu trùng sẵn có) không
    chặn các bảng/index khác trong SCHEMA_SQL không bao giờ được tạo."""
    source = inspect.getsource(storage.init_schema)
    idx = source.find("UNIQUE_SLOT_INDEX_SQL")
    assert idx != -1, "init_schema() phải gọi UNIQUE_SLOT_INDEX_SQL"
    try_idx = source.rfind("try", 0, idx)
    except_idx = source.find("except", idx)
    assert try_idx != -1 and except_idx != -1, (
        "Câu lệnh tạo ux_appointments_doctor_slot phải được bọc try/except riêng"
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
    """UniqueViolation trên ux_appointments_doctor_slot -> response 'đã có
    người đặt', không để exception rò rỉ lên caller."""
    date_str, time_str, dept_code, doctor_id = _pick_slot()

    call_count = {"n": 0}

    def fake_add_appointment(appt):
        call_count["n"] += 1
        raise _make_unique_violation("ux_appointments_doctor_slot")

    monkeypatch.setattr(storage, "add_appointment", fake_add_appointment)

    # Sau khi bắt lỗi, booking gọi lại _confirmed_at để lấy bản ghi thắng race.
    winner = {"code": "SHI-WINNER", "patient_phone": "0900000000"}

    def confirmed_at_seq(*calls):
        it = iter(calls)
        def _f(doctor_id, d, t):
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
        def _f(doctor_id, d, t):
            return next(it)
        return _f

    monkeypatch.setattr(booking, "_confirmed_at",
                        confirmed_at_seq(None, winner))

    def fake_add_appointment(appt):
        raise _make_unique_violation("ux_appointments_doctor_slot")

    monkeypatch.setattr(storage, "add_appointment", fake_add_appointment)

    ok, payload = booking.book_appointment(
        "sess1", dept_code, doctor_id, date_str, time_str,
        patient_name="Nguyễn Văn A", patient_phone="0911111111")

    assert ok is False
    assert payload.get("duplicate") is True
    assert payload.get("existing") == winner


def test_insert_with_race_guard_uses_doctor_id_on_slot_collision(monkeypatch):
    """Chỗ dễ bỏ sót nhất: `_insert_with_race_guard` có 1 lời gọi `_confirmed_at`
    RIÊNG bên trong nhánh xử lý UniqueViolation (khác với lời gọi ở
    book_appointment()) — lời gọi này CŨNG phải truyền đủ 3 tham số
    (doctor_id, date_str, time_str), nếu không sẽ TypeError khi 2 request thật
    race nhau cùng bác sĩ cùng giờ."""
    date_str, time_str, dept_code, doctor_id = _pick_slot()

    received_args = []

    def fake_confirmed_at(*args):
        received_args.append(args)
        return None

    monkeypatch.setattr(booking, "_confirmed_at", fake_confirmed_at)

    def fake_add_appointment(appt):
        raise _make_unique_violation("ux_appointments_doctor_slot")

    monkeypatch.setattr(storage, "add_appointment", fake_add_appointment)

    ok, payload = booking.book_appointment(
        "sess1", dept_code, doctor_id, date_str, time_str,
        patient_name="Nguyễn Văn A", patient_phone="0911111111")

    assert ok is False
    assert "vừa có người đặt" in payload.get("error", "")
    # _confirmed_at bị gọi 2 lần: 1 lần ở book_appointment() (kiểm tra ban đầu,
    # trả None nên cho qua để insert), 1 lần bên trong _insert_with_race_guard
    # (nhánh xử lý UniqueViolation, sau khi insert thất bại vì race) — CẢ 2 lần
    # đều phải nhận đúng 3 tham số, tham số đầu (doctor_id) đúng bằng doctor_id
    # đã truyền vào book_appointment().
    assert len(received_args) == 2
    for args in received_args:
        assert len(args) == 3
        assert args[0] == doctor_id
        assert args[1:] == (date_str, time_str)


def test_book_appointment_retries_on_code_collision(monkeypatch):
    """UniqueViolation trên constraint KHÁC ux_appointments_doctor_slot (vd
    appointments_pkey do _generate_code() sinh trùng mã) -> KHÔNG gọi
    _confirmed_at, retry với code mới, thành công lần 2."""
    date_str, time_str, dept_code, doctor_id = _pick_slot()

    confirmed_at_calls = []
    monkeypatch.setattr(
        booking, "_confirmed_at",
        lambda doc, d, t: confirmed_at_calls.append((doc, d, t)) or None)

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

    monkeypatch.setattr(booking, "_confirmed_at", lambda doc, d, t: None)

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

    monkeypatch.setattr(booking, "_confirmed_at", lambda doc, d, t: None)
    monkeypatch.setattr(storage, "add_appointment", lambda appt: None)

    ok, payload = booking.book_appointment(
        "sess1", dept_code, doctor_id, date_str, time_str,
        patient_name="Nguyễn Văn A", patient_phone="0911111111")

    assert ok is True
    assert payload["date"] == date_str
    assert payload["time"] == time_str
    assert payload["status"] == "confirmed"


# ---------------------------------------------------------------------------
# H1 — khoá trùng giờ phải khoá theo (doctor_id, date, time), KHÔNG chỉ
# (date, time) — 2 bác sĩ khác nhau đặt cùng giờ, cùng ngày phải đều thành
# công; cùng bác sĩ vẫn bị chặn như hành vi C2 cũ (không regress).
# ---------------------------------------------------------------------------
def test_confirmed_at_filters_by_doctor_id(monkeypatch):
    """2 lịch hẹn 'confirmed' cùng (date, time) nhưng khác doctor_id ->
    _confirmed_at(doctor_id, date, time) chỉ trả về đúng lịch của bác sĩ đó."""
    date_str, time_str, dept_code, doctor_id = _pick_slot()
    doctors = DOCTORS[dept_code]
    doctor_a = doctors[0]["id"]
    doctor_b = doctors[1]["id"] if len(doctors) > 1 else "bs-khac-khong-ton-tai"

    appt_a = {"code": "SHI-A", "status": "confirmed", "doctor_id": doctor_a,
              "date": date_str, "time": time_str}
    appt_b = {"code": "SHI-B", "status": "confirmed", "doctor_id": doctor_b,
              "date": date_str, "time": time_str}
    monkeypatch.setattr(storage, "list_appointments", lambda: [appt_a, appt_b])

    assert booking._confirmed_at(doctor_a, date_str, time_str) == appt_a
    assert booking._confirmed_at(doctor_b, date_str, time_str) == appt_b
    assert booking._confirmed_at("bs-hoan-toan-khac", date_str, time_str) is None


def test_book_appointment_different_doctors_same_slot_both_succeed(monkeypatch):
    """2 bệnh nhân đặt CÙNG giờ, CÙNG ngày nhưng KHÁC bác sĩ -> cả 2 đều thành
    công (đúng bug H1 cần sửa: trước fix, người thứ 2 sẽ bị chặn oan)."""
    date_str, time_str, dept_code, _ = _pick_slot()
    doctors = DOCTORS[dept_code]
    if len(doctors) < 2:
        pytest.skip("Cần >=2 bác sĩ trong cùng 1 khoa để test kịch bản này")
    doctor_a, doctor_b = doctors[0]["id"], doctors[1]["id"]

    store = []
    monkeypatch.setattr(storage, "list_appointments", lambda: store)
    monkeypatch.setattr(storage, "add_appointment", lambda appt: store.append(appt))

    ok1, payload1 = booking.book_appointment(
        "sess1", dept_code, doctor_a, date_str, time_str,
        patient_name="Nguyễn Văn A", patient_phone="0911111111")
    ok2, payload2 = booking.book_appointment(
        "sess2", dept_code, doctor_b, date_str, time_str,
        patient_name="Trần Thị B", patient_phone="0922222222")

    assert ok1 is True
    assert ok2 is True
    assert payload1["doctor_id"] == doctor_a
    assert payload2["doctor_id"] == doctor_b


def test_book_appointment_same_doctor_same_slot_blocked(monkeypatch):
    """2 bệnh nhân đặt CÙNG giờ, CÙNG ngày, CÙNG bác sĩ -> lần 2 vẫn bị chặn
    (regression test: không phá hành vi chống trùng đã có từ C2)."""
    date_str, time_str, dept_code, doctor_id = _pick_slot()

    store = []
    monkeypatch.setattr(storage, "list_appointments", lambda: store)
    monkeypatch.setattr(storage, "add_appointment", lambda appt: store.append(appt))

    ok1, payload1 = booking.book_appointment(
        "sess1", dept_code, doctor_id, date_str, time_str,
        patient_name="Nguyễn Văn A", patient_phone="0911111111")
    ok2, payload2 = booking.book_appointment(
        "sess2", dept_code, doctor_id, date_str, time_str,
        patient_name="Trần Thị B", patient_phone="0922222222")

    assert ok1 is True
    assert ok2 is False
    assert "error" in payload2


# ---------------------------------------------------------------------------
# M6 — JSON mode: storage.add_appointment() raise DuplicateCodeError/
# SlotTakenError (thay vì psycopg.errors.UniqueViolation) khi USE_DB=False.
# _insert_with_race_guard phải bắt riêng 2 exception này TRƯỚC nhánh
# `except Exception` chung (mới xử lý UniqueViolation của Postgres).
# ---------------------------------------------------------------------------
def test_book_appointment_json_mode_retries_on_duplicate_code(monkeypatch):
    date_str, time_str, dept_code, doctor_id = _pick_slot()
    monkeypatch.setattr(storage, "USE_DB", False)
    monkeypatch.setattr(booking, "_confirmed_at", lambda doc, d, t: None)

    codes_seen = []
    calls = {"n": 0}

    def fake_add_appointment(appt):
        codes_seen.append(appt["code"])
        calls["n"] += 1
        if calls["n"] == 1:
            raise storage.DuplicateCodeError(appt["code"])
        return None

    monkeypatch.setattr(storage, "add_appointment", fake_add_appointment)

    ok, payload = booking.book_appointment(
        "sess1", dept_code, doctor_id, date_str, time_str,
        patient_name="Nguyễn Văn A", patient_phone="0911111111")

    assert ok is True
    assert payload["code"] == codes_seen[1]
    assert codes_seen[0] != codes_seen[1]
    assert calls["n"] == 2


def test_book_appointment_json_mode_slot_taken(monkeypatch):
    date_str, time_str, dept_code, doctor_id = _pick_slot()
    monkeypatch.setattr(storage, "USE_DB", False)
    monkeypatch.setattr(booking, "_confirmed_at", lambda doc, d, t: None)

    existing_appt = {"code": "SHI-WINNER", "patient_phone": "0900000000"}
    generate_code_calls = {"n": 0}
    orig_generate = booking._generate_code

    def counting_generate():
        generate_code_calls["n"] += 1
        return orig_generate()

    monkeypatch.setattr(booking, "_generate_code", counting_generate)

    def fake_add_appointment(appt):
        raise storage.SlotTakenError(existing_appt)

    monkeypatch.setattr(storage, "add_appointment", fake_add_appointment)

    ok, payload = booking.book_appointment(
        "sess1", dept_code, doctor_id, date_str, time_str,
        patient_name="Nguyễn Văn A", patient_phone="0911111111")

    assert ok is False
    assert "error" in payload
    assert "vừa có người đặt" in payload["error"]
    # _generate_code() chỉ được gọi 1 lần (lúc tạo appointment ban đầu ở
    # book_appointment()) — KHÔNG bị gọi lại trong nhánh SlotTakenError.
    assert generate_code_calls["n"] == 1


def test_book_appointment_json_mode_slot_taken_dedupe_by_phone(monkeypatch):
    date_str, time_str, dept_code, doctor_id = _pick_slot()
    monkeypatch.setattr(storage, "USE_DB", False)
    monkeypatch.setattr(booking, "_confirmed_at", lambda doc, d, t: None)

    existing_appt = {"code": "SHI-WINNER", "patient_phone": "0911111111"}

    def fake_add_appointment(appt):
        raise storage.SlotTakenError(existing_appt)

    monkeypatch.setattr(storage, "add_appointment", fake_add_appointment)

    ok, payload = booking.book_appointment(
        "sess1", dept_code, doctor_id, date_str, time_str,
        patient_name="Nguyễn Văn A", patient_phone="0911111111")

    assert ok is False
    assert payload.get("duplicate") is True
    assert payload.get("existing") == existing_appt


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
