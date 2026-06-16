# SHI Health Assistant — App native (React Native / Expo)

Giao diện điện thoại cho chatbot phân loại khoa + đặt lịch, có **push notification**
(xác nhận khi đặt lịch, nhắc lịch & nhắc ăn uống trước ngày khám).

## Yêu cầu
- Node.js 18+ và npm
- Điện thoại cài app **Expo Go** (App Store / CH Play), **cùng mạng Wi-Fi** với máy tính
- Backend Flask đang chạy (thư mục cha): `.venv/bin/python app.py`

> Project dùng **Expo SDK 54** (khớp với Expo Go bản SDK 54). Nếu Expo Go trên
> máy bạn là SDK khác, cập nhật Expo Go hoặc đổi version trong `package.json`
> rồi chạy `npx expo install --fix`.

## Cài & chạy
```bash
cd mobile
rm -rf node_modules package-lock.json   # nếu trước đó đã cài bản SDK cũ
npm install
npx expo start -c                       # -c = xóa cache (cần sau khi đổi SDK)
```
Quét mã QR hiện ra bằng **Expo Go** trên điện thoại.

## Cấu hình kết nối backend (BẮT BUỘC)
Mở `src/config.js`, sửa `API_BASE` thành IP LAN của máy chạy backend:
```js
export const API_BASE = "http://192.168.1.10:5000"; // đổi IP cho đúng
```
Lấy IP máy Mac: `ipconfig getifaddr en0`. Điện thoại + máy tính phải cùng Wi-Fi.
(Backend đã bật `host=0.0.0.0` nên máy khác trong mạng gọi được.)

## Push notification
- App tự xin quyền thông báo và gửi **device token** lên backend (`/api/register-push`).
- **Đặt lịch xong** → backend bắn push "Đặt lịch thành công" ngay.
- **Nhắc lịch/ăn uống**: chạy worker ở thư mục cha:
  ```bash
  .venv/bin/python reminder_worker.py --watch   # quét mỗi 60s, tự bắn khi tới hạn
  .venv/bin/python reminder_worker.py --test    # gửi thử mọi loại nhắc ngay
  ```
- ⚠️ **Push thật KHÔNG chạy trong Expo Go** (từ SDK 53 Expo gỡ remote push khỏi
  Expo Go). Trong Expo Go, `getExpoPushTokenAsync` sẽ lỗi → app tự dùng token
  DEMO và backend ghi vào `../outbox/push_outbox.jsonl` (vẫn kiểm thử được luồng,
  giao diện chat chạy bình thường).
- Để push **hiện thật trên điện thoại**: tạo project EAS (`npx eas init`), điền
  `extra.eas.projectId` trong `app.json`, rồi build **development build**:
  `npx expo run:ios` / `npx expo run:android` (hoặc `eas build --profile development`).

## Cấu trúc
| File | Vai trò |
|------|---------|
| `App.js` | Màn hình chat (bong bóng, nút chọn nhanh, hiệu ứng đang gõ) |
| `src/api.js` | Gọi API backend (`/api/start`, `/api/chat`, `/api/register-push`) |
| `src/usePush.js` | Xin quyền + lấy & đăng ký device push token |
| `src/html.js` | Chuyển HTML nhẹ của backend thành text in đậm cho RN |
| `src/config.js` | Địa chỉ backend (`API_BASE`) |
