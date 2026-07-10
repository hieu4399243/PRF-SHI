# Lưu trữ dữ liệu — File JSON ↔ Supabase (Postgres)

Dự án có **2 chế độ lưu trữ**, tự chọn theo biến môi trường `DATABASE_URL`:

| Chế độ | Khi nào | Dữ liệu nằm ở |
|---|---|---|
| **File JSON (mặc định)** | Không đặt `DATABASE_URL` | `app/data/appointments.json`, `app/data/device_tokens.json` (local) |
| **Postgres / Supabase** | Có `DATABASE_URL` | Bảng `appointments`, `device_tokens` trên cloud, quản lý qua dashboard Supabase |

Cùng một code, đổi chế độ **không phải sửa nghiệp vụ** — xem `app/storage.py`.

> ⚠️ Lưu ý: `sqlitebrowser.org` (DB Browser for SQLite) là **phần mềm xem/sửa file
> `.sqlite` trên máy**, KHÔNG phải dịch vụ lưu trữ online. Để có "kho quản lý data
> online" như mong muốn, ta dùng **Supabase** (Postgres + dashboard web).

---

## Các bước đưa dữ liệu lên Supabase

### 1. Tạo project Supabase
- Đăng ký tại https://supabase.com → **New project** (chọn region gần VN, vd Singapore).
- Đặt **Database Password** (nhớ lại để dùng ở connection string).

### 2. Lấy connection string
- Vào **Project → Settings → Database → Connection string**.
- Chọn tab **Connection pooler** (chế độ *Transaction*, cổng `6543`) — phù hợp cho web app.
- Dạng: `postgresql://postgres.xxxx:[PASSWORD]@aws-0-...pooler.supabase.com:6543/postgres`

### 3. Cấu hình ở dự án
```bash
cp .env.example .env
# Mở .env, dán DATABASE_URL (thay [PASSWORD]) và đặt SECRET_KEY.
```

### 4. Cài thư viện DB
```bash
./.venv/bin/pip install -r requirements.txt   # đã có psycopg + python-dotenv
```

### 5. Nạp dữ liệu hiện có (tùy chọn) & tạo bảng
```bash
./.venv/bin/python scripts/migrate_to_supabase.py
```
Script tự tạo bảng (nếu chưa có) và đẩy dữ liệu từ JSON lên. Chạy lại an toàn (bỏ qua trùng).

### 6. Chạy app như bình thường
```bash
PORT=5001 ./.venv/bin/python -m app.app
# Khởi động sẽ in: [storage] Chế độ lưu trữ: Postgres/Supabase
```
Mở **Supabase → Table editor** để xem/sửa lịch hẹn & token online.

---

## Sơ đồ bảng
```sql
appointments(
  code PK, session, patient_name, patient_phone, department, department_code,
  doctor, doctor_id, date, time, created_at, status, reminders_sent jsonb
)  -- status: 'confirmed' | 'cancelled'
   -- UNIQUE INDEX ux_appointments_doctor_slot(doctor_id, date, time) WHERE status='confirmed'
   --   → chặn 2 lịch confirmed cùng khung giờ cho một bác sĩ (chống race condition khi đặt)
device_tokens(session, token, PRIMARY KEY(session, token))
services(code PK, name, descr, keywords jsonb, sort_order)   -- danh mục dịch vụ nha khoa
doctors(id PK, service_code -> services.code, name, sort_order)
safety_patterns(kind, pattern, PRIMARY KEY(kind, pattern))   -- guardrail an toàn y tế
```

## Bảo vệ chống trùng lịch (UNIQUE constraint)
Khi 2 request cùng lúc đặt lịch ở khung giờ trống cho **cùng một bác sĩ**, bình thường cả 2
đều thấy slot trống → may được cả 2 lịch cùng khung (lỗi race condition). Hệ thống chặn điều này ở cả 2 chế độ lưu trữ:

**Postgres/Supabase:** **UNIQUE INDEX `ux_appointments_doctor_slot`** ở tầng DB:
```sql
CREATE UNIQUE INDEX ux_appointments_doctor_slot 
  ON appointments (doctor_id, date, time) WHERE status = 'confirmed';
```

**JSON mode:** `app/storage.py` giữ process-wide lock (`_JSON_LOCK`) quanh toàn bộ thao tác đọc-sửa-ghi,
phát hiện trùng slot TRƯỚC khi ghi file (hàm `add_appointment()` quét danh sách hiện có). Khi phát hiện trùng,
ném exception `app/storage.SlotTakenError` — `app/booking.py` bắt nó tương tự như `psycopg.errors.UniqueViolation`
ở Postgres, báo lỗi cho người dùng. **Lưu ý:** bảo vệ này chỉ hoạt động trong 1 process; nếu chạy 2+ worker
process cùng JSON → vẫn có race condition (dùng Postgres để multi-process, hoặc 1 process + queue).

Lưu ý chung: **khoá theo (doctor_id, date, time)** — 2 bác sĩ khác nhau có thể đặt cùng khung giờ,
cùng ngày mà không xung đột. Chỉ **cùng bác sĩ** thì mới bị chặn.

Nếu index Postgres không thể tạo (vd. dữ liệu prod đã có 2+ lịch trùng), app in cảnh báo tại
khởi động nhưng vẫn chạy; lúc này `app/booking.py` dựa vào `psycopg.errors.UniqueViolation`
để bắt race và báo lỗi cho người dùng thay vì im lặng tạo lịch trùng.

## Guardrail an toàn (`safety_patterns`) — có fallback
- `kind` ∈ `emergency` (cấp cứu → 115), `diagnosis` (chặn chẩn đoán/kê đơn), `handoff`
  (chuyển người thật). Sửa/thêm pattern trực tiếp trong **Supabase → Table editor**.
- App nạp lúc khởi động (`safety._load_patterns`); đổi online xong cần **restart backend**.
- ⚠️ **Khác danh mục ở chỗ luôn fail-safe:** đây là dữ liệu an toàn tính mạng, nên nếu
  không có DB / một nhóm bị rỗng / lỗi kết nối → nhóm đó **tự dùng seed baseline** trong
  `app/safety.py` (guardrail không bao giờ biến mất). DB chỉ để **mở rộng**, không thể làm trống.

## Quản trị danh mục dịch vụ / nha sĩ online
- Danh mục (services, doctors) đã được seed lên Supabase từ `app/data._SEED_DEPARTMENTS` /
  `_SEED_DOCTORS`. Sửa trực tiếp trong **Supabase → Table editor** (tên dịch vụ, mô tả,
  **keywords** dùng cho triage, thêm/bớt nha sĩ).
- App **nạp danh mục từ DB lúc khởi động** (`app/data._load_catalog`). Đổi online xong cần
  **restart backend** để có hiệu lực.
- Không có `DATABASE_URL` (hoặc DB lỗi) -> tự dùng dict tĩnh trong `app/data.py` → triage và
  `eval/` vẫn chạy offline.
- ⚠️ `keywords` là "hàm lượng AI" của triage. Sửa keywords trên DB nên **chạy lại
  `eval/evaluate.py`** để kiểm tra chất lượng không tụt.

## Câu hỏi thường gặp
- **Quay lại JSON?** Xóa/để trống `DATABASE_URL` trong `.env` (danh mục về lại seed tĩnh).
- **Seed lại danh mục?** `./.venv/bin/python scripts/migrate_to_supabase.py` (idempotent:
  trùng `code`/`id` thì bỏ qua, **không** ghi đè chỉnh sửa online của bạn).
- **Bảo mật:** không commit `.env` (đã thêm vào `.gitignore`). Dữ liệu sức khỏe nên bật
  Row Level Security trên Supabase khi mở public.
