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

## So với `chatbot.py` thật (cập nhật 02/07)

Cùng tư duy, chỉ nhiều ô hơn. Luồng đặt lịch chính (có thêm **ASK_PHONE** — hỏi SĐT sau tên):

```
GREET → TRIAGE → CONFIRM_DEPT → PICK_DOCTOR → PICK_DATE → PICK_TIME
      → ASK_NAME → ASK_PHONE → CONFIRM_BOOKING → DONE
```

Và một **nhánh hủy lịch** riêng (vào từ câu "hủy lịch", "muốn hủy lịch hẹn"…):

```
CANCEL_ASK_PHONE → CANCEL_PICK → CANCEL_CONFIRM → DONE
(hỏi SĐT đã đặt)   (chọn lịch     (chắc chắn hủy?
                    nào để hủy)    → set cancelled + push)
```

### Thứ tự ưu tiên trong `handle_message` (quan trọng!)

Trước khi định tuyến theo state, mỗi tin nhắn đi qua các "cổng" theo đúng thứ tự:

```python
1. "/reset" / "làm lại"          -> reset phiên
2. safety.check_emergency(...)    -> cảnh báo 115, GIỮ NGUYÊN state
3. safety.needs_human_handoff(...)-> chuyển state HANDOFF
4. _is_cancel_request(...)        -> vào nhánh hủy lịch      ┐ chỉ nhận ở state
5. triage.info_question_service() -> trả mô tả dịch vụ       ┘ nhập TỰ DO
6. if state == ... (định tuyến như demo của bạn)
```

👉 Cổng 4–5 chỉ bật ở các state nhập **tự do** (`TRIAGE`, `CONFIRM_DEPT`, `DONE`) — nếu
bật cả lúc đang bấm chọn giờ/nhập tên thì chữ "hủy" (nghĩa là hủy *thao tác*) sẽ bị hiểu
nhầm thành hủy *lịch hẹn*. Đây là bài học hay về **ngữ cảnh quyết định nghĩa**.

### 3 tình huống "đời thật" file mới xử lý

1. **Trùng SĐT** — bấm xác nhận nhưng chính SĐT này đã đặt đúng khung giờ đó
   (`booking` trả `{"duplicate": True, "existing": ...}`): bot hỏi *"hủy lịch cũ rồi đặt
   lịch này nhé?"* — cờ `sess["resume_booking"] = True` để sau khi hủy xong **đặt tiếp
   lịch đang dở**, không bắt người dùng làm lại từ đầu.
2. **Slot vừa bị người khác chiếm**: quay về `PICK_TIME` và **hiện lại** danh sách giờ
   còn trống (`_start_time_pick(prefix=...)`), không chỉ báo lỗi suông.
3. **Fallback than phiền chung** — "đau răng quá" không trúng dịch vụ nào nhưng
   `triage.mentions_dental_discomfort()` nhận ra là chuyện răng miệng → `_dental_followup()`
   đưa danh sách dịch vụ để chọn, thay vì "mình chưa hiểu".

File thật còn gọi `triage` (độ tin cậy → mơ hồ thì đưa 2–3 lựa chọn), `booking` để lưu
lịch, `push` gửi thông báo. Mở [chatbot.py](../app/chatbot.py) đối chiếu `handle_message` —
bạn sẽ nhận ra đúng khung `xu_ly` bạn vừa viết.

## Bài tập
1. Thêm ô `ASK_NAME`: sau khi `yes`, hỏi tên rồi mới `DONE` (nhớ lưu `sess["ten"]`).
2. Thêm guardrail: nếu message chứa "khó thở" → trả cảnh báo gọi 115, **không** đổi state.
3. (Mới) Thêm nhánh hủy mini: ở `DONE`, gõ "hủy" → hỏi "chắc không?" (`CANCEL_CONFIRM`),
   trả lời `yes` thì xóa `sess["dich_vu"]` và về `TRIAGE`. Chú ý: đừng bắt chữ "hủy"
   khi đang ở `CONFIRM` — thử giải thích vì sao.
