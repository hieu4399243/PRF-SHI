# BÁO CÁO ĐỒ ÁN MÔN HỌC
# Trợ lý Nha khoa SHI — Chatbot tư vấn & đặt lịch nha khoa tiếng Việt

---

## 1. Background (Bối cảnh & Tổng quan)

Tại các phòng khám nha khoa, một tỷ lệ lớn cuộc gọi/đến quầy chỉ để **hỏi nên khám
dịch vụ nào** và **đặt lịch hẹn**. Người bệnh thường mô tả triệu chứng bằng ngôn ngữ
đời thường ("răng ê buốt khi ăn ngọt", "chảy máu chân răng", "niềng răng hết bao nhiêu")
chứ không biết tên chuyên khoa. Việc phân loại thủ công gây quá tải lễ tân, dễ dẫn nhầm
dịch vụ và bỏ lỡ lịch hẹn do thiếu nhắc nhở.

**Trợ lý Nha khoa SHI** là một chatbot tiếng Việt cho **một phòng khám nha khoa**, giải
quyết đúng nút thắt đó: bệnh nhân mô tả triệu chứng răng miệng → hệ thống **phân loại đúng
nhóm dịch vụ nha khoa** (triage) → **đặt lịch** với bác sĩ phụ trách → **nhắc lịch tự động**
qua thông báo đẩy (push) và file lịch `.ics`.

Điểm nhấn của đồ án không chỉ là "một chatbot chạy được", mà là một hệ thống **có đo lường
chất lượng AI** (Precision/Recall/F1 trên tập dữ liệu gán nhãn), **có lớp an toàn y tế**
(phát hiện cấp cứu, không chẩn đoán/kê đơn, ẩn PII, ghi audit log theo Nghị định 13/2023),
và **kiến trúc sẵn sàng mở rộng lên cloud** (chạy được cả với file JSON lẫn Postgres/Supabase).
Sản phẩm phục vụ đồng thời **web demo** và **app native (Expo)** qua cùng một bộ REST API.

---

## 2. Phân chia nhiệm vụ

> *Bảng dưới là khung phân công theo các khối chức năng thực tế của repo. Vui lòng thay
> tên thành viên và điều chỉnh tỷ lệ % cho đúng nhóm trước khi nộp.*

| TT | Thành viên | Nhiệm vụ phụ trách | Sản phẩm/Module | % Đóng góp |
|----|-----------|--------------------|-----------------|:----------:|
| 1 | *(Thành viên A)* | Triage engine + Hệ thống đánh giá AI | `triage.py`, `eval/` (dataset, evaluate, results) | 25% |
| 2 | *(Thành viên B)* | Lõi hội thoại + Lớp an toàn y tế | `chatbot.py`, `safety.py` | 25% |
| 3 | *(Thành viên C)* | Đặt lịch + Lưu trữ + Dữ liệu danh mục | `booking.py`, `storage.py`, `data.py` | 20% |
| 4 | *(Thành viên D)* | Push, nhắc lịch & tích hợp lịch | `push.py`, `reminder_worker.py`, `calendar_ics.py` | 15% |
| 5 | *(Thành viên E)* | App native (Expo) + Web demo + Báo cáo | `mobile/`, `templates/index.html`, tài liệu | 15% |
| | | **Tổng** | | **100%** |

*Ghi chú: backend (`app.py`) và việc tích hợp giữa các module là phần làm chung của cả nhóm.*

---

## 3. Mục tiêu

### 3.1. Mục tiêu chung
Xây dựng một **trợ lý ảo tiếng Việt cho phòng khám nha khoa** giúp người bệnh **chọn đúng
dịch vụ** và **đặt lịch hẹn** một cách an toàn, đồng thời **nhắc lịch chủ động** — vận hành
được trên cả web và điện thoại, tuân thủ pháp luật về dữ liệu cá nhân.

### 3.2. Mục tiêu cụ thể
1. **Triage chính xác**: phân loại mô tả triệu chứng (kể cả gõ thiếu dấu) vào đúng 1 trong
   9 nhóm dịch vụ nha khoa.
2. **Hội thoại có dẫn dắt**: máy trạng thái đưa người dùng đi tuần tự từ mô tả triệu chứng →
   xác nhận dịch vụ → chọn bác sĩ → chọn ngày/giờ → nhập tên & số điện thoại → xác nhận đặt
   lịch; hỗ trợ **hỏi thông tin dịch vụ** và **hủy lịch** đã đặt.
3. **An toàn y tế (guardrails)**: phát hiện cấp cứu (gọi 115), **không chẩn đoán/không kê đơn**,
   chuyển người thật khi cần, ẩn PII và ghi audit log.
4. **Nhắc lịch chủ động**: bắn push xác nhận khi đặt thành công và nhắc trước 1 ngày / 2 giờ;
   cho phép thêm lịch vào Google/Apple Calendar.
5. **Đa nền tảng**: phục vụ cả web demo và app native (Expo) qua cùng bộ REST API.
6. **Đo lường được chất lượng AI**: hệ thống đánh giá tính Precision/Recall/F1, so sánh hai
   phiên bản thuật toán triage.
7. **Sẵn sàng mở rộng**: tách lớp lưu trữ để chạy được cả file JSON (demo) lẫn Postgres/Supabase
   (production), và có điểm cắm LLM (Claude) cho NLU.

---

## 4. Các tính năng chính

| # | Tính năng | Mô tả |
|---|-----------|-------|
| 1 | **Triage theo từ khóa, 2 phiên bản** | Phân loại triệu chứng → nhóm dịch vụ bằng chấm điểm từ khóa. `v1` so khớp có dấu; `v2` (mặc định) **không phân biệt dấu**, bắt được cả văn bản thiếu dấu. Cụm từ có trọng số cao hơn từ đơn. |
| 2 | **Đánh giá độ tin cậy** | `confidence_level()` trả `high/medium/low` để quyết định: tự đề xuất, đưa nhiều lựa chọn, hay hỏi follow-up. |
| 3 | **Hội thoại theo máy trạng thái** | Luồng đặt lịch: `GREET → TRIAGE → CONFIRM_DEPT → PICK_DOCTOR → PICK_DATE → PICK_TIME → ASK_NAME → ASK_PHONE → CONFIRM_BOOKING → DONE`. Thêm nhánh **hủy lịch** `CANCEL_ASK_PHONE → CANCEL_PICK → CANCEL_CONFIRM`. |
| 4 | **Đặt lịch chống trùng (đối chiếu DB)** | Khung giờ **luôn hiển thị đầy đủ**; tới bước xác nhận mới **đối chiếu trực tiếp DB** (`_confirmed_at`): khung đã có người khác đặt → mời chọn giờ khác; cùng SĐT đã đặt đúng khung → hỏi hủy lịch cũ. Sinh mã `SHI-XXXXXX`, lưu bền vững. DB là nguồn chân lý duy nhất. |
| 4b | **Thu thập & xác nhận số điện thoại** | Bước `ASK_PHONE` bắt buộc SĐT, có chuẩn hóa/kiểm tra (10 số, chấp nhận `+84`/khoảng trắng); dùng để nhắc lịch và nhận diện đặt trùng. |
| 5 | **Guardrails an toàn y tế** | Phát hiện cấp cứu → gọi 115; chặn yêu cầu chẩn đoán/kê đơn; human handoff; gắn disclaimer. |
| 6 | **Bảo vệ dữ liệu cá nhân** | Ẩn PII (SĐT, email, CCCD) và ghi **audit log** `audit_log.jsonl` cho mỗi lượt hội thoại. |
| 7 | **Push notification (Expo)** | Bắn thông báo xác nhận đặt lịch + nhắc lịch, miễn phí, không cần API key. |
| 8 | **Worker nhắc lịch** | Nhắc trước **1 ngày**, **tối hôm trước** (chăm sóc), **2 giờ**; mỗi loại gửi đúng 1 lần. |
| 9 | **Xuất lịch `.ics` + Google Calendar** | Thêm lịch hẹn vào iPhone/Outlook/Google, có chuông nhắc (VALARM), không cần OAuth. |
| 10 | **Lớp lưu trữ kép** | Có `DATABASE_URL` → Postgres/Supabase; không có → file JSON. Đổi backend không phải sửa nghiệp vụ. |
| 11 | **App native Expo** | UI chat React Native, mở qua Expo Go bằng QR. |
| 12 | **Hệ thống đánh giá AI** | `eval/` với 63 câu gán nhãn, tính Precision/Recall/F1, so sánh v1 vs v2 → `results.md`, `BAOCAO_DANHGIA.md`. |
| 13 | **Hủy lịch đã đặt** | Người dùng gõ *"hủy lịch"* → tra theo SĐT → chọn lịch → xác nhận hủy (`status='cancelled'`, khung giờ tự trống lại) + push báo hủy. Khi đặt trùng còn hỏi thẳng *"hủy lịch cũ & đặt lại?"* rồi **đặt tiếp lịch đang dở** thay vì bắt làm lại. |
| 14 | **Fallback than phiền chung** | Câu mơ hồ nhưng rõ là vấn đề răng miệng (*"khó chịu ở răng khi ăn cơm"*) → đưa lựa chọn có cấu trúc thay vì báo "chưa rõ" (`mentions_dental_discomfort`). |
| 15 | **Hỏi–đáp thông tin dịch vụ** | *"nội nha khám gì?", "trồng răng là gì?"* → trả mô tả dịch vụ (`data.SERVICE_INFO`) + mời đặt lịch (`info_question_service`). |
| 16 | **Web demo toàn màn hình** | `templates/index.html` bố cục chat trải kín viewport (header/ô nhập full-width, cột hội thoại căn giữa) thay cho khung nổi nhỏ. |

---

## 5. Công nghệ sử dụng

**Backend (Python)**
- **Flask 3.0.3** — web server + REST API (`/`, `/api/start`, `/api/chat`, `/api/register-push`, `/api/ics/<code>`).
- **Thư viện chuẩn Python**: `re` + `unicodedata` (chuẩn hóa/bỏ dấu tiếng Việt cho triage), `urllib` (gọi Expo Push), `json`, `uuid`, `datetime`.
- **psycopg 3.2.3** *(tùy chọn)* — kết nối Postgres/Supabase khi có `DATABASE_URL`.
- **python-dotenv 1.0.1** *(tùy chọn)* — nạp biến môi trường từ `.env`.

**Mobile**
- **React Native / Expo (SDK 54)** — app native, mở qua **Expo Go** + QR.

**Dịch vụ ngoài**
- **Expo Push Service** — gửi thông báo đẩy (miễn phí, không cần key).
- **Supabase / Postgres** *(tùy chọn)* — lưu trữ bền vững cho production.

**Chuẩn & định dạng**
- **iCalendar (.ics)** với VALARM — tích hợp lịch hệ điều hành.
- **JSONL** — audit log, outbox push, dataset đánh giá.

**Điểm cắm AI nâng cao (tùy chọn)**
- **Claude API (Anthropic)** — `triage.classify_with_llm()` là khung sẵn để thay rule-based
  bằng LLM (claude-opus-4-8 / claude-sonnet-4-6) khi cần NLU mạnh hơn.

---

## 6. Workflow và Structure

### 6.1. Workflow vận hành

```
Bệnh nhân (web / app Expo)
        │  POST /api/start, /api/chat  (REST JSON)
        ▼
   chatbot.py  ── máy trạng thái hội thoại ──┐
        │                                    │ ƯU TIÊN: safety.py
        │                                    │ (cấp cứu→115 / handoff / chặn chẩn đoán / audit)
        ▼                                    │
   triage.py  ──► phân loại dịch vụ (v2, không dấu) + độ tin cậy
        ▼
   booking.py ──► chọn bác sĩ → ngày → giờ trống → tạo lịch (mã SHI-XXXXXX)
        ▼
   storage.py ──► Supabase/Postgres  HOẶC  file JSON
        ▼
   push.py (Expo) ──► thông báo "Đặt lịch thành công"
        │
   calendar_ics.py ──► link .ics + Google Calendar
        │
   reminder_worker.py ──► nhắc trước 1 ngày / tối hôm trước / 2 giờ
```

**Tóm tắt một phiên đặt lịch:**
1. App gọi `/api/start` → nhận lời chào + `session`.
2. Người dùng mô tả triệu chứng → `/api/chat` → triage chọn dịch vụ, hỏi xác nhận.
   (Có thể hỏi *"dịch vụ X là gì"* để xem mô tả trước khi đặt.)
3. Chọn bác sĩ → ngày → giờ → nhập **tên** → nhập **số điện thoại** → xác nhận.
4. Khi xác nhận, hệ thống **đối chiếu DB**: nếu khung giờ đã bị đặt hoặc SĐT đã có lịch
   trùng thì báo lại (và cho **hủy lịch cũ để đặt tiếp**); nếu trống thì tạo lịch, bắn
   push xác nhận, trả link `.ics`/Google Calendar.
5. `reminder_worker.py` quét nền và nhắc khi tới hạn.
6. Muốn hủy: gõ *"hủy lịch"* → tra theo SĐT → chọn lịch → xác nhận (`status='cancelled'`).

### 6.2. Cấu trúc thư mục

```
PRF-SHI/
├── app.py                 # Flask app + routes (chạy 0.0.0.0:5001, debug)
├── chatbot.py             # Máy trạng thái hội thoại (SESSIONS in-memory)
├── triage.py              # "Hàm lượng AI": phân loại triệu chứng → dịch vụ (v1/v2)
├── safety.py              # Guardrails: cấp cứu, PII, chặn chẩn đoán, audit log
├── booking.py             # Đặt lịch & hủy lịch; chống trùng đối chiếu DB; sinh mã lịch hẹn
├── data.py                # 9 nhóm dịch vụ + bác sĩ + khung giờ + mô tả (SERVICE_INFO)
├── storage.py             # Lớp lưu trữ kép: Postgres/Supabase ↔ file JSON
├── push.py                # Gửi push qua Expo Push Service
├── reminder_worker.py     # Quét lịch, bắn nhắc (--once/--watch/--test)
├── calendar_ics.py        # Sinh file .ics (VALARM) + link Google Calendar
├── requirements.txt
├── templates/index.html   # Web demo
├── eval/                  # Đánh giá AI
│   ├── dataset.jsonl      #   63 câu gán nhãn
│   ├── evaluate.py        #   tính Precision/Recall/F1, v1 vs v2
│   ├── results.md         #   kết quả
│   └── rubric.md          #   tiêu chí định tính
├── scripts/migrate_to_supabase.py
├── mobile/                # App native Expo (SDK 54)
│   ├── App.js             #   UI chat
│   └── src/{api,config,notify,usePush,calendar,html}.js
├── appointments.json / device_tokens.json   # lưu trữ JSON (fallback)
├── audit_log.jsonl        # nhật ký hội thoại (đã ẩn PII)
└── outbox/push_outbox.jsonl  # push khi chưa có thiết bị thật
```

**Cách chạy local (3 terminal):**
```bash
# Backend (cổng 5001 vì macOS chiếm 5000 cho AirPlay)
PORT=5001 ./.venv/bin/python app.py
# Worker nhắc lịch (tùy chọn)
./.venv/bin/python reminder_worker.py --watch
# App native
cd mobile && npx expo start -c
```

---

## 7. Mã nguồn và giải thích

### 7.1. Triage engine — phần "hàm lượng AI" cốt lõi (`triage.py`)

Đây là điểm AI trung tâm: phân loại triệu chứng tiếng Việt → nhóm dịch vụ bằng **chấm điểm
từ khóa**, có xử lý đặc thù tiếng Việt (bỏ dấu, khớp ranh giới từ).

```python
def _strip_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt: 'răng sâu' -> 'rang sau' (giữ chữ 'đ' -> 'd')."""
    text = text.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")

def _contains_word(haystack: str, needle: str) -> bool:
    """Khớp theo RANH GIỚI TỪ (whole-word), tránh 'chân răng' chứa 'hàn răng'."""
    return f" {needle} " in f" {haystack} "
```

**Giải thích logic:**
- `_strip_accents` dùng phân rã Unicode NFD rồi loại bỏ ký tự dấu (`category == "Mn"`),
  nhờ đó "rang sau" (gõ thiếu dấu) vẫn khớp "răng sâu". Chữ "đ" xử lý riêng vì NFD không tách nó.
- `_contains_word` bao chuỗi bằng dấu cách hai đầu để khớp **trọn từ**, tránh nhận nhầm khi
  từ khóa nằm trong một từ khác.

```python
for kw in dept["keywords"]:
    hit = _contains_word(norm, kw)
    if not hit and version == "v2":
        hit = _contains_word(norm_na, _strip_accents(kw))   # thử lại bản không dấu
    if hit:
        weight = 2 if " " in kw else 1   # cụm từ nặng hơn từ đơn
        score += weight
        matched.append(kw)
```

**Giải thích:** với mỗi nhóm dịch vụ, cộng điểm theo từ khóa khớp. `v2` (mặc định) thử thêm
bản không dấu nếu bản có dấu trượt → **bền với lỗi gõ thiếu dấu**. Cụm từ (như "đau răng dữ
dội") có trọng số 2 vì đặc trưng hơn từ đơn. Các dịch vụ được sắp xếp theo điểm giảm dần.

```python
def confidence_level(results) -> str:
    if not results:           return "low"     # không nhận ra → hỏi thêm
    if len(results) == 1:     return "high"
    top, second = results[0]["score"], results[1]["score"]
    if top >= second + 2:     return "high"     # dẫn đầu rõ ràng
    return "medium"                             # điểm sát nhau → cho chọn
```

**Giải thích:** độ tin cậy quyết định cách bot phản hồi — cơ chế "biết khi nào mình chưa chắc",
tránh đoán bừa.

> Quyết định dùng v2 được kiểm chứng bằng `eval/`: trên 63 câu, **v2 đạt
> Accuracy/Precision/Recall/F1 = 100%** so với v1 (Accuracy 77.8%, F1 87.3%) — chứng minh việc
> xử lý không dấu là cải tiến then chốt.

### 7.2. Lớp an toàn y tế (`safety.py`)

```python
def check_emergency(text: str) -> bool:
    low = text.lower()
    return any(p in low for p in EMERGENCY_PATTERNS)   # "sưng mặt lan", "gãy xương hàm"...

def mask_pii(text: str) -> str:
    masked = text
    for pattern, label in PII_PATTERNS:                # SĐT, email, CCCD
        masked = pattern.sub(label, masked)
    return masked

def audit(session_id, role, message, meta=None):
    entry = {"ts": ..., "session": session_id, "role": role,
             "message": mask_pii(message), "meta": meta or {}}   # luôn ẩn PII trước khi lưu
    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
```

**Giải thích:** đây là điểm phân biệt một chatbot y tế "thật". Mọi lượt hội thoại được ghi log
nhưng **PII luôn bị ẩn trước khi ghi** (tuân thủ NĐ 13/2023). Cấp cứu/handoff/chặn chẩn đoán
được kiểm tra ở tầng cao nhất trong `chatbot.py`.

### 7.3. Điều phối hội thoại — guardrails ưu tiên trước routing (`chatbot.py`)

```python
def handle_message(session_id, raw_message):
    sess = get_session(session_id)
    message = (raw_message or "").strip()
    safety.audit(session_id, "user", message, {"state": sess["state"]})

    # --- GUARDRAIL ưu tiên cao nhất ---
    if safety.check_emergency(message):
        safety.audit(session_id, "bot", "[EMERGENCY]", {"flag": "emergency"})
        return _reply(safety.EMERGENCY_MESSAGE, state=sess["state"])
    if safety.needs_human_handoff(message):
        ...  # chuyển nhân viên thật

    # --- Định tuyến theo trạng thái ---
    state = sess["state"]
    if   state == "TRIAGE":          resp = _do_triage(sess, message)
    elif state == "CONFIRM_DEPT":    resp = _confirm_dept(sess, message)
    elif state == "PICK_DOCTOR":     resp = _pick_doctor(sess, message)
    ...
```

**Giải thích:** dù người dùng đang ở bước nào, **an toàn được kiểm tra trước routing**. Sau đó
mới định tuyến theo trạng thái phiên. Phản hồi gồm `reply` (HTML) + `options` (nút bấm) +
`state` mới, nên cả web và app native dùng chung một hợp đồng dữ liệu.

```python
if conf == "high":
    sess["dept_code"] = top["code"]
    text = f"Dựa trên mô tả, bạn nên dùng dịch vụ <b>{top['name']}</b> ..."
    return _reply(safety.add_disclaimer(text), options=[...], state="CONFIRM_DEPT")
```

**Giải thích:** kết quả triage được "dịch" thành câu trả lời thân thiện kèm **disclaimer**;
nếu độ tin cậy trung bình thì đưa 2–3 lựa chọn, nếu thấp thì hỏi follow-up.

### 7.4. Đặt lịch chống trùng — đối chiếu DB lúc xác nhận (`booking.py`)

```python
def _confirmed_at(date_str, time_str):
    """Lịch 'confirmed' đang chiếm đúng khung ngày+giờ (nếu có). Đối chiếu DB."""
    for a in storage.list_appointments():
        if a.get("status") == "confirmed" and a.get("date") == date_str \
                and a.get("time") == time_str:
            return a
    return None

def book_appointment(session_id, dept_code, doctor_id, date_str, time_str,
                     patient_name="", patient_phone=""):
    if time_str not in generate_available_slots().get(date_str, []):
        return False, {"error": "Khung giờ không hợp lệ..."}
    taken = _confirmed_at(date_str, time_str)          # NGUỒN CHÂN LÝ = DB
    if taken:
        if patient_phone and taken.get("patient_phone") == patient_phone:
            return False, {"duplicate": True, "existing": taken}   # chính người này đã đặt
        return False, {"error": "Khung giờ này vừa có người đặt..."}
    storage.add_appointment(appointment)               # còn trống → ghi lịch
    return True, appointment
```

**Giải thích:** không còn bảng khung giờ in-memory. Danh sách giờ **luôn hiển thị đầy đủ**;
việc một khung đã bị đặt hay chưa được **kiểm tra trực tiếp với DB ngay lúc xác nhận** — nhờ
vậy DB là nguồn chân lý duy nhất, không lệch khi chạy nhiều tiến trình / qua nhiều ngày / sau
restart. Nếu trùng cùng SĐT → trả `duplicate` để hội thoại hỏi **hủy lịch cũ rồi đặt tiếp**.

### 7.4b. Hủy lịch (`booking.py` + `storage.py`)

```python
def cancel_appointment(code):
    """Hủy lịch (đặt status='cancelled'); khung giờ tự trống lại vì _confirmed_at
    chỉ tính lịch 'confirmed'. Trả appt đã hủy, hoặc None nếu không hợp lệ."""
    appt = storage.get_appointment(code)
    if not appt or appt.get("status") != "confirmed":
        return None
    storage.set_status(code, "cancelled")
    return appt
```

**Giải thích:** hủy = đổi trạng thái, không xóa dữ liệu (giữ vết cho audit). Vì khung bận chỉ
tính lịch `confirmed`, hủy xong slot lập tức đặt lại được. `upcoming_by_phone(phone)` liệt kê
lịch sắp tới của một SĐT để người dùng chọn lịch cần hủy.

### 7.5. Lớp lưu trữ kép (`storage.py`)

```python
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
USE_DB = bool(DATABASE_URL)

def add_appointment(appt):
    appt.setdefault("reminders_sent", [])
    if USE_DB:
        init_schema()
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO appointments (...) VALUES (%s,...)", (...))
            conn.commit()
        return
    items = _json_load(APPOINTMENTS_PATH, [])   # fallback file JSON
    items.append(appt); _json_save(APPOINTMENTS_PATH, items)
```

**Giải thích:** một biến môi trường `DATABASE_URL` quyết định toàn bộ backend lưu trữ.
`booking.py` và `push.py` chỉ gọi qua `storage`, nên chuyển từ demo (JSON) sang production
(Supabase) **không phải sửa nghiệp vụ**.

### 7.6. Nhắc lịch (`reminder_worker.py`)

```python
def _rules(appt):
    return [
        {"key": "remind_1d", "before": timedelta(days=1),  "title": "📅 Nhắc lịch khám (còn 1 ngày)", ...},
        {"key": "care_eat",  "before": timedelta(hours=14), "title": "🍵 Nhắc chăm sóc sức khỏe", ...},
        {"key": "remind_2h", "before": timedelta(hours=2),  "title": "⏰ Sắp tới giờ khám (còn 2 giờ)", ...},
    ]

for rule in _rules(appt):
    if rule["key"] in already:           # đã gửi → bỏ qua
        continue
    due_time = appt_dt - rule["before"]
    if force or (now >= due_time and now <= appt_dt):
        _send_for(appt, rule)            # gửi push + đánh dấu reminders_sent
```

**Giải thích:** worker quét toàn bộ lịch, gửi mỗi loại nhắc đúng **một lần** (lưu trong
`reminders_sent`). Chạy `--watch` (nền 60s) hoặc `--once` (cắm vào cron). `push.send_push`
tự ghi `outbox` khi token chưa thật → kiểm thử được luồng mà không cần điện thoại.

---

## 8. Screenshots

> *Chèn ảnh chụp thực tế vào đúng vị trí placeholder bên dưới (kéo ảnh vào file Word, hoặc
> đặt ảnh cùng thư mục rồi thay đường dẫn). Mỗi ảnh kèm chú thích đã gợi ý sẵn.*

**Hình 1 — Màn hình chào & nhập triệu chứng (web demo).**
`![Màn hình chào](screenshots/01-greeting.png)`
*Chú thích:* Bot tự giới thiệu là "Trợ lý Nha khoa SHI", hiển thị disclaimer "không chẩn đoán
bệnh, không kê đơn", và mời người dùng mô tả triệu chứng.

**Hình 2 — Kết quả triage & xác nhận dịch vụ.**
`![Triage](screenshots/02-triage.png)`
*Chú thích:* Người dùng gõ "răng tôi bị sâu và ê buốt khi ăn ngọt" → bot đề xuất dịch vụ
**Trám răng / Sâu răng** kèm 2 nút "Đặt lịch" / "Mô tả lại".

**Hình 3 — Chọn bác sĩ → ngày → khung giờ.**
`![Đặt lịch](screenshots/03-booking-steps.png)`
*Chú thích:* Các bước chọn được hiển thị dưới dạng nút bấm; khung giờ luôn hiển thị đầy đủ,
việc trùng giờ được đối chiếu với DB ở bước xác nhận. Sau khi chọn giờ, bot hỏi thêm **tên**
và **số điện thoại**.

**Hình 4 — Đặt lịch thành công + link lịch.**
`![Thành công](screenshots/04-success.png)`
*Chú thích:* Bot trả mã lịch hẹn `SHI-XXXXXX`, link "Thêm vào Lịch (.ics)" và "Thêm vào Google
Calendar"; đồng thời bắn push xác nhận.

**Hình 5 — Guardrail cấp cứu.**
`![Cấp cứu](screenshots/05-emergency.png)`
*Chú thích:* Khi phát hiện cụm cấp cứu (vd. "gãy xương hàm"), bot dừng tư vấn và hướng dẫn gọi **115**.

**Hình 6 — Thông báo đẩy / nhắc lịch trên điện thoại (Expo).**
`![Push](screenshots/06-push.png)`
*Chú thích:* Thông báo "✅ Đặt lịch thành công" và nhắc "⏰ Sắp tới giờ khám (còn 2 giờ)".

**Hình 7 — Kết quả đánh giá AI (`eval/results.md`).**
`![Eval](screenshots/07-eval.png)`
*Chú thích:* Bảng so sánh v1 vs v2 — v2 đạt Accuracy/Precision/Recall/F1 = 100% trên 63 mẫu.

*Cách tạo nhanh ảnh Hình 1–5:* chạy backend rồi mở `http://127.0.0.1:5001`, thao tác và chụp
màn hình. Hình 7 có thể chụp trực tiếp bảng trong `eval/results.md`.

---

## 9. Kết luận

### 9.1. Mức độ hoàn thành so với mục tiêu

| Mục tiêu | Trạng thái | Bằng chứng |
|----------|:----------:|-----------|
| Triage chính xác (kể cả thiếu dấu) | ✅ Hoàn thành | `triage.py` v2; eval 63 mẫu đạt F1 = 100% |
| Hội thoại dẫn dắt đặt lịch | ✅ Hoàn thành | Máy trạng thái trong `chatbot.py` (đặt lịch + nhánh hủy lịch) |
| Thu thập SĐT & chống đặt trùng | ✅ Hoàn thành | Bước `ASK_PHONE`; `book_appointment` đối chiếu DB (trùng giờ/SĐT) |
| Hủy lịch đã đặt | ✅ Hoàn thành | `cancel_appointment` + nhánh `CANCEL_*`; `status='cancelled'` |
| Hỏi–đáp thông tin dịch vụ | ✅ Hoàn thành | `triage.info_question_service` + `data.SERVICE_INFO` |
| Guardrails an toàn y tế | ✅ Hoàn thành | `safety.py`: cấp cứu, chặn chẩn đoán, PII, audit |
| Nhắc lịch chủ động | ✅ Hoàn thành | `reminder_worker.py` + `push.py` + `.ics` |
| Đa nền tảng (web + app) | ✅ Hoàn thành | REST API dùng chung; `mobile/` (Expo) |
| Đo lường chất lượng AI | ✅ Hoàn thành | `eval/` + `BAOCAO_DANHGIA.md` |
| Sẵn sàng lên cloud (DB) | ✅ Cơ bản | `storage.py` hỗ trợ Postgres/Supabase |

Nhìn chung đồ án **đạt toàn bộ mục tiêu đề ra** ở mức demo hoàn chỉnh, có đo lường định lượng
và có lớp an toàn — vượt trên một chatbot thông thường.

### 9.2. Hạn chế hiện tại
- **Triage rule-based**: phụ thuộc bộ từ khóa, có thể trượt với cách diễn đạt lạ; tập đánh giá
  (63 câu) còn nhỏ và "thân thiện" với từ khóa.
- **Session in-memory** (`chatbot.SESSIONS`): mất khi restart, chưa scale nhiều worker.
- **Chạy bằng dev server + `debug=True`**, `API_BASE` còn là IP LAN, chưa cấu hình CORS — chưa
  phải cấu hình production.

### 9.3. Hướng phát triển tương lai
1. **Nâng NLU bằng LLM**: kích hoạt `classify_with_llm()` (Claude) làm tầng dự phòng/kết hợp
   khi rule-based có độ tin cậy thấp; mở rộng tập đánh giá đa dạng hơn.
2. **Production hardening**: chạy bằng `gunicorn`, tắt debug, thêm CORS, đưa `API_BASE` về URL
   HTTPS công khai (Render/Railway/Fly.io).
3. **Session bền vững**: chuyển trạng thái hội thoại sang Redis/DB để scale nhiều tiến trình.
4. **Phát hành app thật**: build bằng **EAS** → APK/AAB (Google Play) hoặc iOS (App Store),
   kèm privacy policy và disclaimer y tế.
5. **Tích hợp lịch bác sĩ thật & quản trị**: đồng bộ Google Calendar phía phòng khám, trang
   quản trị xem/duyệt lịch hẹn, thống kê.
6. **Mở rộng nghiệp vụ**: nhắc tái khám, đánh giá sau khám, hỏi đáp về chi phí dịch vụ.

---

*Tài liệu này được sinh kèm dự án "Trợ lý Nha khoa SHI". Xem thêm `BAOCAO_DANHGIA.md` (đánh giá
AI chi tiết), `KIEN_TRUC.md` (kiến trúc) và thư mục `hoc/` (giải thích từng module).*
