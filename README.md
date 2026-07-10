# Trợ lý Nha khoa SHI

Chatbot tiếng Việt cho **một phòng khám nha khoa**: bệnh nhân mô tả triệu chứng răng
miệng → bot phân loại **đúng nhóm dịch vụ** (triage) → đặt lịch → nhắc lịch qua
push/`.ics`. Đề tài demo (PRF/SHI), có **hệ thống đánh giá AI** (Precision/Recall/F1,
so sánh v1 vs v2) ở `eval/`.

## Kiến trúc

Hai phần, nối nhau qua REST JSON:

- **Backend** — Flask (Python), package `app/`. Phục vụ web demo (`app/templates/index.html`),
  trang quản trị (`/admin`), và các endpoint `/api/*` cho app native.
- **Mobile** — React Native / Expo (SDK 54), thư mục `mobile/`. Mở bằng **Expo Go** + QR.

```
┌─────────────────────┐      HTTP /api/*      ┌──────────────────────────┐
│  App native (Expo)  │  ───────────────────► │  Backend Flask (app/)   │
│  mobile/  (RN UI)   │  ◄─── push token ──── │  triage · booking · safe │
└─────────────────────┘                       └────────────┬─────────────┘
        ▲   push notification (Expo Push)                   │
        └───────────────────────────────────────────────────┘
                       app/reminder_worker.py (nhắc lịch)
```

Mobile gọi backend qua IP LAN cấu hình ở `mobile/src/config.js` (`API_BASE`).
Phải **cùng Wi-Fi** vì đó là IP nội bộ.

## Sơ đồ file (backend — `app/`)

| File | Vai trò |
|------|---------|
| `app/app.py` | Flask app + routes (public + admin). Chạy `host=0.0.0.0 port=5001`. |
| `app/chatbot.py` | Máy trạng thái hội thoại. Session **in-memory** (dict `SESSIONS`). State: GREET→TRIAGE→CONFIRM_DEPT→PICK_DOCTOR→PICK_DATE→PICK_TIME→ASK_NAME→CONFIRM_BOOKING→DONE. |
| `app/triage.py` | "Hàm lượng AI": phân loại triệu chứng → **nhóm dịch vụ nha khoa**. Rule-based scoring theo keyword, có **2 phiên bản** (`v1` có dấu, `v2` không phân biệt dấu — mặc định); khớp theo ranh giới từ. `classify_with_llm()` là điểm cắm LLM (Claude). |
| `app/safety.py` | Guardrails: lọc PII, phát hiện cấp cứu (→ 115), chặn chẩn đoán/kê đơn, human handoff, **audit log** `app/data/audit_log.jsonl` (Nghị định 13/2023). |
| `app/booking.py` | Đặt lịch, lưu `app/data/appointments.json`, loại khung giờ đã đặt. |
| `app/data.py` | `DEPARTMENTS` (nhóm dịch vụ nha khoa) + `DOCTORS` (nha sĩ) + khung giờ. Có `DATABASE_URL` thì **nạp danh mục từ Supabase**, không thì dùng dict seed tĩnh. |
| `app/storage.py` | Lớp lưu trữ: `DATABASE_URL` → Postgres/Supabase, không có → file JSON trong `app/data/`. Bảng `appointments`, `device_tokens`, `services`, `doctors`. |
| `app/push.py` | Gửi push qua **Expo Push Service** (miễn phí, không cần key). Token lưu `app/data/device_tokens.json`. Không có token → ghi `app/data/outbox/push_outbox.jsonl`. |
| `app/reminder_worker.py` | Quét lịch → bắn nhắc. `--once` (cron), `--watch` (nền 60s), `--test`. Mỗi loại nhắc gửi 1 lần (`reminders_sent`). |
| `app/calendar_ics.py` | Sinh file `.ics` (có VALARM) — thêm vào Google/Apple/Outlook Calendar, không cần OAuth. |
| `app/templates/index.html` | Web demo (bản thay thế nhanh cho app native). |
| `app/templates/admin.html` | Trang quản trị (chỉ đọc lịch đã đặt/lịch làm việc), khóa bằng `ADMIN_KEY`. |
| `eval/` | **Đánh giá AI**: `dataset.jsonl` / `dataset_complex.jsonl` (câu gán nhãn), `evaluate.py` (Accuracy/Precision/Recall/Macro-F1, v1 vs v2). |
| `scripts/migrate_to_supabase.py` | Đưa dữ liệu từ file JSON lên Postgres/Supabase. |
| `scripts/clean_stale_appointments.py` | Dọn lịch hẹn quá hạn/không hợp lệ. |
| `tests/` | Bộ test pytest cho toàn bộ backend (booking, safety, chatbot, push, storage, ...). |
| `Dockerfile` | Image gunicorn (python:3.11-slim, non-root) cho service `web`/`worker`. |
| `docker-compose.yml` | Orchestrate `web` + `worker` + `db` (Postgres 16 local) — xem mục "Chạy bằng Docker". |

## API endpoints (`app/app.py`)

| Method | Path | Việc |
|--------|------|------|
| GET | `/` | Web demo (`app/templates/index.html`) |
| POST | `/api/start` | Bắt đầu phiên, trả `session` |
| POST | `/api/chat` | Gửi `message`, nhận phản hồi bot |
| POST | `/api/register-push` | App native gửi Expo `token` |
| GET | `/api/ics/<code>` | Tải file `.ics` của 1 lịch hẹn |
| GET | `/admin` | Trang quản trị (đọc lịch/lịch làm việc) |
| GET | `/api/admin/appointments` | Danh sách lịch hẹn (yêu cầu header `X-Admin-Key`) |
| GET | `/api/admin/schedule` | Lịch làm việc nha sĩ (yêu cầu `X-Admin-Key`) |
| GET | `/api/admin/meta` | Metadata phòng khám cho trang quản trị |
| POST | `/api/admin/cancel` | Hủy lịch hẹn (yêu cầu `X-Admin-Key`) |

Session id: app native truyền `session` trong body JSON; web dùng cookie. Xem `resolve_sid()` trong `app/app.py`.

## Cài đặt & chạy local

```bash
# 1. Backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
PORT=5001 .venv/bin/python -m app.app        # API tại http://0.0.0.0:5001

# 2. Worker nhắc lịch (tùy chọn)
.venv/bin/python -m app.reminder_worker --watch   # quét mỗi 60s
.venv/bin/python -m app.reminder_worker --test    # gửi thử mọi loại nhắc ngay

# 3. App native
cd mobile
npm install
npx expo start -c              # quét QR bằng Expo Go trên điện thoại
```

Hoặc dùng script cài đặt gộp:

```bash
./setup.sh              # cài backend (Python) + app (npm) + tự dò IP LAN
./setup.sh ip            # đổi Wi-Fi -> chỉ dò lại IP và cập nhật mobile/src/config.js
./setup.sh backend       # chỉ cài backend Python
./setup.sh mobile        # chỉ cài app native (npm)
```

Nhớ sửa `mobile/src/config.js` → `API_BASE` thành IP LAN của máy chạy backend (hoặc
chạy `./setup.sh ip` để tự cập nhật). Chi tiết cấu hình app native: `mobile/README.md`.

> Lưu ý: macOS chiếm cổng 5000 (AirPlay Receiver) → backend chạy ở cổng 5001.

## Biến môi trường

Sao chép `.env.example` thành `.env` rồi điền giá trị thật (xem file để biết chi tiết
từng biến):

- `DATABASE_URL` — kết nối Postgres/Supabase; bỏ trống thì app dùng file JSON local.
- `SECRET_KEY` — khóa Flask session; production **phải** đặt chuỗi ngẫu nhiên.
- `ADMIN_KEY` — khóa truy cập `/api/admin/*`; production **phải** đổi khỏi giá trị demo.

## Chạy bằng Docker

Cách khác để chạy backend, không cần cài Python/venv trên máy. Gồm 3 service:
`web` (gunicorn), `worker` (nhắc lịch, `--watch`), `db` (Postgres 16 local).

```bash
cp .env.docker.example .env    # điền POSTGRES_PASSWORD, SECRET_KEY, ADMIN_KEY riêng
docker compose up --build -d
docker compose logs -f web     # xem log; Ctrl+C để thoát (service vẫn chạy nền)
docker compose down            # dừng (thêm -v để xóa luôn Postgres + app_data — audit log, outbox)
```

API chạy ở `http://localhost:5001` (map từ container ra máy host) — mobile app native
qua Expo Go vẫn trỏ `API_BASE` vào IP LAN của máy này, không đổi hành vi so với chạy
backend không-Docker (xem mục "Chạy app native").

`.env` ở đây là biến riêng cho Docker Compose (`POSTGRES_DB/USER/PASSWORD` +
`SECRET_KEY`/`ADMIN_KEY`) — khác với `.env` dùng khi chạy `python -m app.app` trực tiếp
(mẫu ở `.env.example`, trỏ `DATABASE_URL` ra Supabase thay vì Postgres local). Muốn dùng
Supabase thay vì Postgres local trong Docker: đổi `DATABASE_URL` của service `web`/`worker`
trong `docker-compose.yml` trỏ ra Supabase, bỏ qua service `db`.

## Thử nhanh

- *"răng tôi bị sâu và ê buốt khi ăn ngọt"* → dịch vụ **Trám răng / Sâu răng** → đặt lịch.
- *"toi muon nieng rang"* (không dấu) → **Chỉnh nha** (nhờ engine v2 không phân biệt dấu).
- *"chảy máu chân răng và hôi miệng"* → **Nha chu**.
- *"mặt tôi sưng mặt lan và khó nuốt"* → cảnh báo **cấp cứu, gọi 115**.
- *"cho tôi gặp nhân viên"* → **chuyển người thật** (handoff).
- Gõ **"làm lại"** để bắt đầu phiên mới.

## Test & đánh giá hệ thống AI

```bash
.venv/bin/python -m pytest                 # bộ test backend (tests/)
.venv/bin/python eval/evaluate.py          # Accuracy/Precision/Recall/Macro-F1 cho v1 & v2
```

`eval/evaluate.py` chạy triage engine trên `eval/dataset.jsonl` (và `dataset_complex.jsonl`),
so với nhãn vàng, in kết quả ra màn hình và ghi bảng chi tiết vào `eval/results.md`.

## File sinh ra khi chạy

- `app/data/appointments.json` — lịch hẹn đã đặt.
- `app/data/device_tokens.json` — token push đã đăng ký.
- `app/data/audit_log.jsonl` — nhật ký hội thoại (đã ẩn PII).
- `app/data/outbox/push_outbox.jsonl` — push chưa gửi được (thiếu token/lỗi mạng).

Khi đặt `DATABASE_URL`, các dữ liệu trên chuyển sang lưu ở Postgres/Supabase thay vì file JSON
(xem `app/storage.py`, `scripts/migrate_to_supabase.py`).

## Thêm vào lịch + nhắc tự động

Sau khi đặt lịch thành công, bệnh nhân có 2 lựa chọn:

- **Thêm vào Lịch (.ics)** — tải file mà `app/calendar_ics.py` sinh ra, thêm được vào
  Lịch iPhone/Mac, Outlook, Google Calendar; kèm **2 lời nhắc** (trước 1 ngày &
  trước 1 giờ) nên app lịch của họ tự **thông báo**. Route: `/api/ics/<mã>`.
- **Thêm vào Google Calendar** — link mở sẵn form tạo sự kiện trên web.

Không cần OAuth / API key, hoạt động trên mọi thiết bị.

## Khoảng trống trước khi lên production

1. **Dev server** — `app/app.py` chạy bằng Flask dev server; production nên dùng `gunicorn`
   và tắt `debug`.
2. **`SECRET_KEY` / `ADMIN_KEY`** — đọc từ env, có fallback demo; production **phải** đặt
   giá trị ngẫu nhiên riêng (xem `.env.example`).
3. **Lưu trữ** — có `DATABASE_URL` thì dùng Postgres/Supabase (bền vững), không thì fallback
   file JSON (local). Session hội thoại vẫn **in-memory** (`app.chatbot.SESSIONS`) → cần
   Redis/DB khi scale nhiều worker.
4. **CORS** — chưa cấu hình; cần thêm khi backend khác origin với client web.
5. **`API_BASE`** — đang là IP LAN; khi deploy phải đổi sang URL HTTPS công khai.

## Nâng cấp (ngoài phạm vi demo)

- `triage.classify_with_llm()` — cắm Claude để NLU tiếng Việt mạnh hơn.
- Đồng bộ 2 chiều Google Calendar bằng OAuth (`google-api-python-client`) — để chặn trùng
  lịch phía bác sĩ.
