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

# Nạp biến môi trường từ file .env nếu có (tùy chọn — không có python-dotenv vẫn chạy).
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
USE_DB = bool(DATABASE_URL)

_BASE = os.path.dirname(__file__)
APPOINTMENTS_PATH = os.path.join(_BASE, "appointments.json")
TOKENS_PATH = os.path.join(_BASE, "device_tokens.json")

_schema_ready = False


# ===========================================================================
# POSTGRES backend
# ===========================================================================
def _connect():
    import psycopg  # import trễ: chỉ cần khi thực sự dùng DB
    return psycopg.connect(DATABASE_URL)


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
CREATE TABLE IF NOT EXISTS safety_patterns (
    kind    TEXT NOT NULL,   -- 'emergency' | 'diagnosis' | 'handoff'
    pattern TEXT NOT NULL,
    PRIMARY KEY (kind, pattern)
);
"""

# Tách riêng khỏi SCHEMA_SQL: UNIQUE index này có thể FAIL nếu dữ liệu prod đã có
# sẵn >=2 lịch 'confirmed' trùng (date, time) — đúng tình huống mà index này tồn
# tại để ngăn. `IF NOT EXISTS` chỉ chặn chạy lại DDL, KHÔNG chặn lỗi vì dữ liệu
# trùng sẵn có. Bọc try/except riêng để 1 lỗi ở đây không chặn các bảng/index
# khác trong SCHEMA_SQL (degrade an toàn: app vẫn chạy, tạm thời mất bảo vệ
# UNIQUE, thay vì _schema_ready không bao giờ True -> mọi request storage fail).
UNIQUE_SLOT_INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS ux_appointments_slot
    ON appointments (date, time) WHERE status = 'confirmed';
"""

_APPT_COLS = ["code", "session", "patient_name", "patient_phone", "department",
              "department_code", "doctor", "doctor_id", "date", "time", "created_at",
              "status", "reminders_sent"]


def init_schema():
    """Tạo bảng nếu chưa có (idempotent). Tự gọi trước thao tác DB đầu tiên."""
    global _schema_ready
    if _schema_ready or not USE_DB:
        return
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
        conn.commit()
        try:
            cur.execute(UNIQUE_SLOT_INDEX_SQL)
            conn.commit()
        except Exception as exc:  # noqa: BLE001 - phải bắt mọi lỗi DB ở đây
            # Không để lỗi tạo UNIQUE index (vd. dữ liệu trùng sẵn có) chặn schema
            # init của các bảng khác. Rollback để connection còn dùng được tiếp
            # (Postgres yêu cầu rollback sau lỗi trong transaction).
            conn.rollback()
            print(
                "[storage] CẢNH BÁO: không tạo được UNIQUE INDEX "
                "ux_appointments_slot (appointments.date, time). Lỗi: "
                f"{exc}. Có thể do đã tồn tại lịch 'confirmed' trùng "
                "(date, time) trong dữ liệu hiện có — cần dọn dữ liệu thủ "
                "công rồi khởi động lại app để bật lại bảo vệ chống trùng "
                "lịch ở tầng DB. App vẫn chạy tiếp nhưng KHÔNG có UNIQUE "
                "constraint bảo vệ tạm thời."
            )
    _schema_ready = True


def _row_to_appt(row):
    appt = dict(zip(_APPT_COLS, row))
    rs = appt.get("reminders_sent")
    if isinstance(rs, str):           # phòng khi driver trả chuỗi
        rs = json.loads(rs)
    appt["reminders_sent"] = rs or []
    return appt


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
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


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
    items = _json_load(APPOINTMENTS_PATH, [])
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
    data = _json_load(TOKENS_PATH, {})
    tokens = set(data.get(session_id, []))
    tokens.add(token)
    data[session_id] = sorted(tokens)
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
        cur.execute("SELECT id, service_code, name FROM doctors "
                    "ORDER BY sort_order, id")
        rows = cur.fetchall()
    out = {}
    for did, scode, name in rows:
        out.setdefault(scode, []).append({"id": did, "name": name})
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
