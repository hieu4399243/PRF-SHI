# Khối `booking.py` — Đặt lịch & quản lý khung giờ

> Học: dict trong bộ nhớ, sửa list (remove), sinh mã ngẫu nhiên, hàm trả **nhiều giá trị**
> (tuple), và "trạng thái dùng chung".

File tập:
```bash
touch hoc/booking_demo.py
```

---

## Bước 1 — Bảng giờ trống trong bộ nhớ

Để demo độc lập, ta tự bịa lịch trống (file thật lấy từ `data.py`):

```python
# { "ngày": [danh sách giờ trống] }
AVAILABLE = {
    "2026-07-01": ["08:00", "08:30", "09:00"],
    "2026-07-02": ["14:00", "14:30"],
}

def get_available_dates():
    # chỉ lấy ngày CÒN giờ trống
    return [ngay for ngay, gio in AVAILABLE.items() if gio]

def get_available_times(ngay):
    return AVAILABLE.get(ngay, [])   # .get trả [] nếu không có ngày đó (tránh lỗi)

print(get_available_dates())          # ['2026-07-01', '2026-07-02']
print(get_available_times("2026-07-01"))
```
**Giải thích:**
- `[x for x in ... if dieu_kien]` = **list comprehension**: tạo list mới từ vòng lặp + lọc.
- `dict.get(key, mac_dinh)` = lấy giá trị, không có thì trả mặc định (an toàn hơn `dict[key]`
  vì `dict[key]` báo lỗi khi thiếu key).

---

## Bước 2 — Sinh mã lịch hẹn ngẫu nhiên

```python
import random, string

def tao_ma():
    ky_tu = string.ascii_uppercase + string.digits   # "ABC...Z0123...9"
    return "SHI-" + "".join(random.choices(ky_tu, k=6))

print(tao_ma())   # ví dụ: SHI-7KQ2P9
```
**Giải thích:** `random.choices(nguon, k=6)` chọn 6 ký tự ngẫu nhiên (cho phép lặp);
`"".join(list)` nối list ký tự thành 1 chuỗi.

---

## Bước 3 — Đặt lịch (trả về tuple `(ok, payload)`)

```python
from datetime import datetime

def book_appointment(ngay, gio, ten_benh_nhan):
    # 1) Slot còn trống không?
    if gio not in AVAILABLE.get(ngay, []):
        return False, {"error": "Giờ này vừa được đặt. Chọn giờ khác nhé."}

    # 2) Tạo bản ghi lịch hẹn
    appt = {
        "code": tao_ma(),
        "patient_name": ten_benh_nhan,
        "date": ngay,
        "time": gio,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": "confirmed",
    }

    # 3) Xóa slot khỏi danh sách trống → tránh trùng lịch
    AVAILABLE[ngay].remove(gio)

    return True, appt

ok, kq = book_appointment("2026-07-01", "08:00", "Nguyễn Văn A")
print(ok, kq)
print("Giờ còn trống ngày đó:", get_available_times("2026-07-01"))  # 08:00 đã biến mất
```
**Giải thích chỗ quan trọng:**
- Hàm trả **2 giá trị** `return False, {...}` (gọi là tuple). Người gọi hứng `ok, kq = ...`.
- Quy ước hay dùng: `(thành_công?, dữ_liệu_hoặc_lỗi)`.
- `list.remove(x)` xóa phần tử `x` khỏi list → đó là cách "đánh dấu slot đã đặt".

---

## Bước 4 — File thật khác demo thế nào? (đã đổi thiết kế 02/07)

Bản demo giữ bảng giờ trống trong biến `AVAILABLE` và `remove()` slot khi đặt. File
[booking.py](../app/booking.py) thật **từng làm y hệt**, nhưng giờ đã đổi thiết kế:

**Không còn bảng slot in-memory — DB là "nguồn chân lý" duy nhất.**
- `get_available_times(ngay)` trả **đầy đủ** khung giờ theo lịch làm việc, *không* lọc sẵn.
- Việc "giờ này có ai đặt chưa" được kiểm tra **ngay tại bước xác nhận**, bằng cách đọc
  thẳng storage: hàm `_confirmed_at(ngay, gio)` tìm lịch `confirmed` đang chiếm đúng khung đó.

Vì sao đổi? Bảng in-memory tính 1 lần lúc khởi động sẽ **lệch** khi: (a) restart server,
(b) chạy nhiều tiến trình cùng lúc, (c) một lịch bị **hủy** — slot phải trống trở lại.
Đọc DB lúc xác nhận thì cả 3 trường hợp đều đúng tự nhiên.

**3 khả năng khi bấm xác nhận** (`book_appointment` trả `(ok, payload)`):

| Tình huống | payload | Chatbot xử lý |
|-----------|---------|----------------|
| Khung trống | dict lịch hẹn (`ok=True`) | báo thành công + push |
| Người **khác** vừa đặt mất | `{"error": ...}` | mời chọn lại giờ |
| **Chính SĐT này** đã đặt khung đó | `{"duplicate": True, "existing": {...}}` | hỏi có hủy lịch cũ để đặt lịch mới không |

**Các hàm mới** (phục vụ luồng hủy lịch — xem bài 06):
- Lịch hẹn giờ có thêm trường `patient_phone` (SĐT là "chìa khóa" tra cứu).
- `upcoming_by_phone(phone)`: các lịch `confirmed` sắp tới của 1 SĐT, sớm nhất trước.
- `cancel_appointment(code)`: đặt `status="cancelled"` (gọi `storage.set_status`) —
  **không xóa** bản ghi, chỉ đổi trạng thái; nhờ `_confirmed_at` chỉ đếm lịch `confirmed`
  nên khung giờ tự trống lại, khỏi phải "trả slot" thủ công.

**Các hàm tra cứu cho admin/bác sĩ** (chỉ đọc — xem bài [09](09-admin.md)):
- `query_appointments(date, doctor_id, dept_code, phone, status)`: lọc lịch nhiều tiêu chí.
- `doctor_day_schedule(doctor_id, date)`: mỗi khung giờ của 1 bác sĩ trong 1 ngày → bận/trống.
- `all_doctors()`, `admin_summary()`: danh sách bác sĩ + thống kê nhanh cho trang `/admin`.

## Bài tập
1. Thêm tham số `doctor_id` vào `book_appointment` và đưa vào dict `appt`.
2. Viết hàm `get_appointment(code)` tìm trong 1 list lịch hẹn theo mã (gợi ý: vòng `for` + `if a["code"] == code`).
3. (Mới) Bỏ `AVAILABLE.remove()` trong demo, thay bằng list `APPOINTMENTS` + hàm
   `_confirmed_at(ngay, gio)`; cho `book_appointment` từ chối khi khung đã có người —
   rồi viết `cancel(code)` đổi status và thử đặt lại đúng khung vừa hủy (phải thành công).
