# ISSUES — Trợ lý Nha khoa SHI

Từ audit song song (5 reviewer agent: auth · data-integrity · safety · conversation-state ·
worker), 2026-07-09. Đầy đủ hơn ở
`plans/reports/parallel-codebase-audit-260709-1644-production-readiness-report.md`.

Đánh dấu `[x]` khi fix xong.

## 🔴 Critical

- [ ] **C1 — Cấp cứu/chẩn đoán không bắt được câu KHÔNG DẤU** (`safety.py:111-120`)
  Triage dùng v2 (không phân biệt dấu) nhưng `check_emergency`/`is_diagnosis_request` so khớp
  có dấu. "kho tho nang", "co giat", "dot quy" → không cảnh báo 115. **Rủi ro tính mạng.**
  Fix: dùng `triage._strip_accents`/`_normalize`/`_contains_word`; thêm pattern rút gọn
  ("khó thở", "sưng mặt", "chảy máu nhiều").

- [ ] **C2 — Trùng lịch (double-booking) do race condition** (`booking.py:126` → `storage.py:160`)
  Kiểm tra rồi mới insert, không có unique constraint/transaction. 2 request đặt cùng giờ
  cùng lúc → cả 2 đều thành công. Fix: unique index `WHERE status='confirmed'` trên
  `(doctor_id,date,time)` + bắt `IntegrityError`.

- [ ] **C3 — `SESSIONS` không giới hạn + key do client tự chọn → DoS bộ nhớ** (`chatbot.py:16`,
  `app.py:34`) Không TTL/cap/rate-limit; client gửi `session` tùy ý trong body → tạo entry vô
  hạn → OOM. Fix: cap + TTL/LRU, hoặc chuyển Redis.

- [ ] **C4 — `/api/ics/<code>` không xác thực → lộ dữ liệu sức khỏe** (`app.py:77-88`,
  `booking.py:66-67`) Mã dùng `random` (không phải `secrets`), không kiểm tra quyền sở hữu.
  Đoán/dò mã → tải được tên bệnh nhân + dịch vụ nha khoa. Fix: `secrets.token_urlsafe` hoặc
  yêu cầu khớp session; thêm rate limit.

- [ ] **C5 — Worker `--watch` chết khi gặp 1 bản ghi lỗi** (`reminder_worker.py:88`)
  Không try/except quanh `_send_for`; 1 lịch hẹn thiếu field → KeyError → toàn bộ nhắc lịch
  ngừng cho mọi người. Fix: try/except từng item trong vòng lặp.

## 🟠 High

- [ ] **H1 — Kiểm tra trùng giờ bỏ qua `doctor_id`** (`booking.py:98-105`) — cả phòng khám coi
  như 1 ghế; đặt bác sĩ A giờ X chặn luôn bác sĩ B giờ X. **Cần xác nhận: đúng thiết kế hay bug?**
- [ ] **H2 — Đánh dấu đã nhắc dù gửi push thất bại** (`push.py:91-94`, `reminder_worker.py:65`)
  → mất nhắc lịch vĩnh viễn, không có cơ chế retry từ `outbox/`.
- [ ] **H3 — `--test` làm hỏng dedup thật** (`reminder_worker.py:98`) chạy 1 lần là mọi nhắc
  lịch thật bị coi là "đã gửi" vĩnh viễn.
- [ ] **H4 — So giờ dùng local-time naive, lệch múi giờ VN khi host chạy UTC**
  (`reminder_worker.py:72`).
- [ ] **H5 — `.ics` không escape `patient_name` → chèn được nội dung lịch (calendar injection)**
  (`calendar_ics.py:29,56-57`; `chatbot.py:362` giữ nguyên `\n` nội bộ).
- [ ] **H6 — Khóa admin nhận qua query string `?key=`** → lộ trong log/lịch sử trình duyệt/Referer
  (`app.py:97`).
- [ ] **H7 — `SECRET_KEY`/`ADMIN_KEY` mặc định + `debug=True` trên `0.0.0.0`** (`app.py:23,26,160`)
  — production phải set env + tắt debug (đã ghi trong docs, nhắc lại vì nghiêm trọng).
- [ ] **H8 — Tên bệnh nhân không được ẩn trước khi ghi audit log** (`safety.py:45-57`;
  `mask_pii` chỉ ẩn phone/email/CCCD).
- [ ] **H9 — Session in-memory hỏng khi chạy nhiều worker/gunicorn hoặc restart**
  (`chatbot.py:16`, đã ghi trong docs).

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
