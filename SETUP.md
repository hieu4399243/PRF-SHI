# Hướng dẫn cài đặt & chạy — AI Health Assistant (SHI)

Dành cho mọi thành viên. Có **script tự động** `setup.sh` lo gần hết.

---

## 0. Yêu cầu cài sẵn trên máy
- **Python 3.10+** → kiểm tra: `python3 --version`
- **Node.js 18+** và **npm** → kiểm tra: `node -v` (tải tại https://nodejs.org)
- Trên điện thoại: cài app **Expo Go** (App Store / CH Play)
- Điện thoại và máy tính phải **cùng một mạng Wi-Fi**

---

## 1. Cài đặt (một lệnh)
```bash
cd PRF
./setup.sh
```
Script sẽ:
1. Tạo `.venv` và cài thư viện Python (backend).
2. Chạy `npm install` cho app native (`mobile/`).
3. **Tự dò IP LAN** của máy và ghi vào `mobile/src/config.js`.
4. In ra hướng dẫn chạy.

> Nếu `./setup.sh` báo "permission denied": chạy `chmod +x setup.sh` rồi thử lại.

---

## 2. Chạy (mở 3 cửa sổ Terminal)

**Terminal 1 — Backend (API):**
```bash
cd PRF
PORT=5001 ./.venv/bin/python app.py
```

**Terminal 2 — Worker nhắc lịch (tùy chọn):**
```bash
cd PRF
./.venv/bin/python reminder_worker.py --watch
```

**Terminal 3 — App native:**
```bash
cd PRF/mobile
npx expo start -c
```
Quét mã QR bằng **Expo Go**. Xong!

---

## 3. Đổi IP / cổng (khi đổi mạng Wi-Fi hoặc máy khác)

IP LAN thay đổi mỗi khi đổi mạng. Khi app báo "Không kết nối được máy chủ":

```bash
./setup.sh ip          # tự dò lại IP và cập nhật mobile/src/config.js
```

Ép thủ công IP hoặc cổng:
```bash
IP=192.168.1.50 PORT=5001 ./setup.sh ip
```

Tìm IP máy bằng tay:
- macOS: `ipconfig getifaddr en0`
- Linux: `hostname -I`
- Windows: `ipconfig` → mục "IPv4 Address"

Sau khi đổi IP, **reload app** trong Expo Go (lắc máy → Reload).

> Vì sao cổng **5001** chứ không phải 5000? Trên macOS, dịch vụ **AirPlay Receiver**
> chiếm sẵn cổng 5000. Đổi cổng: `PORT=5002 ./.venv/bin/python app.py` rồi
> `PORT=5002 ./setup.sh ip`.

---

## 4. Các lệnh setup lẻ
```bash
./setup.sh backend     # chỉ cài lại backend Python
./setup.sh mobile      # chỉ cài lại app native (npm install)
./setup.sh ip          # chỉ cập nhật IP trong config
```

---

## 5. Lỗi hay gặp

| Triệu chứng | Cách xử lý |
|-------------|-----------|
| App: "Không kết nối được máy chủ" | Chạy `./setup.sh ip`, đảm bảo backend đang chạy, cùng Wi-Fi. |
| "Port 5000 is in use" | Dùng cổng 5001 (mặc định) hoặc đổi `PORT=...`. |
| Expo Go: "incompatible SDK" | Project là **SDK 54**. Cập nhật Expo Go, hoặc sửa version trong `mobile/package.json` rồi `cd mobile && npx expo install --fix`. |
| npm "ERESOLVE" | `cd mobile && rm -rf node_modules package-lock.json && npm install` |
| Không thấy thông báo nhắc | Cấp quyền **Thông báo** + **Lịch** cho Expo Go; tắt chế độ im lặng/Focus. |
| Push qua server không về máy | Đúng — Expo Go không nhận remote push (SDK 53+). App dùng **local notification** thay thế; push server chỉ chạy khi build dev (EAS). |

---

## 6. Cấu trúc nhanh
```
PRF/
├── setup.sh            # script cài đặt & cấu hình
├── app.py              # backend Flask (API)
├── triage.py booking.py safety.py chatbot.py push.py   # nghiệp vụ
├── reminder_worker.py  # worker nhắc lịch
├── requirements.txt
└── mobile/             # app native (React Native / Expo)
    ├── App.js
    └── src/  (api.js, config.js, notify.js, calendar.js, ...)
```
