# Khối `safety.py` — Lớp an toàn

> Cái phân biệt bot y tế thật với bot thường. Học: hàm trả `True/False`, `any()`, regex
> (biểu thức tìm mẫu), ghi file.

File tập:
```bash
touch hoc/safety_demo.py
```

---

## Bước 1 — Phát hiện cấp cứu

```python
EMERGENCY_PATTERNS = [
    "khó thở nặng", "sưng mặt lan", "chảy máu không cầm", "ngất", "co giật",
]

def check_emergency(text):
    low = text.lower()
    return any(p in low for p in EMERGENCY_PATTERNS)

print(check_emergency("mặt tôi sưng mặt lan và khó nuốt"))   # True
print(check_emergency("tôi bị ê buốt răng"))                  # False
```
**Giải thích:**
- `any(... for ... in ...)` = "có **ít nhất một** phần tử thỏa điều kiện không?" → trả `True/False`.
- Đọc như tiếng Anh: *any p in patterns sao cho p in low*.
- Hàm trả bool để chatbot dễ `if check_emergency(...):` rồi chặn.

---

## Bước 2 — Ẩn thông tin cá nhân (PII) bằng regex

Regex = "công thức" mô tả 1 mẫu chuỗi (vd số điện thoại). Dùng module `re`.

```python
import re   # đặt ĐẦU file

PII_PATTERNS = [
    (re.compile(r"\b(0|\+84)\d{8,10}\b"), "[SĐT]"),       # số điện thoại
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[EMAIL]"),  # email
]

def mask_pii(text):
    masked = text
    for pattern, label in PII_PATTERNS:
        masked = pattern.sub(label, masked)   # thay mọi chỗ trùng mẫu bằng nhãn
    return masked

print(mask_pii("tôi tên An, sđt 0901234567, mail a@gmail.com"))
# → tôi tên An, sđt [SĐT], mail [EMAIL]
```
**Giải thích (không cần thuộc regex):**
- `\d` = 1 chữ số, `\d{8,10}` = 8–10 chữ số, `\b` = ranh giới từ.
- `re.compile(...)` "biên dịch" mẫu trước cho nhanh.
- `.sub(thay_the, chuoi)` = thay tất cả chỗ trùng. Mỗi mẫu đi kèm 1 nhãn che.
- Mục đích: **không bao giờ lưu số ĐT/email thật** vào log.

---

## Bước 3 — Chặn đòi chẩn đoán & disclaimer

```python
DIAGNOSIS_REQUEST_PATTERNS = ["tôi bị bệnh gì", "uống thuốc gì", "kê đơn"]

def is_diagnosis_request(text):
    low = text.lower()
    return any(p in low for p in DIAGNOSIS_REQUEST_PATTERNS)

DISCLAIMER = "Lưu ý: tôi chỉ hỗ trợ chọn dịch vụ & đặt lịch, không chẩn đoán/kê đơn."
```
👉 Bot **không được** chẩn đoán/kê đơn (nguy hiểm + phạm luật). Phát hiện được thì trả lời
khéo: "mình không chẩn đoán được, nhưng giúp bạn chọn dịch vụ".

---

## Bước 4 — Ghi audit log (ghi file)

```python
import json
from datetime import datetime

def audit(session_id, role, message, meta=None):
    entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "session": session_id,
        "role": role,                  # "user" hay "bot"
        "message": mask_pii(message),  # LUÔN ẩn PII trước khi lưu
        "meta": meta or {},
    }
    with open("hoc/audit_demo.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

audit("user1", "user", "sđt tôi 0901234567")
print("đã ghi log, mở hoc/audit_demo.jsonl xem")
```
**Giải thích:**
- `open(path, "a")` = mở để **ghi nối thêm** (append), không xóa nội dung cũ.
- `with open(...) as f:` = mở file an toàn, tự đóng khi xong.
- `json.dumps(dict)` = biến dict thành chuỗi JSON; `ensure_ascii=False` để giữ tiếng Việt có dấu.
- Mỗi dòng 1 JSON → định dạng `.jsonl` (JSON Lines), dễ đọc/ghi từng dòng.

---

## Bài tập
1. Thêm mẫu CCCD (12 chữ số) vào `PII_PATTERNS`.
2. Viết hàm `needs_human_handoff(text)` trả `True` nếu câu chứa "gặp nhân viên"/"người thật".
