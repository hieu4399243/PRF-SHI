# Trợ lý Nha khoa SHI

Chatbot tiếng Việt cho **một phòng khám nha khoa**: phân loại mô tả triệu chứng răng
miệng → **đúng nhóm dịch vụ** (triage) và **đặt lịch hẹn**.
Kiến trúc: **app native React Native (Expo)** làm giao diện + **backend Python (Flask)**
làm API, có **push notification** (xác nhận đặt lịch, nhắc lịch).

> 📊 Phần **đánh giá hệ thống AI** (Precision/Recall/F1, so sánh phiên bản) nằm ở
> `BAOCAO_DANHGIA.md` và thư mục `eval/`.

## 📚 Tài liệu
| File | Nội dung |
|------|----------|
| [docs/](docs/project-overview-pdr.md) | Bộ tài liệu chuẩn: tổng quan/PDR, kiến trúc, bản đồ mã, chuẩn mã, triển khai, lộ trình |
| [docs/getting-started-guide.md](docs/getting-started-guide.md) | Dựng dự án từ đầu (máy trắng → chạy được), chi tiết cho người mới |
| [docs/database-storage-guide.md](docs/database-storage-guide.md) | Lưu trữ JSON ↔ Supabase, cách đưa dữ liệu lên cloud |
| [BAOCAO_DANHGIA.md](BAOCAO_DANHGIA.md) | Báo cáo đánh giá AI (mục đích→mục tiêu→cách đo→kết quả→kết luận) |
| [hoc/](hoc/00-muc-luc.md) | Tự học: viết lại từng khối từ con số 0 |

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
| **Triage engine** | `triage.py` | Phân loại triệu chứng răng miệng → đúng **dịch vụ** (chấm điểm từ khóa, có v1/v2; có chỗ cắm LLM Claude). |
| **Booking** | `booking.py` | Đặt lịch hội thoại: chọn dịch vụ → bác sĩ → ngày → giờ trống → xác nhận; tránh trùng slot; lưu `appointments.json`. |
| **Safety / guardrails** | `safety.py` | Phát hiện **cấp cứu** (→ gọi 115), **lọc PII**, chặn **chẩn đoán/kê đơn**, **human handoff**, **audit log** (Nghị định 13/2023). |
| **Conversational core** | `chatbot.py` | Máy trạng thái điều phối hội thoại, kết nối các khối. |
| **Push** | `push.py` | Lưu device token + gửi push qua Expo Push Service. |
| **Reminder worker** | `reminder_worker.py` | Quét lịch hẹn, bắn nhắc lịch (1 ngày / 2 giờ). |
| **API server** | `app.py` | Flask API cho app native (`/api/start`, `/api/chat`, `/api/register-push`, `/api/ics`). |
| **Dữ liệu** | `data.py` | Danh mục **dịch vụ nha khoa**, nha sĩ, khung giờ trống (thay bằng DB trong thực tế). |
| **Đánh giá AI** | `eval/` | `dataset.jsonl` + `evaluate.py` (Precision/Recall/F1, v1 vs v2) + `rubric.md`; báo cáo ở `BAOCAO_DANHGIA.md`. |

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

- *“răng tôi bị sâu và ê buốt khi ăn ngọt”* → dịch vụ **Trám răng / Sâu răng** → đặt lịch.
- *“toi muon nieng rang”* (không dấu) → **Chỉnh nha** (nhờ engine v2 không phân biệt dấu).
- *“chảy máu chân răng và hôi miệng”* → **Nha chu**.
- *“mặt tôi sưng mặt lan và khó nuốt”* → cảnh báo **cấp cứu, gọi 115**.
- *“cho tôi gặp nhân viên”* → **chuyển người thật** (handoff).
- Gõ **“làm lại”** để bắt đầu phiên mới.

## Đánh giá hệ thống AI
```bash
./.venv/bin/python eval/evaluate.py   # Accuracy/Macro-F1 cho v1 & v2 → ghi eval/results.md
```
Kết quả mới nhất (tập dev 63 câu): **v2 đạt Accuracy 100%, Macro-F1 1.0** (v1: 77.8% / 0.87).
Lưu ý: từ khóa hiệu chỉnh trên chính tập này nên là số "lạc quan"; chi tiết & phân tích
trung thực trong `BAOCAO_DANHGIA.md`.

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
