# Thiết kế: Patient Portal & Gợi ý dịch vụ AI (REC-01/02 + PAT-01)

Doc thiết kế triển khai cho việc mở rộng SHI từ **chatbot-first** sang **patient
portal có gợi ý dịch vụ AI**, trong đó chatbot trở thành một widget trong luồng
bệnh nhân thay vì là toàn bộ ứng dụng.

> **Trạng thái triển khai** (cập nhật 2026-07-30)
>
> | Bước | Trạng thái |
> |---|---|
> | B1 — schema 3 bảng + cột `users` + role `patient` | ✅ đã chạy DDL trên Supabase |
> | B2 — `SERVICE_META` + backfill + seed demo | ✅ |
> | B3 — role `patient`: đăng ký/đăng nhập/redirect | ✅ |
> | B4 — engine `app/reco/` | ✅ |
> | B5 — LLM viết lý do | ✅ |
> | B6 — `app/patient_api.py` | ✅ |
> | B7 — `templates/patient.html` (PAT-01 + REC-01/02 + cold-start + empty) | ✅ |
> | B8 — chat widget + deep-link đặt lịch | ✅ |
> | B9 — endpoint nha sĩ ghi nhận điều trị | ⬜ |
> | B10 — `eval/evaluate_reco.py` | ⬜ |
>
> 166 test mới, toàn bộ pass; đã verify end-to-end trên Supabase thật.
>
> **`/` giờ là portal bệnh nhân**, không còn là trang chatbot. Chatbot chỉ tồn tại
> dưới dạng widget trong trang; `templates/index.html` đã bị xoá. Khách chưa đăng
> nhập vẫn vào được portal (gợi ý cold-start + đặt lịch qua widget) — xem §20.

---

## 1. Nguồn spec & traceability

| Artifact | ID | Trạng thái | Dùng cho |
|---|---|---|---|
| Story: Patient xem gợi ý + lý do | SMMG-65 (REC-01/02) | In Review | AC chính của gợi ý |
| Story: Patient tổng quan sau login | SMMG-131 (PAT-01) | In Review | Trang đệm + lịch sử dịch vụ |
| Doc gốc v2 | Confluence `19103754` | In Review, v2 | **Phạm vi chuẩn** |
| Spec PAT-01 | Confluence `19038211` | v2 | AC trang tổng quan |
| ER model | Confluence `8192034` | TARGET | Schema 3 bảng mới |
| Sequence | Confluence `8060931` | TARGET | Luồng 8 bước, feature vector |
| Test case TC-F2 | Confluence `8061152` | TARGET | TC-REC-001…007 |
| Wireframe 4 states | Confluence `8060976` | TARGET | UI Desktop |
| Story: Dentist validate | SMMG-67 (REC-03) | **Idea** | Ngoài phạm vi vòng này |

Bốn trang `80xxxxx` đều mang banner `[S2-TRACE-2026-07-19] Trạng thái artifact:
TARGET — source code hiện chưa có Recommendation Engine`. Chúng là **thiết kế mục
tiêu**, không phải mô tả hệ thống đang chạy.

### 1.1. Hai lớp tài liệu nói khác nhau — chọn theo doc gốc v2

| | Doc gốc v2 (`19103754`) | ER/SEQ/TC (`80xxxxx`) |
|---|---|---|
| Model | lịch sử + **quy tắc nghiệp vụ tối thiểu** | SVD++ CF + TF-IDF CBF, `0.7×CF + 0.3×CBF` |
| Hạ tầng | không yêu cầu | Redis Feature Store TTL 1h, Model Registry, retrain CN 02:00 |
| Nha sĩ validate | **ngoài phạm vi**, "giữ ở sprint khác" | REC-03 accept/modify/reject đầy đủ |

Doc gốc v2 nói thẳng rằng bản hybrid CF/CBF + feedback nha sĩ nằm ở
*"SPEC-S2-AIRecommendation — Model Specification v1 (archive) — tham khảo, không
phải phạm vi triển khai v2 này"*. Cộng với SMMG-67 đang ở `Idea` trong khi
SMMG-65/90/130/131 đã `In Review` → **doc này theo doc gốc v2**.

---

## 2. Phạm vi

**Trong phạm vi**

1. PAT-01 — trang tổng quan bệnh nhân sau login + bảng lịch sử dịch vụ.
2. REC-01 — top-3 gợi ý: tên, mô tả ngắn, % phù hợp, CTA đặt lịch, bỏ qua.
3. REC-02 — lý do dễ hiểu + màn/modal chi tiết dịch vụ.
4. Role `patient` + đường nối bệnh nhân ↔ lịch hẹn ↔ lịch sử điều trị.
5. Chatbot thành widget trong portal, và là một `trigger` của gợi ý.
6. `RecommendationLog` để đo hiệu quả + đánh giá offline.

**Ngoài phạm vi**

- REC-03 (nha sĩ validate) — chỉ chừa sẵn `dentist_feedback JSONB` trong schema,
  xem §13.
- REC-04 (retrain tự động), REC-05 (admin dashboard hiệu suất).
- CF SVD++, CBF TF-IDF, Redis Feature Store, Model Registry — thuộc v1 archive.
- `materials_used`, `chief_complaint`, `diagnosis` của `TreatmentHistory`: dữ liệu
  lâm sàng, không cần cho quy tắc v2 và làm tăng rủi ro PII y tế.

---

## 3. Sai lệch có chủ đích so với spec

Bảng này cần được đồng bộ ngược lên Confluence khi doc được duyệt.

| # | Spec nói | Doc này làm | Lý do |
|---|---|---|---|
| D1 | SEQ 5.3: `generate reason_text from reason_code template` | **LLM viết `reason_text`** mặc định, template là fallback | Quyết định của chủ dự án; đây là phần "hàm lượng AI" khi demo |
| D2 | ER: SLA inference `<500ms` | **~2.5–5s**, chưa đạt | Nguyên nhân chính KHÔNG phải LLM — xem §19.5 |
| D3 | ER: 3 bảng UUID + FK → `Patient`, `Service`, `Dentist` | Khoá `TEXT` theo `users.id` / `service_code` / `doctor_id` hiện có | Codebase chưa có bảng `Patient`/`Service` dạng UUID; đổi khoá = refactor toàn bộ Sprint 1 |
| D4 | SEQ: Redis Feature Store TTL 1h | Cache in-process, TTL 1h, cùng pattern `_LLM_CACHE` | Dự án 1 process; Redis đã nằm ở P0 roadmap, không gộp vào đây |
| D5 | ER: `patient_rating` dùng cho CF model | Vẫn thu, nhưng chỉ để hiển thị + eval | CF ngoài phạm vi v2 |
| D6 | code-standards: module nghiệp vụ không import lẫn nhau | `reco/llm_reason.py` import `triage/{llm,safety}` | `triage/llm.py` là cổng LLM duy nhất của dự án. Cách sạch là chuyển xuống `core/`, nhưng `tests/test_triage_llm.py` monkeypatch trực tiếp `app.triage.llm` nên việc di chuyển sẽ làm hỏng mock — để lại thành việc riêng |

**Ràng buộc bất biến cho D1:** LLM **chỉ được viết lại câu chữ**. Nó không được
đổi `service_code`, `confidence`, `rank`, `urgency`. Nhờ vậy thứ hạng vẫn sinh ra
từ luật thuần → tái lập được, đánh giá offline được, và một lỗi LLM không bao giờ
đổi nội dung gợi ý y tế.

---

## 4. Hiện trạng: những gì phải xây từ đầu

Khảo sát code hiện tại (nhánh `main`):

| Cần có | Hiện trạng |
|---|---|
| `TreatmentHistory` | **không có bảng nào**; `appointments` chỉ có `confirmed`/`cancelled`, không có khái niệm "đã hoàn tất điều trị" |
| `RecommendationLog` | không có |
| `PatientPreference` (`dismissed_service_ids`) | không có |
| `patient_id` của BN | `appointments` khoá theo `session` + `patient_phone`, không có FK về `users` ([storage.py:73-87](../app/core/storage.py#L73-L87)) |
| Role `patient` | `CHECK (role IN ('admin','doctor','guest'))` ([storage.py:111](../app/core/storage.py#L111)) |
| Tuổi BN (`age_group`) | không có cột nào; AC SMMG-65 yêu cầu gợi ý theo độ tuổi |
| `allergies` (`allergy_flags`) | không có |
| `duration` + giá dịch vụ | `services` chỉ có `code/name/descr/keywords/sort_order`; TC-REC-007 đòi modal hiện thời lượng + giá cơ bản |
| Lịch sử để gợi ý | Có dữ liệu, nhưng **trải quá ngắn** — xem bên dưới |

**Về dữ liệu lịch hẹn** (đo trên Supabase, `USE_DB=True`, ngày 2026-07-30):
43 lịch hẹn, 32 có `patient_phone`, **8 SĐT khác nhau**, ngày từ `2026-06-17` đến
`2026-07-31`; chỉ 4 dòng mang mã dịch vụ của phiên bản đa khoa cũ (`ho_hap`,
`tieu_hoa`). Lưu ý: `app/data/appointments.json` (13 dòng, 11 dòng mã cũ) là dữ
liệu **chết** — app đọc DB, không đọc file này.

Hệ quả: **seed dữ liệu là điều kiện tiên quyết**, không phải việc phụ — nhưng lý do
không phải "thiếu dữ liệu" mà là **dữ liệu chỉ trải ~1.5 tháng**: không bệnh nhân
nào quá hạn tái khám 6 tháng, và 8 SĐT thì không đủ support để tính đồng xuất hiện.
Chạy engine trên dữ liệu này thì mọi bệnh nhân đều rơi vào nhánh cold-start.

Những thứ **đã có và dùng lại được**: JWT + bcrypt + `require_auth`
([auth.py](../app/core/auth.py)), cổng LLM không bao giờ raise
([triage/llm.py](../app/triage/llm.py)), `storage.py` tự chuyển JSON ↔ Postgres,
guardrail an toàn ([triage/safety.py](../app/triage/safety.py)), state machine đặt
lịch ([chatbot/steps/](../app/chatbot/steps/)).

---

## 5. Kiến trúc

```
main.py
  ├→ patient_api.py   (Blueprint /api/patient/*)   ← MỚI
  ├→ doctor_api.py    (+ endpoint hoàn tất điều trị)
  ├→ admin_api.py
  ├→ chatbot/         (+ start_with_service — deep-link từ card gợi ý)
  ├→ reco/            ← MỚI: engine gợi ý
  │    ├─ history.py     đọc lịch sử điều trị (chỉ import core/)
  │    ├─ features.py    feature vector theo SEQ 4.opt.1
  │    ├─ rules.py       sinh tín hiệu + chấm điểm (thuần, không I/O)
  │    ├─ reasons.py     catalog reason_code + template tiếng Việt
  │    ├─ llm_reason.py  LLM viết lại câu (không raise, không đổi số)
  │    ├─ prefs.py       dismissed_service_ids
  │    └─ log.py         RecommendationLog (best-effort)
  ├→ triage/, booking/, notify/
  └→ core/            (+ storage: 3 bảng mới; + catalog: SERVICE_META)
```

Tuân thủ [code-standards.md](./code-standards.md): `reco/` chỉ import từ `core/`,
**không** import `booking/` hay `triage/`. `patient_api.py` ở tầng app nên được
phép import cả `reco` + `booking`.

`rules.py` là **hàm thuần**: nhận feature vector + bảng đồng xuất hiện, trả danh
sách tín hiệu. Không đọc DB, không gọi mạng → test được không cần fixture.

---

## 6. Data model

### 6.1. Ba bảng mới (`core/storage.py`, thêm vào `SCHEMA_SQL`)

```sql
CREATE TABLE IF NOT EXISTS treatment_history (
    history_id        TEXT PRIMARY KEY,
    appointment_code  TEXT UNIQUE REFERENCES appointments(code),
    patient_id        TEXT NOT NULL,          -- users.id, role='patient'
    patient_phone     TEXT,                   -- fallback khi BN chưa có tài khoản
    service_code      TEXT NOT NULL,
    doctor_id         TEXT,
    treatment_date    TEXT NOT NULL,
    outcome           TEXT NOT NULL DEFAULT 'success',  -- success|partial|failed
    followup_required BOOLEAN NOT NULL DEFAULT FALSE,
    followup_due_date TEXT,
    patient_rating    SMALLINT,               -- 1..5
    created_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_th_patient_date
    ON treatment_history (patient_id, treatment_date DESC);

CREATE TABLE IF NOT EXISTS recommendation_log (
    rec_log_id       TEXT PRIMARY KEY,
    patient_id       TEXT NOT NULL,
    generated_at     TEXT NOT NULL,
    trigger          TEXT NOT NULL,           -- booking_page|chatbot|dentist_view
    model_version    TEXT NOT NULL,
    is_cold_start    BOOLEAN NOT NULL DEFAULT FALSE,
    recommendations  JSONB NOT NULL,          -- [{rank, service_code, confidence,
                                              --   reason_code, reason_text, urgency}]
    latency_ms       INT,
    patient_action   TEXT,                    -- book|dismiss|skip_all|view_detail|no_action
    patient_acted_service_code TEXT,
    patient_acted_rank SMALLINT,
    dentist_feedback JSONB,                   -- chừa cho REC-03, luôn NULL ở vòng này
    dentist_acted_at TEXT,
    feature_snapshot JSONB
);
CREATE INDEX IF NOT EXISTS idx_reclog_patient_generated
    ON recommendation_log (patient_id, generated_at DESC);

CREATE TABLE IF NOT EXISTS patient_preference (
    patient_id           TEXT PRIMARY KEY,
    dismissed_service_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    preferred_doctor_id  TEXT,
    service_ratings      JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at           TEXT NOT NULL
);
```

Giữ nguyên tên cột của ER ở những chỗ không phải khoá, để đồng bộ Confluence dễ.
`service_id`→`service_code`, `dentist_id`→`doctor_id` theo D3.

### 6.2. Bổ sung cột cho bệnh nhân

```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name  TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone      TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS birth_year SMALLINT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS allergies  JSONB;
CREATE INDEX IF NOT EXISTS idx_users_phone ON users (phone);
```

Dùng `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, đúng pattern đã có ở
[storage.py:88](../app/core/storage.py#L88) — không cần Alembic cho vòng này.

**Đổi CHECK constraint role** là thay đổi duy nhất không idempotent tự nhiên:

```sql
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
ALTER TABLE users ADD  CONSTRAINT users_role_check
    CHECK (role IN ('admin','doctor','guest','patient'));
```

Đặt trong block `try/except` riêng như `ux_appointments_doctor_slot`
([storage.py:124-140](../app/core/storage.py#L124-L140)): nếu fail thì app vẫn
chạy, chỉ mất khả năng tạo tài khoản `patient`.

> **Cân nhắc đã bỏ:** dùng lại role `guest` làm patient để né migration. Bỏ vì
> `guest` đã xuất hiện trong payload JWT, trong màn đăng ký và trong nhánh
> redirect của [login.html](../app/templates/login.html) — gộp hai khái niệm sẽ
> làm mờ ranh giới phân quyền.

### 6.3. `SERVICE_META` — thời lượng & giá

Thêm vào [core/catalog.py](../app/core/catalog.py) một dict tĩnh khoá theo mã
dịch vụ, **cùng pattern `SERVICE_INFO` đã có** — không cần thêm cột Supabase:

```python
SERVICE_META = {
    "kham_tong_quat": {"duration_min": 30, "price_from": 200_000,  "price_to": 350_000,
                       "recurring_months": 6},
    "sau_rang":       {"duration_min": 45, "price_from": 300_000,  "price_to": 800_000},
    ...
}
```

`recurring_months` là chu kỳ khuyến nghị, chỉ đặt cho dịch vụ có tính định kỳ
(khám tổng quát 6, thẩm mỹ 12, nha chu duy trì 3, nha nhi 6). Dịch vụ không có
khoá này thì **không** bị gợi ý lặp lại.

### 6.4. Nguồn của lịch sử điều trị

Doc gốc v2 nói đầu vào là "lịch sử dịch vụ đã dùng / **hoàn tất**", nhưng
`appointments` không có trạng thái hoàn tất. Cần đúng hai thứ tối thiểu:

1. **Endpoint nha sĩ đánh dấu hoàn tất** — `POST /api/doctor/treatment`, tạo 1
   dòng `treatment_history` (outcome, followup_required, followup_due_date). Đây
   là phần **ngoài AC của SMMG-65/131** nhưng bắt buộc, vì `reason_code`
   `followup_due` — chính là card 91% trong wireframe — không có nguồn dữ liệu nào
   khác.
2. **`scripts/backfill_treatment_history.py`** — suy ra lịch sử từ các lịch hẹn
   `confirmed` có `date < today`, bỏ qua dòng có `department_code` không còn trong
   `DEPARTMENTS` (11/13 dòng hiện tại). Cộng với
   `scripts/seed_reco_demo.py` sinh ~8 bệnh nhân có lịch sử nhiều mốc thời gian
   để demo và eval có dữ liệu thật.

---

## 7. Định danh bệnh nhân

Theo AC PAT-01 *"Chỉ role Patient truy cập được sau login"* và SEQ 1.x
(`POST /auth/login` → JWT):

- Tự đăng ký: `POST /api/register` mở thêm `role="patient"`, yêu cầu `full_name`,
  `phone`, `birth_year`. Lưu ý [main.py:309](../app/main.py#L309) hiện chặn
  `role not in ["guest","doctor"]` → phải mở có kiểm soát, và **không** cho phép
  tự nâng lên `admin`/`doctor`.
- Sau login, redirect theo role: `patient` → `/patient` (hiện chỉ có nhánh
  `admin` và `doctor`, [login.html:384](../app/templates/login.html#L384)).
- **Nối lịch hẹn cũ về tài khoản:** khi tài khoản patient có `phone` khớp
  `appointments.patient_phone`, coi các lịch hẹn đó là của BN này. Đây là cách
  duy nhất để BN đã từng đặt qua chatbot (không có tài khoản) thấy được lịch sử.
  Rủi ro: ai đăng ký với SĐT của người khác sẽ thấy lịch sử người đó → **phải**
  xác thực quyền sở hữu SĐT trước khi nối. Vòng này chưa có SMS/OTP, nên yêu cầu
  **SĐT + một mã lịch hẹn hợp lệ** (`SHI-XXXXXX`) mới nối. Ghi rõ đây là mức
  demo-grade, và OTP nằm ở AUTH-01.

Trong `reco/`, mọi hàm nhận `patient_id` (kiểu `TEXT`), không nhận SĐT — SĐT chỉ
là chi tiết của tầng nối dữ liệu ở §6.4.

---

## 8. Engine gợi ý

### 8.1. Luồng

```
patient_id
  → history.recent(patient_id, limit=20)        # SEQ 3.3: 20 lần gần nhất
  → features.build(history, profile)            # cache in-process, TTL 1h (D4)
  → rules.signals(features, cooccurrence)       # hàm thuần
  → scoring: noisy-OR → confidence, urgency
  → post_filter: dismissed · trùng gần đây · lịch sắp tới · age_group
  → top-3  (cold-start: <3 lượt → popularity + age_group)
  → reasons.render() → llm_reason.polish()      # chỉ đổi câu chữ
  → log.write() (best-effort)                   # SEQ 5.4
```

### 8.2. Feature vector (theo SEQ 4.opt.1)

| Feature | Cách tính |
|---|---|
| `age_group` | `birth_year` → `child` <13 · `teen` 13–17 · `adult` 18–59 · `senior` ≥60 |
| `time_since_last` | số ngày từ `treatment_date` gần nhất |
| `followup_overdue` | có dòng `followup_required=true` và `followup_due_date < today` |
| `category_distribution` | tần suất `service_code` trong 20 lượt gần nhất |
| `allergy_flags` | từ `users.allergies`; rỗng thì bỏ qua bộ lọc dị ứng |
| `visit_count` | số lượt hoàn tất — quyết định nhánh cold-start |

### 8.3. Bộ luật & `reason_code`

| `reason_code` | Kích hoạt khi | Trọng số |
|---|---|---|
| `followup_due` | `followup_overdue`, hoặc dịch vụ định kỳ đã quá `recurring_months` | 0.55 → 0.85 theo mức quá hạn |
| `past_treatment` | đã dùng dịch vụ định kỳ và tới chu kỳ | 0.50 (+0.15 nếu quá 1.5× chu kỳ) |
| `similar_patients` | đồng xuất hiện: `P(B \| A)` trên toàn bộ BN, `A` thuộc lịch sử BN này | `0.6 × conf`, chỉ nhận khi support ≥ 3 BN |
| `care_pathway` | bảng chuỗi điều trị tĩnh: `noi_nha→phuc_hinh`, `nho_rang→phuc_hinh`, `nha_chu→kham_tong_quat` | 0.30 → 0.60, có cửa sổ thời gian |
| `age_group` | dịch vụ phù hợp nhóm tuổi (`teen→chinh_nha`, `senior→phuc_hinh`, `child→nha_nhi`) | 0.25 |
| `popular` | chỉ ở cold-start | 0.20 × tỉ trọng đặt lịch |

`similar_patients` là collaborative filtering dạng đồng xuất hiện (market-basket),
không phải SVD++ — nằm trong "quy tắc nghiệp vụ tối thiểu" của doc gốc v2, và
giải thích được cho BN. Khi support < 3 thì rơi về `care_pathway`, tránh việc
hiện một con số thống kê dựa trên 1–2 người.

**Gộp điểm — noisy-OR:** `confidence = 1 − Π(1 − wᵢ)`, cap `0.95`.
Nhiều tín hiệu cùng chỉ về một dịch vụ thì điểm tăng, nhưng không bao giờ đạt
100% — hệ thống không hứa chắc chắn về y tế. `% phù hợp = round(confidence × 100)`,
luôn `≠ 0` như TC-REC-001 yêu cầu.

`reason_code` hiển thị = tín hiệu có trọng số lớn nhất. Màn chi tiết (REC-02) liệt
kê **mọi** tín hiệu → khớp 3 bullet "Tại sao AI gợi ý?" trong wireframe.

**`urgency`:** `high` khi có `followup_overdue` hoặc quá hạn ≥ 2× chu kỳ;
`medium` khi `confidence ≥ 0.6`; còn lại `low`. Wireframe hiện nhãn "Cần thiết"
cho `high`.

### 8.4. Post-filter (SEQ 4.5)

Áp dụng **sau** khi chấm điểm, **trước** khi cắt top-3:

1. `service_code` nằm trong `dismissed_service_codes` → loại **vĩnh viễn**
   (TC-REC-004: "lần sau không xuất hiện").
2. Đã có lịch hẹn `confirmed` sắp tới cho dịch vụ đó → loại.
3. Vừa làm trong < 1 tháng và dịch vụ không định kỳ → loại (spec: "trùng gần đây").
4. `nha_nhi` chỉ giữ khi `age_group == child`; ngược lại, `child` thì loại các
   dịch vụ người lớn thuần (`tham_my`, `chinh_nha` giữ lại từ `teen`).
5. `allergy_flags` khớp chống chỉ định của dịch vụ → loại.
6. `confidence < 0.25` → loại, kể cả khi còn chỗ trong top-3. Thà hiện 2 card
   đúng hơn 3 card có 1 card rác.

### 8.5. Cold-start

Ngưỡng theo TC-REC-002: **`visit_count < 3`** (không phải "lịch sử rỗng").
Nhánh này trả `popularity` + `age_group`, `is_cold_start=true`, và **vẫn trả đủ 3
gợi ý**. UI hiện dải cảnh báo *"Chưa có đủ dữ liệu để gợi ý cá nhân"* + thời lượng
và giá thay cho `%` — đúng state 4 của wireframe.

### 8.6. Empty state

Khi post-filter không còn đủ ứng viên (TC-REC-005), trả `items: []` kèm
`empty_reason: "all_dismissed"`. UI hiện đúng câu spec:

> "Không còn gợi ý phù hợp. Chúng tôi sẽ cập nhật sau khi có thêm dữ liệu."

kèm link reset `dismissed_service_codes`.

---

## 9. Lớp LLM viết lý do (D1)

### 9.1. Hợp đồng

`llm_reason.polish(items, features)` nhận danh sách đã xếp hạng, trả về danh sách
**cùng thứ tự, cùng `service_code`/`confidence`/`rank`/`urgency`**, chỉ khác
`reason_text`. Dùng lại [triage/llm.py](../app/triage/llm.py) — cổng LLM duy nhất
của dự án, đã đảm bảo không bao giờ raise.

### 9.2. Validate đầu ra — bỏ câu LLM nếu vi phạm bất kỳ điều nào

- Trả về mã không có trong đầu vào, hoặc thiếu mã → **bỏ toàn bộ**, dùng template.
- `reason_text` > 120 ký tự, rỗng, hoặc chứa thuật ngữ kỹ thuật (`CF`, `CBF`,
  `embedding`, `score`, `model`) → dùng template cho riêng mục đó (TC-REC-006).
- Chứa dấu hiệu chẩn đoán/kê thuốc → chạy qua
  [`safety.is_diagnosis_request`](../app/triage/safety.py) trên output; vi phạm →
  template.
- Chứa số điện thoại/tên riêng → template (PII).

### 9.3. Cache & độ trễ (D2)

Cache khoá theo `(service_code, câu template)` — **không** theo `patient_id`, nên
`reason_text` không bao giờ chứa dữ liệu riêng của một BN, và tỉ lệ cache hit cao
(tập câu hữu hạn ≈ số `reason_code` × số dịch vụ). Đo thực tế: LLM thêm **~1.4s**
ở lần cache miss, ~0ms khi hit. Cache miss mà LLM lỗi/timeout thì fallback template.

Phải có `service_code` trong khoá: hai dịch vụ khác nhau có thể sinh ra CÙNG một
câu template, mà câu đã viết lại thì gắn với ngữ cảnh dịch vụ — dùng chung sẽ nói
sai dịch vụ.

Cờ `REC_LLM_REASON` (mặc định `1`) để tắt hoàn toàn khi đo eval hoặc khi chạy
offline không có `OPENROUTER_API_KEY`.

---

## 10. Chatbot thành widget

- `templates/_chat_widget.html` — Jinja partial chứa khung chat + JS, dùng ở cả
  `/` (toàn trang, giữ nguyên hành vi hiện tại) và `/patient` (bubble góc phải mở
  ra panel). Không thêm bước build, không nhân bản code.
- **Deep-link từ card gợi ý:** `POST /api/start {"service": "<code>"}` →
  `chatbot.start_with_service(sid, dept_code)` đặt `sess["dept_code"]` rồi gọi
  thẳng [`doctor_step.start_doctor_pick`](../app/chatbot/steps/doctor_step.py#L18),
  bỏ qua TRIAGE. Đúng TC-REC-003: "booking flow mở với dịch vụ được pre-selected;
  không cần chọn lại dịch vụ".
- Khi mở gợi ý từ trong chat, ghi `trigger="chatbot"` — enum đã có sẵn trong ER.

---

## 11. API

Theo tiền tố `/api/v1/patient/...` mà spec PAT-01 nêu, nhưng các endpoint hiện tại
đều là `/api/*` không version. Đề xuất: dùng `/api/patient/*` cho nhất quán nội
bộ, và ghi chú lệch tiền tố này lên Confluence.

| Method | Path | Auth | Mô tả |
|---|---|---|---|
| `GET` | `/patient` | patient | Trang PAT-01 |
| `GET` | `/api/patient/me` | patient | `{full_name, age_group, has_history}` |
| `GET` | `/api/patient/history` | patient | Lịch sử dịch vụ: ngày, dịch vụ, bác sĩ, trạng thái |
| `GET` | `/api/patient/appointments` | patient | Lịch hẹn sắp tới |
| `GET` | `/api/patient/recommendations?trigger=` | patient | Top-3 + `is_cold_start` + `rec_log_id` |
| `POST` | `/api/patient/recommendations/action` | patient | `{rec_log_id, action, service_code, rank}` — `book`/`dismiss`/`skip_all`/`view_detail` |
| `POST` | `/api/patient/recommendations/reset` | patient | Xoá `dismissed_service_codes` |
| `POST` | `/api/doctor/treatment` | doctor | Đánh dấu hoàn tất điều trị (§6.4) |

`GET /api/patient/recommendations` trả **luôn** phần chi tiết (`reason_detail`,
`duration_min`, `price_from/to`, bác sĩ phụ trách) để REC-02 mở modal không cần
round-trip thứ hai.

Mọi endpoint dùng `@require_auth(allowed_roles=["patient"])`. BN chỉ đọc được dữ
liệu của chính `patient_id` trong token — không nhận `patient_id` từ query string.

---

## 12. UI

`app/templates/patient.html` — Desktop, dùng lại bảng màu teal của
[admin.html](../app/templates/admin.html).

1. **PAT-01** — topbar (tên app + Đăng xuất), bảng lịch sử dịch vụ, nút "Xem gợi ý
   dịch vụ", ba trạng thái loading/empty/error (AC yêu cầu rõ).
2. **REC-01** — dải "AI gợi ý cho bạn · Dựa trên lịch sử khám · top 3", 3 card:
   tên · `% phù hợp` · nhãn urgency · lý do 1 câu · `Đặt lịch` / `Bỏ qua`.
3. **REC-02** — modal chi tiết: mô tả đầy đủ, thời lượng, giá cơ bản, "Tại sao AI
   gợi ý?" (mọi tín hiệu), gợi ý khác, `Không quan tâm` / `Xem gợi ý khác`.
4. **Cold-start** — dải cam + dịch vụ phổ biến kèm thời lượng/giá.
5. Chat widget nổi ở góc.
6. Disclaimer trên mỗi card: gợi ý là **dịch vụ**, không phải chẩn đoán.

**Không dựng theo wireframe:** cụm `BS. Nguyễn Minh Tú · ★4.9` — dự án không có
dữ liệu rating bác sĩ và không được bịa. Hiện tên bác sĩ phụ trách, bỏ phần sao.

---

## 13. Chừa chỗ cho REC-03

Không code màn nha sĩ ở vòng này, nhưng để sau này cắm vào mà không phải sửa
engine: `recommendation_log.dentist_feedback` + `dentist_acted_at` đã có trong
schema §6.1; `rec_log_id` được trả về cho client ngay từ vòng này. REC-03 khi làm
chỉ cần thêm 1 endpoint ghi feedback + 1 block UI trong
[doctor.html](../app/templates/doctor.html).

---

## 14. Đo lường & đánh giá

**Online** (từ `recommendation_log`): CTR gợi ý = `book / tổng`; dismiss rate;
`NDCG@3` từ `patient_acted_rank`; tỉ lệ cold-start; `latency_ms` p50/p95;
tỉ lệ `reason_text` phải fallback về template (đo chất lượng LLM).

**Offline** — `eval/evaluate_reco.py` + `eval/dataset_reco.jsonl`, cùng khuôn với
[eval/evaluate.py](../eval/evaluate.py) đã có: mỗi dòng là một hồ sơ BN tổng hợp
(lịch sử + tuổi) kèm nhãn vàng là tập dịch vụ hợp lý.

Chỉ số: `Precision@3`, `Recall@3`, `HitRate@3`, `MRR`, coverage.
**Baseline bắt buộc: `popular`** — gợi ý top phổ biến cho mọi người. Nếu engine
theo luật không thắng baseline này thì cá nhân hoá chưa có giá trị; đây là phép đo
đúng bài cho recommender và dùng được trong báo cáo đồ án.

`REC_LLM_REASON=0` khi chạy eval — vì LLM không tham gia xếp hạng, mọi chỉ số trên
đều tái lập được.

---

## 15. Test

Theo quy ước một file test cho một module ([code-standards.md](./code-standards.md)),
và map ngược về TC-F2 để giữ traceability:

| File | Phủ |
|---|---|
| `tests/test_reco_features.py` | `age_group`, `time_since_last`, `followup_overdue`, dữ liệu rác (`department_code` cũ) |
| `tests/test_reco_rules.py` | từng `reason_code`, noisy-OR, cap 0.95, urgency — TC-REC-001 |
| `tests/test_reco_filter.py` | dismissed vĩnh viễn (TC-REC-004), trùng gần đây, `nha_nhi` theo tuổi, empty state (TC-REC-005) |
| `tests/test_reco_coldstart.py` | `visit_count < 3` vẫn trả đủ 3 (TC-REC-002) |
| `tests/test_reco_llm_reason.py` | LLM đổi mã → bỏ; thuật ngữ kỹ thuật → template (TC-REC-006); timeout → template; **assert `confidence`/`rank` không đổi** |
| `tests/test_patient_api.py` | auth theo role, BN A không đọc được dữ liệu BN B, deep-link đặt lịch (TC-REC-003) |
| `tests/test_reco_log.py` | ghi log không chặn response khi storage lỗi |

---

## 16. Kế hoạch thực hiện

| # | Việc | File chính | Ước lượng |
|---|---|---|---|
| B1 | 3 bảng mới + cột `users` + CHECK role | `core/storage.py` | 0.5d |
| B2 | `SERVICE_META`; backfill + seed demo | `core/catalog.py`, `scripts/` | 1d |
| B3 | Role `patient`: register/login/redirect, nối SĐT+mã lịch hẹn | `main.py`, `login.html` | 1d |
| B4 | `reco/`: history, features, rules, reasons + test | `app/reco/` | 2.5d |
| B5 | `llm_reason.py` + cache + validate + test | `app/reco/llm_reason.py` | 0.5d |
| B6 | `patient_api.py` + log + prefs | `app/patient_api.py` | 1d |
| B7 | `patient.html` (PAT-01 + REC-01/02 + cold-start) | `app/templates/` | 2d |
| B8 | Chat widget partial + deep-link đặt lịch | `templates/_chat_widget.html`, `chatbot/` | 1d |
| B9 | Endpoint hoàn tất điều trị + nút trong doctor.html | `doctor_api.py` | 0.5d |
| B10 | `eval/evaluate_reco.py` + dataset | `eval/` | 1d |
| B11 | Cập nhật `docs/` + đồng bộ sai lệch lên Confluence | `docs/` | 0.5d |

**Tổng ≈ 11.5 ngày.** Thứ tự bắt buộc: B1 → B2 → B4. B7 làm được song song với B4
nếu chốt trước hình dạng JSON response.

Đường ngắn nhất tới bản demo chạy được: **B1 → B2 → B4 → B6 → B7** (≈7d), rồi bổ
sung B3/B8/B10.

---

## 17. Rủi ro

| Rủi ro | Mức | Xử lý |
|---|---|---|
| Gợi ý bị hiểu là chẩn đoán y tế | **Cao** | Chỉ gợi ý *dịch vụ*, không nêu bệnh; disclaimer mỗi card; cap 95%; validate output LLM qua `safety` |
| Nối SĐT sai → lộ lịch sử khám người khác | **Cao** | Yêu cầu SĐT + mã lịch hẹn hợp lệ; OTP thuộc AUTH-01 |
| `reason_text` LLM lọt PII hoặc câu sai | Trung bình | Cache không theo `patient_id`; validate 4 lớp §9.2; fallback template |
| Không đủ dữ liệu → `similar_patients` vô nghĩa | Trung bình | Ngưỡng support ≥ 3 BN, rơi về `care_pathway` |
| SLA `<500ms` vỡ vì D1 | Trung bình | Cache §9.3; hạ `LLM_TIMEOUT` còn 3s |
| Sai lệch doc ↔ code tiếp tục nới ra | Trung bình | Bảng §3 phải được đồng bộ lên Confluence khi merge |
| Đổi CHECK constraint fail trên DB có sẵn | Thấp | Bọc `try/except` riêng, app vẫn chạy |

---

## 18. Cần xác nhận với team

1. **Ai duyệt việc bỏ REC-03?** Doc gốc v2 + SMMG-67=`Idea` nói bỏ, nhưng
   wireframe `8060976` đang vẽ 4 states gồm màn nha sĩ.
2. **Giá dịch vụ ở `SERVICE_META` lấy từ đâu?** Hiện là số minh hoạ. TC-REC-007
   yêu cầu hiện "giá cơ bản" — cần bảng giá thật, và nó có thể trùng phạm vi
   Dynamic Pricing (SMMG-66/68/69).
3. **Chống chỉ định theo dị ứng** — spec có `allergy_flags` nhưng không có bảng
   ánh xạ dị ứng → dịch vụ. Vòng này chỉ chừa cột, chưa có luật thật.
4. **`/api/v1/...` hay `/api/...`?** Xem §11.
5. **Ngưỡng cold-start `<3`** áp trên số lượt *điều trị hoàn tất* hay số *lịch hẹn*?
   TC-REC-002 viết "appointments", doc gốc v2 viết "đã dùng / hoàn tất". Doc này
   chọn **lượt hoàn tất**.

---

## 19. Quyết định phát sinh lúc code (khác doc ban đầu)

Bốn điểm dưới đây được sửa **sau khi chạy engine trên dữ liệu thật** và thấy kết
quả sai; mỗi điểm đều có test khoá lại.

1. **`followup_required` không được suy ra từ `recurring_months`.** Doc ban đầu để
   backfill tự đặt hẹn tái khám cho mọi dịch vụ định kỳ. Hậu quả: luật
   `followup_due` kích hoạt cho *mọi* dịch vụ định kỳ và nuốt sạch luật
   `past_treatment` — `past_treatment` thành code chết, và card nói sai bản chất
   ("nha sĩ đã hẹn" trong khi không ai hẹn). `followup_required` giờ chỉ mang nghĩa
   **chỉ định của nha sĩ**; gợi ý theo chu kỳ do `past_treatment` lo.

2. **Card bù không dùng tỉ lệ phổ biến làm `% phù hợp`.** "88% bệnh nhân từng khám
   tổng quát" không có nghĩa dịch vụ đó phù hợp 88% với riêng người này. Điểm của
   card bù được quy về thang `W_POPULAR_FACTOR`, và `fit_percent` bị đặt `None` cho
   card bù + toàn bộ nhánh cold-start — hiện "5% phù hợp" vừa vô nghĩa vừa trông
   như lỗi. Danh sách được sắp lại để `%` luôn giảm dần theo thứ hạng.

3. **Thiếu năm sinh thì xét như người trưởng thành**, thay vì loại mọi dịch vụ có
   giới hạn tuổi (§8.4 bản đầu). Bản đầu loại oan cả `tham_my`, `chinh_nha`,
   `phuc_hinh`. Bản hiện tại chỉ loại dịch vụ mà người trưởng thành không dùng —
   đủ để không gợi ý "Nha khoa trẻ em" cho người chưa khai tuổi.

4. **Cần bộ chặn riêng cho câu KHẲNG ĐỊNH y tế.** Doc ban đầu định dùng lại
   `safety.is_diagnosis_request()` để kiểm duyệt đầu ra LLM, nhưng bộ pattern đó
   được xây để bắt câu **hỏi** của người dùng ("uống thuốc gì") nên không chặn được
   câu **khẳng định** do LLM sinh ("Bạn bị viêm tủy, cần uống kháng sinh"). Thêm
   `reasons.has_medical_claim()` cho chiều ngược lại.

5. **SLA `<500ms` không đạt, và nút thắt KHÔNG phải LLM.** Đo trên Supabase thật:

   | | engine | ghi chú |
   |---|---|---|
   | LLM tắt (`REC_LLM_REASON=0`) | 1.4–2.0s | thuần rule + đọc DB |
   | LLM bật, cache miss | ~3.0–3.4s | LLM thêm ~1.4s |
   | LLM bật, cache hit | ~1.6s | bằng mức LLM tắt |

   Instrument `storage._connect`: **6 connection Postgres cho một request, và 81%
   tổng thời gian chỉ để MỞ connection** (~700ms/lần tới Supabase qua internet).
   `storage.py` mở connection MỚI cho mỗi lần gọi hàm — thuộc tính có từ Sprint 1,
   không phải do tính năng này. Tắt LLM cũng không đạt 500ms.

   Cách sửa đúng là **connection pool** (`psycopg_pool`) ở `core/storage.py`, ảnh
   hưởng toàn bộ dự án nên tách thành việc riêng, không gộp vào đây. Đã giảm được
   1 round-trip bằng cách gộp `cooccurrence` + `popularity` vào một lần đọc có cache.

6. **Guard "không nói về dịch vụ khác" phải miễn trừ dịch vụ được tham chiếu.**
   Bản đầu loại mọi câu LLM có nhắc tên dịch vụ khác, nhưng `care_pathway` và
   `similar_patients` BUỘC phải nhắc dịch vụ trước đó ("Sau khi nội nha…") — nên hai
   luật này luôn bị loại oan và mất hẳn phần LLM. Giờ chỉ chặn dịch vụ **không**
   nằm trong `ctx.from_service` của chính tín hiệu đó.

Ngoài ra `top_up` (bù cho đủ 3 gợi ý) được thêm để đúng TC-REC-001/002, thay cho
quy tắc "thà hiện 2 card đúng hơn 3 card rác" ở §8.4 bản đầu — ngưỡng
`MIN_CONFIDENCE` vẫn áp cho các card *cá nhân hoá*, phần bù nằm ngoài ngưỡng đó và
được đánh dấu `is_filler`.

### Còn lại để demo được trên máy thật

Tài khoản bệnh nhân nằm ở `users`, mà bảng đó **không có JSON-mode fallback** (quyết
định từ Sprint 1). Nên muốn mở `/patient` bằng trình duyệt cần Postgres:

```bash
.venv/bin/python -c "from app.core import storage; storage.init_schema()"  # tạo bảng + role
.venv/bin/python scripts/backfill_treatment_history.py                     # lịch sử từ lịch hẹn cũ
.venv/bin/python scripts/seed_reco_demo.py                                 # 8 hồ sơ demo + tài khoản
PORT=5001 .venv/bin/python -m app.main                                     # login bn101 / test123
```

---

## 20. Chế độ khách (chưa đăng nhập)

Chatbot không còn là trang riêng, nên `/` phải phục vụ cả người chưa có tài khoản —
nếu không, khách mất đường đặt lịch trên web.

| | Khách | Bệnh nhân đã đăng nhập |
|---|---|---|
| Vào `/` | ✅ | ✅ |
| Lịch sử điều trị / lịch hẹn | trống, mời đăng nhập | đầy đủ |
| Gợi ý | luôn **cold-start** (dịch vụ phổ biến, không hiện %) | cá nhân hoá, có % |
| "Không quan tâm" | ẩn nút (không có tài khoản để lưu) | lưu bền |
| Đặt lịch qua widget chat | ✅ | ✅ |
| Ghi `recommendation_log` | không (không có `patient_id`) | có |

**Bẫy đã gặp và đã chặn:** `storage.list_treatments()` gọi không tham số trả về
TOÀN BỘ bảng (cố ý — bảng đồng xuất hiện cần thế). `reco.history.recent()` là API
theo-từng-bệnh-nhân, nếu không chặn thì khách (không id, không SĐT) sẽ rơi vào
nhánh đó và nhận **lịch sử của cả phòng khám làm lịch sử của mình** — vừa mất
cold-start vừa là rò rỉ dữ liệu. Đã chốt chặn ở `recent()` + test riêng.

---

## Tài liệu liên quan

- [project-overview-pdr.md](./project-overview-pdr.md) — bài toán & phạm vi gốc
- [system-architecture.md](./system-architecture.md) — kiến trúc hiện tại
- [code-standards.md](./code-standards.md) — quy tắc phụ thuộc module, đặt tên
- [project-roadmap.md](./project-roadmap.md) — khoảng trống production
