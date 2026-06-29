# Hướng dẫn dựng dự án Nha khoa SHI từ đầu (chi tiết, cho người mới)

Tài liệu này đi **từ máy trắng → chạy được toàn bộ** (backend → database → web → app điện
thoại → đánh giá AI → chia sẻ). Mỗi bước có lệnh copy-paste và cách kiểm tra "đã đúng chưa".

> Muốn **hiểu code** từng khối thì đọc thêm thư mục [hoc/](hoc/00-muc-luc.md).
> Muốn hiểu **bức tranh tổng** thì xem [KIEN_TRUC.md](KIEN_TRUC.md).

Mục lục:
1. [Cài công cụ](#1-cài-công-cụ)
2. [Lấy mã nguồn & môi trường ảo](#2-lấy-mã-nguồn--môi-trường-ảo)
3. [Chạy backend (chế độ file JSON)](#3-chạy-backend-chế-độ-file-json)
4. [Thử nhanh backend](#4-thử-nhanh-backend)
5. [Nối Database Supabase](#5-nối-database-supabase)
6. [Chạy app điện thoại (Expo)](#6-chạy-app-điện-thoại-expo)
7. [Worker nhắc lịch](#7-worker-nhắc-lịch)
8. [Đánh giá AI](#8-đánh-giá-ai)
9. [Chia sẻ cho người khác](#9-chia-sẻ-cho-người-khác)
10. [Lỗi hay gặp](#10-lỗi-hay-gặp)

---

## 1. Cài công cụ

| Công cụ | Để làm gì | Kiểm tra |
|--------|-----------|----------|
| **Python 3.10+** | Chạy backend | `python3 --version` |
| **Node.js 18+** + npm | Chạy app điện thoại | `node -v` |
| **VS Code** | Soạn code | (đang dùng) |
| **Git** (tùy chọn) | Tải/lưu mã nguồn | `git --version` |
| **Expo Go** (điện thoại) | Mở app native | cài từ App Store / CH Play |

> macOS: nếu chưa có Python/Node, cài nhanh bằng Homebrew: `brew install python node`.

---

## 2. Lấy mã nguồn & môi trường ảo

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

## 3. Chạy backend (chế độ file JSON)

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

## 4. Thử nhanh backend

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

## 5. Nối Database Supabase

Làm bước này khi muốn dữ liệu **bền vững + quản lý online** (không mất khi tắt máy).

### 5.1. Tạo project Supabase
- Vào https://supabase.com → **New project** (chọn region **Singapore** cho gần VN).
- Đặt **Database Password** (nhớ kỹ).

### 5.2. Lấy connection string
- **Settings → Database → Connection string** → tab **Connection pooler** (Transaction, cổng `6543`).
- Dạng: `postgresql://postgres.xxxx:[PASSWORD]@aws-...pooler.supabase.com:6543/postgres`

### 5.3. Cấu hình `.env`
```bash
cp .env.example .env      # tạo file .env (nếu chưa có)
```
Mở `.env`, điền:
```
DATABASE_URL=postgresql://postgres.xxxx:matkhau-that@aws-...pooler.supabase.com:6543/postgres
SECRET_KEY=mot-chuoi-ngau-nhien-bat-ky
```

### 5.4. Tạo bảng + đẩy dữ liệu lên
```bash
./.venv/bin/python scripts/migrate_to_supabase.py
```
**Kết quả đúng:**
```
✅ Đã tạo/đảm bảo bảng trên Postgres.
✅ Đã nạp danh mục: 9 dịch vụ, 11 nha sĩ ...
✅ Đã nạp ... lịch hẹn ... device token.
```

### 5.5. Chạy lại app
```bash
PORT=5001 ./.venv/bin/python app.py
# giờ in: [storage] Chế độ lưu trữ: Postgres/Supabase
```
Mở **Supabase → Table editor** thấy 4 bảng `appointments`, `device_tokens`, `services`,
`doctors`. Từ đây sửa danh mục online (xong **restart app**).

> Muốn quay lại file JSON: xóa/để trống dòng `DATABASE_URL` trong `.env`.
> Chi tiết & FAQ: [DATABASE.md](DATABASE.md).

---

## 6. Chạy app điện thoại (Expo)

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

## 7. Worker nhắc lịch

Tiến trình **riêng**, quét lịch hẹn và bắn nhắc trước giờ khám.
```bash
./.venv/bin/python reminder_worker.py --test    # gửi thử mọi nhắc ngay
./.venv/bin/python reminder_worker.py --watch   # chạy nền, quét mỗi 60 giây
```
Chưa có điện thoại thật? Token giả sẽ được ghi vào `outbox/push_outbox.jsonl` để bạn xem.

---

## 8. Đánh giá AI

```bash
./.venv/bin/python eval/evaluate.py
```
In bảng **Accuracy / Macro-F1** cho 2 phiên bản triage (v1 vs v2) và ghi `eval/results.md`.
Báo cáo đầy đủ (để nộp/ trình bày): [BAOCAO_DANHGIA.md](BAOCAO_DANHGIA.md).

---

## 9. Chia sẻ cho người khác

| Mức | Cách | Khi nào |
|-----|------|---------|
| Demo nhanh | `ngrok http 5001` → link tạm (máy phải bật) | cho thầy/bạn xem ngay |
| Vĩnh viễn | Deploy backend lên **Render/Railway** (thêm `gunicorn`, set env `DATABASE_URL`,`SECRET_KEY`) | ai cũng vào bất kỳ lúc nào |
| App cài đặt | `eas build -p android` → file APK | gửi người khác cài |

Vì DB đã ở Supabase nên deploy backend rất gọn — máy bạn tắt vẫn chạy. Khi deploy nhớ đổi
`API_BASE` trong `mobile/src/config.js` sang URL HTTPS công khai.

---

## 10. Lỗi hay gặp

| Triệu chứng | Cách xử lý |
|-------------|-----------|
| `Port 5000 is in use` | Dùng `PORT=5001` (mặc định) hoặc cổng khác |
| App "Không kết nối được máy chủ" | Chạy `./setup.sh ip`, đảm bảo backend đang chạy, **cùng Wi-Fi** |
| `psycopg ... could not connect` | Sai `DATABASE_URL`/mật khẩu; kiểm tra lại connection string Supabase |
| Vẫn chạy file JSON dù đã set DB | Sai tên biến trong `.env` (phải đúng `DATABASE_URL`); chạy lại app |
| Expo Go "incompatible SDK" | Cập nhật Expo Go (project dùng **SDK 54**) |
| `pip install` lỗi | Đảm bảo đã tạo `.venv` và dùng `./.venv/bin/pip` |

---

## Tóm tắt 1 màn hình
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
