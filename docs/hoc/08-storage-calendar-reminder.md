# 3 khối phụ trợ: `storage.py`, `calendar_ics.py`, `reminder_worker.py`

> Không cần viết lại từng dòng — hiểu nhiệm vụ và "mẹo" của mỗi khối là đủ. Có kèm đoạn
> thử nhỏ.

---

## 1) `storage.py` — Lưu ở đâu? (JSON hay Supabase)

**Vấn đề:** dữ liệu để trong biến/file local sẽ mất khi restart, không share online được.
**Cách giải:** 1 lớp trung gian — *cùng hàm gọi, đổi nơi cất tùy cấu hình*.

```python
DATABASE_URL = os.environ.get("DATABASE_URL", "")
USE_DB = bool(DATABASE_URL)      # có chuỗi kết nối → True

def add_appointment(appt):
    if USE_DB:
        ... # ghi vào Postgres/Supabase
    else:
        ... # ghi vào appointments.json
```
👉 Nhờ vậy `booking.py`/`push.py` **không cần biết** dữ liệu nằm ở đâu — chúng chỉ gọi
`storage.add_appointment(...)`. Đây là nguyên tắc quan trọng: **tách "logic" khỏi "nơi lưu"**.

Thử xem đang ở chế độ nào:
```bash
./.venv/bin/python -c "import app.storage; print('DB' if app.storage.USE_DB else 'JSON')"
```

**Hiện có 5 bảng** (cập nhật 02/07): `appointments`, `device_tokens`, `services`,
`doctors`, và mới nhất **`safety_patterns`** (kind, pattern) — cho phép quản lý từ khóa
cấp cứu / chẩn đoán / handoff online (xem bài 03, phần fail-safe).

**Các hàm mới đáng chú ý:**
- `set_status(code, status)` — đổi trạng thái lịch hẹn (luồng **hủy lịch** dùng
  `status="cancelled"`; không xóa bản ghi, giữ lại để tra cứu/audit).
- `list_safety_patterns()` / `seed_safety_patterns(...)` — đọc/nạp bộ pattern an toàn.
- `get_appointment(code)` đọc **thẳng storage** — vì thiết kế mới coi **DB là nguồn chân
  lý duy nhất** cho slot trống (xem bài 04): không còn bảng giờ trống in-memory.

Chi tiết cấu hình Supabase: xem [DATABASE.md](../database-storage-guide.md).

---

## 2) `calendar_ics.py` — Tạo file lịch `.ics`

**Mục đích:** sau khi đặt lịch, sinh 1 file `.ics` để người dùng bấm "Thêm vào Lịch"
(iPhone/Google/Outlook), và lịch đó **tự nhắc** trước giờ khám.

`.ics` chỉ là **văn bản theo khuôn chuẩn**:
```
BEGIN:VEVENT
SUMMARY:Nha khoa SHI: Sâu răng - BS. Châu
DTSTART;TZID=Asia/Ho_Chi_Minh:20260701T080000
BEGIN:VALARM
TRIGGER:-P1D            ← nhắc trước 1 NGÀY
END:VALARM
END:VEVENT
```
👉 Code chỉ là **ghép chuỗi** từ thông tin lịch hẹn theo đúng khuôn này. `TRIGGER:-P1D` =
báo trước 1 ngày, `-PT1H` = trước 1 giờ. Không cần OAuth/API key — mọi app lịch đều đọc được.

File thật: `build_ics(appt)` trả chuỗi; route `GET /api/ics/<code>` cho tải về.

---

## 3) `reminder_worker.py` — Chương trình chạy nền nhắc lịch

**Mục đích:** đây là 1 chương trình **riêng** (không phải web), lặp đi lặp lại: quét các
lịch hẹn → cái nào sắp tới giờ thì bắn thông báo.

Khung rút gọn:
```python
def scan_once():
    for appt in booking.all_appointments():      # duyệt mọi lịch hẹn
        for rule in [nhac_1_ngay, nhac_2_gio]:   # các mốc nhắc
            if đã_tới_giờ_nhắc and chưa_gửi:
                push.send_push(...)               # gửi
                booking.mark_reminder_sent(...)   # đánh dấu để KHÔNG gửi trùng
```
Chạy:
```bash
./.venv/bin/python -m app.reminder_worker --test    # gửi thử mọi nhắc ngay
./.venv/bin/python -m app.reminder_worker --watch   # quét mỗi 60 giây (chạy nền)
```
**Giải thích:**
- `--watch` dùng `while True: ...; time.sleep(60)` → cứ 60 giây quét 1 lần.
- `mark_reminder_sent` ghi lại loại nhắc đã gửi (trong `reminders_sent`) → **mỗi nhắc chỉ
  gửi đúng 1 lần**, tránh spam.
- Đây là mẫu "background job" rất phổ biến: tách việc chạy định kỳ ra khỏi web server.

---

## Tổng kết cả series
Bạn đã đi qua: dữ liệu (`data`) → AI (`triage`) → an toàn (`safety`) → đặt lịch (`booking`)
→ thông báo (`push`) → điều phối (`chatbot`) → API (`app`) → lưu trữ & tiện ích.

Giờ mở lần lượt các file thật ở thư mục gốc và đối chiếu — bạn sẽ đọc hiểu **toàn bộ dự án**.
Muốn đi sâu thêm phần nào (vd viết test, hay nối Supabase từng bước) cứ nói nhé.
