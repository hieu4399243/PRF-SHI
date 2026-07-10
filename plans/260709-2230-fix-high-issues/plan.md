---
title: "Fix High Issues (H1-H9) - ISSUES.md"
description: "Vá 8 vấn đề High còn code (H1-H8) trong ISSUES.md, TDD, chạy song song hoàn toàn (không file nào bị đụng chéo). H9 đóng bằng ghi chú, không cần code."
status: completed
priority: P2
branch: "main"
tags: ["security", "high-fix", "tdd"]
blockedBy: []
blocks: []
created: "2026-07-09T15:34:36.862Z"
createdBy: "ck:plan"
source: skill
---

# Fix High Issues (H1-H9) - ISSUES.md

## Overview

Vá 8/9 vấn đề High trong `ISSUES.md` (H1-H8). H9 KHÔNG cần code — xem "H9 — đóng bằng ghi
chú" bên dưới. Kế thừa toàn bộ context/quyết định đã có từ plan trước
(`plans/260709-2126-fix-critical-issues/`), đặc biệt: production chạy 1 Flask process (không
Redis), `DATABASE_URL` luôn có ở production (Postgres).

**3 quyết định đã chốt với user trước khi lên plan này:**
1. **H1 là bug**, không phải spec đúng — khoá trùng giờ phải theo `(doctor_id, date, time)`,
   không phải `(date, time)` toàn phòng khám.
2. **H2 thu hẹp phạm vi** — không có tiến trình nào đọc `outbox/push_outbox.jsonl` để gửi
   lại (đã hỏi, không có). Vì vậy CHỈ sửa phần khả thi: không đánh dấu `reminders_sent` khi
   push tới token thật thất bại do lỗi mạng (để lần quét sau tự thử lại) — KHÔNG xây thêm
   worker/tiến trình đọc outbox (over-engineering, ngoài phạm vi).
3. **H9 đóng lại, chấp nhận rủi ro** — quyết định "1 process" ở plan trước đã trả lời đúng
   phần multi-worker của H9. Mất session khi restart là trade-off chấp nhận được cho quy mô
   đồ án; không xây persistence (Redis/DB) — YAGNI.

## Ngoài phạm vi (không đụng trong plan này)

- H9 code fix (xem trên — chỉ đóng bằng ghi chú trong `ISSUES.md`).
- Toàn bộ mục Medium/Low trong `ISSUES.md`.
- Xây tiến trình retry đọc `outbox/push_outbox.jsonl` (H2 đã thu hẹp, không làm).
- Đổi cơ chế lưu session sang Redis/DB (đã quyết định ở plan C1-C5, không lặp lại ở đây).

## Phases — TẤT CẢ chạy song song (không file nào bị đụng chéo)

| Phase | Name | Vấn đề | File(s) touched | Status |
|-------|------|--------|------------------|--------|
| 1 | [H1 Doctor Scoped Slot Uniqueness](./phase-01-h1-doctor-scoped-slot-uniqueness.md) | H1 | `storage.py`, `booking.py`, `tests/test_booking.py` | Completed |
| 2 | [H2H3H4 Worker Reliability And Timezone](./phase-02-h2h3h4-worker-reliability-and-timezone.md) | H2, H3, H4 | `push.py`, `reminder_worker.py`, `tests/test_reminder_worker.py` | Completed |
| 3 | [H5 ICS Calendar Injection Escaping](./phase-03-h5-ics-calendar-injection-escaping.md) | H5 | `calendar_ics.py`, `tests/test_calendar_ics.py` (mới) | Completed |
| 4 | [H6H7 Admin Auth Hardening](./phase-04-h6h7-admin-auth-hardening.md) | H6, H7 | `app.py`, `docs/getting-started-guide.md`, `tests/test_app_admin.py` (mới) | Completed |
| 5 | [H8 Audit Log Name Redaction](./phase-05-h8-audit-log-name-redaction.md) | H8 | `chatbot.py`, `tests/test_chatbot_audit.py` (mới) | Completed |

Lý do gộp H2+H3+H4 vào 1 phase: cả 3 đều sửa `reminder_worker.py` (và H2 cần sửa thêm
`push.py`) — gộp để tránh 2-3 agent cùng sửa 1 file. Lý do gộp H6+H7: cả 2 đều sửa `app.py`
(admin auth + startup warning), cùng lý do.

**File ownership matrix — xác nhận KHÔNG có overlap giữa 5 phase:**
`storage.py`/`booking.py` (Phase 1) · `push.py`/`reminder_worker.py` (Phase 2) ·
`calendar_ics.py` (Phase 3) · `app.py` (Phase 4) · `chatbot.py` (Phase 5) — 5 file nguồn
khác nhau hoàn toàn, mỗi phase cũng tạo/sửa file test riêng của mình. Không cần Group A/B
như plan trước — TẤT CẢ 5 phase là 1 group duy nhất, chạy song song hết.

## H9 — đóng bằng ghi chú (không phải 1 phase)

Không tạo phase riêng vì không có code cần sửa. Khi hoàn tất plan này, cập nhật `ISSUES.md`
đánh dấu H9 `[x]` với ghi chú: "Quyết định 1-process ở C3 (`plans/260709-2126-...`) đã trả
lời phần multi-worker. Mất session khi restart là rủi ro chấp nhận, không persist — xem
comment tại `chatbot.py` gần khai báo `SESSIONS`."

## Test Infrastructure

Kế thừa từ plan trước: `pytest==8.3.3` đã có trong `requirements.txt`, `tests/` đã tồn tại.
Interpreter test: `python3.10` (có đủ flask/psycopg/dotenv/pytest — `python3`/`python` mặc
định trên máy này là 3.14, THIẾU các gói này, không dùng).

## Red Team Review

### Session — 2026-07-10
**Findings:** 13 unique sau dedupe (từ 3 reviewer: Security Adversary/Fact Checker,
Failure Mode Analyst/Flow Tracer, Assumption Destroyer/Scope Auditor — 2 finding Critical
được 2 reviewer độc lập tìm ra trùng nhau, tăng độ tin cậy).
**Severity breakdown:** 2 Critical, 4 High, 7 Medium.
**Kết quả:** Tất cả 13 finding Accept, không finding nào bị reject — tất cả có bằng chứng
`file:line` hợp lệ.

| # | Finding | Severity | Disposition | Applied To |
|---|---------|----------|-------------|------------|
| 1 | `_insert_with_race_guard` bên trong vẫn gọi `_confirmed_at` 2 tham số cũ — TypeError đúng lúc race thật xảy ra | Critical | Accept | Phase 1 |
| 2 | H7 bỏ sót `debug=True`/`host=0.0.0.0` (RCE qua Werkzeug debugger) dù ISSUES.md định nghĩa H7 gồm cả phần này | Critical | Accept | Phase 4 |
| 3 | Claim "không ai dùng ?key=" sai — docs/getting-started-guide.md có ví dụ curl dùng ?key= | High | Accept | Phase 4 |
| 4 | Đếm sai số chỗ cần sửa lambda 2-tham số trong tests/test_booking.py | High | Accept | Phase 1 |
| 5 | `_check_admin()` sau hardening vẫn so sánh `==` không constant-time | High | Accept | Phase 4 |
| 6 | DROP+CREATE gộp 1 execute() — psycopg3 xử lý multi-statement không đảm bảo | High | Accept | Phase 1 |
| 7 | Thứ tự DROP-trước-CREATE: CREATE fail sau khi DROP xong → mất hết bảo vệ | Medium | Accept | Phase 1 |
| 8 | H2 chỉ bắt lỗi mạng, không bắt lỗi ticket cấp ứng dụng của Expo | Medium | Accept (chỉ ghi chú) | Phase 2 |
| 9 | Risk Assessment Phase 1 chưa nói rõ JSON-fallback vẫn không có bảo vệ DB-level | Medium | Accept (chỉ ghi chú) | Phase 1 |
| 10 | Không phân tích rủi ro rollback/downgrade tên constraint | Medium | Accept (chỉ ghi chú) | Phase 1 |
| 11 | Code mẫu Phase 2 dùng `...` che mất lớp `except ValueError` lồng bên trong | Medium | Accept | Phase 2 |
| 12 | Comment cũ trên `_check_admin` vẫn nói còn hỗ trợ `?key=` | Medium | Accept | Phase 4 |
| 13 | Kỹ thuật test `importlib.reload(app)` rò rỉ state global qua test khác | Medium | Accept | Phase 4 |

### Whole-Plan Consistency Sweep
- Files reread: plan.md, phase-01, phase-02, phase-03, phase-04, phase-05 (toàn bộ, sau khi
  áp dụng 13 finding).
- Decision deltas checked: 13 (đổi thứ tự DROP/CREATE thành CREATE/DROP; tách 2
  `cur.execute()`; thêm sửa `_insert_with_race_guard` nội bộ; bỏ đếm số cố định "3 chỗ" cho
  test stub; thêm `hmac.compare_digest`; thêm cập nhật comment `_check_admin`; thêm cập nhật
  `docs/getting-started-guide.md`; đổi kỹ thuật test H7 từ `importlib.reload` sang hàm thuần
  `_default_key_warnings`; thêm cảnh báo debug=True/host=0.0.0.0; viết đầy đủ cấu trúc
  try/except lồng nhau ở Phase 2 thay vì rút gọn `...`).
- Reconciled stale references: 2 (plan.md bảng phase 4 thiếu `docs/getting-started-guide.md`
  trong cột File(s) touched — đã thêm; phase-04's Related Code Files/Success
  Criteria/Risk Assessment đồng bộ lại theo Architecture mới, không còn nhắc
  `importlib.reload` như phương án chính).
- Unresolved contradictions: 0.

## Dependencies

Không phụ thuộc plan khác đang mở. Không blocked bởi plan nào trong `plans/`.

## Acceptance Criteria (toàn plan)

- [x] Cả 5 phase có test mới, fail trước khi sửa, pass sau khi sửa (TDD) — xác nhận qua báo
  cáo từng subagent.
- [x] `pytest tests/ -v` toàn bộ pass — 49 passed, 1 skipped (skip có tài liệu: thiếu
  Postgres local, kế thừa từ plan C1-C5). Xác nhận qua code review độc lập, score 9/10.
- [x] App chạy được không lỗi import/syntax —
  `python3.10 -c "import app, safety, storage, booking, chatbot, reminder_worker, triage,
  push, calendar_ics"` clean.
- [x] `reminder_worker.py --once` và `--test` đều chạy sạch trên `appointments.json` hiện
  tại — verify thủ công, `appointments.json` KHÔNG đổi sau `--test` (xác nhận H3 hoạt động
  đúng end-to-end, không chỉ trong test mock).
- [x] `ISSUES.md`: đánh dấu `[x]` cho H1-H9 (H9 chỉ ghi chú, không code).
- [x] Không thay đổi hành vi nghiệp vụ ngoài phạm vi 8 issue này — code review độc lập xác
  nhận không rate-limit, không sửa MAX_CONTENT_LENGTH, không đụng file-locking JSON mode
  (đều là Medium/Low ngoài phạm vi).
