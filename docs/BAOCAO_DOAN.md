# BÁO CÁO ĐỒ ÁN MÔN HỌC
# Trợ lý Nha khoa SHI — Chatbot tư vấn & đặt lịch nha khoa tiếng Việt

---

## 1. Bối cảnh và bài toán

### 1.1. Quy trình đặt lịch khám nha khoa hiện nay

Hiện nay, phần lớn phòng khám nha khoa vừa và nhỏ ở Việt Nam vẫn tiếp nhận bệnh nhân
theo hình thức **thủ công qua điện thoại hoặc đến trực tiếp quầy lễ tân**. Qua quan sát
và khảo sát nhanh của nhóm ở một số phòng khám, quy trình từ lúc người bệnh có nhu cầu
đến lúc có lịch hẹn thường gồm **6 bước** như Hình 1.

**Hình 1 — Quy trình đặt lịch nha khoa thủ công hiện tại (6 bước).**

```
(1) Người bệnh        (2) Gọi điện /        (3) Lễ tân hỏi lại      (4) Lễ tân đoán
  có triệu chứng  ──►   đến quầy trong    ──►  triệu chứng, ghi   ──►  dịch vụ & bác sĩ
  ("ê buốt","niềng")     giờ hành chính        tay thông tin            phụ trách
                                                                             │
   (6) Không có hệ       (5) Lễ tân tra sổ/                                   ▼
   thống nhắc → dễ   ◄──  Excel tìm lịch bác  ◄──────────────────────────────┘
   quên, bỏ lịch hẹn      sĩ trống rồi chốt giờ
```
*Chú thích:* Toàn bộ quy trình phụ thuộc lễ tân, chỉ chạy trong giờ hành chính và không có
bước nhắc lịch tự động. Các bước (3), (4), (5), (6) là nơi phát sinh phần lớn bất tiện.

Phân rã chi tiết từng bước cùng thời gian ước lượng và điểm chưa hợp lý:

**Bảng 1 — Phân rã các bước và điểm nghẽn của quy trình hiện tại.**

| Bước | Mô tả | Thời gian ước lượng | Điểm chưa hợp lý |
|------|-------|:-------------------:|------------------|
| 1 | Người bệnh nhận ra triệu chứng, muốn đặt khám | — | Người bệnh **không biết mình cần dịch vụ/chuyên khoa nào** (mô tả "ê buốt", "niềng răng bao nhiêu tiền"). |
| 2 | Gọi điện / đến quầy | 1–5 phút chờ máy | **Chỉ trong giờ hành chính**; giờ cao điểm máy bận, khách bỏ cuộc gọi. |
| 3 | Lễ tân hỏi lại & ghi tay | 2–3 phút | Lặp lại thủ công cho **từng khách**; dễ ghi nhầm/thiếu thông tin. |
| 4 | Lễ tân **đoán dịch vụ** & bác sĩ phụ trách | 1–2 phút | Phụ thuộc kinh nghiệm lễ tân → **dễ định tuyến nhầm dịch vụ**, khách phải khám lại. |
| 5 | Tra sổ/Excel tìm giờ trống, chốt lịch | 2–4 phút | Thủ công, **dễ trùng giờ** khi nhiều người gọi cùng lúc. |
| 6 | (Thường thiếu) nhắc lịch | — | Không nhắc tự động → **tỷ lệ quên/bỏ lịch (no-show) cao**. |

Tổng thời gian mỗi lượt đặt lịch **≈ 6–14 phút** và **toàn bộ nằm trên vai lễ tân**.

> *Ghi chú số liệu:* các con số thời gian trong Bảng 1 là **ước lượng của nhóm** từ khảo sát
> nhanh; nhóm khuyến nghị thay bằng số đo thực tế khi triển khai (mẫu phiếu khảo sát ở Phụ lục).

### 1.2. Các điểm nghẽn (pain point) và bằng chứng

Từ quy trình trên, nhóm tổng hợp **bốn nút thắt chính**, gắn với bước phát sinh và hệ quả
đo được:

**Bảng 2 — Điểm nghẽn, nguyên nhân và tác động (ước lượng).**

| # | Điểm nghẽn | Phát sinh ở bước | Tác động (ước lượng) |
|---|------------|:----------------:|----------------------|
| A | Người bệnh **không biết chọn dịch vụ nào** | 1, 4 | ~**60–70%** cuộc gọi/đến quầy chỉ để **hỏi nên khám gì** rồi mới đặt. |
| B | **Định tuyến nhầm dịch vụ** do đoán thủ công | 4 | Khách phải chuyển bác sĩ/khám lại → mất thêm 1 lượt hẹn. |
| C | **Quá tải lễ tân & giới hạn giờ hành chính** | 2, 3, 5 | Mất khách gọi ngoài giờ; giờ cao điểm khách bỏ cuộc gọi. |
| D | **Không nhắc lịch → no-show** | 6 | Bỏ lịch hẹn gây trống ghế, giảm doanh thu; đây là vấn đề **được ghi nhận phổ biến** trong y tế. |

**Hình 2 — Cơ cấu lý do liên hệ phòng khám (biểu đồ cột, số liệu ước lượng để minh họa).**

```
Hỏi nên khám dịch vụ nào  ██████████████████████████████████  65%
Đặt / đổi lịch hẹn        ████████████████████              40%
Hỏi giá / thông tin dịch vụ ████████████                    25%
Việc khác                 ████                              10%
                          0%      20%      40%      60%
```
*Chú thích:* Phần lớn tương tác đầu vào là **hỏi dịch vụ + đặt lịch** — đúng hai việc mà hệ
thống SHI tự động hóa. (Số liệu minh họa; các cột lấy từ bảng dữ liệu ở Phụ lục để nhóm vẽ
lại thành biểu đồ trong bản Word.)

Ba việc lặp đi lặp lại nhiều nhất — **(1) phân loại dịch vụ, (2) chốt lịch trống, (3) nhắc
lịch** — đều có thể tự động hóa. Đó chính là phạm vi bài toán của đồ án.

### 1.3. Giải pháp đề xuất — Trợ lý Nha khoa SHI

**Trợ lý Nha khoa SHI** là một chatbot tiếng Việt cho **một phòng khám nha khoa**, thay quy
trình 6 bước thủ công bằng luồng tự phục vụ, giải quyết trực tiếp bốn nút thắt A–D:

- **(→ A, B) Phân loại dịch vụ tự động (triage):** người bệnh mô tả triệu chứng bằng ngôn
  ngữ đời thường → hệ thống phân loại đúng **nhóm dịch vụ nha khoa** và gợi ý bác sĩ phụ trách,
  không phụ thuộc lễ tân đoán.
- **(→ C) Đặt lịch 24/7, chống trùng:** chọn bác sĩ → ngày → giờ, đối chiếu trực tiếp cơ sở
  dữ liệu ở bước xác nhận nên **không trùng giờ**, hoạt động **mọi lúc**, không cần lễ tân.
- **(→ D) Nhắc lịch chủ động:** gửi thông báo đẩy (push) khi đặt thành công và nhắc trước
  1 ngày / 2 giờ, kèm file lịch `.ics` để thêm vào Google/Apple Calendar → **giảm no-show**.

**Bảng 3 — So sánh quy trình hiện tại và quy trình với SHI.**

| Tiêu chí | Quy trình thủ công | Với Trợ lý SHI |
|----------|--------------------|----------------|
| Thời gian mỗi lượt đặt | ~6–14 phút | ~1–2 phút, tự phục vụ |
| Chọn đúng dịch vụ | Lễ tân đoán | Triage tự động (đo được độ chính xác) |
| Khung giờ phục vụ | Giờ hành chính | 24/7 |
| Trùng giờ | Dễ xảy ra | Đối chiếu DB, không trùng |
| Nhắc lịch | Thường không có | Push + `.ics` tự động |
| Tải lễ tân | Cao | Chỉ xử lý ca khó / xác nhận |

Điểm nhấn của đồ án không chỉ là "một chatbot chạy được", mà là một hệ thống **có đo lường
chất lượng AI** (Precision/Recall/F1, top-1/top-2 trên tập dữ liệu gán nhãn), **có lớp an toàn
y tế** (phát hiện cấp cứu, không chẩn đoán/kê đơn, ẩn PII, ghi audit log theo Nghị định
13/2023), **có trang quản trị cho admin/bác sĩ** xem lịch đã đặt & lịch làm việc, và **kiến
trúc sẵn sàng mở rộng lên cloud** (chạy được cả với file JSON lẫn Postgres/Supabase). Sản phẩm
phục vụ đồng thời **web demo** và **app native (Expo)** qua cùng một bộ REST API.

---

## 2. Phân chia nhiệm vụ

> *Bảng dưới là khung phân công theo các khối chức năng thực tế của repo. Vui lòng thay
> tên thành viên và điều chỉnh tỷ lệ % cho đúng nhóm trước khi nộp.*

| TT | Thành viên | Nhiệm vụ phụ trách | Sản phẩm/Module | % Đóng góp |
|----|-----------|--------------------|-----------------|:----------:|
| 1 | *(Thành viên A)* | Triage engine + Hệ thống đánh giá AI | `triage.py`, `eval/` (dataset, evaluate, results) | 25% |
| 2 | *(Thành viên B)* | Lõi hội thoại + Lớp an toàn y tế | `chatbot.py`, `safety.py` | 25% |
| 3 | *(Thành viên C)* | Đặt lịch + Trang quản trị + Lưu trữ | `booking.py`, `templates/admin.html`, `storage.py`, `data.py` | 20% |
| 4 | *(Thành viên D)* | Push, nhắc lịch & tích hợp lịch | `push.py`, `reminder_worker.py`, `calendar_ics.py` | 15% |
| 5 | *(Thành viên E)* | App native (Expo) + Web demo + Báo cáo | `mobile/`, `templates/index.html`, tài liệu | 15% |
| | | **Tổng** | | **100%** |

*Ghi chú: backend (`app.py`) và việc tích hợp giữa các module là phần làm chung của cả nhóm.*

---

## 3. Mục tiêu

### 3.1. Mục tiêu chung
Xây dựng một **trợ lý ảo tiếng Việt cho phòng khám nha khoa** giúp người bệnh **chọn đúng
dịch vụ** và **đặt lịch hẹn** một cách an toàn, đồng thời **nhắc lịch chủ động** và **hỗ trợ
admin/bác sĩ quản lý lịch** — vận hành được trên cả web và điện thoại, tuân thủ pháp luật về
dữ liệu cá nhân.

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
5. **Quản trị cho admin/bác sĩ**: trang riêng để xem lịch hẹn đã đặt (lọc theo ngày/bác sĩ/
   trạng thái/SĐT) và xem lịch làm việc (khung bận/trống) của từng bác sĩ.
6. **Đa nền tảng**: phục vụ cả web demo và app native (Expo) qua cùng bộ REST API.
7. **Đo lường được chất lượng AI**: hệ thống đánh giá tính Precision/Recall/F1, top-1/top-2,
   so sánh hai phiên bản thuật toán triage và đo cả câu ghép nhiều ý.
8. **Sẵn sàng mở rộng**: tách lớp lưu trữ để chạy được cả file JSON (demo) lẫn Postgres/Supabase
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
| 5 | **Guardrails an toàn y tế** | Phát hiện cấp cứu → gọi 115; chặn yêu cầu chẩn đoán/kê đơn; human handoff; gắn disclaimer. Bộ pattern quản lý online ở DB (`safety_patterns`) nhưng **fail-safe** (rỗng/mất DB → dùng seed code). |
| 6 | **Bảo vệ dữ liệu cá nhân** | Ẩn PII (SĐT, email, CCCD) và ghi **audit log** `app/audit_log.jsonl` cho mỗi lượt hội thoại. |
| 7 | **Push notification (Expo)** | Bắn thông báo xác nhận đặt lịch + nhắc lịch, miễn phí, không cần API key. |
| 8 | **Worker nhắc lịch** | Nhắc trước **1 ngày**, **tối hôm trước** (chăm sóc), **2 giờ**; mỗi loại gửi đúng 1 lần. |
| 9 | **Xuất lịch `.ics` + Google Calendar** | Thêm lịch hẹn vào iPhone/Outlook/Google, có chuông nhắc (VALARM), không cần OAuth. |
| 10 | **Lớp lưu trữ kép** | Có `DATABASE_URL` → Postgres/Supabase; không có → file JSON. Đổi backend không phải sửa nghiệp vụ. |
| 11 | **App native Expo** | UI chat React Native, mở qua Expo Go bằng QR. |
| 12 | **Hệ thống đánh giá AI** | `eval/` với **90 câu đơn-ý + 20 câu ghép nhiều ý** gán nhãn, tính Precision/Recall/F1, top-1/top-2, so sánh v1 vs v2 → `results.md`, `BAOCAO_DANHGIA.md`. |
| 13 | **Hủy lịch đã đặt** | Người dùng gõ *"hủy lịch"* → tra theo SĐT → chọn lịch → xác nhận hủy (`status='cancelled'`, khung giờ tự trống lại) + push báo hủy. Khi đặt trùng còn hỏi thẳng *"hủy lịch cũ & đặt lại?"* rồi **đặt tiếp lịch đang dở** thay vì bắt làm lại. |
| 14 | **Fallback than phiền chung** | Câu mơ hồ nhưng rõ là vấn đề răng miệng (*"khó chịu ở răng khi ăn cơm"*) → đưa lựa chọn có cấu trúc thay vì báo "chưa rõ" (`mentions_dental_discomfort`). |
| 15 | **Hỏi–đáp thông tin dịch vụ** | *"nội nha khám gì?", "trồng răng là gì?"* → trả mô tả dịch vụ (`data.SERVICE_INFO`) + mời đặt lịch (`info_question_service`). |
| 16 | **Trang quản trị admin/bác sĩ** | `/admin` (bảo vệ bằng `ADMIN_KEY`): xem **danh sách lịch hẹn** lọc theo ngày/bác sĩ/trạng thái/SĐT, **thống kê nhanh**, **hủy lịch**, và xem **lịch làm việc** (khung bận/trống) của từng bác sĩ trong ngày. |
| 17 | **Web demo toàn màn hình** | `templates/index.html` bố cục chat trải kín viewport thay cho khung nổi nhỏ. |

---

## 5. Công nghệ sử dụng

**Backend (Python)**
- **Flask 3.0.3** — web server + REST API (`/`, `/admin`, `/api/start`, `/api/chat`, `/api/register-push`, `/api/ics/<code>`, `/api/admin/*`).
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

## 6. Kiến trúc và luồng vận hành

### 6.1. Luồng vận hành

**Hình 3 — Luồng xử lý một phiên đặt lịch của bệnh nhân.**

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
*Chú thích:* An toàn (`safety.py`) luôn được kiểm tra **trước** khi định tuyến hội thoại. Cùng
dữ liệu này, **admin/bác sĩ** truy cập qua `/admin` để đọc lại lịch đã đặt và lịch làm việc
(Hình 4).

**Hình 4 — Luồng truy cập của admin/bác sĩ (chỉ đọc).**

```
Admin / Bác sĩ ──► /admin (nhập ADMIN_KEY)
        │
        ├─► /api/admin/appointments  → danh sách lịch hẹn (lọc ngày/bác sĩ/trạng thái/SĐT)
        ├─► /api/admin/schedule      → lịch làm việc 1 bác sĩ trong 1 ngày (khung bận/trống)
        ├─► /api/admin/meta          → danh sách bác sĩ + ngày + thống kê nhanh
        └─► /api/admin/cancel        → hủy 1 lịch hẹn (status='cancelled')
                    │
                    ▼
              storage.py  (cùng nguồn dữ liệu với luồng đặt lịch)
```
*Chú thích:* Trang quản trị **không tạo dữ liệu mới**, chỉ **đọc** lịch bệnh nhân đã đặt và cho
phép hủy — trả lời cho câu hỏi "chatbot có dùng cho admin/bác sĩ kiểm tra lịch không?".

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
7. Admin/bác sĩ mở `/admin` để xem toàn bộ lịch đã đặt và lịch làm việc của mình.

### 6.2. Cấu trúc thư mục

```
PRF-SHI/
├── app/
│   ├── app.py                 # Flask app + routes (bệnh nhân + admin), chạy 0.0.0.0:5001
│   ├── chatbot.py             # Máy trạng thái hội thoại (SESSIONS in-memory)
│   ├── triage.py              # "Hàm lượng AI": phân loại triệu chứng → dịch vụ (v1/v2)
│   ├── safety.py              # Guardrails: cấp cứu, PII, chặn chẩn đoán, audit log
│   ├── booking.py             # Đặt lịch, hủy lịch, chống trùng + truy vấn cho admin/bác sĩ
│   ├── data.py                # 9 nhóm dịch vụ + bác sĩ + khung giờ + mô tả (SERVICE_INFO)
│   ├── storage.py             # Lớp lưu trữ kép: Postgres/Supabase ↔ file JSON
│   ├── push.py                # Gửi push qua Expo Push Service
│   ├── reminder_worker.py     # Quét lịch, bắn nhắc (--once/--watch/--test)
│   ├── calendar_ics.py        # Sinh file .ics (VALARM) + link Google Calendar
│   ├── templates/
│   │   ├── index.html         #   Web demo cho bệnh nhân
│   │   └── admin.html         #   Trang quản trị cho admin/bác sĩ
│   ├── appointments.json / device_tokens.json   # lưu trữ JSON (fallback)
│   ├── audit_log.jsonl        # nhật ký hội thoại (đã ẩn PII)
│   └── outbox/push_outbox.jsonl  # push khi chưa có thiết bị thật
├── requirements.txt
├── eval/                  # Đánh giá AI (data + script)
│   ├── dataset.jsonl      #   90 câu đơn-ý gán nhãn
│   ├── dataset_complex.jsonl  # 20 câu ghép nhiều ý (label chính + accept)
│   └── evaluate.py        #   tính Precision/Recall/F1, top-1/top-2, v1 vs v2
├── docs/                  # Tài liệu dự án
│   ├── BAOCAO_DOAN.md     #   báo cáo đồ án (file này)
│   ├── BAOCAO_DANHGIA.md  #   báo cáo đánh giá AI
│   ├── hoc/                # 10 bài học giải thích từng module
│   └── eval/
│       ├── results.md     #   kết quả đánh giá (do evaluate.py sinh)
│       └── rubric.md      #   tiêu chí định tính
├── scripts/migrate_to_supabase.py
└── mobile/                # App native Expo (SDK 54)
    ├── App.js             #   UI chat
    └── src/{api,config,notify,usePush,calendar,html}.js
```

**Cách chạy local (3 terminal):**
```bash
# Backend (cổng 5001 vì macOS chiếm 5000 cho AirPlay)
PORT=5001 ./.venv/bin/python -m app.app
# Worker nhắc lịch (tùy chọn)
./.venv/bin/python -m app.reminder_worker --watch
# App native
cd mobile && npx expo start -c
```
Bệnh nhân mở `http://127.0.0.1:5001`; admin/bác sĩ mở `http://127.0.0.1:5001/admin`
(khóa mặc định demo: `shi-admin-demo`, đổi qua biến môi trường `ADMIN_KEY`).

---

## 7. Giải thích các đoạn mã quan trọng

> Phần này chọn **bốn đoạn mã cốt lõi** và trình bày theo cùng một khung ba ý cho dễ theo dõi:
> **(1) Mục đích**, **(2) Kiến thức/thuật toán áp dụng**, **(3) Kết quả mang lại**.

### 7.1. Xử lý tiếng Việt cho triage — bỏ dấu & khớp trọn từ (`triage.py`)

```python
def _strip_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt: 'răng sâu' -> 'rang sau' (giữ chữ 'đ' -> 'd')."""
    text = text.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)      # tách chữ và dấu
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")

def _contains_word(haystack: str, needle: str) -> bool:
    """Khớp theo RANH GIỚI TỪ (whole-word), tránh 'chân răng' chứa 'hàn răng'."""
    return f" {needle} " in f" {haystack} "
```

**(1) Mục đích.** Người Việt hay **gõ thiếu dấu** ("nieng rang") và từ khóa có thể **nằm lọt
trong từ khác** ("hàn răng" ⊂ "chân răng"). Hai hàm này chuẩn hóa đầu vào để so khớp từ khóa
cho đúng.

**(2) Kiến thức/thuật toán.** Dùng **chuẩn hóa Unicode NFD** (môn Xử lý văn bản): phân rã mỗi
ký tự có dấu thành *chữ gốc + dấu tổ hợp*, rồi loại các dấu (Unicode category `"Mn"` — *Mark,
nonspacing*). Chữ "đ" xử lý riêng vì NFD không tách nó. Kỹ thuật **khớp theo ranh giới từ** được
làm gọn bằng cách bao chuỗi bởi khoảng trắng hai đầu.

**(3) Kết quả.** Cùng một bộ từ khóa nhận ra được cả câu có dấu lẫn không dấu, và loại lỗi khớp
nhầm chuỗi con. Đây là nền tảng giúp phiên bản `v2` vượt hẳn `v1` (xem mục 4.1 báo cáo đánh giá).

### 7.2. Chấm điểm phân loại dịch vụ (`triage.py`)

```python
for kw in dept["keywords"]:
    hit = _contains_word(norm, kw)
    if not hit and version == "v2":
        hit = _contains_word(norm_na, _strip_accents(kw))   # thử bản không dấu
    if hit:
        weight = 2 if " " in kw else 1     # cụm từ đặc trưng hơn -> nặng hơn
        score += weight
        matched.append(kw)
# ... results.sort(key=lambda r: r["score"], reverse=True)
```

**(1) Mục đích.** Biến một câu mô tả thành **điểm số cho từng nhóm dịch vụ** rồi xếp hạng, chọn
dịch vụ phù hợp nhất.

**(2) Kiến thức/thuật toán.** Đây là **phân loại văn bản theo luật (rule-based scoring)** — mô
hình *túi từ khóa có trọng số*: cụm từ (2 từ trở lên) mang trọng số 2, từ đơn trọng số 1, vì cụm
đặc trưng hơn. `v2` còn thử thêm bản **không dấu** khi bản có dấu trượt. So với học máy, cách này
**không cần dữ liệu huấn luyện lớn, chạy < 1 ms, chi phí 0đ**, và **giải thích được** (biết chính
xác từ khóa nào khiến quyết định).

**(3) Kết quả.** Trên tập 90 câu đơn-ý, `v2` đạt **Accuracy top-1 = 97.8%, Macro-F1 = 98.3%**
(v1 chỉ 73.3%). Kèm hàm `confidence_level()`, khi điểm sát nhau bot chủ động đưa 2–3 lựa chọn
thay vì đoán bừa.

### 7.3. Đặt lịch chống trùng — đối chiếu DB lúc xác nhận (`booking.py`)

```python
def _confirmed_at(date_str, time_str):
    """Lịch 'confirmed' đang chiếm đúng khung ngày+giờ (nếu có). Đối chiếu DB."""
    for a in storage.list_appointments():
        if (a.get("status") == "confirmed"
                and a.get("date") == date_str and a.get("time") == time_str):
            return a
    return None

def book_appointment(session_id, dept_code, doctor_id, date_str, time_str,
                     patient_name="", patient_phone=""):
    taken = _confirmed_at(date_str, time_str)              # kiểm tra ngay lúc xác nhận
    if taken:
        if patient_phone and taken.get("patient_phone") == patient_phone:
            return False, {"duplicate": True, "existing": taken}
        return False, {"error": "Khung giờ này vừa có người đặt..."}
    storage.add_appointment(appointment)
    return True, appointment
```

**(1) Mục đích.** Đảm bảo **không hai người đặt trùng một khung giờ**, kể cả khi nhiều người đặt
gần như đồng thời hoặc chạy nhiều tiến trình.

**(2) Kiến thức/thuật toán.** Áp dụng nguyên tắc **"một nguồn chân lý duy nhất" (single source of
truth)**: bỏ bảng slot tạm trong bộ nhớ, thay bằng **kiểm tra tại thời điểm ghi** (check-on-write)
trực tiếp với cơ sở dữ liệu. Đây là tư duy nền của **giao dịch (transaction)** và **tính nhất
quán dữ liệu** trong môn Cơ sở dữ liệu.

**(3) Kết quả.** Danh sách giờ luôn hiển thị đầy đủ nhưng vẫn không trùng lịch sau restart / qua
nhiều ngày / nhiều tiến trình. Nếu trùng đúng SĐT → trả `duplicate` để hội thoại mời **hủy lịch
cũ rồi đặt tiếp**, thay vì bắt người dùng làm lại từ đầu.

### 7.4. Truy vấn cho admin/bác sĩ — lịch làm việc theo khung giờ (`booking.py`)

```python
def doctor_day_schedule(doctor_id, date_str):
    slots = generate_available_slots().get(date_str, [])
    booked = {a["time"]: a for a in query_appointments(
        date=date_str, doctor_id=doctor_id, status="confirmed")}
    return [{"time": s, "appt": booked.get(s)} for s in slots]
```

**(1) Mục đích.** Cho bác sĩ/admin nhìn thấy **trong một ngày mình bận khung nào, ai đặt, khung
nào còn trống** — trả lời trực tiếp nhận xét "chatbot có dùng cho admin/bác sĩ kiểm tra lịch
không?".

**(2) Kiến thức/thuật toán.** Xây một **bảng tra cứu (hash map) `giờ → lịch hẹn`** để tra O(1),
rồi *ghép (join)* với danh sách khung giờ chuẩn của ngày. Dữ liệu đọc qua `storage` nên **đúng
cả khi lưu bằng file JSON lẫn Postgres**. Toàn bộ nhóm hàm admin (`query_appointments`,
`doctor_day_schedule`, `admin_summary`) là **read-only**, không đụng nghiệp vụ đặt lịch.

**(3) Kết quả.** Trang `/admin` hiển thị lịch làm việc dạng lưới khung giờ (bận/trống) và danh
sách lịch hẹn lọc theo ngày/bác sĩ/trạng thái/SĐT, kèm thống kê nhanh và nút hủy — một công cụ
quản trị hoàn chỉnh dựng trên đúng nguồn dữ liệu bệnh nhân đã đặt.

### 7.5. Chấm điểm AI tự động (`eval/evaluate.py`)

```python
def evaluate(rows, version):
    tp = {c: 0 for c in LABELS}; fp = {c: 0 for c in LABELS}; fn = {c: 0 for c in LABELS}
    correct = correct_top2 = 0
    for r in rows:
        gold = r["label"]
        ranked = ranked_codes(r["text"], version)     # danh sách dịch vụ xếp theo điểm
        pred = ranked[0] if ranked else None
        if gold in ranked[:2]: correct_top2 += 1       # đáp án nằm trong 2 gợi ý đầu?
        if pred == gold: correct += 1; tp[gold] += 1   # top-1 đúng?
        else:
            fn[gold] += 1
            if pred is not None: fp[pred] += 1          # đoán nhầm sang lớp khác
    # ... từ tp/fp/fn tính Precision = tp/(tp+fp), Recall = tp/(tp+fn), F1, Accuracy
```

**(1) Mục đích.** Đo **khách quan** chất lượng triage: cho engine đoán trên bộ câu đã biết đáp
án rồi tính điểm, thay vì "cảm tính thấy nó trả lời đúng".

**(2) Kiến thức/thuật toán.** Áp dụng **các độ đo phân loại (classification metrics)** trong
Học máy: đếm **TP/FP/FN** cho từng lớp → tính **Precision, Recall, F1, Macro-F1, Accuracy**;
thêm **top-2 accuracy** cho hợp với việc bot đưa vài gợi ý. Toàn bộ chạy tự động, đọc dataset
gán nhãn (`dataset.jsonl`) — đúng quy trình đánh giá một mô hình AI.

**(3) Kết quả.** Một lệnh `python eval/evaluate.py` sinh ra `results.md` với bảng so sánh v1/v2,
P/R/F1 từng dịch vụ và phân tích lỗi. Nhờ đó mọi thay đổi ở `triage.py` đều **đo lại được ngay**
(kết quả cụ thể ở Mục 8).

---

## 8. Đánh giá chất lượng AI (triage engine)

> Mọi số liệu dưới đây được **sinh tự động** bởi `../eval/evaluate.py` (ghi ra `eval/results.md`).
> Bản đánh giá độc lập, chi tiết hơn: `BAOCAO_DANHGIA.md`.

### 8.1. Mục tiêu đánh giá

**Bảng 4 — Chỉ tiêu chất lượng đặt ra cho thành phần AI.**

| Mục tiêu | Chỉ số | Ngưỡng |
|----------|--------|:------:|
| Phân loại đúng dịch vụ | Accuracy (top-1) | ≥ 90% |
| Gợi ý đúng trong vài lựa chọn | Accuracy (top-2) | ≥ 95% |
| Cân bằng giữa các lớp | Macro-F1 | ≥ 0.90 |
| Xử lý câu **ghép nhiều ý** | Top-2 chấp nhận được | ≥ 90% |
| Phản hồi nhanh | Thời gian/câu | < 50 ms |
| Chi phí vận hành | Chi phí/1.000 lượt | 0đ (rule-based) |

### 8.2. Dữ liệu & cách chấm điểm

Đánh giá tự động hóa trong `eval/`: **đề + đáp án** (`dataset.jsonl`, `dataset_complex.jsonl`)
→ **bộ chấm** (`evaluate.py`, xem code ở Mục 7.5) → **bảng điểm** (`results.md`). Hai tập:
- **Tập đơn-ý** — `dataset.jsonl`: **90 câu**, mỗi câu đúng 1 dịch vụ, cân bằng 10 câu/lớp × 9
  lớp; cố ý có ~**25 câu gõ thiếu dấu** và nhiều câu khẩu ngữ/nói vòng.
- **Tập phức tạp** — `dataset_complex.jsonl`: **20 câu ghép 2-3 ý**; mỗi câu có `label` (dịch
  vụ chính) và `accept` (mọi dịch vụ hợp lệ được nhắc).

So sánh **v1** (khớp có dấu) với **v2** (không phân biệt dấu → bắt cả câu thiếu dấu). Với câu
phức tạp đo thêm **top-1 chấp nhận được** (top-1 là một dịch vụ hợp lệ) và **top-2 chấp nhận
được** (có dịch vụ hợp lệ trong 2 gợi ý đầu) — hợp với việc bot cho người dùng chọn trong vài gợi ý.

### 8.3. Kết quả định lượng

**Bảng 5 — So sánh tổng thể v1 vs v2 (tập 90 câu đơn-ý).**

| Chỉ số | v1 (có dấu) | v2 (không phân biệt dấu) | Mục tiêu |
|--------|:-----------:|:------------------------:|:--------:|
| Accuracy (top-1) | 73.3% | **97.8%** | ≥ 90% ✅ |
| Accuracy (top-2) | 74.4% | **98.9%** | ≥ 95% ✅ |
| Macro F1 | 83.9% | **98.3%** | ≥ 0.90 ✅ |
| Thời gian TB | 0.07 ms | 0.18 ms | < 50 ms ✅ |
| Chi phí | 0đ | 0đ | 0đ ✅ |

> v1 bỏ sót phần lớn câu gõ thiếu dấu (Recall thấp); v2 xử lý không dấu nên tăng Accuracy top-1
> từ 73.3% → 97.8% — **cải tiến then chốt**. *(Lưu ý trung thực: từ khóa được hiệu chỉnh trên
> chính tập phát triển, chưa tách tập test riêng nên số liệu có thể lạc quan hơn thực tế.)*

**Bảng 6 — F1 theo dịch vụ (v2) — chỉ liệt kê 3 lớp còn lỗi lẻ; 6 lớp còn lại đạt 100%.**

| Dịch vụ | Precision | Recall | F1 |
|---------|:---------:|:------:|:--:|
| Trám răng / Sâu răng | 90.9% | 100.0% | 95.2% |
| Phục hình / Trồng răng | 100.0% | 90.0% | 94.7% |
| Nha khoa trẻ em | 100.0% | 90.0% | 94.7% |

**Bảng 7 — Kết quả tập câu ghép nhiều ý (v2).**

| Chỉ số | Ý nghĩa | Kết quả |
|--------|---------|:-------:|
| Top-1 đúng nhãn chính | top-1 == dịch vụ chính | 55.0% |
| Top-1 chấp nhận được | top-1 là một dịch vụ hợp lệ | **90.0%** |
| Top-2 chấp nhận được | có dịch vụ hợp lệ trong top-2 | **100.0%** ✅ |

Với câu ghép nhiều ý, "top-1 đúng nhãn chính" thấp là **hợp lý** (nói cùng lúc *"nhổ răng"* và
*"niềng"* thì chọn cái nào làm hạng 1 cũng đúng). Hai chỉ số sát thực tế hơn — **top-1 chấp nhận
90%, top-2 chấp nhận 100%** — cho thấy engine **luôn** đưa ít nhất một dịch vụ đúng vào 2 gợi ý
đầu, đúng thiết kế "câu mơ hồ → hiển thị 2–3 lựa chọn cho người dùng chốt".

### 8.4. Phân tích lỗi

Chỉ **2/90 câu** đơn-ý sai, đều ở "vùng mờ" đã biết:

| Câu nhập | Nhãn đúng | Dự đoán | Nguyên nhân |
|----------|-----------|---------|-------------|
| "làm **cầu răng sứ** cho chỗ **răng đã mất**" | Phục hình / Trồng răng | (không nhận ra) | Thiếu từ khóa "cầu răng sứ"; "răng đã mất" ≠ trọn từ "mất răng". |
| "**Bé** 6 tuổi bị **sâu răng sữa**" | Nha khoa trẻ em | Trám răng / Sâu răng | Tín hiệu trẻ em + sâu răng cùng xuất hiện → điểm nghiêng Sâu răng. |

Cả hai đúng **hạn chế cố hữu của rule-based** (phụ thuộc từ khóa; ranh giới Nha nhi ↔ Sâu răng).
Hướng khắc phục: bổ sung từ khóa và **ưu tiên tín hiệu trẻ em**.

### 8.5. Kết luận đánh giá

Phiên bản **v2** đạt/vượt mọi chỉ tiêu (Accuracy top-1 97.8%, top-2 98.9%, Macro-F1 0.983,
< 1 ms/câu, 0đ; câu ghép nhiều ý top-2 chấp nhận 100%) — là bản đang dùng trong sản phẩm. Hạn
chế chính: rule-based phụ thuộc từ khóa và chưa có tập test độc lập; hướng nâng cấp là mở rộng
dataset + tập test riêng và cắm LLM (Claude) làm tầng dự phòng khi độ tin cậy thấp.

---

## 9. Giao diện & hình ảnh minh họa

> *Chèn ảnh chụp thực tế vào đúng vị trí placeholder bên dưới. Mỗi hình đã có sẵn caption đầy đủ
> theo mẫu "Hình X — Tiêu đề. Mô tả".*

**Hình 5 — Màn hình chào & nhập triệu chứng (web demo).**
`![Màn hình chào](screenshots/01-greeting.png)`
*Chú thích:* Bot tự giới thiệu là "Trợ lý Nha khoa SHI", hiển thị disclaimer "không chẩn đoán
bệnh, không kê đơn", và mời người dùng mô tả triệu chứng.

**Hình 6 — Kết quả triage & xác nhận dịch vụ.**
`![Triage](screenshots/02-triage.png)`
*Chú thích:* Người dùng gõ "răng tôi bị sâu và ê buốt khi ăn ngọt" → bot đề xuất dịch vụ
**Trám răng / Sâu răng** kèm 2 nút "Đặt lịch" / "Mô tả lại".

**Hình 7 — Chọn bác sĩ → ngày → khung giờ.**
`![Đặt lịch](screenshots/03-booking-steps.png)`
*Chú thích:* Các bước chọn hiển thị dưới dạng nút bấm; khung giờ luôn hiển thị đầy đủ, việc
trùng giờ được đối chiếu với DB ở bước xác nhận. Sau khi chọn giờ, bot hỏi thêm **tên** và
**số điện thoại**.

**Hình 8 — Đặt lịch thành công + link lịch.**
`![Thành công](screenshots/04-success.png)`
*Chú thích:* Bot trả mã lịch hẹn `SHI-XXXXXX`, link "Thêm vào Lịch (.ics)" và "Thêm vào Google
Calendar"; đồng thời bắn push xác nhận.

**Hình 9 — Guardrail cấp cứu.**
`![Cấp cứu](screenshots/05-emergency.png)`
*Chú thích:* Khi phát hiện cụm cấp cứu (vd. "gãy xương hàm"), bot dừng tư vấn và hướng dẫn gọi **115**.

**Hình 10 — Thông báo đẩy / nhắc lịch trên điện thoại (Expo).**
`![Push](screenshots/06-push.png)`
*Chú thích:* Thông báo "✅ Đặt lịch thành công" và nhắc "⏰ Sắp tới giờ khám (còn 2 giờ)".

**Hình 11 — Trang quản trị: danh sách lịch hẹn (admin/bác sĩ).**
`![Admin danh sách](screenshots/07-admin-list.png)`
*Chú thích:* Trang `/admin` liệt kê các lịch đã đặt, lọc theo ngày/bác sĩ/trạng thái/SĐT, có
thống kê nhanh (tổng/đã xác nhận/đã hủy) và nút hủy lịch.

**Hình 12 — Trang quản trị: lịch làm việc của một bác sĩ.**
`![Admin lịch làm việc](screenshots/08-admin-schedule.png)`
*Chú thích:* Chọn bác sĩ + ngày → hiển thị từng khung giờ **bận** (ai đặt, dịch vụ) hay **trống**.

**Hình 13 — Kết quả đánh giá AI (`eval/results.md`).**
`![Eval](screenshots/09-eval.png)`
*Chú thích:* Bảng so sánh v1 vs v2 và tập câu ghép nhiều ý — v2 đạt Accuracy top-1 97.8%,
top-2 98.9% trên 90 câu đơn-ý; câu ghép nhiều ý đạt top-2 chấp nhận 100%.

*Cách tạo nhanh ảnh Hình 5–9:* chạy backend rồi mở `http://127.0.0.1:5001`, thao tác và chụp
màn hình. Hình 11–12 mở `http://127.0.0.1:5001/admin`. Hình 13 chụp bảng trong `eval/results.md`.

---

## 10. Kết luận

### 10.1. Mức độ hoàn thành so với mục tiêu

| Mục tiêu | Trạng thái | Bằng chứng |
|----------|:----------:|-----------|
| Triage chính xác (kể cả thiếu dấu) | ✅ Hoàn thành | `triage.py` v2; 90 câu đạt top-1 97.8%, top-2 98.9% |
| Hội thoại dẫn dắt đặt lịch | ✅ Hoàn thành | Máy trạng thái trong `chatbot.py` (đặt lịch + nhánh hủy lịch) |
| Thu thập SĐT & chống đặt trùng | ✅ Hoàn thành | Bước `ASK_PHONE`; `book_appointment` đối chiếu DB |
| Hủy lịch đã đặt | ✅ Hoàn thành | `cancel_appointment` + nhánh `CANCEL_*` |
| Hỏi–đáp thông tin dịch vụ | ✅ Hoàn thành | `triage.info_question_service` + `data.SERVICE_INFO` |
| Guardrails an toàn y tế | ✅ Hoàn thành | `safety.py`: cấp cứu, chặn chẩn đoán, PII, audit |
| Nhắc lịch chủ động | ✅ Hoàn thành | `reminder_worker.py` + `push.py` + `.ics` |
| Quản trị admin/bác sĩ | ✅ Hoàn thành | `/admin` + `/api/admin/*`; xem lịch đã đặt & lịch làm việc |
| Đa nền tảng (web + app) | ✅ Hoàn thành | REST API dùng chung; `mobile/` (Expo) |
| Đo lường chất lượng AI | ✅ Hoàn thành | `eval/` (90 + 20 câu) + `BAOCAO_DANHGIA.md` |
| Sẵn sàng lên cloud (DB) | ✅ Cơ bản | `storage.py` hỗ trợ Postgres/Supabase |

Nhìn chung đồ án **đạt toàn bộ mục tiêu đề ra** ở mức demo hoàn chỉnh, có đo lường định lượng,
có lớp an toàn và có công cụ quản trị — vượt trên một chatbot thông thường.

### 10.2. Hạn chế hiện tại
- **Triage rule-based**: phụ thuộc bộ từ khóa nên vẫn trượt với cách diễn đạt lạ — ví dụ "cầu
  răng sứ cho chỗ răng đã mất" (thiếu từ khóa) và ranh giới **Nha nhi vs Sâu răng** khi câu vừa
  nhắc "bé" vừa "sâu răng" (xem phân tích lỗi ở Mục 8.4).
- **Chưa tách tập test độc lập**: từ khóa được hiệu chỉnh trên chính tập phát triển nên số liệu
  có thể lạc quan hơn thực tế.
- **Session in-memory** (`chatbot.SESSIONS`): mất khi restart, chưa scale nhiều worker.
- **Trang quản trị mới bảo vệ tối thiểu** bằng `ADMIN_KEY` chung; chưa có đăng nhập theo tài
  khoản/vai trò từng bác sĩ.
- **Chạy bằng dev server + `debug=True`**, `API_BASE` còn là IP LAN, chưa cấu hình CORS — chưa
  phải cấu hình production.

### 10.3. Hướng phát triển tương lai
1. **Nâng NLU bằng LLM**: kích hoạt `classify_with_llm()` (Claude) làm tầng dự phòng khi
   rule-based có độ tin cậy thấp; mở rộng tập đánh giá đa dạng hơn, có tập test riêng.
2. **Production hardening**: chạy bằng `gunicorn`, tắt debug, thêm CORS, đưa `API_BASE` về URL
   HTTPS công khai (Render/Railway/Fly.io).
3. **Session bền vững**: chuyển trạng thái hội thoại sang Redis/DB để scale nhiều tiến trình.
4. **Phát hành app thật**: build bằng **EAS** → APK/AAB (Google Play) hoặc iOS (App Store),
   kèm privacy policy và disclaimer y tế.
5. **Quản trị nâng cao**: đăng nhập theo tài khoản bác sĩ, đồng bộ Google Calendar phía phòng
   khám, duyệt/đổi lịch, thống kê doanh thu và tỷ lệ no-show.
6. **Mở rộng nghiệp vụ**: nhắc tái khám, đánh giá sau khám, hỏi đáp về chi phí dịch vụ.

---

## Phụ lục — Mẫu khảo sát để thay số liệu ước lượng

Các số liệu trong mục 1 (Bảng 1, Bảng 2, Hình 2) hiện là **ước lượng của nhóm** và nên được thay
bằng số đo thực tế. Gợi ý khảo sát nhanh tại 3–5 phòng khám:
1. Đo **thời gian trung bình mỗi lượt đặt lịch** (bấm giờ 20–30 cuộc).
2. Đếm **lý do liên hệ** trong 1 tuần (hỏi dịch vụ / đặt-đổi lịch / hỏi giá / khác) → vẽ lại Hình 2.
3. Ghi **tỷ lệ no-show** (số lịch bỏ / tổng lịch) trong 1 tháng.
4. Đếm **số ca định tuyến nhầm dịch vụ** phải khám lại.

---

*Tài liệu này được sinh kèm dự án "Trợ lý Nha khoa SHI". Xem thêm `BAOCAO_DANHGIA.md` (đánh giá
AI chi tiết), `KIEN_TRUC.md` (kiến trúc) và thư mục `hoc/` (giải thích từng module).*
