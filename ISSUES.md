# ISSUES — Trợ lý Nha khoa SHI

Từ audit song song (5 reviewer agent: auth · data-integrity · safety · conversation-state ·
worker), 2026-07-09. Đầy đủ hơn ở
`plans/reports/parallel-codebase-audit-260709-1644-production-readiness-report.md`.

Đánh dấu `[x]` khi fix xong.

## 🔴 Critical

- [x] **C1 — Cấp cứu/chẩn đoán không bắt được câu KHÔNG DẤU** (`safety.py:111-120`)
  Triage dùng v2 (không phân biệt dấu) nhưng `check_emergency`/`is_diagnosis_request` so khớp
  có dấu. "kho tho nang", "co giat", "dot quy" → không cảnh báo 115. **Rủi ro tính mạng.**
  Fix: dùng `triage._strip_accents`/`_normalize`/`_contains_word`; thêm pattern rút gọn
  ("khó thở", "sưng mặt", "chảy máu nhiều").
  **Đã fix** (2026-07-09, `plans/260709-2126-fix-critical-issues/phase-01-...md`):
  `safety.py` giờ `_normalize` + `_strip_accents` CẢ input lẫn pattern (kể cả pattern nạp từ
  Supabase, không chỉ seed hardcode). Test: `tests/test_safety.py` (8/8 pass).

- [x] **C2 — Trùng lịch (double-booking) do race condition** (`booking.py:126` → `storage.py:160`)
  Kiểm tra rồi mới insert, không có unique constraint/transaction. 2 request đặt cùng giờ
  cùng lúc → cả 2 đều thành công. Fix: unique index `WHERE status='confirmed'` trên
  `(doctor_id,date,time)` + bắt `IntegrityError`.
  **Đã fix** (2026-07-09, `plans/260709-2126-fix-critical-issues/phase-02-...md`): UNIQUE
  INDEX `ux_appointments_slot` trên `(date,time)` (giữ nguyên semantics hiện tại, KHÔNG theo
  `doctor_id` — xem H1 bên dưới, chưa xác nhận là bug hay spec), tạo tách riêng trong
  `init_schema()` để 1 lỗi migrate không sập cả app. `booking.py` bắt
  `psycopg.errors.UniqueViolation`, phân biệt theo `constraint_name`. Test:
  `tests/test_booking.py` (8 pass, 1 skip — thiếu Postgres local để test race thật, chỉ
  verify qua monkeypatch + review SQL).

- [x] **C3 — `SESSIONS` không giới hạn + key do client tự chọn → DoS bộ nhớ** (`chatbot.py:16`,
  `app.py:34`) Không TTL/cap/rate-limit; client gửi `session` tùy ý trong body → tạo entry vô
  hạn → OOM. Fix: cap + TTL/LRU, hoặc chuyển Redis.
  **Đã fix** (2026-07-09, `plans/260709-2126-fix-critical-issues/phase-03-...md`):
  `SESSIONS` là `OrderedDict` với cap 2000 + TTL 3600s + `threading.Lock`. Quyết định: sản
  phẩm chạy 1 Flask process, không cần Redis. Residual risk chấp nhận: cap không gắn
  rate-limit nên vẫn có thể bị đá phiên hợp lệ nếu 1 client spam `/api/start` (fix đúng —
  rate-limit — là mục Medium riêng, chưa làm). Test: `tests/test_chatbot_sessions.py` (5/5).

- [x] **C4 — `/api/ics/<code>` không xác thực → lộ dữ liệu sức khỏe** (`app.py:77-88`,
  `booking.py:66-67`) Mã dùng `random` (không phải `secrets`), không kiểm tra quyền sở hữu.
  Đoán/dò mã → tải được tên bệnh nhân + dịch vụ nha khoa. Fix: `secrets.token_urlsafe` hoặc
  yêu cầu khớp session; thêm rate limit.
  **Đã fix** (2026-07-09, `plans/260709-2126-fix-critical-issues/phase-04-...md`):
  `_generate_code()` dùng `secrets.choice`; `/api/ics/<code>` yêu cầu `appt["session"] ==
  sid`, 404 đồng nhất cho "không tồn tại" và "sai chủ sở hữu". Residual risk chấp nhận: user
  web mất cookie sẽ không tải lại được link cũ (đúng mô hình bảo mật, không phải bug). Test:
  `tests/test_app_ics.py` (4/4).

- [x] **C5 — Worker `--watch` chết khi gặp 1 bản ghi lỗi** (`reminder_worker.py:88`)
  Không try/except quanh `_send_for`; 1 lịch hẹn thiếu field → KeyError → toàn bộ nhắc lịch
  ngừng cho mọi người. Fix: try/except từng item trong vòng lặp.
  **Đã fix** (2026-07-09, `plans/260709-2126-fix-critical-issues/phase-05-...md`): 2 lớp
  try/except trong `scan_once()` — `[SKIP]` cho lỗi dữ liệu, `[SEND-ERROR]` cho lỗi
  gửi/đánh dấu (tách log để không lẫn với H2/H3). Test: `tests/test_reminder_worker.py` (3/3).

## 🟠 High

- [x] **H1 — Kiểm tra trùng giờ bỏ qua `doctor_id`** (`booking.py:98-105`) — cả phòng khám coi
  như 1 ghế; đặt bác sĩ A giờ X chặn luôn bác sĩ B giờ X. **Cần xác nhận: đúng thiết kế hay bug?**
  **Đã fix** (2026-07-10, `plans/260709-2230-fix-high-issues/phase-01-...md`): xác nhận là
  bug. `_confirmed_at` + UNIQUE INDEX đổi sang khoá `(doctor_id, date, time)` (đổi tên
  `ux_appointments_slot` → `ux_appointments_doctor_slot`, CREATE-trước-DROP-sau). Đã sửa cả
  2 chỗ gọi `_confirmed_at` (kể cả bên trong `_insert_with_race_guard` — chỗ dễ bỏ sót nhất,
  bị bắt bởi 2 reviewer độc lập ở red-team). Test: `tests/test_booking.py`.
- [x] **H2 — Đánh dấu đã nhắc dù gửi push thất bại** (`push.py:91-94`, `reminder_worker.py:65`)
  → mất nhắc lịch vĩnh viễn, không có cơ chế retry từ `outbox/`.
  **Đã fix (thu hẹp phạm vi)** (2026-07-10, `phase-02-...md`): không có tiến trình đọc
  outbox để retry → chỉ sửa phần khả thi: `push.send_push` trả thêm `failed`, không đánh
  dấu `reminders_sent` khi push tới token thật lỗi mạng (tự thử lại ở lần quét sau). Residual
  risk: chưa bắt lỗi ticket cấp ứng dụng của Expo (HTTP 200 nhưng ticket lỗi) — chấp nhận,
  ghi trong Risk Assessment phase-02. Test: `tests/test_reminder_worker.py`.
- [x] **H3 — `--test` làm hỏng dedup thật** (`reminder_worker.py:98`) chạy 1 lần là mọi nhắc
  lịch thật bị coi là "đã gửi" vĩnh viễn.
  **Đã fix** (2026-07-10, `phase-02-...md`): thêm `dry_run` xuyên suốt `scan_once`/`_send_for`,
  `--test` gọi `scan_once(force=True, dry_run=True)`, không bao giờ gọi
  `mark_reminder_sent`. Verify thủ công: `appointments.json` không đổi sau khi chạy `--test`.
- [x] **H4 — So giờ dùng local-time naive, lệch múi giờ VN khi host chạy UTC**
  (`reminder_worker.py:72`).
  **Đã fix** (2026-07-10, `phase-02-...md`): `_now_vn()`/`_appt_datetime()` gắn tường minh
  `zoneinfo.ZoneInfo("Asia/Ho_Chi_Minh")` cho cả 2 vế so sánh, không phụ thuộc giờ hệ thống
  host. Test: `tests/test_reminder_worker.py`.
- [x] **H5 — `.ics` không escape `patient_name` → chèn được nội dung lịch (calendar injection)**
  (`calendar_ics.py:29,56-57`; `chatbot.py:362` giữ nguyên `\n` nội bộ).
  **Đã fix** (2026-07-10, `phase-03-...md`): thêm `_esc()` escape đúng RFC 5545 (backslash →
  `;` → `,` → xuống dòng, đúng thứ tự tránh escape-kép), áp dụng cho mọi field nội suy vào
  `.ics`. Test: `tests/test_calendar_ics.py`.
- [x] **H6 — Khóa admin nhận qua query string `?key=`** → lộ trong log/lịch sử trình duyệt/Referer
  (`app.py:97`).
  **Đã fix** (2026-07-10, `phase-04-...md`): `_check_admin()` chỉ chấp nhận header
  `X-Admin-Key`, so sánh bằng `hmac.compare_digest` (constant-time, red-team bắt thêm lỗi
  timing side-channel). Cập nhật `docs/getting-started-guide.md` (ví dụ curl cũ dùng `?key=`
  — đã đổi sang header). Test: `tests/test_app_admin.py`.
- [x] **H7 — `SECRET_KEY`/`ADMIN_KEY` mặc định + `debug=True` trên `0.0.0.0`** (`app.py:23,26,160`)
  — production phải set env + tắt debug (đã ghi trong docs, nhắc lại vì nghiêm trọng).
  **Đã fix** (2026-07-10, `phase-04-...md`): cảnh báo runtime khi `SECRET_KEY`/`ADMIN_KEY`
  còn giá trị demo mặc định (hàm thuần `_default_key_warnings`, test không cần reload
  module) + cảnh báo riêng khi chạy `debug=True`+`host=0.0.0.0` (rủi ro RCE qua Werkzeug
  debugger — phần này bị bỏ sót ở bản nháp đầu, 2 reviewer độc lập bắt được ở red-team).
  KHÔNG đổi `debug=True` mặc định (vẫn cần cho demo local). Test: `tests/test_app_admin.py`.
- [x] **H8 — Tên bệnh nhân không được ẩn trước khi ghi audit log** (`safety.py:45-57`;
  `mask_pii` chỉ ẩn phone/email/CCCD).
  **Đã fix** (2026-07-10, `phase-05-...md`): `chatbot.handle_message` ẩn message thành
  `"[TÊN ĐÃ ẨN]"` trước khi ghi audit log khi state là `ASK_NAME` (nơi duy nhất message = tên
  thật). `patient_name` lưu trong nghiệp vụ không bị ảnh hưởng. Test:
  `tests/test_chatbot_audit.py`.
- [x] **H9 — Session in-memory hỏng khi chạy nhiều worker/gunicorn hoặc restart**
  (`chatbot.py:16`, đã ghi trong docs).
  **Đóng bằng ghi chú, không code** (2026-07-10): quyết định "1 process, không Redis" đã
  chốt ở `plans/260709-2126-fix-critical-issues/` (C3) trả lời đúng phần multi-worker của
  H9. Mất session khi restart là rủi ro chấp nhận cho quy mô đồ án — không xây persistence
  (YAGNI). Xem comment tại khai báo `SESSIONS`/`_MAX_SESSIONS` trong `chatbot.py`.

## 🟡 Medium

- [ ] Chặn chẩn đoán chỉ chạy ở state TRIAGE, các state khác không chặn (`chatbot.py:177`).
- [ ] Chế độ JSON: race điều kiện đọc-sửa-ghi + ghi không atomic (`storage.py:124-126,156-226`).
- [ ] Không giới hạn `MAX_CONTENT_LENGTH` → DoS bằng message khổng lồ (`app.py:62`).
- [ ] Mỗi lần đặt lịch mở connection mới + quét toàn bảng, không có `WHERE` (`storage.py:39,132-139`).
- [ ] Token Expo hết hạn (`DeviceNotRegistered`) không bao giờ bị xóa; lỗi ticket HTTP 200 bị bỏ qua (`push.py:88-90`).
- [ ] Trùng mã lịch hẹn không được xử lý → 500 (DB) hoặc dữ liệu trùng âm thầm (JSON) (`booking.py:66`).
- [ ] Client tự chọn `session` id (giảm nhẹ nhờ entropy uuid4) (`app.py:34`).
- [ ] Không có rate limiting trên endpoint công khai.
- [ ] Audit log: không xoay vòng, timestamp không theo UTC, chỉ bắt `OSError` (meta lỗi kiểu dữ liệu sẽ crash lượt chat) (`safety.py:137-150`).
- [ ] Sửa session dict không có khóa (lock) khi Flask threaded → state có thể bị ghi đè (`chatbot.py`).

## 🟢 Low

- [ ] So sánh khóa admin không constant-time (`app.py:98`, dùng `hmac.compare_digest`).
- [ ] SĐT chấp nhận số hợp lệ về hình thức nhưng không tồn tại (`chatbot.py:601-611`).
- [ ] Nhắc lịch quá hạn bị bỏ qua âm thầm (`reminder_worker.py:88`).

## Thứ tự fix đề xuất

1. C1 (life-safety, nhỏ) → 2. H5 (.ics escape) → 3. C5/H2/H3 (worker) → 4. C4 (ics auth/mã)
→ 5. H1 (xác nhận thiết kế trước) → 6. C2 (unique constraint) → 7. C3/H9 (session store)
→ 8. H4 (timezone) → 9. H8 (redact tên) → 10. H6/H7 (admin key + secrets).

## Câu hỏi cần trả lời trước khi fix

1. Production chạy 1 Flask worker hay nhiều worker (gunicorn)? (ảnh hưởng C3/H9)
2. `DATABASE_URL` có luôn được set ở production không? (race JSON chỉ là vấn đề dev?)
3. Thiết kế đúng là 1 slot/bác sĩ hay 1 slot/toàn phòng khám? (quyết định H1 là bug hay spec)
4. Có tiến trình nào đọc `outbox/push_outbox.jsonl` để gửi lại không? (nếu không, H2 vô phương cứu)
