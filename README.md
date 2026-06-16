# AI Health Assistant (SHI)

Chatbot **phân loại bệnh nhân vào khoa** (triage) và **đặt lịch hẹn** với phòng khám.
Kiến trúc: **app native React Native (Expo)** làm giao diện + **backend Python (Flask)**
làm API, có **push notification** (xác nhận đặt lịch, nhắc lịch & nhắc ăn uống).

```
┌─────────────────────┐      HTTP /api/*      ┌──────────────────────────┐
│  App native (Expo)  │  ───────────────────► │  Backend Flask (Python)  │
│  mobile/  (RN UI)   │  ◄─── push token ──── │  triage · booking · safe │
└─────────────────────┘                       └────────────┬─────────────┘
        ▲   push notification (Expo Push)                   │
        └───────────────────────────────────────────────────┘
                         reminder_worker.py (nhắc lịch/ăn uống)
```

## Chức năng (backend)

| Khối | File | Mô tả |
|------|------|-------|
| **Triage engine** | `triage.py` | Phân loại triệu chứng tiếng Việt → đúng khoa (chấm điểm theo từ khóa; có chỗ cắm LLM Claude). |
| **Booking** | `booking.py` | Đặt lịch hội thoại: chọn khoa → bác sĩ → ngày → giờ trống → xác nhận; tránh trùng slot; lưu `appointments.json`. |
| **Safety / guardrails** | `safety.py` | Phát hiện **cấp cứu** (→ gọi 115), **lọc PII**, chặn **chẩn đoán/kê đơn**, **human handoff**, **audit log** (Nghị định 13/2023). |
| **Conversational core** | `chatbot.py` | Máy trạng thái điều phối hội thoại, kết nối các khối. |
| **Push** | `push.py` | Lưu device token + gửi push qua Expo Push Service. |
| **Reminder worker** | `reminder_worker.py` | Quét lịch hẹn, bắn nhắc lịch (1 ngày / 2 giờ) + nhắc ăn uống. |
| **API server** | `app.py` | Flask API cho app native (`/api/start`, `/api/chat`, `/api/register-push`, `/api/ics`). |
| **Dữ liệu** | `data.py` | Danh mục khoa, bác sĩ, khung giờ trống (thay bằng DB trong thực tế). |

> Giao diện chính là **app native trong `mobile/`** (xem `mobile/README.md`).
> File `templates/index.html` là bản web cũ, giữ lại để test nhanh trên trình duyệt.

## Chạy backend

```bash
cd /Users/hieutm3/Desktop/PRF
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py        # API tại http://0.0.0.0:5000
```

## Chạy app native
```bash
cd mobile
npm install
npx expo start                 # quét QR bằng Expo Go trên điện thoại
```
Nhớ sửa `mobile/src/config.js` → `API_BASE` thành IP LAN của máy chạy backend.
Chi tiết: **`mobile/README.md`**.

## Chạy worker nhắc lịch
```bash
.venv/bin/python reminder_worker.py --watch   # quét mỗi 60s, tự bắn khi tới hạn
.venv/bin/python reminder_worker.py --test    # gửi thử mọi loại nhắc ngay
```

## Thử nhanh

- *“mấy hôm nay tôi ho và đau họng”* → gợi ý khoa Hô hấp / Tai Mũi Họng.
- *“tôi đau bụng và ợ chua”* → khoa Tiêu hóa → đặt lịch.
- *“tôi bị đau ngực dữ dội”* → cảnh báo **cấp cứu, gọi 115**.
- *“cho tôi gặp nhân viên”* → **chuyển người thật** (handoff).
- Gõ **“làm lại”** để bắt đầu phiên mới.

## File sinh ra khi chạy
- `appointments.json` — lịch hẹn đã đặt.
- `audit_log.jsonl` — nhật ký hội thoại (đã ẩn PII).

## Thêm vào lịch + nhắc tự động
Sau khi đặt lịch thành công, bệnh nhân có 2 nút:
- **Thêm vào Lịch (.ics)** — tải file `calendar_ics.py` sinh ra, thêm được vào
  Lịch iPhone/Mac, Outlook, Google Calendar; kèm **2 lời nhắc** (trước 1 ngày &
  trước 1 giờ) nên app lịch của họ tự **thông báo**. Route: `/api/ics/<mã>`.
- **Thêm vào Google Calendar** — link mở sẵn form tạo sự kiện trên web.

Không cần OAuth / API key, hoạt động trên mọi thiết bị.

## Nâng cấp (ngoài phạm vi demo)
- `triage.classify_with_llm()` — cắm Claude (`claude-opus-4-8` / `claude-sonnet-4-6`) để NLU tiếng Việt mạnh hơn.
- Đồng bộ 2 chiều Google Calendar bằng OAuth (`google-api-python-client`) — để chặn trùng lịch phía bác sĩ.
