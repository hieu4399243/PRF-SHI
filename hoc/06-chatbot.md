# Khối `chatbot.py` — Máy trạng thái (khó nhất, nhưng "aha" nhất)

> Đây là "nhạc trưởng" nối triage + booking + safety thành hội thoại nhiều bước. Khái niệm
> cốt lõi: **STATE (đang ở bước nào)**. Học: dict làm bộ nhớ, định tuyến theo state, hàm gọi hàm.

File tập:
```bash
touch hoc/chatbot_demo.py
```
Ta sẽ viết 1 chatbot mini **tự chạy được**, luồng rút gọn:
`GREET → TRIAGE → CONFIRM → DONE`.

---

## Ý tưởng: hội thoại = trò chơi đi qua các "ô"

Người dùng luôn đứng ở 1 **ô (state)**. Mỗi lần họ nhắn:
1. Xem họ đang ở ô nào.
2. Xử lý theo ô đó.
3. **Đẩy sang ô kế tiếp** và nhớ lại.

Bot không "thông minh đoán" — nó chỉ làm đúng việc của ô hiện tại. Đơn giản mà chắc.

---

## Bước 1 — Bộ nhớ phiên (SESSIONS)

Mỗi người dùng cần 1 "phiếu" nhớ họ đang ở đâu, đã chọn gì.

```python
SESSIONS = {}   # { "id người dùng": {state, dich_vu, ...} }

def phien_moi():
    return {"state": "GREET", "dich_vu": None}

def lay_phien(uid):
    if uid not in SESSIONS:          # lần đầu gặp → tạo phiếu mới
        SESSIONS[uid] = phien_moi()
    return SESSIONS[uid]
```
**Giải thích:** `SESSIONS` là dict chứa nhiều phiên. Khóa là id người dùng, giá trị là 1
dict nhớ trạng thái riêng của họ → 2 người chat cùng lúc không lẫn nhau.

---

## Bước 2 — Triage mini (tái dùng ý từ bài 01)

```python
DICH_VU = {
    "sau_rang":  {"ten": "Sâu răng",  "tu_khoa": ["sâu răng", "ê buốt", "lỗ sâu"]},
    "nha_chu":   {"ten": "Nha chu",   "tu_khoa": ["chảy máu chân răng", "viêm lợi"]},
    "chinh_nha": {"ten": "Chỉnh nha", "tu_khoa": ["niềng răng", "răng hô"]},
}

def doan_dich_vu(cau):
    cau = cau.lower()
    for ma, dv in DICH_VU.items():
        if any(kw in cau for kw in dv["tu_khoa"]):
            return ma, dv["ten"]      # trả mã + tên dịch vụ đầu tiên trúng
    return None, None
```

---

## Bước 3 — Định dạng câu trả lời thống nhất

Mọi bước trả về **cùng 1 khuôn**: lời nói + nút bấm + ô kế tiếp.

```python
def tra_loi(text, options=None, state=None):
    return {"reply": text, "options": options or [], "state": state}
```
👉 `options` là list các nút, mỗi nút `{"label": chữ hiện, "value": giá trị gửi đi}`.

---

## Bước 4 — Hàm trung tâm: định tuyến theo state

```python
def xu_ly(uid, message):
    sess = lay_phien(uid)
    state = sess["state"]

    if state == "TRIAGE":
        ma, ten = doan_dich_vu(message)
        if ma is None:
            return _set(sess, tra_loi("Mình chưa rõ, bạn mô tả lại triệu chứng nhé.",
                                      state="TRIAGE"))
        sess["dich_vu"] = ma
        return _set(sess, tra_loi(
            f"Bạn nên dùng dịch vụ: {ten}. Đặt lịch nhé?",
            options=[{"label": "Đồng ý", "value": "yes"},
                     {"label": "Mô tả lại", "value": "no"}],
            state="CONFIRM"))

    if state == "CONFIRM":
        if message.lower() == "yes":
            return _set(sess, tra_loi("Đã ghi nhận! (demo dừng ở đây). Gõ 'lại' để thử tiếp.",
                                      state="DONE"))
        return _set(sess, tra_loi("Ok, bạn mô tả lại triệu chứng.", state="TRIAGE"))

    if state == "DONE":
        if message.lower() == "lại":
            SESSIONS[uid] = phien_moi()
            return _set(SESSIONS[uid], tra_loi("Bắt đầu lại. Bạn bị sao?", state="TRIAGE"))
        return tra_loi("Đã xong. Gõ 'lại' để thử tiếp.", state="DONE")

    # GREET hoặc state lạ → chào
    return _set(sess, tra_loi("Chào bạn! Bạn đang gặp vấn đề răng miệng gì?", state="TRIAGE"))


def _set(sess, resp):
    """Lưu state mới vào phiên rồi trả resp (để lượt sau định tuyến đúng)."""
    if resp.get("state"):
        sess["state"] = resp["state"]
    return resp
```
**Giải thích chỗ hay rối:**
- Mỗi `if state == "...":` là 1 "ô". Trong ô, xử xong thì trả `tra_loi(..., state="Ô_KẾ")`.
- `_set` ghi `state` mới vào `sess` → lần sau `xu_ly` chạy đúng nhánh. **Đây là mấu chốt**
  làm hội thoại "đi tiếp" thay vì lặp lại mãi 1 chỗ.
- Bắt đầu ở `GREET`: lượt đầu rơi xuống nhánh cuối → chào + chuyển sang `TRIAGE`.

---

## Bước 5 — Chạy thử bằng vòng chat trong terminal

```python
if __name__ == "__main__":
    uid = "me"
    print("BOT:", xu_ly(uid, "")["reply"])      # mở màn (GREET)
    while True:
        msg = input("BẠN: ")                     # nhập từ bàn phím
        if msg == "thoát":
            break
        resp = xu_ly(uid, msg)
        print("BOT:", resp["reply"])
        if resp["options"]:
            print("   nút:", [o["value"] for o in resp["options"]])
```
Chạy:
```bash
./.venv/bin/python hoc/chatbot_demo.py
```
Thử lần lượt: `tôi bị sâu răng` → `yes` → `lại` → `niềng răng` ... Gõ `thoát` để dừng.

**Giải thích:** `input("BẠN: ")` dừng chờ bạn gõ. `while True:` lặp vô hạn tới khi `break`.

---

## So với `chatbot.py` thật

Cùng tư duy, chỉ nhiều ô hơn:
`GREET → TRIAGE → CONFIRM_DEPT → PICK_DOCTOR → PICK_DATE → PICK_TIME → ASK_NAME → CONFIRM_BOOKING → DONE`

Và **ưu tiên guardrail trước mọi ô**:
```python
if safety.check_emergency(message): ...   # cấp cứu chặn hết
if safety.needs_human_handoff(message): ...
```
File thật còn gọi `triage` (có độ tin cậy → khi mơ hồ thì đưa 2–3 lựa chọn), `booking` để
lưu lịch, `push` để gửi thông báo. Mở [chatbot.py](../chatbot.py) đối chiếu hàm
`handle_message` — bạn sẽ nhận ra đúng khung `xu_ly` bạn vừa viết.

## Bài tập
1. Thêm ô `ASK_NAME`: sau khi `yes`, hỏi tên rồi mới `DONE` (nhớ lưu `sess["ten"]`).
2. Thêm guardrail: nếu message chứa "khó thở" → trả cảnh báo gọi 115, **không** đổi state.
