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

from .paths import (  # noqa: F401  (re-export cho code cũ)
    APPOINTMENTS_PATH,
    DOCTORS_PATH,
    HANDOFF_PATH,
    PATIENT_PREFS_PATH,
    PATIENTS_PATH,
    REC_LOG_PATH,
    TOKENS_PATH,
    TREATMENT_HISTORY_PATH,
)

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
-- Tài khoản đã đặt lịch này (NULL = khách chưa đăng nhập). Đóng dấu từ JWT lúc
-- đặt, client không truyền được. Đây là câu trả lời DUY NHẤT đáng tin cho "lịch
-- này của ai": SĐT trên lịch hẹn là số người dùng TỰ GÕ, và đặt hộ bằng số của
-- người khác là hợp lệ — suy chủ nhân từ SĐT làm ca khám chui vào bệnh án người
-- khác. Không FK sang users(id) để xoá tài khoản không kéo theo mất lịch hẹn.
ALTER TABLE appointments ADD COLUMN IF NOT EXISTS booked_by_user_id TEXT;
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

-- Thuộc tính LÂM SÀNG của bệnh nhân, dùng làm đầu vào cho engine gợi ý:
-- `birth_year` -> feature age_group (AC SMMG-65 yêu cầu gợi ý theo độ tuổi),
-- `allergies`  -> feature allergy_flags.
-- Đặt trên `patients` chứ không phải `users`: một bệnh nhân là một hồ sơ lâm sàng,
-- có thể chưa có tài khoản đăng nhập nào.
ALTER TABLE patients ADD COLUMN IF NOT EXISTS birth_year SMALLINT;
ALTER TABLE patients ADD COLUMN IF NOT EXISTS allergies  JSONB;

-- ===========================================================================
-- GỢI Ý DỊCH VỤ (REC-01/02) — 3 bảng theo ER-S2-Recommendation (Confluence 8192034).
-- Sai lệch có chủ đích so với ER: khoá dùng TEXT (patients.id / service_code /
-- doctor_id) thay vì UUID — xem §3 (D3) docs/patient-recommendation-design.md.
-- ===========================================================================
CREATE TABLE IF NOT EXISTS treatment_history (
    history_id        TEXT PRIMARY KEY,
    appointment_code  TEXT UNIQUE REFERENCES appointments(code),
    patient_id        TEXT,
    patient_phone     TEXT,
    service_code      TEXT NOT NULL,
    doctor_id         TEXT,
    treatment_date    TEXT NOT NULL,
    outcome           TEXT NOT NULL DEFAULT 'success',
    followup_required BOOLEAN NOT NULL DEFAULT FALSE,
    followup_due_date TEXT,
    patient_rating    SMALLINT,
    created_at        TEXT NOT NULL
);
-- KHÔNG đặt FK trên patient_id: lịch sử được backfill từ các lịch hẹn đặt qua
-- chatbot, mà những lịch đó chưa gắn với hồ sơ bệnh nhân nào.
CREATE INDEX IF NOT EXISTS idx_th_patient_date
    ON treatment_history (patient_id, treatment_date DESC);
CREATE INDEX IF NOT EXISTS idx_th_phone_date
    ON treatment_history (patient_phone, treatment_date DESC);

CREATE TABLE IF NOT EXISTS recommendation_log (
    rec_log_id       TEXT PRIMARY KEY,
    patient_id       TEXT NOT NULL,
    generated_at     TEXT NOT NULL,
    trigger          TEXT NOT NULL,
    model_version    TEXT NOT NULL,
    is_cold_start    BOOLEAN NOT NULL DEFAULT FALSE,
    recommendations  JSONB NOT NULL DEFAULT '[]'::jsonb,
    latency_ms       INT,
    patient_action   TEXT,
    patient_acted_service_code TEXT,
    patient_acted_rank SMALLINT,
    dentist_feedback JSONB,
    dentist_acted_at TEXT,
    feature_snapshot JSONB
);
CREATE INDEX IF NOT EXISTS idx_reclog_patient_generated
    ON recommendation_log (patient_id, generated_at DESC);

CREATE TABLE IF NOT EXISTS patient_preference (
    patient_id              TEXT PRIMARY KEY,
    dismissed_service_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    preferred_doctor_id     TEXT,
    service_ratings         JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS handoff_requests (
    code            TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL,
    reason          TEXT NOT NULL,   -- 'patient_request' | 'bot_stuck'
    status          TEXT NOT NULL,   -- 'new' | 'handled'
    created_at      TEXT NOT NULL,
    within_hours    BOOLEAN NOT NULL DEFAULT TRUE,
    callback_at     TEXT,            -- mốc hẹn gọi lại khi tạo ngoài giờ làm việc
    patient_name    TEXT,
    patient_phone   TEXT,
    last_message    TEXT,
    transcript      JSONB NOT NULL DEFAULT '[]'::jsonb,
    handled_at      TEXT,
    handled_by      TEXT
);
CREATE INDEX IF NOT EXISTS idx_handoff_status_created
    ON handoff_requests (status, created_at DESC);
"""

# Tách riêng khỏi SCHEMA_SQL vì KHÔNG idempotent theo kiểu `IF NOT EXISTS`:
# constraint cũ phải DROP rồi ADD lại để nhận thêm role 'patient' (bệnh nhân đăng
# nhập vào portal gợi ý). Chạy trong try/except riêng — fail thì app vẫn chạy, chỉ
# mất khả năng TẠO tài khoản role='patient'.
ROLE_CHECK_SQL = """
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
ALTER TABLE users ADD  CONSTRAINT users_role_check
    CHECK (role IN ('admin', 'doctor', 'guest', 'patient'));
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
              "status", "reminders_sent", "booked_by_user_id"]
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
                cur.execute(ROLE_CHECK_SQL)
                conn.commit()
            except Exception as exc:  # noqa: BLE001 - phải bắt mọi lỗi DB ở đây
                conn.rollback()
                print(
                    "[storage] CẢNH BÁO: không cập nhật được CHECK constraint "
                    f"users.role để nhận role 'patient'. Lỗi: {exc}. App vẫn chạy "
                    "nhưng KHÔNG tạo được tài khoản bệnh nhân."
                )
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
                " doctor, doctor_id, date, time, created_at, status, reminders_sent, "
                " booked_by_user_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (appt["code"], appt.get("session"), appt.get("patient_name"),
                 appt.get("patient_phone"), appt.get("department"),
                 appt.get("department_code"), appt.get("doctor"),
                 appt.get("doctor_id"), appt.get("date"), appt.get("time"),
                 appt.get("created_at"), appt.get("status"),
                 json.dumps(appt["reminders_sent"]), appt.get("booked_by_user_id")),
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


class UserStoreUnavailableError(Exception):
    """User store cần Postgres (DATABASE_URL) — không có JSON-mode fallback.

    (Khôi phục: class này bị thiếu định nghĩa trong khi vẫn được `raise` ở 3 hàm
    đọc/ghi user -> mọi đường JSON mode ném NameError thay vì lỗi có nghĩa.)
    """


class DuplicateUsernameError(Exception):
    """Username đã được sử dụng."""
    pass


def create_user(user_id, username, password_hash, role, email=None, doctor_id=None,
                phone=None, address=None, patient_id=None):
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
    """Lấy user theo doctor_id. Trả về dict hoặc None.

    Raises:
        UserStoreUnavailableError: không có DATABASE_URL — GIỐNG 3 hàm user còn
        lại. Trả None ở JSON mode sẽ khiến `/api/register` tưởng doctor_id còn
        trống và đi tiếp, thay vì báo lỗi cấu hình (xem commit 54b0e0e "fail loud
        on storage unavailable").
    """
    if not USE_DB:
        raise UserStoreUnavailableError(
            "User accounts cần DATABASE_URL (Postgres) — không hỗ trợ JSON-file mode."
        )
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


def get_user_by_phone(phone):
    """Tài khoản đang dùng SĐT này (role bất kỳ). None nếu chưa ai dùng.

    SĐT là KHOÁ ĐỊNH DANH của lịch sử điều trị: `list_treatments()` gộp theo
    (patient_id OR patient_phone), nên hai tài khoản mang cùng một SĐT nghĩa là hai
    người đăng nhập cùng đọc được một lịch sử điều trị. Cột `users.phone` không có
    ràng buộc UNIQUE (SĐT có thể trống, và tài khoản nha sĩ/admin dùng SĐT nội bộ),
    nên chỗ chặn phải nằm ở luồng đăng ký — đây là hàm tra cho nó.
    """
    p = (phone or "").strip()
    if not p or not USE_DB:
        return None
    init_schema()
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, username, password_hash, role, email, phone, address, doctor_id, patient_id, created_at, updated_at "
            "FROM users WHERE phone = %s ORDER BY created_at LIMIT 1",
            (p,),
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
# ===========================================================================
# API CÔNG KHAI — LỊCH SỬ ĐIỀU TRỊ (treatment_history)
#
# Khác `users`: các bảng gợi ý CÓ JSON-mode fallback, vì `eval/` phải chạy được
# offline (không DATABASE_URL) để chấm điểm engine — xem §14 doc thiết kế.
# ===========================================================================
_TH_COLS = ["history_id", "appointment_code", "patient_id", "patient_phone",
            "service_code", "doctor_id", "treatment_date", "outcome",
            "followup_required", "followup_due_date", "patient_rating", "created_at"]


def _row_to_treatment(row):
    rec = dict(zip(_TH_COLS, row))
    rec["followup_required"] = bool(rec.get("followup_required"))
    return rec


def add_treatment(rec):
    """Ghi 1 lượt điều trị đã hoàn tất. Trả True nếu thêm mới, False nếu đã có.

    `ON CONFLICT DO NOTHING` KHÔNG chỉ định cột đích -> bắt cả trùng `history_id`
    (PK) lẫn trùng `appointment_code` (UNIQUE). Cần cả hai: backfill dedupe theo
    mã lịch hẹn, còn dữ liệu seed demo không gắn với lịch hẹn nào
    (`appointment_code = NULL`, mà nhiều NULL thì Postgres coi là không trùng) nên
    chỉ dedupe được theo `history_id`.
    """
    if USE_DB:
        init_schema()
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO treatment_history ({', '.join(_TH_COLS)}) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT DO NOTHING",
                tuple(rec.get(c) for c in _TH_COLS),
            )
            added = cur.rowcount
            conn.commit()
        return added > 0
    with _JSON_LOCK:
        items = _json_load(TREATMENT_HISTORY_PATH, [])
        code = rec.get("appointment_code")
        hid = rec.get("history_id")
        if any(r.get("history_id") == hid for r in items):
            return False
        if code and any(r.get("appointment_code") == code for r in items):
            return False
        items.append({c: rec.get(c) for c in _TH_COLS})
        _json_save(TREATMENT_HISTORY_PATH, items)
        return True


def list_treatments(patient_id=None, patient_phone=None, limit=None):
    """Lịch sử điều trị, MỚI NHẤT TRƯỚC.

    Lọc theo `patient_id` HOẶC `patient_phone` (OR, không phải AND): một bệnh nhân
    có thể có lịch đặt trước khi tạo tài khoản (chỉ có SĐT) lẫn sau khi có tài
    khoản (có patient_id) — cả hai đều là lịch sử của cùng người.
    Không truyền tiêu chí nào -> trả toàn bộ (dùng cho bảng đồng xuất hiện).
    """
    if USE_DB:
        init_schema()
        where, params = [], []
        if patient_id:
            where.append("patient_id = %s")
            params.append(patient_id)
        if patient_phone:
            where.append("patient_phone = %s")
            params.append(patient_phone)
        sql = f"SELECT {', '.join(_TH_COLS)} FROM treatment_history"
        if where:
            sql += " WHERE " + " OR ".join(where)
        sql += " ORDER BY treatment_date DESC, created_at DESC"
        if limit:
            sql += " LIMIT %s"
            params.append(int(limit))
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            return [_row_to_treatment(r) for r in cur.fetchall()]
    items = _json_load(TREATMENT_HISTORY_PATH, [])
    if patient_id or patient_phone:
        items = [r for r in items
                 if (patient_id and r.get("patient_id") == patient_id)
                 or (patient_phone and r.get("patient_phone") == patient_phone)]
    items.sort(key=lambda r: (r.get("treatment_date") or "",
                              r.get("created_at") or ""), reverse=True)
    return items[:int(limit)] if limit else items


# ===========================================================================
# API CÔNG KHAI — LOG GỢI Ý (recommendation_log)
# Append-only: mỗi lần engine sinh gợi ý ghi 1 dòng; hành động của bệnh nhân
# được cập nhật sau vào đúng dòng đó (SEQ 5.4 + bước 7).
# ===========================================================================
_RECLOG_COLS = ["rec_log_id", "patient_id", "generated_at", "trigger",
                "model_version", "is_cold_start", "recommendations", "latency_ms",
                "patient_action", "patient_acted_service_code", "patient_acted_rank",
                "dentist_feedback", "dentist_acted_at", "feature_snapshot"]

# JSON mode: chặn file phình vô hạn (Postgres thì giữ đủ để làm analytics).
_RECLOG_JSON_MAX = 2000

_JSONB_RECLOG_FIELDS = ("recommendations", "dentist_feedback", "feature_snapshot")


def _row_to_rec_log(row):
    entry = dict(zip(_RECLOG_COLS, row))
    for field in _JSONB_RECLOG_FIELDS:
        val = entry.get(field)
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except json.JSONDecodeError:
                val = None
        entry[field] = val
    entry["recommendations"] = entry.get("recommendations") or []
    entry["is_cold_start"] = bool(entry.get("is_cold_start"))
    return entry


def add_rec_log(entry):
    """Ghi 1 dòng log gợi ý. Trả về rec_log_id."""
    if USE_DB:
        init_schema()
        values = []
        for col in _RECLOG_COLS:
            val = entry.get(col)
            if col in _JSONB_RECLOG_FIELDS and val is not None:
                val = json.dumps(val)
            values.append(val)
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO recommendation_log ({', '.join(_RECLOG_COLS)}) "
                "VALUES (" + ",".join(["%s"] * len(_RECLOG_COLS)) + ")",
                tuple(values),
            )
            conn.commit()
        return entry.get("rec_log_id")
    with _JSON_LOCK:
        items = _json_load(REC_LOG_PATH, [])
        items.append({c: entry.get(c) for c in _RECLOG_COLS})
        _json_save(REC_LOG_PATH, items[-_RECLOG_JSON_MAX:])
    return entry.get("rec_log_id")


def get_rec_log(rec_log_id):
    """Đọc 1 dòng log theo id. Trả dict hoặc None."""
    if USE_DB:
        init_schema()
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT {', '.join(_RECLOG_COLS)} FROM recommendation_log "
                "WHERE rec_log_id = %s", (rec_log_id,))
            row = cur.fetchone()
            return _row_to_rec_log(row) if row else None
    for entry in _json_load(REC_LOG_PATH, []):
        if entry.get("rec_log_id") == rec_log_id:
            return entry
    return None


def set_rec_log_action(rec_log_id, action, service_code=None, rank=None):
    """Ghi hành động của bệnh nhân lên dòng log đã có. Trả True nếu có cập nhật.

    CHỈ ghi khi dòng đó chưa có hành động: một lượt gợi ý có đúng một hành động
    quyết định, và người dùng bấm 2 lần (hoặc 2 tab) không được ghi đè 'book'
    thành 'view_detail' — thứ tự tới của request không đảm bảo.
    """
    if USE_DB:
        init_schema()
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE recommendation_log SET patient_action = %s, "
                "patient_acted_service_code = %s, patient_acted_rank = %s "
                "WHERE rec_log_id = %s AND patient_action IS NULL",
                (action, service_code, rank, rec_log_id),
            )
            updated = cur.rowcount
            conn.commit()
        return updated > 0
    with _JSON_LOCK:
        items = _json_load(REC_LOG_PATH, [])
        for entry in items:
            if entry.get("rec_log_id") == rec_log_id and not entry.get("patient_action"):
                entry["patient_action"] = action
                entry["patient_acted_service_code"] = service_code
                entry["patient_acted_rank"] = rank
                _json_save(REC_LOG_PATH, items)
                return True
    return False


# ===========================================================================
# API CÔNG KHAI — SỞ THÍCH BỆNH NHÂN (patient_preference)
# ===========================================================================
def get_patient_preference(patient_id):
    """Sở thích của 1 bệnh nhân. Luôn trả dict (rỗng nếu chưa có bản ghi)."""
    empty = {"patient_id": patient_id, "dismissed_service_codes": [],
             "preferred_doctor_id": None, "service_ratings": {}, "updated_at": None}
    if not patient_id:
        return empty
    if USE_DB:
        init_schema()
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT patient_id, dismissed_service_codes, preferred_doctor_id, "
                "       service_ratings, updated_at "
                "FROM patient_preference WHERE patient_id = %s", (patient_id,))
            row = cur.fetchone()
        if not row:
            return empty
        dismissed, ratings = row[1], row[3]
        if isinstance(dismissed, str):
            dismissed = json.loads(dismissed)
        if isinstance(ratings, str):
            ratings = json.loads(ratings)
        return {"patient_id": row[0], "dismissed_service_codes": dismissed or [],
                "preferred_doctor_id": row[2], "service_ratings": ratings or {},
                "updated_at": row[4]}
    return _json_load(PATIENT_PREFS_PATH, {}).get(patient_id) or empty


def add_dismissed_service(patient_id, service_code):
    """Thêm 1 dịch vụ vào danh sách bệnh nhân đã "Không quan tâm".

    TC-REC-004 yêu cầu dịch vụ bị bỏ qua KHÔNG xuất hiện lại ở lần sau -> lưu
    bền, không phải trạng thái phiên. Trả về danh sách đã cập nhật.
    """
    from datetime import datetime
    now = datetime.now().isoformat(timespec="seconds")
    if not patient_id or not service_code:
        return []
    if USE_DB:
        init_schema()
        with _connect() as conn, conn.cursor() as cur:
            # Gộp không trùng ở phía DB (cùng cách set_reminder_sent làm) -> không
            # cần đọc-sửa-ghi, nên 2 request song song không ghi đè lẫn nhau.
            cur.execute(
                "INSERT INTO patient_preference "
                "(patient_id, dismissed_service_codes, updated_at) "
                "VALUES (%s, %s, %s) "
                "ON CONFLICT (patient_id) DO UPDATE SET "
                "  dismissed_service_codes = ("
                "    SELECT to_jsonb(array(SELECT DISTINCT jsonb_array_elements_text("
                "      patient_preference.dismissed_service_codes || %s::jsonb))) ), "
                "  updated_at = EXCLUDED.updated_at",
                (patient_id, json.dumps([service_code]), now,
                 json.dumps([service_code])),
            )
            conn.commit()
        return get_patient_preference(patient_id)["dismissed_service_codes"]
    with _JSON_LOCK:
        prefs = _json_load(PATIENT_PREFS_PATH, {})
        entry = prefs.setdefault(patient_id, {
            "patient_id": patient_id, "dismissed_service_codes": [],
            "preferred_doctor_id": None, "service_ratings": {}, "updated_at": None})
        if service_code not in entry["dismissed_service_codes"]:
            entry["dismissed_service_codes"].append(service_code)
        entry["updated_at"] = now
        _json_save(PATIENT_PREFS_PATH, prefs)
        return list(entry["dismissed_service_codes"])


def reset_dismissed_services(patient_id):
    """Xoá danh sách đã bỏ qua (link "reset preferences" ở empty state, TC-REC-005)."""
    from datetime import datetime
    now = datetime.now().isoformat(timespec="seconds")
    if not patient_id:
        return False
    if USE_DB:
        init_schema()
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE patient_preference SET dismissed_service_codes = '[]'::jsonb, "
                "updated_at = %s WHERE patient_id = %s", (now, patient_id))
            updated = cur.rowcount
            conn.commit()
        return updated > 0
    with _JSON_LOCK:
        prefs = _json_load(PATIENT_PREFS_PATH, {})
        entry = prefs.get(patient_id)
        if not entry:
            return False
        entry["dismissed_service_codes"] = []
        entry["updated_at"] = now
        _json_save(PATIENT_PREFS_PATH, prefs)
        return True


def get_patient_clinical(patient_id):
    """Thuộc tính lâm sàng của bệnh nhân cho engine gợi ý: tuổi + dị ứng + SĐT.

    Tách khỏi `get_patient_detail()` (hàm đó gộp cả tài khoản + lịch hẹn, dùng cho
    màn admin) vì engine chỉ cần đúng 4 trường và được gọi ở mọi request gợi ý.
    Trả dict rỗng nếu không tìm thấy — engine coi như không biết tuổi, không loại
    oan dịch vụ nào.
    """
    pid = (patient_id or "").strip()
    if not pid:
        return {}
    if USE_DB:
        init_schema()
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, phone, birth_year, allergies FROM patients "
                "WHERE id = %s", (pid,))
            row = cur.fetchone()
        if not row:
            return {}
        allergies = row[4]
        if isinstance(allergies, str):
            try:
                allergies = json.loads(allergies)
            except json.JSONDecodeError:
                allergies = None
        return {"id": row[0], "name": row[1], "phone": row[2],
                "birth_year": row[3], "allergies": allergies or []}
    for p in _json_patient_items():
        if p.get("id") == pid:
            return {"id": p.get("id"), "name": p.get("name"), "phone": p.get("phone"),
                    "birth_year": p.get("birth_year"),
                    "allergies": p.get("allergies") or []}
    return {}


def set_patient_clinical(patient_id, birth_year=None, allergies=None):
    """Cập nhật thuộc tính lâm sàng của hồ sơ bệnh nhân (tuổi, dị ứng).

    Chỉ ghi những trường được truyền (None = giữ nguyên), để không vô tình xoá dữ
    liệu do nha sĩ nhập khi seed/script chỉ muốn đặt một trường.
    """
    pid = (patient_id or "").strip()
    if not pid or (birth_year is None and allergies is None):
        return False
    if USE_DB:
        init_schema()
        sets, params = [], []
        if birth_year is not None:
            sets.append("birth_year = %s")
            params.append(int(birth_year))
        if allergies is not None:
            sets.append("allergies = %s")
            params.append(json.dumps(allergies))
        params.append(pid)
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE patients SET {', '.join(sets)} WHERE id = %s",
                        tuple(params))
            updated = cur.rowcount
            conn.commit()
        return updated > 0
    with _JSON_LOCK:
        items = _json_load(PATIENTS_PATH, [])
        for p in items:
            if p.get("id") == pid:
                if birth_year is not None:
                    p["birth_year"] = int(birth_year)
                if allergies is not None:
                    p["allergies"] = allergies
                _json_save(PATIENTS_PATH, items)
                return True
    return False


# ---------------------------------------------------------------------------
# YÊU CẦU CHUYỂN TIẾP SANG NHÂN VIÊN (CB-05 / SMMG-52)
# ---------------------------------------------------------------------------
_HANDOFF_COLS = ["code", "session_id", "reason", "status", "created_at",
                 "within_hours", "callback_at", "patient_name", "patient_phone",
                 "last_message", "transcript", "handled_at", "handled_by"]

_JSONB_HANDOFF_FIELDS = ("transcript",)

# Bản JSON (chế độ không DB) chỉ giữ ngần này yêu cầu gần nhất — file demo, không
# phải kho lưu trữ. Bản Postgres không cắt.
_HANDOFF_JSON_MAX = 500


def _row_to_handoff(row):
    entry = dict(zip(_HANDOFF_COLS, row))
    for field in _JSONB_HANDOFF_FIELDS:
        if isinstance(entry.get(field), str):
            entry[field] = json.loads(entry[field])
    return entry


def add_handoff(entry):
    """Ghi 1 yêu cầu chuyển tiếp. Trả về `code`."""
    if USE_DB:
        init_schema()
        values = []
        for col in _HANDOFF_COLS:
            val = entry.get(col)
            if col in _JSONB_HANDOFF_FIELDS and val is not None:
                val = json.dumps(val, ensure_ascii=False)
            values.append(val)
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO handoff_requests ({', '.join(_HANDOFF_COLS)}) "
                "VALUES (" + ",".join(["%s"] * len(_HANDOFF_COLS)) + ")",
                tuple(values),
            )
            conn.commit()
        return entry.get("code")
    with _JSON_LOCK:
        items = _json_load(HANDOFF_PATH, [])
        items.append({c: entry.get(c) for c in _HANDOFF_COLS})
        _json_save(HANDOFF_PATH, items[-_HANDOFF_JSON_MAX:])
    return entry.get("code")


def list_handoffs(status=None, limit=200):
    """Danh sách yêu cầu chuyển tiếp, MỚI NHẤT TRƯỚC (nhân viên xử lý từ trên xuống)."""
    if USE_DB:
        init_schema()
        sql = f"SELECT {', '.join(_HANDOFF_COLS)} FROM handoff_requests"
        params = []
        if status:
            sql += " WHERE status = %s"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(int(limit))
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            return [_row_to_handoff(r) for r in cur.fetchall()]
    items = _json_load(HANDOFF_PATH, [])
    if status:
        items = [h for h in items if h.get("status") == status]
    items.sort(key=lambda h: h.get("created_at") or "", reverse=True)
    return items[:limit]


def get_handoff(code):
    """Đọc 1 yêu cầu theo mã. Trả dict hoặc None."""
    if USE_DB:
        init_schema()
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT {', '.join(_HANDOFF_COLS)} FROM handoff_requests "
                "WHERE code = %s", (code,))
            row = cur.fetchone()
            return _row_to_handoff(row) if row else None
    for entry in _json_load(HANDOFF_PATH, []):
        if entry.get("code") == code:
            return entry
    return None


def append_handoff_message(code, role, message, update_last=True):
    """Nối 1 lượt vào transcript của yêu cầu ĐANG CHỜ.

    Bệnh nhân vẫn gõ tiếp sau khi được báo "đang chuyển nhân viên"; những câu đó
    phải nằm trong bản ghi nhân viên đọc, nếu không họ tiếp nhận thiếu ngữ cảnh.
    Yêu cầu đã `handled` thì thôi — cuộc trao đổi đã sang kênh khác.

    `update_last=False` cho các lượt KHÔNG phải nội dung thật của bệnh nhân —
    hiện chỉ có lượt nhập tên/SĐT, vốn được thay bằng nhãn ẩn PII trước khi ghi.
    Không có cờ này thì cột "Câu cuối" ở trang nhân viên hiện "[LIÊN HỆ ĐÃ ẨN]"
    thay vì câu bệnh nhân thật sự nói, tức mất đúng thứ cột đó sinh ra để hiển thị.
    """
    turn = {"role": role, "message": message}
    if USE_DB:
        init_schema()
        sql = ("UPDATE handoff_requests SET transcript = transcript || %s::jsonb"
               + (", last_message = %s" if update_last else "")
               + " WHERE code = %s AND status = 'new'")
        params = [json.dumps([turn], ensure_ascii=False)]
        if update_last:
            params.append(message)
        params.append(code)
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            updated = cur.rowcount
            conn.commit()
        return updated > 0
    with _JSON_LOCK:
        items = _json_load(HANDOFF_PATH, [])
        for h in items:
            if h.get("code") == code and h.get("status") == "new":
                h.setdefault("transcript", []).append(turn)
                if update_last:
                    h["last_message"] = message
                _json_save(HANDOFF_PATH, items)
                return True
    return False


def set_handoff_handled(code, handled_by=None):
    """Đánh dấu đã tiếp nhận. Trả True nếu có cập nhật.

    CHỈ ghi khi còn 'new': hai nhân viên cùng bấm thì người đầu tiên là người
    tiếp nhận, không được ghi đè tên nhau.
    """
    now = _now_iso()
    if USE_DB:
        init_schema()
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE handoff_requests SET status = 'handled', handled_at = %s, "
                "handled_by = %s WHERE code = %s AND status = 'new'",
                (now, handled_by, code))
            updated = cur.rowcount
            conn.commit()
        return updated > 0
    with _JSON_LOCK:
        items = _json_load(HANDOFF_PATH, [])
        for h in items:
            if h.get("code") == code and h.get("status") == "new":
                h["status"] = "handled"
                h["handled_at"] = now
                h["handled_by"] = handled_by
                _json_save(HANDOFF_PATH, items)
                return True
    return False


def set_handoff_contact(code, name, phone):
    """Ghi tên + SĐT liên hệ lên yêu cầu đã tạo (bệnh nhân để lại sau khi chuyển).

    Tên rỗng thì GIỮ NGUYÊN tên cũ thay vì xoá: bệnh nhân có thể chỉ gõ mỗi số
    điện thoại, mà tên có sẵn (từ lịch hẹn trước đó) vẫn hữu ích cho nhân viên.
    """
    if USE_DB:
        init_schema()
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE handoff_requests SET patient_phone = %s, "
                "patient_name = COALESCE(NULLIF(%s, ''), patient_name) "
                "WHERE code = %s",
                (phone, name or "", code))
            updated = cur.rowcount
            conn.commit()
        return updated > 0
    with _JSON_LOCK:
        items = _json_load(HANDOFF_PATH, [])
        for h in items:
            if h.get("code") == code:
                h["patient_phone"] = phone
                if name:
                    h["patient_name"] = name
                _json_save(HANDOFF_PATH, items)
                return True
    return False
