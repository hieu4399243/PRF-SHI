# Khối `push.py` — Gửi thông báo (push notification)

> Học: phân loại phần tử bằng vòng lặp, gọi API qua HTTP (khái niệm), và mẹo "outbox" để
> test khi chưa có điện thoại thật.

File tập:
```bash
touch hoc/push_demo.py
```

---

## Bối cảnh
- App điện thoại xin quyền thông báo → nhận 1 **token** dạng `ExponentPushToken[...]`.
- App gửi token lên server (`/api/register-push`) → server lưu lại theo người dùng.
- Khi đặt lịch / tới giờ nhắc → server gửi token + nội dung tới **Expo Push Service** →
  Expo đẩy thông báo xuống máy.

---

## Bước 1 — Lưu / lấy token (bản demo bằng dict)

```python
# { "người dùng": [danh sách token thiết bị] }
TOKENS = {}

def register_token(user, token):
    if not token:
        return
    TOKENS.setdefault(user, [])      # nếu chưa có user thì tạo list rỗng
    if token not in TOKENS[user]:    # tránh lưu trùng
        TOKENS[user].append(token)

def get_tokens(user):
    return TOKENS.get(user, [])

register_token("user1", "ExponentPushToken[ABC]")
register_token("user1", "ExponentPushToken[ABC]")   # trùng → bỏ qua
print(get_tokens("user1"))    # ['ExponentPushToken[ABC]']
```
**Giải thích:** `dict.setdefault(key, [])` = "nếu chưa có key thì gán bằng []". Giúp tránh
lỗi khi `append` vào key chưa tồn tại.

---

## Bước 2 — Tách token thật / token giả & "outbox"

Khi đang code mà chưa có điện thoại, ta dùng token giả và **ghi ra file outbox** thay vì
gửi thật — vẫn kiểm tra được "đáng lẽ gửi gì".

```python
import json
from datetime import datetime

def la_token_that(t):
    return t.startswith("ExponentPushToken[") or t.startswith("ExpoPushToken[")

def send_push(tokens, title, body):
    if isinstance(tokens, str):     # lỡ truyền 1 chuỗi → bọc thành list
        tokens = [tokens]
    that = [t for t in tokens if la_token_that(t)]
    gia  = [t for t in tokens if not la_token_that(t)]

    # token giả → ghi file để xem (demo)
    for t in gia:
        with open("hoc/push_outbox_demo.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"to": t, "title": title, "body": body},
                               ensure_ascii=False) + "\n")

    # token thật → (ở file thật) gọi HTTP tới Expo. Demo chỉ in ra.
    for t in that:
        print(f"[GỬI THẬT] {t}: {title} - {body}")

    return {"that": len(that), "gia": len(gia)}

print(send_push(["ExponentPushToken[ABC]", "TOKEN-GIA"], "Đặt lịch OK", "Mã SHI-123"))
print("Mở hoc/push_outbox_demo.jsonl để xem token giả")
```
**Giải thích:**
- `str.startswith("...")` = chuỗi có **bắt đầu bằng** mẫu không.
- `isinstance(x, str)` = kiểm tra kiểu dữ liệu (đề phòng truyền nhầm 1 chuỗi thay vì list).
- Tách `that`/`gia` bằng 2 list comprehension có điều kiện ngược nhau.

---

## Bước 3 — Gửi thật ở file thực (chỉ cần hiểu ý)

File [push.py](../../app/push.py) thật, phần token thật, gửi qua HTTP:
```python
import urllib.request
req = urllib.request.Request(EXPO_PUSH_URL, data=..., headers=..., method="POST")
urllib.request.urlopen(req, timeout=10)
```
👉 Đây là cách Python **gọi 1 API trên mạng**: đóng gói dữ liệu JSON, POST lên URL của Expo.
Lỗi mạng thì cũng ghi outbox để thử lại — không làm sập luồng đặt lịch.

> Token & lưu trữ ở file thật đi qua `storage.py` (JSON/Supabase), không lưu trong biến như demo.

## Bài tập
1. Thêm tham số `data` (dict) vào `send_push` và ghi kèm vào outbox.
2. Viết hàm `unregister_token(user, token)` để gỡ 1 token (gợi ý: `list.remove`).
