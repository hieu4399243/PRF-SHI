# Kiến trúc dự án — Trợ lý Nha khoa SHI

Chatbot tiếng Việt cho **một phòng khám nha khoa**: người dùng mô tả triệu chứng → AI phân
loại đúng **dịch vụ nha khoa** (triage) → **đặt lịch hẹn** → **nhắc lịch** qua thông báo/.ics.

---

## 1. Tổng quan hệ thống

```
┌──────────────────────┐        HTTP /api/* (JSON)        ┌────────────────────────────┐
│  CLIENT                │ ───────────────────────────────► │  BACKEND  (Flask, Python)   │
│  • App native (Expo)   │                                  │                              │
│    mobile/             │ ◄─────── JSON phản hồi ────────── │   app.py  (cửa ngõ API)      │
│  • Web demo            │                                  │     │                        │
│    templates/index.html│ ─── device push token ─────────► │   chatbot.py (nhạc trưởng)   │
└──────────┬─────────────┘                                  │     ├─ triage.py  (AI)        │
           │                                                │     ├─ booking.py (đặt lịch)  │
           │  thông báo đẩy (Expo Push)                     │     ├─ safety.py  (an toàn)   │
           ▼                                                │     └─ push.py    (thông báo) │
   ┌────────────────┐                                       │   storage.py  ←→  data.py     │
   │ Điện thoại      │                                       └─────────┬──────────┬─────────┘
   │ (thông báo)     │                                                 │          │
   └────────────────┘                                          ┌───────▼───┐  ┌──▼─────────┐
                                                               │ Supabase  │  │ File JSON  │
   reminder_worker.py (chạy nền) ──quét lịch──► push           │ (Postgres)│  │ (fallback) │
                                                               └───────────┘  └────────────┘
```

**3 tầng:**
- **Client** — giao diện (app điện thoại Expo + web demo), chỉ gọi API, không chứa logic.
- **Backend** — Flask, toàn bộ nghiệp vụ (AI, đặt lịch, an toàn, thông báo).
- **Lưu trữ** — `storage.py` chọn Supabase (nếu có `DATABASE_URL`) hoặc file JSON.

---

## 2. Luồng xử lý 1 tin nhắn (request lifecycle)

```
Người dùng gõ "răng tôi bị sâu"
   │ POST /api/chat {session, message}
   ▼
app.py ──► resolve_sid() xác định "ai đang nói"
   │
   ▼
chatbot.handle_message(sid, message)
   ├─ safety.audit()            ghi log (đã ẩn PII)
   ├─ safety.check_emergency()  cấp cứu? → chặn, khuyên gọi 115
   ├─ ở bước nhập tự do (TRIAGE/CONFIRM_DEPT/DONE) còn bắt:
   │     • câu hỏi thông tin "X là khám gì?" → triage.info_question_service() → mô tả dịch vụ
   │     • ý định "hủy lịch" → nhánh CANCEL_*
   ├─ định tuyến theo STATE:
   │     TRIAGE → triage.classify_symptoms() (đọc DEPARTMENTS); mơ hồ mà rõ là vấn đề
   │              răng miệng → mentions_dental_discomfort() → cho chọn có cấu trúc
   │     PICK_* → booking.get_doctors/dates/times()  (khung giờ luôn hiển thị đầy đủ)
   │     ASK_NAME → ASK_PHONE (bắt buộc SĐT, có chuẩn hóa/kiểm tra)
   │     CONFIRM_BOOKING → booking.book_appointment() → ĐỐI CHIẾU DB (trùng giờ / trùng
   │                       SĐT) → storage → (Supabase/JSON) + push.send_push() + calendar_ics
   │     CANCEL_* → booking.upcoming_by_phone()/cancel_appointment() (status='cancelled')
   └─ trả {reply, options, state, appointment?}
   ▼
app.py → jsonify → Client hiển thị bong bóng chat + nút bấm
```

**Máy trạng thái (state machine) của hội thoại:**
```
GREET → TRIAGE → CONFIRM_DEPT → PICK_DOCTOR → PICK_DATE
      → PICK_TIME → ASK_NAME → ASK_PHONE → CONFIRM_BOOKING → DONE

Nhánh hủy lịch:   CANCEL_ASK_PHONE → CANCEL_PICK → CANCEL_CONFIRM → DONE
(khi đặt trùng, CONFIRM_BOOKING cũng rẽ sang CANCEL_CONFIRM: hủy lịch cũ rồi đặt tiếp)

Ưu tiên mọi lúc: EMERGENCY / HANDOFF.
```

---

## 3. Bản đồ file & trách nhiệm

### Backend (thư mục gốc)
| File | Vai trò | Phụ thuộc |
|------|---------|-----------|
| `app.py` | Cửa ngõ API Flask: `/api/start`, `/api/chat`, `/api/register-push`, `/api/ics/<code>` | chatbot, booking, storage |
| `chatbot.py` | **Máy trạng thái** điều phối hội thoại (gồm nhánh đặt lịch, hủy lịch, hỏi thông tin) | triage, booking, safety, push |
| `triage.py` | **AI** phân loại triệu chứng → dịch vụ (v1 có dấu / v2 không dấu); fallback than phiền chung; nhận câu hỏi thông tin dịch vụ | data |
| `safety.py` | Guardrails: cấp cứu→115, ẩn PII, chặn chẩn đoán, audit log. Bộ pattern nạp từ DB (`safety_patterns`) + seed code làm fail-safe | storage |
| `booking.py` | Đặt lịch & **hủy lịch**; **kiểm tra trùng (giờ/SĐT) trực tiếp với DB lúc xác nhận**; sinh mã lịch hẹn | data, storage |
| `push.py` | Gửi thông báo qua Expo Push; token qua storage | storage |
| `data.py` | Danh mục dịch vụ/nha sĩ (seed + nạp từ DB), **mô tả dịch vụ (`SERVICE_INFO`)**, khung giờ | storage |
| `storage.py` | **Lớp lưu trữ**: Supabase (Postgres) ↔ file JSON theo `DATABASE_URL` | psycopg (khi dùng DB) |
| `calendar_ics.py` | Sinh file `.ics` (có lời nhắc) để thêm vào Lịch | — |
| `reminder_worker.py` | Tiến trình nền quét lịch hẹn → bắn nhắc (1 ngày/2 giờ) | booking, push |

### Client
| File | Vai trò |
|------|---------|
| `templates/index.html` | Web demo (1 file HTML+CSS+JS) gọi `/api/*` |
| `mobile/App.js` | Màn hình chat app native |
| `mobile/src/api.js` | Gọi backend |
| `mobile/src/config.js` | `API_BASE` (URL backend) |
| `mobile/src/notify.js`, `usePush.js` | Thông báo & đăng ký push |
| `mobile/src/calendar.js` | Thêm lịch hẹn vào Lịch máy |
| `mobile/src/html.js` | Đổi HTML in đậm → text app |

### Đánh giá AI & tài liệu
| Đường dẫn | Nội dung |
|-----------|----------|
| `eval/dataset.jsonl` | 63 câu gán nhãn (test triage) |
| `eval/evaluate.py` | Tính Precision/Recall/F1, so sánh v1 vs v2 → `results.md` |
| `eval/rubric.md` | Đánh giá định tính |
| `BAOCAO_DANHGIA.md` | Báo cáo đánh giá (mục đích→mục tiêu→cách đo→kết quả→kết luận) |
| `hoc/` | Bộ tự học, dựng lại từng khối từ đầu |
| `scripts/migrate_to_supabase.py` | Đẩy dữ liệu JSON + seed danh mục lên Supabase |

---

## 4. Mô hình dữ liệu

**Supabase (Postgres)** — khi có `DATABASE_URL`:
```sql
appointments(code PK, session, patient_name, patient_phone, department, department_code,
             doctor, doctor_id, date, time, created_at, status, reminders_sent jsonb)
             -- status: 'confirmed' | 'cancelled'; slot chỉ bị coi là bận khi 'confirmed'
device_tokens(session, token, PRIMARY KEY(session, token))
services(code PK, name, descr, keywords jsonb, sort_order)
doctors(id PK, service_code → services.code, name, sort_order)
safety_patterns(kind, pattern, PRIMARY KEY(kind, pattern))  -- guardrail (emergency/diagnosis/handoff)
```
**Fallback file JSON** — khi không có DB: `appointments.json`, `device_tokens.json`, danh mục
lấy từ dict `_SEED_*` trong `data.py`. Xem chi tiết: [DATABASE.md](DATABASE.md).

> Quy tắc: dữ liệu **phát sinh** (lịch hẹn, token) → chỉ ở DB. **Danh mục** (services/doctors)
> → DB là nguồn chính, `data.py` là seed/dự phòng.

---

## 5. Công nghệ sử dụng
| Mảng | Công nghệ |
|------|-----------|
| Backend | Python 3, **Flask** |
| AI/NLU | Rule-based scoring (từ khóa, không dấu) + fallback than phiền chung + Q&A "dịch vụ là gì" — có chỗ cắm LLM Claude |
| Database | **Supabase (Postgres)** qua `psycopg`; fallback JSON |
| Thông báo | **Expo Push Service** + local notification + file `.ics` |
| Mobile | **React Native / Expo (SDK 54)** |
| Cấu hình | `.env` (`python-dotenv`) |

---

## 6. Cây thư mục
```
PRF-SHI/
├── app.py                  # API Flask (cửa ngõ)
├── chatbot.py              # máy trạng thái hội thoại
├── triage.py               # AI phân loại triệu chứng
├── safety.py               # guardrails an toàn
├── booking.py              # đặt lịch
├── push.py                 # thông báo đẩy
├── data.py                 # danh mục dịch vụ/nha sĩ (seed + nạp DB)
├── storage.py              # lớp lưu trữ JSON ↔ Supabase
├── calendar_ics.py         # sinh file .ics
├── reminder_worker.py      # worker nhắc lịch (chạy nền)
├── requirements.txt        # thư viện Python
├── .env / .env.example     # cấu hình (DATABASE_URL, SECRET_KEY)
├── setup.sh                # script cài đặt & dò IP
│
├── templates/index.html    # web demo
├── mobile/                 # app native (Expo)
│   ├── App.js
│   └── src/ (api, config, notify, usePush, calendar, html).js
│
├── eval/                   # đánh giá AI
│   ├── dataset.jsonl  evaluate.py  rubric.md  results.md
├── scripts/migrate_to_supabase.py
├── hoc/                    # tài liệu tự học (dựng lại từng khối)
│
├── README.md  SETUP.md  DATABASE.md  KIEN_TRUC.md  HUONG_DAN_TU_DAU.md
├── BAOCAO_DANHGIA.md       # báo cáo đánh giá AI
└── (sinh khi chạy) appointments.json  device_tokens.json  audit_log.jsonl  outbox/
```

---

## 7. Nguyên tắc thiết kế (vì sao tách như vậy)
1. **Tách tầng:** client chỉ hiển thị, backend giữ logic → đổi giao diện không đụng nghiệp vụ.
2. **Một việc một khối:** triage/booking/safety/push độc lập, dễ test riêng & thay thế.
3. **Tách "logic" khỏi "nơi lưu":** `storage.py` cho phép đổi JSON ↔ Supabase mà không sửa
   booking/push.
4. **Chạy được ngay (offline-first):** không có DB/LLM vẫn chạy nhờ fallback → dễ demo, dễ chấm.
5. **An toàn là bắt buộc:** guardrail (cấp cứu, PII, chống chẩn đoán) ưu tiên cao nhất.
   Bộ pattern quản lý online ở DB (`safety_patterns`) nhưng **fail-safe**: DB chỉ mở rộng,
   nhóm rỗng/mất kết nối → tự dùng seed trong `safety.py` → guardrail không bao giờ biến mất.
