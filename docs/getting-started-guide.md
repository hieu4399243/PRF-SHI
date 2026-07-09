# Hướng dẫn dựng dự án Nha khoa SHI từ đầu (chi tiết, cho người mới)

Tài liệu này có **2 phần**, tùy bạn muốn gì:

| Bạn muốn | Đọc phần | Mất khoảng |
|----------|----------|------------|
| **Chạy được** dự án có sẵn trên máy mình (backend → DB → app điện thoại) | [Phần A](#phần-a--chạy-dự-án-có-sẵn) | 30–60 phút |
| **Tự xây lại từ số 0** để hiểu code, biết cách tạo API, viết được cái tương tự | [Phần B](#phần-b--tự-xây-lại-từ-số-0) | vài buổi |

> Muốn hiểu **bức tranh tổng** (khối nào nói chuyện với khối nào) thì xem [system-architecture.md](system-architecture.md).

---

# PHẦN A — Chạy dự án có sẵn

Đi **từ máy trắng → chạy được toàn bộ**. Mỗi bước có lệnh copy-paste và cách kiểm tra
"đã đúng chưa".

Mục lục:
1. [Cài công cụ](#a1-cài-công-cụ)
2. [Lấy mã nguồn & môi trường ảo](#a2-lấy-mã-nguồn--môi-trường-ảo)
3. [Chạy backend (chế độ file JSON)](#a3-chạy-backend-chế-độ-file-json)
4. [Thử nhanh backend](#a4-thử-nhanh-backend)
4a. [Chạy bộ test](#a4a-chạy-bộ-test-tuỳ-chọn)
4b. [Trang quản trị](#a4b-trang-quản-trị-cho-admin/bác-sĩ)
5. [Nối Database Supabase](#a5-nối-database-supabase)
6. [Chạy app điện thoại (Expo)](#a6-chạy-app-điện-thoại-expo)
7. [Worker nhắc lịch](#a7-worker-nhắc-lịch)
8. [Đánh giá AI](#a8-đánh-giá-ai)
9. [Chia sẻ cho người khác](#a9-chia-sẻ-cho-người-khác)
10. [Lỗi hay gặp](#a10-lỗi-hay-gặp)

---

## A1. Cài công cụ

| Công cụ | Để làm gì | Kiểm tra |
|--------|-----------|----------|
| **Python 3.10+** | Chạy backend | `python3 --version` |
| **Node.js 18+** + npm | Chạy app điện thoại | `node -v` |
| **VS Code** | Soạn code | (đang dùng) |
| **Git** (tùy chọn) | Tải/lưu mã nguồn | `git --version` |
| **Expo Go** (điện thoại) | Mở app native | cài từ App Store / CH Play |

> macOS: nếu chưa có Python/Node, cài nhanh bằng Homebrew: `brew install python node`.

---

## A2. Lấy mã nguồn & môi trường ảo

```bash
cd /Users/hieutm3/Desktop/PRF-SHI     # vào thư mục dự án

# Tạo "môi trường ảo" — hộp riêng chứa thư viện cho dự án này
python3 -m venv .venv

# Cài thư viện backend (đọc từ requirements.txt)
./.venv/bin/pip install -r requirements.txt
```
**Kiểm tra đúng:** lệnh cuối in `Successfully installed Flask ... psycopg ... python-dotenv ...`.

> Vì sao `./.venv/bin/python` mà không phải `python`? Để chắc chắn dùng Python **trong**
> môi trường ảo (có sẵn thư viện), không phải Python hệ thống.

---

## A3. Chạy backend (chế độ file JSON)

Lần đầu cứ chạy **không cần database** cho đơn giản — app tự lưu vào file JSON.

```bash
PORT=5001 ./.venv/bin/python app.py
```
**Kết quả đúng:** thấy dòng
```
[storage] Chế độ lưu trữ: file JSON (local)
 * Running on http://0.0.0.0:5001
```
Mở trình duyệt vào **http://127.0.0.1:5001** → hiện giao diện chat "Trợ lý Nha khoa SHI". 🎉

> macOS chiếm cổng 5000 (AirPlay) nên ta dùng **5001**. Muốn cổng khác: đổi `PORT=5002`.
> Dừng server: bấm `Ctrl + C`.

---

## A4. Thử nhanh backend

Trên giao diện web, gõ thử:
- `răng tôi bị sâu và ê buốt khi ăn ngọt` → gợi ý **Trám răng / Sâu răng** → bấm đặt lịch.
- `toi muon nieng rang` (không dấu) → **Chỉnh nha**.
- `mặt tôi sưng mặt lan và khó nuốt` → cảnh báo **cấp cứu 115**.
- `cho tôi gặp nhân viên` → chuyển người thật.

Hoặc test API bằng dòng lệnh (mở Terminal thứ 2, giữ server chạy):
```bash
curl -X POST http://127.0.0.1:5001/api/start -H "Content-Type: application/json" -d '{}'
```
Nhận về JSON có `reply` và `session` là backend OK.

File sinh ra khi chạy: `appointments.json` (lịch hẹn), `audit_log.jsonl` (log đã ẩn PII).

---

## A4a. Chạy bộ test (tuỳ chọn)

Dự án có bộ test để kiểm tra **triage, booking, safety, reminder, chatbot sessions** hoạt động đúng:
```bash
# Chạy tất cả test
./.venv/bin/python -m pytest tests/ -v

# Hoặc chạy test riêng từng khối
./.venv/bin/python -m pytest tests/test_safety.py -v
./.venv/bin/python -m pytest tests/test_booking.py -v
```
**Khi nào chạy:** trước khi commit khi sửa logic triage/booking/safety/reminder, để tránh regression.

---

## A4b. Trang quản trị cho admin/bác sĩ

Chatbot (`http://127.0.0.1:5001`) dành cho **bệnh nhân đặt lịch**. Ngoài ra có một trang riêng
cho **admin/bác sĩ** xem lại lịch đã đặt & lịch làm việc:

1. Giữ server đang chạy, mở **http://127.0.0.1:5001/admin**.
2. Nhập **khóa truy cập**. Mặc định demo là `shi-admin-demo`.
   - Đổi khóa: thêm dòng `ADMIN_KEY=khoa-cua-ban` vào file `.env` rồi chạy lại server.
3. Sau khi vào, có 2 tab:
   - **📋 Danh sách lịch hẹn** — lọc theo ngày / bác sĩ / trạng thái / SĐT; xem thống kê nhanh
     (tổng, đã xác nhận, đã hủy); bấm **Hủy** để hủy một lịch.
   - **🗓️ Lịch làm việc bác sĩ** — chọn bác sĩ + ngày → xem từng khung giờ **bận** (ai đặt) hay **trống**.

> Trang admin chỉ **đọc** lịch bệnh nhân đã đặt (không tạo dữ liệu mới), dùng chung nguồn dữ
> liệu với chatbot nên chạy đúng cả chế độ file JSON lẫn Supabase. Muốn thấy dữ liệu, hãy đặt
> vài lịch bằng chatbot trước.

Test nhanh bằng dòng lệnh (khóa qua header hoặc `?key=`):
```bash
curl "http://127.0.0.1:5001/api/admin/appointments?status=confirmed&key=shi-admin-demo"
```

---

## A5. Nối Database Supabase

Làm bước này khi muốn dữ liệu **bền vững + quản lý online** (không mất khi tắt máy).

### A5.1. Tạo project Supabase
- Vào https://supabase.com → **New project** (chọn region **Singapore** cho gần VN).
- Đặt **Database Password** (nhớ kỹ).

### A5.2. Lấy connection string
- **Settings → Database → Connection string** → tab **Connection pooler** (Transaction, cổng `6543`).
- Dạng: `postgresql://postgres.xxxx:[PASSWORD]@aws-...pooler.supabase.com:6543/postgres`

### A5.3. Cấu hình `.env`
```bash
cp .env.example .env      # tạo file .env (nếu chưa có)
```
Mở `.env`, điền:
```
DATABASE_URL=postgresql://postgres.xxxx:matkhau-that@aws-...pooler.supabase.com:6543/postgres
SECRET_KEY=mot-chuoi-ngau-nhien-bat-ky
```

### A5.4. Tạo bảng + đẩy dữ liệu lên
```bash
./.venv/bin/python scripts/migrate_to_supabase.py
```
**Kết quả đúng:**
```
✅ Đã tạo/đảm bảo bảng trên Postgres.
✅ Đã nạp danh mục: 9 dịch vụ, 11 nha sĩ ...
✅ Đã nạp ... lịch hẹn ... device token.
```

### A5.5. Chạy lại app
```bash
PORT=5001 ./.venv/bin/python app.py
# giờ in: [storage] Chế độ lưu trữ: Postgres/Supabase
```
Mở **Supabase → Table editor** thấy 4 bảng `appointments`, `device_tokens`, `services`,
`doctors`. Từ đây sửa danh mục online (xong **restart app**).

> Muốn quay lại file JSON: xóa/để trống dòng `DATABASE_URL` trong `.env`.
> Chi tiết & FAQ: [database-storage-guide.md](database-storage-guide.md).

---

## A6. Chạy app điện thoại (Expo)

```bash
cd mobile
npm install                 # cài thư viện (lần đầu, hơi lâu)
npx expo start -c           # mở, hiện mã QR
```
- Mở **Expo Go** trên điện thoại → quét QR.
- **Quan trọng:** điện thoại và máy tính phải **cùng Wi-Fi**, và `mobile/src/config.js` →
  `API_BASE` phải trỏ về **IP LAN** của máy chạy backend (không phải `127.0.0.1`).

Tự dò & cập nhật IP:
```bash
cd ..            # về thư mục gốc
./setup.sh ip    # tự tìm IP LAN, ghi vào mobile/src/config.js
```
Sau đó **reload** trong Expo Go (lắc máy → Reload).

---

## A7. Worker nhắc lịch

Tiến trình **riêng**, quét lịch hẹn và bắn nhắc trước giờ khám.
```bash
./.venv/bin/python reminder_worker.py --test    # gửi thử mọi nhắc ngay
./.venv/bin/python reminder_worker.py --watch   # chạy nền, quét mỗi 60 giây
```
Chưa có điện thoại thật? Token giả sẽ được ghi vào `outbox/push_outbox.jsonl` để bạn xem.

---

## A8. Đánh giá AI

```bash
./.venv/bin/python eval/evaluate.py
```
In bảng **Accuracy / Macro-F1** cho 2 phiên bản triage (v1 vs v2) và ghi `eval/results.md`.
Báo cáo đầy đủ (để nộp/ trình bày): [BAOCAO_DANHGIA.md](BAOCAO_DANHGIA.md).

---

## A9. Chia sẻ cho người khác

| Mức | Cách | Khi nào |
|-----|------|---------|
| Demo nhanh | `ngrok http 5001` → link tạm (máy phải bật) | cho thầy/bạn xem ngay |
| Vĩnh viễn | Deploy backend lên **Render/Railway** (thêm `gunicorn`, set env `DATABASE_URL`,`SECRET_KEY`) | ai cũng vào bất kỳ lúc nào |
| App cài đặt | `eas build -p android` → file APK | gửi người khác cài |

Vì DB đã ở Supabase nên deploy backend rất gọn — máy bạn tắt vẫn chạy. Khi deploy nhớ đổi
`API_BASE` trong `mobile/src/config.js` sang URL HTTPS công khai.

---

## A10. Lỗi hay gặp

| Triệu chứng | Cách xử lý |
|-------------|-----------|
| `Port 5000 is in use` | Dùng `PORT=5001` (mặc định) hoặc cổng khác |
| App "Không kết nối được máy chủ" | Chạy `./setup.sh ip`, đảm bảo backend đang chạy, **cùng Wi-Fi** |
| `psycopg ... could not connect` | Sai `DATABASE_URL`/mật khẩu; kiểm tra lại connection string Supabase |
| Vẫn chạy file JSON dù đã set DB | Sai tên biến trong `.env` (phải đúng `DATABASE_URL`); chạy lại app |
| Expo Go "incompatible SDK" | Cập nhật Expo Go (project dùng **SDK 54**) |
| `pip install` lỗi | Đảm bảo đã tạo `.venv` và dùng `./.venv/bin/pip` |

---

# PHẦN B — Tự xây lại từ số 0

Phần này trả lời câu hỏi: **"Nếu chưa có gì cả, tôi viết dự án này theo thứ tự nào?
Tạo API như thế nào?"** Mỗi khối có 1 bài học chi tiết trong thư mục [hoc/](hoc/00-muc-luc.md)
— gõ tới đâu chạy thử tới đó. Ở đây là **lộ trình + mốc kiểm tra**.

## B1. Tư duy: xây từ trong ra ngoài

Nguyên tắc: **xây phần "não" trước, "cửa ngõ" (API) sau, giao diện cuối cùng.**
Vì mỗi khối Python có thể chạy thử độc lập bằng `print()`, chưa cần server, chưa cần app.

```
Mốc 1        Mốc 2        Mốc 3           Mốc 4         Mốc 5
triage.py →  data.py  →  chatbot.py  →   app.py    →   mobile/
(phân loại)  booking.py  (máy trạng      (API Flask)   (app điện thoại
             safety.py    thái nối                      gọi API)
                          tất cả)
```

## B2. Lộ trình 5 mốc

### Mốc 1 — Lõi AI: phân loại triệu chứng (`triage.py`)
📖 Bài học: [hoc/01-viet-triage-tu-dau.md](hoc/01-viet-triage-tu-dau.md)

Viết 1 hàm thuần Python: nhận câu `"răng tôi bị sâu"` → trả về nhóm dịch vụ `"Trám răng"`.
Cách làm: mỗi dịch vụ có danh sách **từ khóa**, đếm xem câu khớp từ khóa nào nhiều nhất
(rule-based scoring). Chưa cần Flask, chưa cần gì cả — chỉ 1 file `.py` chạy bằng:
```bash
./.venv/bin/python hoc/triage_demo.py
```
**Đạt mốc khi:** gõ 5–7 câu triệu chứng khác nhau, hàm trả đúng dịch vụ.

### Mốc 2 — Kho dữ liệu + nghiệp vụ (`data.py`, `booking.py`, `safety.py`)
📖 Bài học: [hoc/02-data.md](hoc/02-data.md) → [hoc/03-safety.md](hoc/03-safety.md) →
[hoc/04-booking.md](hoc/04-booking.md)

- `data.py`: dict chứa **dịch vụ, bác sĩ, khung giờ** (ban đầu cứ hard-code, sau mới nối DB).
- `booking.py`: hàm đặt lịch — ghi 1 dict lịch hẹn vào file JSON, loại khung giờ đã có người.
- `safety.py`: hàm kiểm tra câu nhập — phát hiện từ khóa **cấp cứu** (→ báo gọi 115),
  che số điện thoại trong log, chặn câu hỏi "kê đơn thuốc".

**Đạt mốc khi:** chạy file tập, đặt được 1 lịch giả vào `appointments.json` và câu
"sưng lan khó thở" bị chặn thành cảnh báo cấp cứu.

### Mốc 3 — Máy trạng thái hội thoại (`chatbot.py`) — khó nhất
📖 Bài học: [hoc/06-chatbot.md](hoc/06-chatbot.md)

Bot là 1 **máy trạng thái**: mỗi phiên (session) nhớ đang ở bước nào, tin nhắn đến thì
xử lý theo bước đó rồi chuyển bước tiếp:
```
GREET → TRIAGE → CONFIRM_DEPT → PICK_DOCTOR → PICK_DATE → PICK_TIME
      → ASK_NAME → ASK_PHONE → CONFIRM_BOOKING → DONE
(+ nhánh hủy lịch: CANCEL_ASK_PHONE → CANCEL_PICK → CANCEL_CONFIRM)
```
Cốt lõi chỉ là: dict `SESSIONS[sid] = {"state": ..., "data": ...}` + 1 hàm
`handle_message(sid, text)` với chuỗi `if state == ...`. Khối này **gọi** cả 3 khối trên:
safety kiểm tra trước → triage phân loại → booking chốt lịch.

**Đạt mốc khi:** chat trọn 1 vòng **trong terminal** (vòng lặp `input()`), từ khai triệu
chứng đến chốt lịch, chưa cần web.

### Mốc 4 — Tạo API bằng Flask (`app.py`) ← "tạo API như nào" là đây
📖 Bài học chi tiết từng dòng: [hoc/07-app.md](hoc/07-app.md)

API chỉ là **lớp vỏ mỏng** bọc quanh chatbot đã chạy được ở Mốc 3. Trình tự:

**Bước 4.1 — Server Flask nhỏ nhất (5 dòng):**
```python
from flask import Flask
app = Flask(__name__)

@app.route("/")                    # ai vào địa chỉ "/" thì chạy hàm dưới
def home():
    return "Server đang chạy!"

app.run(debug=True, port=5001)
```
Chạy rồi mở `http://127.0.0.1:5001` thấy chữ là xong.

**Bước 4.2 — Endpoint nhận & trả JSON:** một API endpoint = 1 hàm có `@app.route`,
đọc JSON client gửi lên, trả JSON về:
```python
from flask import request, jsonify

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True, silent=True) or {}
    message = data.get("message", "")
    resp = chatbot.handle_message(sid, message)   # gọi "não" ở Mốc 3
    return jsonify(resp)
```
Test không cần giao diện, dùng `curl`:
```bash
curl -X POST http://127.0.0.1:5001/api/chat \
     -H "Content-Type: application/json" \
     -d '{"message":"răng tôi bị sâu"}'
```

**Bước 4.3 — Session id (`resolve_sid`):** để bot biết "ai đang nói" — web dùng cookie,
app điện thoại gửi kèm `session` trong body JSON. Xem hàm `resolve_sid()` trong `app.py`.

**Bước 4.4 — Đủ bộ endpoint của dự án:**

| Method | Path | Việc | Ai gọi |
|--------|------|------|--------|
| GET | `/` | Trang web demo | trình duyệt |
| POST | `/api/start` | Mở phiên mới, trả `session` + lời chào | web + app |
| POST | `/api/chat` | Gửi tin nhắn, nhận trả lời | web + app |
| POST | `/api/register-push` | App gửi token nhận thông báo | app |
| GET | `/api/ics/<code>` | Tải file lịch `.ics` của 1 lịch hẹn | app |

**Đạt mốc khi:** `curl /api/start` rồi `curl /api/chat` (kèm `session` nhận được) đi
trọn vòng đặt lịch y như Mốc 3 nhưng qua HTTP.

### Mốc 5 — Giao diện: web rồi mobile
- **Web** (`templates/index.html`): 1 trang HTML + JS `fetch()` gọi 2 endpoint trên,
  vẽ bong bóng chat. Flask trả trang này ở route `GET /`.
- **Mobile** (`mobile/`): app Expo/React Native làm đúng việc đó nhưng bằng
  `fetch(API_BASE + "/api/chat", ...)` — xem `mobile/src/api.js`. Vì điện thoại là máy
  khác nên `API_BASE` phải là **IP LAN** của máy chạy backend (Phần A6).

**Đạt mốc khi:** đặt lịch được từ điện thoại, lịch hiện trong `appointments.json`.

### Mốc 6 (nâng cao, thêm sau khi mọi thứ chạy)
| Tính năng | File | Bài học |
|-----------|------|---------|
| Push notification (Expo Push) | `push.py` | [hoc/05-push.md](hoc/05-push.md) |
| Worker quét lịch → bắn nhắc | `reminder_worker.py` | [hoc/08-storage-calendar-reminder.md](hoc/08-storage-calendar-reminder.md) |
| File lịch `.ics` | `calendar_ics.py` | như trên |
| Đổi file JSON → Postgres/Supabase | `storage.py` | như trên + [database-storage-guide.md](database-storage-guide.md) |
| Đo chất lượng AI (Precision/Recall/F1) | `eval/` | [BAOCAO_DANHGIA.md](BAOCAO_DANHGIA.md) |

## B3. Vì sao thứ tự này?

1. **Mỗi mốc chạy thử được ngay** — không phải viết 5 file rồi mới biết sai ở đâu.
2. **API viết sau cùng cực nhanh** — vì logic đã xong, API chỉ nhận JSON → gọi hàm → trả JSON.
3. **Giao diện tách khỏi logic** — web hỏng không ảnh hưởng bot; sau này thay UI thoải mái.

> Quy ước khi học: tạo file tập trong `hoc/` (vd `hoc/triage_demo.py`) để **không đụng
> code thật**. Hiểu rồi mở file thật ở thư mục gốc đối chiếu.

---

## Tóm tắt 1 màn hình (chạy hằng ngày)
```bash
# Lần đầu
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt

# (tùy chọn) bật Supabase
cp .env.example .env            # rồi điền DATABASE_URL
./.venv/bin/python scripts/migrate_to_supabase.py

# Chạy hằng ngày
PORT=5001 ./.venv/bin/python app.py                 # backend
./.venv/bin/python reminder_worker.py --watch       # worker nhắc (tùy chọn)
cd mobile && npx expo start -c                       # app điện thoại
```

- Bệnh nhân: **http://127.0.0.1:5001**
- Admin/bác sĩ: **http://127.0.0.1:5001/admin** (khóa demo `shi-admin-demo`)
