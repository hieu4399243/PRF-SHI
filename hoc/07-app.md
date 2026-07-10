# Khối `app.py` — Cửa ngõ API (Flask)

> Khối mỏng nhất: nhận yêu cầu HTTP từ web/app → gọi chatbot → trả JSON. Học: route, nhận
> JSON, trả JSON, session.

File tập:
```bash
touch hoc/app_demo.py
```
Chạy: `./.venv/bin/python hoc/app_demo.py` rồi mở `http://127.0.0.1:5005`.

---

## Bước 1 — Server nhỏ nhất

```python
from flask import Flask, request, jsonify

app = Flask(__name__)            # tạo ứng dụng web

@app.route("/")                  # ai vào "/" thì chạy hàm dưới
def home():
    return "Server đang chạy!"

if __name__ == "__main__":
    app.run(debug=True, port=5005)
```
**Giải thích:**
- `@app.route("/")` là **decorator** — "dán" địa chỉ URL vào hàm. Vào URL đó → Flask gọi hàm.
- `app.run(...)` khởi động server. `debug=True` = tự nạp lại khi sửa code + hiện lỗi chi tiết.

---

## Bước 2 — API nhận & trả JSON (giống `/api/chat`)

```python
@app.route("/api/chat", methods=["POST"])   # POST = client GỬI dữ liệu lên
def chat():
    data = request.get_json(force=True, silent=True) or {}   # đọc JSON client gửi
    message = data.get("message", "")
    # (ở app thật: resp = chatbot.handle_message(sid, message))
    resp = {"reply": f"Bạn vừa nói: {message}", "options": []}
    return jsonify(resp)         # trả về JSON
```
Test bằng Terminal khác (giữ server đang chạy):
```bash
curl -X POST http://127.0.0.1:5005/api/chat \
     -H "Content-Type: application/json" \
     -d '{"message":"răng tôi bị sâu"}'
```
Kỳ vọng nhận: `{"options":[],"reply":"Bạn vừa nói: răng tôi bị sâu"}`

**Giải thích:**
- `methods=["POST"]`: route này chỉ nhận POST (gửi dữ liệu), khác GET (chỉ xem).
- `request.get_json()` lấy dữ liệu JSON client gửi; `or {}` để khỏi lỗi khi rỗng.
- `jsonify(dict)` biến dict Python → phản hồi JSON đúng chuẩn.
- `curl` là công cụ gọi thử API từ dòng lệnh.

---

## Bước 3 — Nhớ "ai đang nói" (session id)

Web dùng cookie, app native gửi `session` trong body. File thật:
```python
def resolve_sid(data):
    sid = data.get("session") or session.get("sid")   # app native / web
    if not sid:
        sid = uuid.uuid4().hex                          # chưa có → tạo id mới
    session["sid"] = sid
    return sid
```
👉 `sid` này được truyền vào `chatbot.handle_message(sid, message)` để bot lấy đúng phiên
(`SESSIONS[sid]`) — khớp với bài 06.

---

## Các route trong `app.py` thật
| Route | Việc |
|-------|------|
| `GET /` | Trả trang web demo (`templates/index.html`) |
| `POST /api/start` | Bắt đầu phiên → lời chào |
| `POST /api/chat` | Gửi tin nhắn → phản hồi bot |
| `POST /api/register-push` | App gửi device token |
| `GET /api/ics/<code>` | Tải file lịch `.ics` |

Mở [app.py](../app/app.py) — bạn sẽ thấy mỗi route chỉ vài dòng: lấy `sid` → gọi chatbot/booking
→ `jsonify`. **app.py không chứa logic nghiệp vụ**, nó chỉ là người gác cổng.

## Bài tập
1. Thêm route `GET /api/health` trả `{"ok": True}` (để kiểm tra server sống).
2. Nối thật: `import` chatbot demo ở bài 06 và gọi trong `/api/chat`.
