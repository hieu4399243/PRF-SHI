---
name: shi-project
description: Bản đồ & kiến thức dự án "AI Health Assistant (SHI)" — backend Flask + app native Expo (đặt lịch khám, triage triệu chứng, nhắc lịch qua push). Dùng skill này khi làm việc với repo PRF-SHI để khỏi đọc lại cả project: kiến trúc, sơ đồ file, API, cách chạy local, cách deploy/share, và các khoảng trống cần vá trước khi lên production hoặc lên store.
---

# AI Health Assistant (SHI)

Trợ lý y tế hội thoại tiếng Việt: bệnh nhân chat mô tả triệu chứng → bot phân khoa
(triage) → đặt lịch khám → nhắc lịch qua push/lịch .ics. Đề tài demo (PRF/SHI).

## Kiến trúc tổng quan

Hai phần, nối nhau qua REST JSON:

- **Backend** — Flask (Python), thư mục gốc. Phục vụ cả web demo (`templates/index.html`)
  lẫn app native qua các endpoint `/api/*`.
- **Mobile** — React Native / Expo (SDK 54), thư mục `mobile/`. Mở bằng **Expo Go** + QR.

Mobile gọi backend qua IP LAN cấu hình ở `mobile/src/config.js` (`API_BASE`).
Phải **cùng Wi-Fi** vì đó là IP nội bộ.

## Sơ đồ file (backend)

| File | Vai trò |
|------|---------|
| `app.py` | Flask app + routes. Chạy `host=0.0.0.0 port=5001 debug=True`. |
| `chatbot.py` | Máy trạng thái hội thoại. Session **in-memory** (dict `SESSIONS`). State: GREET→TRIAGE→CONFIRM_DEPT→PICK_DOCTOR→PICK_DATE→PICK_TIME→ASK_NAME→CONFIRM_BOOKING→DONE. |
| `triage.py` | "Hàm lượng AI": phân loại triệu chứng → khoa. Hiện là **rule-based scoring** theo keyword; có `classify_with_llm()` là điểm cắm LLM (vd Claude) sau này. |
| `safety.py` | Guardrails: lọc PII, phát hiện cấp cứu (→115), chặn chẩn đoán/kê đơn, human handoff, **audit log** `audit_log.jsonl` (NĐ 13/2023). |
| `booking.py` | Đặt lịch, lưu `appointments.json`, loại khung giờ đã đặt. |
| `data.py` | Dữ liệu tĩnh: `DEPARTMENTS`, `DOCTORS`, sinh khung giờ trống. Thật thì thay bằng DB. |
| `push.py` | Gửi push qua **Expo Push Service** (miễn phí, không cần key). Token lưu `device_tokens.json`. Không có token → ghi `outbox/push_outbox.jsonl`. |
| `reminder_worker.py` | Quét lịch → bắn nhắc. `--once` (cron), `--watch` (nền 60s), `--test`. Mỗi loại nhắc gửi 1 lần (`reminders_sent`). |
| `calendar_ics.py` | Sinh file `.ics` (có VALARM) — thêm vào Google/Apple/Outlook Calendar, không cần OAuth. |

## API endpoints (`app.py`)

| Method | Path | Việc |
|--------|------|------|
| GET | `/` | Web demo (`templates/index.html`) |
| POST | `/api/start` | Bắt đầu phiên, trả `session` |
| POST | `/api/chat` | Gửi `message`, nhận phản hồi bot |
| POST | `/api/register-push` | App native gửi Expo `token` |
| GET | `/api/ics/<code>` | Tải file `.ics` của 1 lịch hẹn |

Session id: app native truyền `session` trong body JSON; web dùng cookie. Xem `resolve_sid()`.

## Sơ đồ file (mobile/)

`App.js` (UI chat), `src/api.js` (gọi backend), `src/config.js` (`API_BASE`),
`src/notify.js` + `src/usePush.js` (thông báo/push), `src/calendar.js` (thêm .ics),
`src/html.js`. SDK 54 → cần Expo Go bản mới.

## Chạy local (dev)

3 terminal (xem `SETUP.md`):
```bash
# 1. Backend
PORT=5001 ./.venv/bin/python app.py
# 2. Worker nhắc lịch (tùy chọn)
./.venv/bin/python reminder_worker.py --watch
# 3. App native
cd mobile && npx expo start -c
```
Đổi mạng Wi-Fi → IP đổi → chạy `./setup.sh ip` để cập nhật `config.js`, rồi reload Expo Go.

Lưu ý: macOS chiếm cổng 5000 (AirPlay) → dùng 5001.

## Khoảng trống cần vá trước khi "lên thật" / production

1. **Dev server + `debug=True`** (`app.py:85`) — production phải dùng `gunicorn` và tắt debug.
2. **`secret_key` hard-code** (`app.py:20`) — đưa vào biến môi trường.
3. **Lưu trữ là file JSON + session in-memory** — trên cloud sẽ **mất khi restart/scale**.
   Cần DB (Postgres/SQLite-volume) cho `appointments`, `device_tokens`, session (Redis).
4. **CORS** — chưa cấu hình; khi backend khác origin với client web cần thêm.
5. `API_BASE` đang là IP LAN — khi deploy phải đổi sang URL HTTPS công khai.

## Share cho nhiều người — 3 mức

- **Demo nhanh:** giữ máy bật + `ngrok http 5001` (hoặc `npx expo start --tunnel`) → link tạm.
- **Backend cloud:** deploy lên Render/Railway/Fly.io (thêm `gunicorn` vào `requirements.txt`,
  `Procfile`/start command `gunicorn app:app`), set env `SECRET_KEY`, gắn volume/DB cho dữ liệu.
  Sửa `API_BASE` thành URL HTTPS. App vẫn mở qua Expo Go.
- **App cài đặt thật:** build bằng **EAS** (`eas build`) → APK/AAB (Android) hoặc iOS build.

## Lên "chợ" (App Store / Google Play)

Có, nhưng cần build thật bằng EAS, không qua Expo Go:
- **Google Play:** `eas build -p android` → AAB; tài khoản Play Console **25 USD trả 1 lần**.
- **App Store:** `eas build -p ios` → cần **Apple Developer 99 USD/năm** + máy/CI để submit;
  `eas submit` đẩy lên. Review của Apple với app **y tế** khắt khe (cần disclaimer rõ
  "không thay thế tư vấn y khoa", chính sách quyền riêng tư — hợp với `safety.py`).
- Trước đó backend **bắt buộc** đã ở cloud (HTTPS công khai), không còn IP LAN.
- Chuẩn bị: icon/splash, `app.json` (bundle id, version), privacy policy, xử lý dữ liệu
  sức khỏe (NĐ 13/2023 đã có audit log — tận dụng).

Đường tối thiểu để "nhiều người cài thử" mà chưa cần lên chợ: **EAS build APK Android**
rồi gửi file APK / link cho mọi người cài trực tiếp.
