"""
Lớp lưu trữ (storage layer) — tách nghiệp vụ khỏi nơi cất dữ liệu.

Hai backend, tự chọn theo biến môi trường:
  - Có `DATABASE_URL`  -> **Postgres** (dùng cho Supabase / cloud). Dữ liệu BỀN VỮNG,
    không mất khi restart/scale, quản lý online qua dashboard Supabase.
  - Không có           -> **file JSON** (appointments.json / device_tokens.json) như cũ,
    để demo và chạy đánh giá (eval) được ngay mà không cần DB.

Cả booking.py và push.py đều gọi qua module này, nên đổi backend không phải sửa
nghiệp vụ. Lấy connection string ở Supabase: Project → Settings → Database →
Connection string (khuyên dùng **Connection pooler / Transaction**), gán vào
biến môi trường `DATABASE_URL`.
"""

import json
import os
import threading
import uuid
from datetime import datetime

# Nạp biến môi trường từ file .env nếu có (tùy chọn — không có python-dotenv vẫn chạy).
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
USE_DB = bool(DATABASE_URL)

from .paths import APPOINTMENTS_PATH, DOCTORS_PATH, PATIENTS_PATH, TOKENS_PATH  # noqa: F401  (re-export cho code cũ)

_schema_ready = False
_SCHEMA_LOCK = threading.Lock()

# Khoá trong-process cho MỌI thao tác JSON đọc-sửa-ghi (add_appointment,
# set_reminder_sent, set_status, add_token, remove_token) — chỉ bảo vệ trong 1
# process (nhất quán với quyết định "1 process" của dự án), không bảo vệ đa
# process/đa worker cùng ghi 1 file JSON.
_JSON_LOCK = threading.Lock()


class DuplicateCodeError(Exception):
    """Mã lịch hẹn đã tồn tại (JSON mode) — tương đương UniqueViolation trên
    appointments_pkey ở Postgres."""


class SlotTakenError(Exception):
    """Khung giờ (doctor_id, date, time) đã có lịch 'confirmed' khác (JSON
    mode) — tương đương UNIQUE INDEX ux_appointments_doctor_slot ở Postgres."""

    def __init__(self, existing):
        super().__init__(existing.get("code"))
        self.existing = existing


# ===========================================================================
# POSTGRES backend
# ===========================================================================
def _connect():
    import psycopg  # import trễ: chỉ cần khi thực sự dùng DB
    # prepare_threshold=None -> TẮT auto-prepare của psycopg3.
    #
    # Mặc định psycopg3 tự PREPARE một câu lệnh sau 5 lần chạy giống nhau. Supabase
    # (và mọi pgbouncer chạy transaction pooling — cổng 6543) KHÔNG giữ session giữa
    # các transaction, nên prepared statement của lần trước vẫn còn tên nhưng lại
    # nằm ở backend khác -> lỗi `DuplicatePreparedStatement: prepared statement
    # "_pg3_0" already exists`. Lỗi này CHỈ xuất hiện từ lần chạy thứ 6 trở đi nên
    # rất dễ lọt qua test/demo rồi mới nổ khi có nhiều lượt đặt lịch thật.
    return psycopg.connect(DATABASE_URL, prepare_threshold=None)


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS appointments (
    code            TEXT PRIMARY KEY,
    session         TEXT,
    patient_name    TEXT,
    patient_phone   TEXT,
    department      TEXT,
    department_code TEXT,
    doctor          TEXT,
    doctor_id       TEXT,
    date            TEXT,
    time            TEXT,
    created_at      TEXT,
    status          TEXT,
    reminders_sent  JSONB NOT NULL DEFAULT '[]'::jsonb
);
ALTER TABLE appointments ADD COLUMN IF NOT EXISTS patient_phone TEXT;
CREATE TABLE IF NOT EXISTS device_tokens (
    session TEXT,
    token   TEXT,
    PRIMARY KEY (session, token)
);
CREATE TABLE IF NOT EXISTS services (
    code        TEXT PRIMARY KEY,
    name        TEXT,
    descr       TEXT,
    keywords    JSONB NOT NULL DEFAULT '[]'::jsonb,
    sort_order  INT DEFAULT 0
);
CREATE TABLE IF NOT EXISTS doctors (
    id           TEXT PRIMARY KEY,
    service_code TEXT REFERENCES services(code),
    name         TEXT,
    sort_order   INT DEFAULT 0
);
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS phone TEXT;
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS email TEXT;
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS created_at TEXT;
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS updated_at TEXT;
CREATE TABLE IF NOT EXISTS patients (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    phone       TEXT NOT NULL UNIQUE,
    email       TEXT,
    address     TEXT,
    notes       TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,
    username        TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('admin', 'doctor', 'guest')),
    email           TEXT,
    phone           TEXT,
    address         TEXT,
    doctor_id       TEXT REFERENCES doctors(id),
    patient_id      TEXT REFERENCES patients(id),
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS address TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS patient_id TEXT REFERENCES patients(id);
CREATE TABLE IF NOT EXISTS safety_patterns (
    kind    TEXT NOT NULL,   -- 'emergency' | 'diagnosis' | 'handoff'
    pattern TEXT NOT NULL,
    PRIMARY KEY (kind, pattern)
);
"""

# Tách riêng khỏi SCHEMA_SQL: UNIQUE index này có thể FAIL nếu dữ liệu prod đã có
# sẵn >=2 lịch 'confirmed' trùng (doctor_id, date, time) — đúng tình huống mà index
# này tồn tại để ngăn. `IF NOT EXISTS` chỉ chặn chạy lại DDL, KHÔNG chặn lỗi vì dữ
# liệu trùng sẵn có. Bọc try/except riêng để 1 lỗi ở đây không chặn các bảng/index
# khác trong SCHEMA_SQL (degrade an toàn: app vẫn chạy, tạm thời mất bảo vệ
# UNIQUE, thay vì _schema_ready không bao giờ True -> mọi request storage fail).
#
# Khoá theo (doctor_id, date, time) thay vì (date, time): 2 bác sĩ khác nhau đặt
# cùng giờ, cùng ngày phải đều thành công (chỉ trùng giờ CÙNG 1 bác sĩ mới bị
# chặn). Tên index cũ `ux_appointments_slot` (khoá (date, time), coi cả phòng
# khám là 1 ghế) bị DROP sau khi index mới tạo xong — xem DROP_OLD_SLOT_INDEX_SQL
# và init_schema() bên dưới.
UNIQUE_SLOT_INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS ux_appointments_doctor_slot
    ON appointments (doctor_id, date, time) WHERE status = 'confirmed';
"""

DROP_OLD_SLOT_INDEX_SQL = """
DROP INDEX IF EXISTS ux_appointments_slot;
"""

_APPT_COLS = ["code", "session", "patient_name", "patient_phone", "department",
              "department_code", "doctor", "doctor_id", "date", "time", "created_at",
              "status", "reminders_sent"]
_DOCTOR_COLS = ["id", "service_code", "name", "phone", "email", "created_at", "updated_at"]
_PATIENT_COLS = ["id", "name", "phone", "email", "address", "notes", "created_at", "updated_at"]


def init_schema():
    """Tạo bảng nếu chưa có (idempotent). Tự gọi trước thao tác DB đầu tiên.

    Khoá bằng _SCHEMA_LOCK: 2 request đầu tiên gọi gần như đồng thời (trước
    khi _schema_ready=True) mà không khoá có thể cùng chạy CREATE TABLE/INDEX
    IF NOT EXISTS đồng thời -> Postgres có thể báo lỗi trùng khoá hệ thống dù
    DDL "idempotent". Double-checked locking: kiểm tra cờ lần 2 sau khi có
    khoá để tránh chạy lại DDL nếu request khác đã hoàn tất trong lúc chờ."""
    global _schema_ready
    if _schema_ready or not USE_DB:
        return
    with _SCHEMA_LOCK:
        if _schema_ready:  # request khác đã chạy xong DDL trong lúc chờ khoá
            return
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
            conn.commit()
            try:
                # THỨ TỰ BẮT BUỘC: CREATE index mới TRƯỚC, DROP index cũ SAU. Nếu
                # CREATE fail (vd. dữ liệu trùng sẵn có theo bộ khoá mới), index cũ
                # vẫn còn nguyên -> ứng dụng vẫn có 1 lớp bảo vệ UNIQUE (chặt hơn
                # cần thiết nhưng còn hơn không). Nếu DROP chạy trước mà CREATE fail,
                # ứng dụng mất HOÀN TOÀN bảo vệ unique cho tới lần deploy sau. Tách 2
                # lệnh execute() riêng biệt (không gộp 1 chuỗi SQL): psycopg3 xử lý
                # multi-statement trong 1 lần execute() không đảm bảo, có thể lỗi/
                # no-op âm thầm.
                cur.execute(UNIQUE_SLOT_INDEX_SQL)
                cur.execute(DROP_OLD_SLOT_INDEX_SQL)
                conn.commit()
            except Exception as exc:  # noqa: BLE001 - phải bắt mọi lỗi DB ở đây
                # Không để lỗi tạo UNIQUE index (vd. dữ liệu trùng sẵn có) chặn schema
                # init của các bảng khác. Rollback để connection còn dùng được tiếp
                # (Postgres yêu cầu rollback sau lỗi trong transaction).
                conn.rollback()
                print(
                    "[storage] CẢNH BÁO: không tạo được UNIQUE INDEX "
                    "ux_appointments_doctor_slot (appointments.doctor_id, date, "
                    f"time). Lỗi: {exc}. Có thể do đã tồn tại lịch 'confirmed' "
                    "trùng (doctor_id, date, time) trong dữ liệu hiện có — cần dọn "
                    "dữ liệu thủ công rồi khởi động lại app để bật lại bảo vệ "
                    "chống trùng lịch ở tầng DB. App vẫn chạy tiếp nhưng KHÔNG có "
                    "UNIQUE constraint bảo vệ tạm thời."
                )
        _schema_ready = True


def _row_to_appt(row):
    appt = dict(zip(_APPT_COLS, row))
    rs = appt.get("reminders_sent")
    if isinstance(rs, str):           # phòng khi driver trả chuỗi
        rs = json.loads(rs)
    appt["reminders_sent"] = rs or []
    return appt


def _row_to_doctor(row):
    return dict(zip(_DOCTOR_COLS, row))


def _row_to_patient(row):
    return dict(zip(_PATIENT_COLS, row))


# ---------------------------------------------------------------------------
# JSON backend (giữ nguyên hành vi cũ)
# ---------------------------------------------------------------------------
def _json_load(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _json_save(path, data):
    """Ghi atomic: viết ra file tạm cùng thư mục rồi os.replace() — không bao
    giờ để lại file nửa-ghi nếu process chết giữa chừng."""
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


# ===========================================================================
# API CÔNG KHAI — APPOINTMENTS
# ===========================================================================
def list_appointments():
    if USE_DB:
        init_schema()
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(_APPT_COLS)} FROM appointments "
                        "ORDER BY created_at")
            return [_row_to_appt(r) for r in cur.fetchall()]
    return _json_load(APPOINTMENTS_PATH, [])


def get_appointment(code):
    if USE_DB:
        init_schema()
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(_APPT_COLS)} FROM appointments "
                        "WHERE code = %s", (code,))
            row = cur.fetchone()
            return _row_to_appt(row) if row else None
    for a in _json_load(APPOINTMENTS_PATH, []):
        if a["code"] == code:
            return a
    return None


def add_appointment(appt):
    appt.setdefault("reminders_sent", [])
    if USE_DB:
        init_schema()
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO appointments "
                "(code, session, patient_name, patient_phone, department, department_code, "
                " doctor, doctor_id, date, time, created_at, status, reminders_sent) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (appt["code"], appt.get("session"), appt.get("patient_name"),
                 appt.get("patient_phone"), appt.get("department"),
                 appt.get("department_code"), appt.get("doctor"),
                 appt.get("doctor_id"), appt.get("date"), appt.get("time"),
                 appt.get("created_at"), appt.get("status"),
                 json.dumps(appt["reminders_sent"])),
            )
            conn.commit()
        return
    with _JSON_LOCK:
        items = _json_load(APPOINTMENTS_PATH, [])
        if any(a["code"] == appt["code"] for a in items):
            raise DuplicateCodeError(appt["code"])
        if appt.get("status") == "confirmed":
            for a in items:
                if (a.get("status") == "confirmed"
                        and a.get("doctor_id") == appt.get("doctor_id")
                        and a.get("date") == appt.get("date")
                        and a.get("time") == appt.get("time")):
                    raise SlotTakenError(a)
        items.append(appt)
        _json_save(APPOINTMENTS_PATH, items)


def set_reminder_sent(code, reminder_key):
    """Thêm 1 loại nhắc vào reminders_sent của lịch hẹn (tránh gửi trùng)."""
    if USE_DB:
        init_schema()
        with _connect() as conn, conn.cursor() as cur:
            # gộp không trùng ở phía DB
            cur.execute(
                "UPDATE appointments "
                "SET reminders_sent = ("
                "  SELECT to_jsonb(array(SELECT DISTINCT jsonb_array_elements_text("
                "    reminders_sent || %s::jsonb))) ) "
                "WHERE code = %s",
                (json.dumps([reminder_key]), code),
            )
            updated = cur.rowcount
            conn.commit()
        return updated > 0
    with _JSON_LOCK:
        items = _json_load(APPOINTMENTS_PATH, [])
        for a in items:
            if a["code"] == code:
                sent = set(a.get("reminders_sent", []))
                sent.add(reminder_key)
                a["reminders_sent"] = sorted(sent)
                _json_save(APPOINTMENTS_PATH, items)
                return True
        return False


def set_status(code, status):
    """Cập nhật trạng thái một lịch hẹn (vd. 'cancelled'). True nếu có cập nhật."""
    if USE_DB:
        init_schema()
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("UPDATE appointments SET status = %s WHERE code = %s",
                        (status, code))
            updated = cur.rowcount
            conn.commit()
        return updated > 0
    with _JSON_LOCK:
        items = _json_load(APPOINTMENTS_PATH, [])
        changed = False
        for a in items:
            if a["code"] == code:
                a["status"] = status
                changed = True
        if changed:
            _json_save(APPOINTMENTS_PATH, items)
        return changed


# ===========================================================================
# API CÔNG KHAI — DEVICE TOKENS
# ===========================================================================
def get_tokens(session_id):
    if USE_DB:
        init_schema()
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT token FROM device_tokens WHERE session = %s",
                        (session_id,))
            return [r[0] for r in cur.fetchall()]
    return _json_load(TOKENS_PATH, {}).get(session_id, [])


def add_token(session_id, token):
    if not token:
        return
    if USE_DB:
        init_schema()
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO device_tokens (session, token) VALUES (%s, %s) "
                "ON CONFLICT (session, token) DO NOTHING",
                (session_id, token),
            )
            conn.commit()
        return
    with _JSON_LOCK:
        data = _json_load(TOKENS_PATH, {})
        tokens = set(data.get(session_id, []))
        tokens.add(token)
        data[session_id] = sorted(tokens)
        _json_save(TOKENS_PATH, data)


def remove_token(token):
    """Xoá 1 token khỏi mọi session (token hết hạn/DeviceNotRegistered thì hết
    hạn ở mọi session, không cần biết session nào)."""
    if not token:
        return
    if USE_DB:
        init_schema()
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM device_tokens WHERE token = %s", (token,))
            conn.commit()
        return
    with _JSON_LOCK:
        data = _json_load(TOKENS_PATH, {})
        changed = False
        for sess_id, tokens in list(data.items()):
            if token in tokens:
                tokens.remove(token)
                changed = True
        if changed:
            _json_save(TOKENS_PATH, data)


# ===========================================================================
# API CÔNG KHAI — DANH MỤC (services / doctors)
# Chỉ dùng khi USE_DB. Khi không có DB, data.py tự dùng dict tĩnh (seed).
# ===========================================================================
def list_services():
    """Trả về dict dạng DEPARTMENTS: {code: {name, desc, keywords:[...]}}.

    Rỗng -> trả {} để data.py fallback sang seed tĩnh.
    """
    if not USE_DB:
        return {}
    init_schema()
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT code, name, descr, keywords FROM services "
                    "ORDER BY sort_order, code")
        rows = cur.fetchall()
    out = {}
    for code, name, descr, keywords in rows:
        if isinstance(keywords, str):
            keywords = json.loads(keywords)
        out[code] = {"name": name, "desc": descr, "keywords": keywords or []}
    return out


def list_doctors():
    """Trả về dict dạng DOCTORS: {service_code: [{id, name}, ...]}."""
    if not USE_DB:
        return {}
    init_schema()
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, service_code, name, phone, email, "
                    "COALESCE(created_at, ''), COALESCE(updated_at, '') "
                    "FROM doctors "
                    "ORDER BY sort_order, id")
        rows = cur.fetchall()
    out = {}
    for row in rows:
        doctor = _row_to_doctor(row)
        out.setdefault(doctor["service_code"], []).append(doctor)
    return out


def list_safety_patterns():
    """Trả về dict {kind: [pattern, ...]} của guardrail. Rỗng -> {} để safety.py
    fallback sang seed tĩnh trong code (đảm bảo guardrail không bao giờ trống)."""
    if not USE_DB:
        return {}
    init_schema()
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT kind, pattern FROM safety_patterns ORDER BY kind, pattern")
        rows = cur.fetchall()
    out = {}
    for kind, pattern in rows:
        out.setdefault(kind, []).append(pattern)
    return out


def seed_safety_patterns(patterns_by_kind):
    """Nạp bộ pattern an toàn lên DB (idempotent: trùng (kind, pattern) -> bỏ qua).

    Trả về số dòng thêm mới.
    """
    if not USE_DB:
        return 0
    init_schema()
    n = 0
    with _connect() as conn, conn.cursor() as cur:
        for kind, patterns in patterns_by_kind.items():
            for p in patterns:
                cur.execute(
                    "INSERT INTO safety_patterns (kind, pattern) VALUES (%s, %s) "
                    "ON CONFLICT (kind, pattern) DO NOTHING",
                    (kind, p),
                )
                n += cur.rowcount
        conn.commit()
    return n


def seed_catalog(departments, doctors):
    """Nạp danh mục dịch vụ + nha sĩ lên DB (idempotent: trùng code/id -> bỏ qua).

    Trả về (số dịch vụ thêm, số nha sĩ thêm).
    """
    if not USE_DB:
        return (0, 0)
    init_schema()
    n_sv = n_dr = 0
    with _connect() as conn, conn.cursor() as cur:
        for i, (code, d) in enumerate(departments.items()):
            cur.execute(
                "INSERT INTO services (code, name, descr, keywords, sort_order) "
                "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (code) DO NOTHING",
                (code, d["name"], d.get("desc", ""), json.dumps(d.get("keywords", [])), i),
            )
            n_sv += cur.rowcount
        for scode, docs in doctors.items():
            for j, doc in enumerate(docs):
                cur.execute(
                    "INSERT INTO doctors (id, service_code, name, sort_order) "
                    "VALUES (%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",
                    (doc["id"], scode, doc["name"], j),
                )
                n_dr += cur.rowcount
        conn.commit()
    return (n_sv, n_dr)


def sync_catalog(departments, doctors):
    """ĐỒNG BỘ danh mục từ code (seed) -> DB, GHI ĐÈ bản trên DB.

    Khác seed_catalog (chỉ thêm mới): hàm này cập nhật cả name/desc/keywords cho
    dịch vụ đã có. Dùng khi bạn sửa danh mục trong data.py và muốn đẩy lên Supabase.
    ⚠️ Sẽ ghi đè mọi chỉnh sửa thực hiện trực tiếp trên Supabase.
    """
    if not USE_DB:
        return (0, 0)
    init_schema()
    with _connect() as conn, conn.cursor() as cur:
        for i, (code, d) in enumerate(departments.items()):
            cur.execute(
                "INSERT INTO services (code, name, descr, keywords, sort_order) "
                "VALUES (%s,%s,%s,%s,%s) "
                "ON CONFLICT (code) DO UPDATE SET "
                "  name = EXCLUDED.name, descr = EXCLUDED.descr, "
                "  keywords = EXCLUDED.keywords, sort_order = EXCLUDED.sort_order",
                (code, d["name"], d.get("desc", ""), json.dumps(d.get("keywords", [])), i),
            )
        for scode, docs in doctors.items():
            for j, doc in enumerate(docs):
                cur.execute(
                    "INSERT INTO doctors (id, service_code, name, sort_order) "
                    "VALUES (%s,%s,%s,%s) "
                    "ON CONFLICT (id) DO UPDATE SET "
                    "  service_code = EXCLUDED.service_code, name = EXCLUDED.name, "
                    "  sort_order = EXCLUDED.sort_order",
                    (doc["id"], scode, doc["name"], j),
                )
        conn.commit()
    return (len(departments), sum(len(v) for v in doctors.values()))


def _now_iso():
    return datetime.utcnow().isoformat(timespec="seconds")


def _seed_doctor_records():
    from .catalog import DEPARTMENTS, DOCTORS

    out = []
    now = _now_iso()
    for dept_code, docs in DOCTORS.items():
        for d in docs:
            out.append({
                "id": d["id"],
                "service_code": dept_code,
                "name": d["name"],
                "phone": "",
                "email": "",
                "created_at": now,
                "updated_at": now,
                "dept_name": DEPARTMENTS.get(dept_code, {}).get("name", dept_code),
            })
    return out


def _json_doctor_items():
    items = _json_load(DOCTORS_PATH, [])
    if items:
        return items
    items = _seed_doctor_records()
    _json_save(DOCTORS_PATH, items)
    return items


def _json_patient_items():
    return _json_load(PATIENTS_PATH, [])


def list_admin_doctors(search=None):
    """Danh sách bác sĩ cho màn quản trị."""
    if USE_DB:
        init_schema()
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT d.id, d.service_code, d.name, d.phone, d.email, "
                "COALESCE(d.created_at, ''), COALESCE(d.updated_at, ''), "
                "COALESCE(s.name, d.service_code) "
                "FROM doctors d "
                "LEFT JOIN services s ON s.code = d.service_code "
                "ORDER BY d.sort_order, d.id"
            )
            rows = cur.fetchall()
        doctors = []
        for row in rows:
            doctor = _row_to_doctor(row[:7])
            doctor["dept_name"] = row[7]
            doctors.append(doctor)
    else:
        from .catalog import DEPARTMENTS

        doctors = []
        for d in _json_doctor_items():
            doctor = dict(d)
            doctor["dept_name"] = DEPARTMENTS.get(
                doctor.get("service_code", ""), {}
            ).get("name", doctor.get("service_code", ""))
            doctors.append(doctor)

    if search:
        q = search.strip().lower()
        doctors = [
            d for d in doctors
            if q in (d.get("id") or "").lower()
            or q in (d.get("name") or "").lower()
            or q in (d.get("phone") or "").lower()
            or q in (d.get("email") or "").lower()
        ]
    return doctors


def create_admin_doctor(doctor_id, name, service_code, phone=None, email=None):
    """Tạo mới bác sĩ."""
    did = (doctor_id or "").strip()
    dname = (name or "").strip()
    scode = (service_code or "").strip()
    if not did or not dname or not scode:
        raise ValueError("doctor_id, name, service_code là bắt buộc")

    if USE_DB:
        init_schema()
        now = _now_iso()
        try:
            with _connect() as conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO services (code, name, descr, keywords, sort_order) "
                    "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (code) DO NOTHING",
                    (scode, scode, "", "[]", 9999),
                )
                cur.execute(
                    "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM doctors "
                    "WHERE service_code = %s",
                    (scode,),
                )
                sort_order = cur.fetchone()[0]
                cur.execute(
                    "INSERT INTO doctors "
                    "(id, service_code, name, sort_order, phone, email, created_at, updated_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (did, scode, dname, sort_order, phone or None, email or None, now, now),
                )
                conn.commit()
        except Exception as exc:
            if "duplicate key" in str(exc).lower() or "unique" in str(exc).lower():
                raise ValueError("Mã bác sĩ đã tồn tại")
            raise
        return {
            "id": did,
            "service_code": scode,
            "name": dname,
            "phone": phone or "",
            "email": email or "",
            "created_at": now,
            "updated_at": now,
        }

    with _JSON_LOCK:
        items = _json_doctor_items()
        if any((d.get("id") or "") == did for d in items):
            raise ValueError("Mã bác sĩ đã tồn tại")
        now = _now_iso()
        doctor = {
            "id": did,
            "service_code": scode,
            "name": dname,
            "phone": phone or "",
            "email": email or "",
            "created_at": now,
            "updated_at": now,
        }
        items.append(doctor)
        _json_save(DOCTORS_PATH, items)
        return doctor


def update_admin_doctor(doctor_id, name=None, service_code=None, phone=None, email=None):
    """Cập nhật thông tin bác sĩ theo id."""
    did = (doctor_id or "").strip()
    if not did:
        raise ValueError("doctor_id là bắt buộc")

    if USE_DB:
        init_schema()
        now = _now_iso()
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, service_code, name, phone, email, "
                "COALESCE(created_at, ''), COALESCE(updated_at, '') "
                "FROM doctors WHERE id = %s",
                (did,),
            )
            row = cur.fetchone()
            if not row:
                return None
            current = _row_to_doctor(row)
            new_name = (name or current["name"]).strip()
            new_service_code = (service_code or current["service_code"]).strip()
            new_phone = phone if phone is not None else current.get("phone")
            new_email = email if email is not None else current.get("email")
            cur.execute(
                "UPDATE doctors SET service_code = %s, name = %s, phone = %s, "
                "email = %s, updated_at = %s WHERE id = %s",
                (new_service_code, new_name, new_phone or None, new_email or None, now, did),
            )
            cur.execute(
                "UPDATE appointments SET doctor = %s, department_code = %s "
                "WHERE doctor_id = %s",
                (new_name, new_service_code, did),
            )
            conn.commit()
        current.update({
            "service_code": new_service_code,
            "name": new_name,
            "phone": new_phone or "",
            "email": new_email or "",
            "updated_at": now,
        })
        return current

    with _JSON_LOCK:
        items = _json_doctor_items()
        target = None
        for d in items:
            if (d.get("id") or "") == did:
                target = d
                break
        if not target:
            return None
        if name is not None:
            target["name"] = name.strip()
        if service_code is not None:
            target["service_code"] = service_code.strip()
        if phone is not None:
            target["phone"] = phone.strip()
        if email is not None:
            target["email"] = email.strip()
        target["updated_at"] = _now_iso()
        _json_save(DOCTORS_PATH, items)

        appts = _json_load(APPOINTMENTS_PATH, [])
        changed = False
        for a in appts:
            if a.get("doctor_id") == did:
                a["doctor"] = target.get("name")
                if target.get("service_code"):
                    a["department_code"] = target.get("service_code")
                changed = True
        if changed:
            _json_save(APPOINTMENTS_PATH, appts)
        return dict(target)


def list_patients(search=None):
    """Danh sách hồ sơ bệnh nhân cho admin."""
    if USE_DB:
        init_schema()
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, phone, email, address, notes, created_at, updated_at "
                "FROM patients ORDER BY updated_at DESC, created_at DESC"
            )
            patients = [_row_to_patient(r) for r in cur.fetchall()]
    else:
        patients = _json_patient_items()

    if search:
        q = search.strip().lower()
        patients = [
            p for p in patients
            if q in (p.get("name") or "").lower()
            or q in (p.get("phone") or "").lower()
            or q in (p.get("email") or "").lower()
        ]
    return patients


def create_patient_profile(name, phone, email=None, address=None, notes=None):
    """Tạo hồ sơ bệnh nhân mới."""
    pname = (name or "").strip()
    pphone = (phone or "").strip()
    if not pname or not pphone:
        raise ValueError("name và phone là bắt buộc")

    patient_id = f"pt_{uuid.uuid4().hex[:10]}"
    now = _now_iso()

    if USE_DB:
        init_schema()
        try:
            with _connect() as conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO patients "
                    "(id, name, phone, email, address, notes, created_at, updated_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (patient_id, pname, pphone, email or None, address or None, notes or None, now, now),
                )
                conn.commit()
        except Exception as exc:
            if "duplicate key" in str(exc).lower() or "unique" in str(exc).lower():
                raise ValueError("Số điện thoại đã tồn tại")
            raise
    else:
        with _JSON_LOCK:
            items = _json_patient_items()
            if any((p.get("phone") or "") == pphone for p in items):
                raise ValueError("Số điện thoại đã tồn tại")
            items.append({
                "id": patient_id,
                "name": pname,
                "phone": pphone,
                "email": email or "",
                "address": address or "",
                "notes": notes or "",
                "created_at": now,
                "updated_at": now,
            })
            _json_save(PATIENTS_PATH, items)

    return {
        "id": patient_id,
        "name": pname,
        "phone": pphone,
        "email": email or "",
        "address": address or "",
        "notes": notes or "",
        "created_at": now,
        "updated_at": now,
    }


def update_patient_profile_admin(patient_id, name=None, phone=None, email=None,
                                 address=None, notes=None):
    """Cập nhật hồ sơ bệnh nhân theo id."""
    pid = (patient_id or "").strip()
    if not pid:
        raise ValueError("patient_id là bắt buộc")

    if USE_DB:
        init_schema()
        now = _now_iso()
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, phone, email, address, notes, created_at, updated_at "
                "FROM patients WHERE id = %s",
                (pid,),
            )
            row = cur.fetchone()
            if not row:
                return None
            current = _row_to_patient(row)
            new_name = (name if name is not None else current["name"]).strip()
            new_phone = (phone if phone is not None else current["phone"]).strip()
            new_email = (email if email is not None else current.get("email") or "").strip()
            new_address = (address if address is not None else current.get("address") or "").strip()
            new_notes = (notes if notes is not None else current.get("notes") or "").strip()
            try:
                cur.execute(
                    "UPDATE patients SET name = %s, phone = %s, email = %s, "
                    "address = %s, notes = %s, updated_at = %s WHERE id = %s",
                    (new_name, new_phone, new_email or None, new_address or None,
                     new_notes or None, now, pid),
                )
            except Exception as exc:
                if "duplicate key" in str(exc).lower() or "unique" in str(exc).lower():
                    raise ValueError("Số điện thoại đã tồn tại")
                raise

            old_phone = (current.get("phone") or "").strip()
            if old_phone:
                cur.execute(
                    "UPDATE appointments SET patient_name = %s, patient_phone = %s "
                    "WHERE patient_phone = %s",
                    (new_name, new_phone, old_phone),
                )
            conn.commit()
        current.update({
            "name": new_name,
            "phone": new_phone,
            "email": new_email,
            "address": new_address,
            "notes": new_notes,
            "updated_at": now,
        })
        return current

    with _JSON_LOCK:
        items = _json_patient_items()
        target = None
        for p in items:
            if (p.get("id") or "") == pid:
                target = p
                break
        if not target:
            return None

        new_name = (name if name is not None else target.get("name") or "").strip()
        new_phone = (phone if phone is not None else target.get("phone") or "").strip()
        if any((p.get("phone") or "") == new_phone and p.get("id") != pid for p in items):
            raise ValueError("Số điện thoại đã tồn tại")

        old_phone = (target.get("phone") or "").strip()
        target["name"] = new_name
        target["phone"] = new_phone
        if email is not None:
            target["email"] = email.strip()
        if address is not None:
            target["address"] = address.strip()
        if notes is not None:
            target["notes"] = notes.strip()
        target["updated_at"] = _now_iso()
        _json_save(PATIENTS_PATH, items)

        appts = _json_load(APPOINTMENTS_PATH, [])
        changed = False
        if old_phone:
            for a in appts:
                if a.get("patient_phone") == old_phone:
                    a["patient_name"] = new_name
                    a["patient_phone"] = new_phone
                    changed = True
        if changed:
            _json_save(APPOINTMENTS_PATH, appts)

        return dict(target)


# ===========================================================================
# API CÔNG KHAI — USERS (authentication)
# ===========================================================================
class UserNotFoundError(Exception):
    """User không tồn tại."""
    pass


class DuplicateUsernameError(Exception):
    """Username đã được sử dụng."""
    pass


def create_user(user_id, username, password_hash, role, email=None, doctor_id=None):
    """Tạo user mới (idempotent nếu đã tồn tại).

    Trả về True nếu tạo thành công, False nếu username đã tồn tại.

    Raises:
        UserStoreUnavailableError: không có DATABASE_URL.
    """
    if not USE_DB:
        raise UserStoreUnavailableError(
            "User accounts cần DATABASE_URL (Postgres) — không hỗ trợ JSON-file mode."
        )
    init_schema()
    try:
        with _connect() as conn, conn.cursor() as cur:
            from datetime import datetime
            now = datetime.utcnow().isoformat()
            cur.execute(
                "INSERT INTO users "
                "(id, username, password_hash, role, email, phone, address, doctor_id, patient_id, created_at, updated_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (user_id, username, password_hash, role, email, phone, address, doctor_id, patient_id, now, now),
            )
            conn.commit()
        return True
    except Exception as e:
        if "duplicate key" in str(e).lower() or "unique" in str(e).lower():
            raise DuplicateUsernameError(username)
        raise


def get_user_by_username(username):
    """Lấy user theo username. Trả về dict hoặc None.

    Raises:
        UserStoreUnavailableError: không có DATABASE_URL.
    """
    if not USE_DB:
        raise UserStoreUnavailableError(
            "User accounts cần DATABASE_URL (Postgres) — không hỗ trợ JSON-file mode."
        )
    init_schema()
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, username, password_hash, role, email, phone, address, doctor_id, patient_id, created_at, updated_at "
            "FROM users WHERE username = %s",
            (username,),
        )
        row = cur.fetchone()
        if row:
            return {
                "id": row[0],
                "username": row[1],
                "password_hash": row[2],
                "role": row[3],
                "email": row[4],
                "phone": row[5],
                "address": row[6],
                "doctor_id": row[7],
                "patient_id": row[8],
                "created_at": row[9],
                "updated_at": row[10],
            }
    return None


def get_user_by_id(user_id):
    """Lấy user theo id. Trả về dict hoặc None.

    Raises:
        UserStoreUnavailableError: không có DATABASE_URL.
    """
    if not USE_DB:
        raise UserStoreUnavailableError(
            "User accounts cần DATABASE_URL (Postgres) — không hỗ trợ JSON-file mode."
        )
    init_schema()
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, username, password_hash, role, email, phone, address, doctor_id, patient_id, created_at, updated_at "
            "FROM users WHERE id = %s",
            (user_id,),
        )
        row = cur.fetchone()
        if row:
            return {
                "id": row[0],
                "username": row[1],
                "password_hash": row[2],
                "role": row[3],
                "email": row[4],
                "phone": row[5],
                "address": row[6],
                "doctor_id": row[7],
                "patient_id": row[8],
                "created_at": row[9],
                "updated_at": row[10],
            }
    return None


def update_user_profile(user_id, email=None, phone=None, address=None):
    """Cập nhật email, phone, address của user. Trả về True nếu thành công."""
    if not USE_DB:
        return False
    init_schema()
    from datetime import datetime
    now = datetime.utcnow().isoformat()
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE users SET email = %s, phone = %s, address = %s, updated_at = %s "
            "WHERE id = %s",
            (email, phone, address, now, user_id),
        )
        updated = cur.rowcount
        conn.commit()
    return updated > 0


def get_user_by_doctor_id(doctor_id):
    """Lấy user theo doctor_id. Trả về dict hoặc None."""
    if not USE_DB:
        return None
    init_schema()
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, username, password_hash, role, email, phone, address, doctor_id, patient_id, created_at, updated_at "
            "FROM users WHERE doctor_id = %s",
            (doctor_id,),
        )
        row = cur.fetchone()
        if row:
            return {
                "id": row[0], "username": row[1], "password_hash": row[2],
                "role": row[3], "email": row[4], "phone": row[5],
                "address": row[6], "doctor_id": row[7], "patient_id": row[8],
                "created_at": row[9], "updated_at": row[10],
            }
    return None


def get_user_by_patient_id(patient_id):
    """Lấy user theo patient_id. Trả về dict hoặc None."""
    if not USE_DB:
        return None
    init_schema()
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, username, password_hash, role, email, phone, address, doctor_id, patient_id, created_at, updated_at "
            "FROM users WHERE patient_id = %s",
            (patient_id,),
        )
        row = cur.fetchone()
        if row:
            return {
                "id": row[0], "username": row[1], "password_hash": row[2],
                "role": row[3], "email": row[4], "phone": row[5],
                "address": row[6], "doctor_id": row[7], "patient_id": row[8],
                "created_at": row[9], "updated_at": row[10],
            }
    return None


def link_user_patient(user_id, patient_id):
    """Liên kết user với hồ sơ bệnh nhân."""
    if not USE_DB:
        return
    init_schema()
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("UPDATE users SET patient_id = %s WHERE id = %s", (patient_id, user_id))
        conn.commit()


def get_doctor_detail(doctor_id):
    """Chi tiết đầy đủ của một bác sĩ: thông tin bác sĩ + tài khoản + khoa."""
    from .catalog import DEPARTMENTS

    did = (doctor_id or "").strip()
    if not did:
        return None

    doctor = None
    if USE_DB:
        init_schema()
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT d.id, d.service_code, d.name, d.phone, d.email, "
                "COALESCE(d.created_at,''), COALESCE(d.updated_at,''), "
                "COALESCE(s.name, d.service_code) "
                "FROM doctors d "
                "LEFT JOIN services s ON s.code = d.service_code "
                "WHERE d.id = %s",
                (did,),
            )
            row = cur.fetchone()
            if row:
                doctor = _row_to_doctor(row[:7])
                doctor["dept_name"] = row[7]
    else:
        for d in _json_doctor_items():
            if d.get("id") == did:
                doctor = dict(d)
                doctor["dept_name"] = DEPARTMENTS.get(
                    doctor.get("service_code", ""), {}
                ).get("name", doctor.get("service_code", ""))
                break

    if not doctor:
        return None

    # Gộp thông tin tài khoản user
    user = get_user_by_doctor_id(did)
    if user:
        doctor["user"] = {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "created_at": str(user.get("created_at") or ""),
            "updated_at": str(user.get("updated_at") or ""),
        }

    # Lịch hẹn gần đây (10 lịch mới nhất)
    all_appts = list_appointments()
    doctor_appts = [a for a in all_appts if a.get("doctor_id") == did]
    doctor_appts.sort(key=lambda a: (a.get("date", ""), a.get("time", "")), reverse=True)
    doctor["recent_appointments"] = doctor_appts[:10]
    doctor["total_appointments"] = len(doctor_appts)
    doctor["confirmed_appointments"] = sum(1 for a in doctor_appts if a.get("status") == "confirmed")

    return doctor


def get_patient_detail(patient_id):
    """Chi tiết đầy đủ của một bệnh nhân: thông tin hồ sơ + tài khoản + lịch sử lịch hẹn."""
    pid = (patient_id or "").strip()
    if not pid:
        return None

    patient = None
    if USE_DB:
        init_schema()
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, phone, email, address, notes, created_at, updated_at "
                "FROM patients WHERE id = %s",
                (pid,),
            )
            row = cur.fetchone()
            if row:
                patient = _row_to_patient(row)
    else:
        for p in _json_patient_items():
            if p.get("id") == pid:
                patient = dict(p)
                break

    if not patient:
        return None

    # Gộp thông tin tài khoản user
    user = get_user_by_patient_id(pid)
    if user:
        patient["user"] = {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "created_at": str(user.get("created_at") or ""),
            "updated_at": str(user.get("updated_at") or ""),
        }

    # Lịch sử lịch hẹn theo SĐT
    all_appts = list_appointments()
    phone = patient.get("phone", "")
    patient_appts = [a for a in all_appts if a.get("patient_phone") == phone]
    patient_appts.sort(key=lambda a: (a.get("date", ""), a.get("time", "")), reverse=True)
    patient["appointment_history"] = patient_appts[:20]
    patient["total_appointments"] = len(patient_appts)
    patient["confirmed_appointments"] = sum(1 for a in patient_appts if a.get("status") == "confirmed")

    return patient
