# Kiến trúc hệ thống — Trợ lý Nha khoa SHI

> File này tóm tắt cấp cao cho người mới định hướng. Bản đồ file chi tiết:
> [codebase-summary.md](codebase-summary.md).

## 1. Ba tầng

```
Client (Expo app + web demo)  ──HTTP /api/* JSON──►  Backend (Flask)  ──►  Lưu trữ
       ▲                                                   │                 (Supabase / JSON)
       └────────── Expo Push notification ─────────────────┘
                    reminder_worker.py (nền) ── quét lịch ──► push
```

- **Client** — chỉ hiển thị, gọi API, không chứa nghiệp vụ. App native `mobile/` (React
  Native / Expo SDK 54) + web demo `templates/index.html`.
- **Backend** — Flask (Python), toàn bộ logic: AI triage, đặt/hủy lịch, an toàn, thông báo.
- **Lưu trữ** — `storage.py` chọn Postgres/Supabase (khi có `DATABASE_URL`) hoặc file JSON.

## 2. Thành phần backend

| Thành phần | File | Trách nhiệm |
|-----------|------|-------------|
| API gateway | `app.py` | Routes Flask, `resolve_sid()`, trang admin. Chạy `0.0.0.0:5001`. |
| Nhạc trưởng hội thoại | `chatbot.py` | State machine (`SESSIONS` in-memory), điều phối các khối. |
| AI triage | `triage.py` | Phân loại triệu chứng → dịch vụ (v1/v2), Q&A dịch vụ, chỗ cắm LLM. |
| An toàn | `safety.py` | Cấp cứu→115, ẩn PII, chặn chẩn đoán, handoff, audit log. |
| Đặt/hủy lịch | `booking.py` | Chọn slot, chống trùng (giờ/SĐT) đối chiếu DB, sinh mã lịch. |
| Danh mục | `data.py` | 9 nhóm dịch vụ + nha sĩ + khung giờ (seed tĩnh hoặc nạp từ DB). |
| Lưu trữ | `storage.py` | Trừu tượng Postgres ↔ JSON theo `DATABASE_URL`. |
| Push | `push.py` | Gửi qua Expo Push Service; không token → `outbox/`. |
| Nhắc lịch | `reminder_worker.py` | Worker nền (`--once`/`--watch`/`--test`). |
| Lịch .ics | `calendar_ics.py` | Sinh file `.ics` có VALARM, không cần OAuth. |

## 3. State machine hội thoại

```
GREET → TRIAGE → CONFIRM_DEPT → PICK_DOCTOR → PICK_DATE → PICK_TIME
      → ASK_NAME → ASK_PHONE → CONFIRM_BOOKING → DONE

Nhánh hủy:  CANCEL_ASK_PHONE → CANCEL_PICK → CANCEL_CONFIRM → DONE
Ưu tiên mọi lúc:  EMERGENCY / HANDOFF
```

## 4. Vòng đời 1 request `/api/chat`

1. `app.py` → `resolve_sid()` xác định session (app: body `session`; web: cookie).
2. `chatbot.handle_message()` → `safety.audit()` (ghi log ẩn PII) → `check_emergency()`.
3. Định tuyến theo STATE (triage / booking / cancel / hỏi thông tin).
4. `CONFIRM_BOOKING` → đối chiếu DB chống trùng → `storage` → `push` + `calendar_ics`.
5. Trả `{reply, options, state, appointment?}` → client render.

## 5. Mô hình dữ liệu

**Postgres/Supabase** (khi có `DATABASE_URL`):
```sql
appointments(code PK, session, patient_name, patient_phone, department, department_code,
             doctor, doctor_id, date, time, created_at, status, reminders_sent jsonb;
             UNIQUE INDEX (doctor_id, date, time) WHERE status='confirmed')  -- chặn race booking
device_tokens(session, token, PRIMARY KEY(session, token))
services(code PK, name, descr, keywords jsonb, sort_order)
doctors(id PK, service_code → services.code, name, sort_order)
safety_patterns(kind, pattern, PRIMARY KEY(kind, pattern))  -- emergency/diagnosis/handoff
```
**Fallback JSON:** `appointments.json`, `device_tokens.json`; danh mục lấy từ `_SEED_*` trong
`data.py`. Chi tiết + hướng dẫn migrate: [database-storage-guide.md](database-storage-guide.md).

> Quy tắc: dữ liệu **phát sinh** (lịch, token) → chỉ ở DB. **Danh mục** → DB là nguồn chính,
> `data.py` là seed dự phòng. Guardrail (`safety_patterns`) → DB chỉ mở rộng, luôn fail-safe.

## 6. Công nghệ

Python 3 / Flask · rule-based NLU (từ khóa, không dấu) + chỗ cắm LLM Claude · Supabase
(Postgres qua `psycopg`) fallback JSON · Expo Push + `.ics` · React Native / Expo SDK 54 ·
cấu hình `.env` (`python-dotenv`).

## 7. Nguyên tắc thiết kế

1. Tách tầng client/backend/lưu trữ. 2. Một khối một việc (triage/booking/safety/push độc lập).
3. Tách logic khỏi nơi lưu (`storage.py`). 4. Offline-first (fallback → dễ demo/chấm).
5. An toàn là ưu tiên cao nhất, fail-safe.
