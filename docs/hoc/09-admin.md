# Khối `admin` — Trang quản trị cho admin/bác sĩ

> Học: hàm **lọc dữ liệu nhiều tiêu chí**, **bảng tra cứu (hash map)** để ghép giờ ↔ lịch hẹn,
> route Flask có **bảo vệ bằng khóa**, và tư duy **read-only** (chỉ đọc, không phá nghiệp vụ).

Chatbot phục vụ **bệnh nhân đặt lịch**. Nhưng phòng khám còn cần **admin/bác sĩ** xem lại
lịch đã đặt và lịch làm việc. Khối này thêm đúng phần đó — **không tạo dữ liệu mới**, chỉ
đọc lại lịch bệnh nhân đã đặt.

File tập:
```bash
touch docs/hoc/admin_demo.py
```

---

## Bước 1 — Lọc lịch hẹn theo nhiều tiêu chí

Ý tưởng: cầm cả danh sách lịch, rồi **lọc dần** theo từng tiêu chí nào được truyền vào.

```python
APPTS = [
    {"code":"SHI-1","date":"2026-07-07","time":"08:00","doctor_id":"bs01","status":"confirmed"},
    {"code":"SHI-2","date":"2026-07-07","time":"09:00","doctor_id":"bs02","status":"cancelled"},
    {"code":"SHI-3","date":"2026-07-08","time":"08:00","doctor_id":"bs01","status":"confirmed"},
]

def query(date=None, doctor_id=None, status=None):
    out = APPTS
    if status:    out = [a for a in out if a["status"] == status]
    if date:      out = [a for a in out if a["date"] == date]
    if doctor_id: out = [a for a in out if a["doctor_id"] == doctor_id]
    out.sort(key=lambda a: (a["date"], a["time"]))   # sắp theo ngày rồi giờ
    return out

print(query(status="confirmed"))                 # 2 lịch
print(query(date="2026-07-07", doctor_id="bs01"))  # 1 lịch
```
**Giải thích:**
- Tiêu chí nào để `None` thì **bỏ qua** (không lọc) → một hàm phục vụ mọi kiểu tìm.
- `sort(key=lambda a: (a["date"], a["time"]))` sắp xếp theo **cặp** (ngày, giờ).

Đây chính là `booking.query_appointments()` trong file thật (thêm tiêu chí `phone`, `dept_code`).

---

## Bước 2 — Lịch làm việc của 1 bác sĩ trong 1 ngày

Muốn hiện **mỗi khung giờ bận hay trống**, ta lấy đủ khung giờ chuẩn rồi ghép với lịch đã đặt.

```python
SLOTS = ["08:00","08:30","09:00"]           # khung giờ chuẩn của ngày

def day_schedule(doctor_id, date):
    booked = {a["time"]: a for a in query(date=date, doctor_id=doctor_id, status="confirmed")}
    return [{"time": s, "appt": booked.get(s)} for s in SLOTS]

for row in day_schedule("bs01", "2026-07-07"):
    print(row["time"], "BẬN" if row["appt"] else "trống")
```
**Giải thích chỗ hay:**
- `booked = {a["time"]: a for a in ...}` là **dict comprehension**: dựng **bảng tra cứu**
  `giờ → lịch hẹn`. Tra một giờ có bận không chỉ tốn O(1).
- `booked.get(s)` trả lịch hẹn nếu khung `s` đã đặt, `None` nếu trống → chuyển thẳng thành
  "BẬN/trống". Đây là `booking.doctor_day_schedule()` thật.

---

## Bước 3 — Route Flask có bảo vệ bằng khóa

Trang quản trị phải **chặn người lạ**. Bản demo dùng một khóa chung `ADMIN_KEY`
(production nên thay bằng đăng nhập theo tài khoản/vai trò).

```python
import os
from flask import Flask, request, jsonify, abort
app = Flask(__name__)
ADMIN_KEY = os.environ.get("ADMIN_KEY", "shi-admin-demo")

def _check_admin():
    key = request.headers.get("X-Admin-Key") or request.args.get("key", "")
    return key == ADMIN_KEY

@app.route("/api/admin/appointments")
def admin_appointments():
    if not _check_admin():
        abort(401)                       # sai khóa → 401 Unauthorized
    return jsonify(query(status=request.args.get("status") or None))
```
**Giải thích:**
- Khóa nhận từ **header** `X-Admin-Key` (app/JS gọi) hoặc **query** `?key=` (mở nhanh trên trình duyệt).
- `abort(401)` dừng ngay khi khóa sai — mọi endpoint admin đều gọi `_check_admin()` đầu tiên.

File thật có thêm các endpoint: `/api/admin/schedule` (lịch làm việc), `/api/admin/meta`
(danh sách bác sĩ + ngày + thống kê), `/api/admin/cancel` (hủy lịch).

---

## Bước 4 — File thật gồm những gì?

| Nơi | Vai trò |
|-----|---------|
| `booking.py` | `all_doctors()`, `query_appointments()`, `doctor_day_schedule()`, `admin_summary()` — **read-only** |
| `app/app.py` | 4 route `/api/admin/*` + `/admin` (trang HTML), tất cả sau `_check_admin()` |
| `app/templates/admin.html` | Giao diện: nhập khóa → tab **Danh sách lịch hẹn** (lọc) + tab **Lịch làm việc bác sĩ** |
| `.env` | `ADMIN_KEY=...` (không có thì dùng khóa demo) |

Mở thử: chạy `python -m app.app` rồi vào `http://127.0.0.1:5001/admin`, nhập khóa `shi-admin-demo`.

**Vì sao read-only quan trọng?** Nhóm hàm admin chỉ **đọc** qua `storage`, nên:
- Không có nguy cơ làm hỏng luồng đặt lịch của bệnh nhân.
- Chạy đúng cả khi lưu bằng **file JSON** lẫn **Postgres/Supabase** (cùng `storage`).
- Riêng hủy lịch dùng lại đúng `cancel_appointment()` đã có (đổi `status`, không xóa).

## Bài tập
1. Thêm tiêu chí lọc theo `phone` vào hàm `query()` demo.
2. Viết `admin_summary()` đếm số lịch theo `status` (gợi ý: dùng `dict` cộng dồn).
3. Thêm route `/api/admin/schedule?doctor_id=&date=` gọi `day_schedule()` và trả JSON.
