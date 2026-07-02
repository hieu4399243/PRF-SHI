# Lưu trữ dữ liệu — File JSON ↔ Supabase (Postgres)

Dự án có **2 chế độ lưu trữ**, tự chọn theo biến môi trường `DATABASE_URL`:

| Chế độ | Khi nào | Dữ liệu nằm ở |
|---|---|---|
| **File JSON (mặc định)** | Không đặt `DATABASE_URL` | `appointments.json`, `device_tokens.json` (local) |
| **Postgres / Supabase** | Có `DATABASE_URL` | Bảng `appointments`, `device_tokens` trên cloud, quản lý qua dashboard Supabase |

Cùng một code, đổi chế độ **không phải sửa nghiệp vụ** — xem `storage.py`.

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
PORT=5001 ./.venv/bin/python app.py
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
device_tokens(session, token, PRIMARY KEY(session, token))
services(code PK, name, descr, keywords jsonb, sort_order)   -- danh mục dịch vụ nha khoa
doctors(id PK, service_code -> services.code, name, sort_order)
safety_patterns(kind, pattern, PRIMARY KEY(kind, pattern))   -- guardrail an toàn y tế
```

## Guardrail an toàn (`safety_patterns`) — có fallback
- `kind` ∈ `emergency` (cấp cứu → 115), `diagnosis` (chặn chẩn đoán/kê đơn), `handoff`
  (chuyển người thật). Sửa/thêm pattern trực tiếp trong **Supabase → Table editor**.
- App nạp lúc khởi động (`safety._load_patterns`); đổi online xong cần **restart backend**.
- ⚠️ **Khác danh mục ở chỗ luôn fail-safe:** đây là dữ liệu an toàn tính mạng, nên nếu
  không có DB / một nhóm bị rỗng / lỗi kết nối → nhóm đó **tự dùng seed baseline** trong
  `safety.py` (guardrail không bao giờ biến mất). DB chỉ để **mở rộng**, không thể làm trống.

## Quản trị danh mục dịch vụ / nha sĩ online
- Danh mục (services, doctors) đã được seed lên Supabase từ `data._SEED_DEPARTMENTS` /
  `_SEED_DOCTORS`. Sửa trực tiếp trong **Supabase → Table editor** (tên dịch vụ, mô tả,
  **keywords** dùng cho triage, thêm/bớt nha sĩ).
- App **nạp danh mục từ DB lúc khởi động** (`data._load_catalog`). Đổi online xong cần
  **restart backend** để có hiệu lực.
- Không có `DATABASE_URL` (hoặc DB lỗi) -> tự dùng dict tĩnh trong `data.py` → triage và
  `eval/` vẫn chạy offline.
- ⚠️ `keywords` là "hàm lượng AI" của triage. Sửa keywords trên DB nên **chạy lại
  `eval/evaluate.py`** để kiểm tra chất lượng không tụt.

## Câu hỏi thường gặp
- **Quay lại JSON?** Xóa/để trống `DATABASE_URL` trong `.env` (danh mục về lại seed tĩnh).
- **Seed lại danh mục?** `./.venv/bin/python scripts/migrate_to_supabase.py` (idempotent:
  trùng `code`/`id` thì bỏ qua, **không** ghi đè chỉnh sửa online của bạn).
- **Bảo mật:** không commit `.env` (đã thêm vào `.gitignore`). Dữ liệu sức khỏe nên bật
  Row Level Security trên Supabase khi mở public.
