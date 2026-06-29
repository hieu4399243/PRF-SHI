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

## Bước 4 — Hiểu phần "lưu trữ" ở file thật

Bản demo lưu trong biến `AVAILABLE` (mất khi tắt chương trình). File [booking.py](../booking.py)
thật gọi `storage.add_appointment(appt)` → ghi vào **file JSON hoặc Supabase**, nên lịch
**còn nguyên sau khi restart**. Ngoài ra nó còn:
- `_build_availability()`: sinh giờ trống rồi **trừ đi các slot đã đặt** đọc từ storage.
- Kiểm tra bác sĩ tồn tại trước khi đặt.

Ý tưởng thì y hệt bản bạn vừa viết.

## Bài tập
1. Thêm tham số `doctor_id` vào `book_appointment` và đưa vào dict `appt`.
2. Viết hàm `get_appointment(code)` tìm trong 1 list lịch hẹn theo mã (gợi ý: vòng `for` + `if a["code"] == code`).
