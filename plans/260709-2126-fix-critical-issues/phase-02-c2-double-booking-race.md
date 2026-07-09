---
phase: 2
title: "C2 Double-Booking Race"
status: pending
priority: P1
dependencies: []
---

# Phase 2: C2 — Trùng lịch (double-booking) do race condition

## Overview

`booking.book_appointment()` kiểm tra `_confirmed_at(date_str, time_str)` rồi mới
`storage.add_appointment()` — không transaction/unique constraint. Hai request đặt cùng
giờ gần như đồng thời → cả hai đều pass check trước khi bên kia insert → 2 lịch trùng.
Fix ở tầng DB (Postgres, theo quyết định user: production luôn có `DATABASE_URL`):
UNIQUE index chặn insert trùng, `booking.py` bắt lỗi và trả về response giống lỗi "khung giờ
đã bị đặt" hiện có.

**Giữ nguyên semantics hiện tại**: `_confirmed_at` khoá theo `(date, time)` — KHÔNG theo
`doctor_id` (đó là H1, chưa được xác nhận là bug hay spec — ngoài phạm vi phase này).
Index mới phải khoá đúng `(date, time)` để không âm thầm đổi hành vi nghiệp vụ.

## Requirements

- Functional: 2 request đặt trùng `(date, time)` cùng lúc → chỉ 1 thành công, người
  thua nhận đúng response lỗi hiện có (`{"error": "Khung giờ này vừa có người đặt..."}`
  hoặc `{"duplicate": True, ...}` nếu cùng SĐT).
- Non-functional: Không đổi API response shape của `book_appointment`. Chỉ nhánh
  Postgres (`USE_DB=True`) được sửa; nhánh JSON giữ nguyên (rủi ro race JSON là vấn đề
  dev-only đã biết, chấp nhận theo quyết định user).

## Architecture

1. `storage.py` `SCHEMA_SQL`: thêm UNIQUE partial index:
   ```sql
   CREATE UNIQUE INDEX IF NOT EXISTS ux_appointments_slot
       ON appointments (date, time) WHERE status = 'confirmed';
   ```
   Đặt trong `SCHEMA_SQL` (chạy qua `init_schema()`, đã idempotent nhờ `IF NOT EXISTS`).

   **[Red team — Accept, Finding "migration có thể brick app"]** `IF NOT EXISTS` chỉ chặn
   chạy lại DDL, KHÔNG chặn lỗi nếu prod đã có sẵn ≥2 lịch `confirmed` trùng
   `(date,time)` — đúng tình huống mà C2 tồn tại để sửa. Nếu `CREATE UNIQUE INDEX` fail vì
   dữ liệu trùng sẵn có, `init_schema()` (`storage.py:91-99`) không có try/except,
   `_schema_ready` không bao giờ thành `True` → MỌI request đụng storage (list/get/add
   appointment) đều fail lặp lại vĩnh viễn, sập toàn app. Bắt buộc bọc `init_schema()`
   bằng try/except quanh riêng câu lệnh `CREATE UNIQUE INDEX` (không phải toàn bộ
   `SCHEMA_SQL` — các `CREATE TABLE IF NOT EXISTS` khác không có rủi ro này): nếu tạo index
   fail (do dữ liệu trùng), log rõ ràng ra stdout mã lỗi + gợi ý dọn dữ liệu thủ công, và
   để các bảng/index khác trong `SCHEMA_SQL` vẫn được tạo bình thường — KHÔNG để 1 lỗi
   index chặn toàn bộ schema init. App vẫn chạy được (không có UNIQUE bảo vệ tạm thời) thay
   vì sập hoàn toàn — chấp nhận degrade an toàn hơn outage toàn phần.
2. `storage.add_appointment()`: không nuốt exception — để `psycopg.errors.UniqueViolation`
   propagate lên caller (không try/except ở storage layer, vì storage không biết cách xử
   lý nghiệp vụ đúng — đó là việc của `booking.py`).
3. `booking.book_appointment()`: bọc `storage.add_appointment(appointment)` bằng
   try/except bắt `psycopg.errors.UniqueViolation` (import trễ, cùng kiểu lazy-import đã
   dùng trong `storage._connect()`, tránh psycopg là hard dependency khi chạy JSON-only).

   **[Red team — Accept, Finding "handler không phân biệt constraint"]**
   `appointments.code` đã là `TEXT PRIMARY KEY` (`storage.py:46`) TRƯỚC KHI thêm
   `ux_appointments_slot`. `UniqueViolation` có thể đến từ 2 nguồn khác nhau: (a) đúng ý —
   trùng slot `(date,time)`, hoặc (b) hiếm nhưng có thật — `_generate_code()` sinh trùng mã
   với 1 lịch hẹn khác (không gian 36^6, không có vòng lặp retry). Handler PHẢI kiểm tra
   `exc.diag.constraint_name` (thuộc tính chuẩn của `psycopg.errors.UniqueViolation`):
   - `== "ux_appointments_slot"` → xử lý như dưới (gọi lại `_confirmed_at`).
   - Khác đi (vd `"appointments_pkey"`) → KHÔNG gọi `_confirmed_at` (sẽ trả `None` vì slot
     không thực sự bị chiếm, gây `AttributeError` khi code cũ giả định `taken` luôn có
     giá trị) — thay vào đó sinh lại `code` mới (gọi lại `_generate_code()`) và retry
     insert một lần; nếu vẫn lỗi, trả `(False, {"error": "Lỗi hệ thống, vui lòng thử lại."})`
     thay vì để exception rò rỉ (route Flask không chạy production với `debug=False` được
     đảm bảo — xem H7 trong `ISSUES.md`, ngoài phạm vi phase này để sửa `debug=True`, nhưng
     handler ở đây phải tự bảo vệ không phụ thuộc vào cấu hình đó).

   Khi bắt được lỗi đúng slot: gọi lại `_confirmed_at(date_str, time_str)` để lấy bản ghi
   vừa thắng race, trả về response giống nhánh "đã có người đặt" hiện tại (dedupe theo SĐT
   y hệt logic ở trên).

## Related Code Files

- Modify: `storage.py` (`SCHEMA_SQL`, có thể cần rollback connection khi lỗi)
- Modify: `booking.py` (`book_appointment`, bọc try/except quanh
  `storage.add_appointment`)
- Create: `tests/test_booking.py`

## Implementation Steps (TDD)

1. **Red** — viết `tests/test_booking.py` với DB thật KHÔNG khả dụng trong môi trường
   dev (không có `DATABASE_URL`) → test race condition ở tầng Postgres không chạy được
   trực tiếp trong CI/dev không DB. Chiến lược test theo 2 tầng:
   - `test_schema_has_unique_index()`: parse `storage.SCHEMA_SQL` (string) và assert
     có `CREATE UNIQUE INDEX` trên `appointments(date, time)` với `WHERE status =
     'confirmed'`. Test nhanh, không cần kết nối DB thật — chạy fail trước khi thêm SQL.
   - `test_book_appointment_catches_slot_integrity_error(monkeypatch)`: monkeypatch
     `storage.add_appointment` để raise `psycopg.errors.UniqueViolation` với
     `diag.constraint_name = "ux_appointments_slot"` (dùng `psycopg.errors.UniqueViolation`
     thật, set `.diag` qua object giả hoặc `unittest.mock.Mock(constraint_name=...)` tuỳ
     API thực tế của `psycopg.errors` — kiểm tra khi code). Gọi `booking.book_appointment(...)`
     → assert trả về `(False, {...})` với message lỗi "vừa có người đặt" hoặc
     `duplicate=True`, KHÔNG để exception propagate lên caller.
   - `test_book_appointment_retries_on_code_collision(monkeypatch)`: **[Red team —
     Accept, Finding "handler không phân biệt constraint"]** monkeypatch
     `storage.add_appointment` raise `UniqueViolation` với
     `diag.constraint_name = "appointments_pkey"` lần gọi đầu, thành công lần gọi thứ 2 →
     assert `book_appointment` retry với `code` MỚI (khác code lần đầu) và trả về
     `(True, {...})`, KHÔNG gọi `_confirmed_at` và KHÔNG raise `AttributeError`.
   - `test_schema_has_unique_index()` (như cũ) + verify trong cùng test hoặc test riêng
     rằng câu lệnh tạo `ux_appointments_slot` được bọc try/except riêng trong
     `init_schema()` (đọc source `storage.py`, assert bằng cách kiểm tra cấu trúc code —
     vd `inspect.getsource(storage.init_schema)` chứa `try` bao quanh đoạn liên quan tới
     `ux_appointments_slot`, hoặc đơn giản hơn: test bằng cách monkeypatch cursor.execute để
     raise lỗi CHỈ khi SQL chứa `ux_appointments_slot`, gọi `init_schema()`, assert KHÔNG
     raise và các bảng khác vẫn được tạo — cách tiếp cận cụ thể quyết định lúc code, miễn
     đúng ý "1 index lỗi không chặn toàn bộ schema").
   - Nếu môi trường CÓ `DATABASE_URL` trỏ tới Postgres local/test khả dụng
     (`pytest.mark.skipif` khi thiếu biến môi trường): test 2 thread gọi `book_appointment`
     đồng thời cùng slot → assert chỉ 1 trả `ok=True`. **[Red team — Accept, Finding
     "không có test Postgres thật"]** Đây KHÔNG phải optional-bỏ-qua-im-lặng: nếu môi
     trường dev/CI không có `DATABASE_URL`, báo cáo hoàn thành phase PHẢI ghi rõ dòng
     "C2: race condition thật CHƯA được verify trên Postgres thật, chỉ verify qua unit
     test monkeypatch + đọc SQL" — không được báo "done" mà không nêu giới hạn này.
   - Chạy `pytest tests/test_booking.py -v` → fail (chưa có index, chưa có try/except).
2. **Green**:
   - Thêm UNIQUE INDEX vào `SCHEMA_SQL`.
   - Thêm try/except `UniqueViolation` trong `booking.book_appointment`.
3. Chạy lại `pytest tests/test_booking.py -v` → pass.
4. Nếu có `DATABASE_URL` local để verify thủ công: chạy
   `python -c "import storage; storage.init_schema()"` rồi kiểm tra index tồn tại qua
   `\d appointments` (psql) hoặc query `pg_indexes`. Nếu không có DB local, ghi rõ trong
   báo cáo hoàn thành là chưa verify trên Postgres thật, chỉ verify qua unit test
   monkeypatch + đọc SQL.

## Success Criteria

- [ ] `tests/test_booking.py` pass.
- [ ] `SCHEMA_SQL` chứa UNIQUE INDEX đúng cột `(date, time)` + `WHERE status='confirmed'`.
- [ ] `book_appointment` không để lộ exception thô ra ngoài khi trùng — luôn trả
  `(bool, dict)` như cũ.
- [ ] Nhánh JSON (`USE_DB=False`) không bị đổi hành vi (không thêm lock nào — ngoài
  phạm vi, theo quyết định user).

## Risk Assessment

- **Không có Postgres local để test thật**: rủi ro chính. Giảm thiểu bằng
  monkeypatch-based unit test (không cần DB) + review SQL bằng mắt. Ghi rõ trong báo cáo
  nếu chưa chạy được integration test thật trên Postgres.
- **`psycopg.errors.UniqueViolation` chỉ import được nếu `psycopg` đã cài** — đã có sẵn
  trong `requirements.txt` (comment "tuỳ chọn"). Nếu môi trường dev không cài `psycopg`,
  import lazy bên trong except-block phải tự bọc thêm `except ImportError` fallback (rethrow
  nguyên exception gốc) để không crash khi thiếu lib — nhưng đây là nhánh hiếm, chỉ xảy ra
  khi `USE_DB=True` mà thiếu `psycopg`, vốn đã là lỗi cấu hình có sẵn từ trước.
