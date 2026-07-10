# Hướng dẫn triển khai — Trợ lý Nha khoa SHI

> Dựng từ máy trắng đến chạy được: [getting-started-guide.md](getting-started-guide.md).
> Lưu trữ/DB: [database-storage-guide.md](database-storage-guide.md).

## 1. Chạy local (dev)

```bash
# 1. Backend
PORT=5001 ./.venv/bin/python -m app.app            # API tại http://0.0.0.0:5001
# 2. Worker nhắc lịch (tùy chọn)
./.venv/bin/python -m app.reminder_worker --watch  # quét mỗi 60s
# 3. App native
cd mobile && npx expo start -c                 # quét QR bằng Expo Go
```

- macOS chiếm cổng 5000 (AirPlay) → dùng **5001**.
- Client và backend phải **cùng Wi-Fi** (dùng IP LAN). Đổi mạng → `./setup.sh ip` cập nhật
  `mobile/src/config.js` (`API_BASE`), rồi reload Expo Go.

## 2. Cấu hình môi trường (`.env`)

| Biến | Ý nghĩa |
|------|---------|
| `DATABASE_URL` | Connection string Postgres/Supabase. Trống → dùng file JSON. |
| `SECRET_KEY` | Khóa Flask session (production đặt chuỗi ngẫu nhiên). |
| `ADMIN_KEY` | Khóa vào trang `/admin`. |

Sao chép `.env.example` → `.env`. **Không commit `.env`.**

## 3. Ba mức chia sẻ

| Mức | Cách làm |
|-----|----------|
| **Demo nhanh** | Giữ máy bật + `ngrok http 5001` (hoặc `npx expo start --tunnel`) → link tạm. |
| **Backend cloud** | Deploy Render/Railway/Fly.io: thêm `gunicorn` vào `requirements.txt`, start `gunicorn app.app:app`, set `SECRET_KEY`, gắn DB/volume. Đổi `API_BASE` → URL HTTPS. |
| **App cài thật** | Build EAS (`eas build -p android` → AAB/APK; `eas build -p ios`). Không qua Expo Go. |

## 4. Lên "chợ" (App Store / Google Play)

- **Google Play:** `eas build -p android` → AAB; Play Console **25 USD trả 1 lần**.
- **App Store:** `eas build -p ios` + **Apple Developer 99 USD/năm**, `eas submit`. Review app
  **y tế** khắt khe → cần disclaimer "không thay thế tư vấn y khoa" + privacy policy
  (hợp với `app/safety.py`).
- Điều kiện: backend đã ở cloud (HTTPS công khai, không còn IP LAN); chuẩn bị icon/splash,
  `app.json` (bundle id, version), xử lý dữ liệu sức khỏe (NĐ 13/2023 — đã có audit log).

Đường tối thiểu để nhiều người cài thử mà chưa lên chợ: **EAS build APK Android**, gửi file
APK/link cài trực tiếp.

## 5. Đưa dữ liệu lên Supabase (tóm tắt)

```bash
cp .env.example .env                                 # điền DATABASE_URL + SECRET_KEY
./.venv/bin/pip install -r requirements.txt          # đã có psycopg + python-dotenv
./.venv/bin/python scripts/migrate_to_supabase.py    # tạo bảng + seed danh mục (idempotent)
PORT=5001 ./.venv/bin/python -m app.app              # in "[storage] ... Postgres/Supabase"
```
Chi tiết bảng, guardrail online, quản trị danh mục: [database-storage-guide.md](database-storage-guide.md).

## 6. Khoảng trống trước khi lên production

1. `debug=True` + dev server (`app/app.py`) → dùng `gunicorn`, tắt debug.
2. **Session hội thoại vẫn in-memory** (`app/chatbot.SESSIONS`) → cần Redis/DB khi nhiều worker.
3. **CORS** chưa cấu hình — thêm khi web client khác origin.
4. `API_BASE` là IP LAN → đổi sang URL HTTPS công khai khi deploy.
5. Bật Row Level Security trên Supabase khi mở public (dữ liệu sức khỏe).
