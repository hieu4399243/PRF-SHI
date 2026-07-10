# Khối `data.py` — Kho dữ liệu (dịch vụ, bác sĩ, khung giờ)

> Khối đơn giản nhất, không phụ thuộc ai. Học: dict lồng nhau, list, và **làm việc với
> ngày tháng** (module `datetime`).

File tập:
```bash
touch hoc/data_demo.py
```
Chạy: `./.venv/bin/python hoc/data_demo.py`

---

## Bước 1 — Danh mục dịch vụ (`DEPARTMENTS`)

```python
DEPARTMENTS = {
    "sau_rang": {
        "name": "Trám răng / Sâu răng",
        "desc": "Điều trị sâu răng, trám răng, răng mẻ vỡ.",
        "keywords": ["sâu răng", "lỗ sâu", "trám răng", "ê buốt"],
    },
    "nha_chu": {
        "name": "Nha chu (Nướu / Lợi)",
        "desc": "Bệnh lý nướu: viêm lợi, tụt lợi, răng lung lay.",
        "keywords": ["chảy máu chân răng", "viêm lợi", "hôi miệng"],
    },
}

print(DEPARTMENTS["sau_rang"]["name"])   # Trám răng / Sâu răng
```
👉 Mỗi dịch vụ: `name` (hiển thị), `desc` (mô tả), `keywords` (cho triage). Khóa ngoài
("sau_rang") là **mã** — viết liền, không dấu, máy dùng.

---

## Bước 2 — Bác sĩ theo dịch vụ (`DOCTORS`)

```python
DOCTORS = {
    "sau_rang":  [{"id": "bs_sr_01", "name": "BS. Lê Minh Châu"}],
    "chinh_nha": [
        {"id": "bs_cn_01", "name": "BS. Đỗ Thị Giang"},
        {"id": "bs_cn_02", "name": "BS. Ngô Văn Hải"},
    ],
}

# Lấy danh sách bác sĩ của 1 dịch vụ:
for bs in DOCTORS["chinh_nha"]:
    print(bs["id"], "-", bs["name"])
```
👉 Dùng **chung mã dịch vụ** với `DEPARTMENTS` để 2 bảng "ăn khớp" nhau. Mỗi bác sĩ có
`id` (máy) + `name` (người).

---

## Bước 3 — Sinh khung giờ trống (làm việc với ngày tháng)

```python
from datetime import date, timedelta   # đặt ở ĐẦU file

WORK_SLOTS = ["08:00", "08:30", "09:00", "14:00", "14:30"]

def generate_available_slots(num_days=5):
    slots = {}
    d = date.today() + timedelta(days=1)   # bắt đầu từ NGÀY MAI
    added = 0
    while added < num_days:                # lặp tới khi đủ num_days ngày
        if d.weekday() != 6:               # 6 = Chủ nhật → bỏ qua
            slots[d.isoformat()] = list(WORK_SLOTS)   # "2026-06-30": [các giờ]
            added += 1
        d += timedelta(days=1)             # sang ngày kế tiếp
    return slots

print(generate_available_slots(2))
```
Chạy sẽ thấy 2 ngày tới (trừ CN), mỗi ngày kèm list giờ.

**Giải thích:**
- `date.today()` = hôm nay; `timedelta(days=1)` = "1 ngày" để cộng/trừ.
- `d.weekday()` trả 0=Thứ 2 ... 6=Chủ nhật.
- `d.isoformat()` → chuỗi `"2026-06-30"`.
- `list(WORK_SLOTS)` tạo **bản sao** của list (để mỗi ngày có list giờ riêng, sửa ngày này
  không ảnh hưởng ngày kia).
- `while dieu_kien:` = lặp **chừng nào còn đúng** (khác `for` lặp theo danh sách).

---

## Điểm nâng cao trong file thật
File [data.py](../../app/data.py) thật có thêm đoạn:
```python
DEPARTMENTS, DOCTORS = _load_catalog()
```
→ nếu có Supabase thì nạp danh mục từ DB, không thì dùng dict tĩnh `_SEED_*`. Lúc học cứ
coi như chỉ có dict tĩnh.

## Bài tập
1. Thêm dịch vụ `tham_my` (tẩy trắng) + 1 bác sĩ cho nó.
2. Cho `generate_available_slots` bỏ qua cả Thứ 7 (gợi ý: `d.weekday() not in (5, 6)`).
