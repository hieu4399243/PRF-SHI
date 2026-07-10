# Bản đồ mã nguồn — Trợ lý Nha khoa SHI

Điểm vào nhanh cho người mới: file nào làm gì, đọc theo thứ tự nào.

## Thứ tự đọc đề xuất

`README.md` → `docs/system-architecture.md` → `app/chatbot.py` (nhạc trưởng) →
`app/triage.py` (AI) → `app/booking.py` → `app/safety.py` → `app/storage.py`/`app/data.py`.

## Backend (package `app/`)

| File | LOC | Vai trò |
|------|-----|---------|
| `app/app.py` | ~160 | API Flask + trang admin. `resolve_sid()`. Chạy `0.0.0.0:5001 debug=True`. |
| `app/chatbot.py` | ~620 | Máy trạng thái hội thoại; session in-memory (`SESSIONS`). |
| `app/triage.py` | ~220 | Phân loại triệu chứng → dịch vụ (v1/v2), Q&A dịch vụ, `classify_with_llm()` placeholder. |
| `app/safety.py` | ~150 | Guardrails y tế + audit log `app/data/audit_log.jsonl`. |
| `app/booking.py` | ~250 | Đặt/hủy lịch, chống trùng, sinh mã. |
| `app/storage.py` | ~400 | Lớp lưu trữ Postgres ↔ JSON. |
| `app/data.py` | ~220 | Danh mục dịch vụ/nha sĩ + khung giờ (seed + nạp DB), `SERVICE_INFO`. |
| `app/push.py` | ~96 | Expo Push; fallback `app/data/outbox/push_outbox.jsonl`. |
| `app/reminder_worker.py` | ~113 | Worker nhắc lịch nền. |
| `app/calendar_ics.py` | ~98 | Sinh file `.ics` có lời nhắc. |

## API endpoints (`app.py`)

| Method | Path | Việc |
|--------|------|------|
| GET | `/` | Web demo (`templates/index.html`) |
| POST | `/api/start` | Bắt đầu phiên, trả `session` |
| POST | `/api/chat` | Gửi `message`, nhận phản hồi bot |
| POST | `/api/register-push` | App gửi Expo push token |
| GET | `/api/ics/<code>` | Tải file `.ics` của 1 lịch hẹn |
| GET | `/admin` | Trang quản trị (cần `ADMIN_KEY`) |
| GET | `/api/admin/appointments` · `/api/admin/schedule` · `/api/admin/meta` | Dữ liệu admin |
| POST | `/api/admin/cancel` | Hủy lịch từ trang admin |

## Client — `mobile/` (Expo)

| File | Vai trò |
|------|---------|
| `App.js` | Màn hình chat app native |
| `src/api.js` | Gọi backend |
| `src/config.js` | `API_BASE` (IP LAN / URL backend) |
| `src/notify.js`, `src/usePush.js` | Thông báo & đăng ký push |
| `src/calendar.js` | Thêm `.ics` vào Lịch máy |
| `src/html.js` | Đổi HTML in đậm → text app |

## Đánh giá AI & tài liệu

| Đường dẫn | Nội dung |
|-----------|----------|
| `eval/dataset.jsonl`, `dataset_complex.jsonl` | Câu gán nhãn test triage |
| `eval/evaluate.py` | Accuracy/Macro-F1, v1 vs v2 → `docs/eval/results.md` |
| `docs/eval/rubric.md` | Đánh giá định tính |
| `scripts/migrate_to_supabase.py` | Đẩy JSON + seed danh mục lên Supabase |
| `scripts/clean_stale_appointments.py` | Dọn lịch hẹn cũ |
| `docs/hoc/` | Tài liệu tự học (dựng lại từng khối) |
| `docs/BAOCAO_DANHGIA.md`, `docs/BAOCAO_DOAN.md` | Báo cáo đánh giá AI & đồ án |

## File sinh ra khi chạy

`app/data/appointments.json`, `app/data/device_tokens.json`, `app/data/audit_log.jsonl`,
`app/data/outbox/push_outbox.jsonl`
(chế độ JSON — khi có DB thì dữ liệu ở Supabase).
