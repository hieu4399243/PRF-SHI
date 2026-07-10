---
title: "Fix Medium and Low Issues - ISSUES.md"
description: "Vá 9 Medium + 1 Low còn lại trong ISSUES.md, TDD, chạy song song hoàn toàn (không file nào bị đụng chéo). 2 mục đóng bằng ghi chú, 1 mục đã fix từ trước."
status: completed
priority: P3
branch: "main"
tags: ["reliability", "medium-fix", "tdd"]
blockedBy: []
blocks: []
created: "2026-07-10T03:00:08.074Z"
createdBy: "ck:plan"
source: skill
---

# Fix Medium and Low Issues - ISSUES.md

## Overview

Vá các mục Medium/Low còn lại trong `ISSUES.md` sau 2 vòng fix Critical
(`plans/260709-2126-fix-critical-issues/`) và High (`plans/260709-2230-fix-high-issues/`).
Kế thừa toàn bộ quyết định đã chốt trước đó: production 1 Flask process, `DATABASE_URL`
luôn có ở production (Postgres), không xây Redis/hạ tầng mới.

## Đã xử lý trước khi lên plan này (không cần phase)

- **L1 (so sánh khoá admin không constant-time)** — đã fix TỪ TRƯỚC như tác dụng phụ của H6
  (`_check_admin()` đã dùng `hmac.compare_digest` từ `plans/260709-2230-fix-high-issues/`).
  Đánh dấu `[x]` trong `ISSUES.md`, không cần code.
- **M4 (quét toàn bảng, mở connection mới mỗi lần)** — user quyết định BỎ QUA, chỉ ghi chú.
  Quy mô đồ án nhỏ, tối ưu connection pooling + WHERE clause là premature optimization
  (YAGNI). Đóng bằng ghi chú trong `ISSUES.md`, không code trong plan này.
- **L2 (SĐT hợp lệ hình thức nhưng không tồn tại)** — user quyết định KHÔNG fix. Xác minh
  thật cần dịch vụ SMS/telco ngoài, ngoài phạm vi đồ án. Đóng bằng ghi chú.

## Quyết định đã chốt với user cho các mục còn lại (5 câu hỏi)

1. **M8 (rate limiting)** — LÀM, giới hạn đơn giản theo IP (in-memory, không thêm
   dependency, không Redis).
2. **M5 (Expo token hết hạn/lỗi ticket)** — LÀM, parse ticket response của Expo, xoá token
   báo `DeviceNotRegistered`. Tiện thể đóng nốt residual risk đã ghi ở H2 (ticket lỗi HTTP
   200 bị bỏ qua, không tính vào `failed`).
3. **M7 (session id client tự chọn)** — LÀM, validate format uuid4-hex, không đúng format
   thì bỏ qua giá trị client gửi, tự mint mới.
4. **M4 (perf)** — BỎ QUA (xem trên).
5. **L2 (SĐT không tồn tại)** — KHÔNG FIX (xem trên).

## Phases — TẤT CẢ chạy song song (không file nào bị đụng chéo)

| Phase | Name | Vấn đề | File(s) touched | Status |
|-------|------|--------|------------------|--------|
| 1 | [M1M10 Chatbot Guardrail And Session Lock](./phase-01-m1m10-chatbot-guardrail-and-session-lock.md) | M1, M10 | `chatbot.py`, `tests/test_chatbot_guardrail.py` (mới), `tests/test_chatbot_session_lock.py` (mới) | Completed |
| 2 | [M2M5M6 Storage And Push Reliability](./phase-02-m2m5m6-storage-and-push-reliability.md) | M2, M5, M6 | `storage.py`, `push.py`, `booking.py`, `tests/test_storage.py` (mới), `tests/test_push.py` (mới), `tests/test_booking.py` (mở rộng) | Completed |
| 3 | [M3M7M8 App Hardening](./phase-03-m3m7m8-app-hardening.md) | M3, M7, M8 | `app.py`, `tests/test_app_hardening.py` (mới), `tests/conftest.py` (mới) | Completed |
| 4 | [M9 Audit Log Robustness](./phase-04-m9-audit-log-robustness.md) | M9 | `safety.py`, `tests/test_safety.py` (mở rộng) | Completed |
| 5 | [L3 Reminder Overdue Logging](./phase-05-l3-reminder-overdue-logging.md) | L3 | `reminder_worker.py`, `tests/test_reminder_worker.py` (mở rộng) | Completed |

**File ownership matrix — xác nhận KHÔNG có overlap giữa 5 phase:**
`chatbot.py` (Phase 1) · `storage.py`/`push.py`/`booking.py` (Phase 2) · `app.py` (Phase 3) ·
`safety.py` (Phase 4) · `reminder_worker.py` (Phase 5) — 5 nhóm file khác nhau hoàn toàn.
Mỗi phase cũng chỉ đụng file test của riêng mình (kể cả khi mở rộng file test đã có từ vòng
trước — chỉ 1 phase mở rộng mỗi file test). TẤT CẢ 5 phase chạy song song, không cần
Group A/B như 2 plan trước.

## Test Infrastructure

Kế thừa từ 2 plan trước: `pytest==8.3.3` đã có trong `requirements.txt`, `tests/` đã tồn
tại. Interpreter test: `python3.10` (có đủ flask/psycopg/dotenv/pytest — `python3`/`python`
mặc định trên máy này là 3.14, THIẾU các gói này, không dùng).

## Red Team Review

### Session — 2026-07-10
**Findings:** 11 unique sau dedupe (từ 3 reviewer: Security Adversary/Fact Checker,
Failure Mode Analyst/Flow Tracer, Assumption Destroyer/Scope Auditor — 1 finding Critical
(khoá per-session bị `/reset` vô hiệu) được CẢ 3 reviewer độc lập tìm ra trùng nhau).
**Severity breakdown:** 4 Critical, 1 High, 6 Medium.
**Kết quả:** Tất cả 11 finding Accept, không finding nào bị reject.

| # | Finding | Severity | Disposition | Applied To |
|---|---------|----------|-------------|------------|
| 1 | Khoá per-session (M10) bị `/reset`/TTL-expiry vô hiệu — dict/lock mới thay thế dict cũ giữa chừng, mất tác dụng bảo vệ | Critical | Accept | Phase 1 |
| 2 | M6 không thực sự đóng race trùng SLOT ở JSON mode — chỉ fix trùng code, `_confirmed_at` chạy ngoài khoá | Critical | Accept | Phase 2 |
| 3 | M7 crash (`TypeError`) nếu client gửi `session` không phải string | Critical | Accept | Phase 3 |
| 4 | M5: parse ticket Expo có thể raise xuyên qua booking đã thành công, crash `/api/chat` | Critical | Accept | Phase 2 |
| 5 | M2: `add_token` không được đưa vào danh sách khoá `_JSON_LOCK` dù `remove_token` mới có khoá | High | Accept | Phase 2 |
| 6 | M1: vị trí chèn guardrail (trước cancel-intent/info-question) có thể nuốt mất 2 ý định đó | Medium | Accept | Phase 1 |
| 7 | M8: reset `_RATE_BUCKETS` giữa test chỉ là gợi ý có điều kiện, không bắt buộc | Medium | Accept | Phase 3 |
| 8 | M9: rotation audit log không khoá — race giữa nhiều session ghi đồng thời | Medium | Accept | Phase 4 |
| 9 | M8: rate limit loại trừ `/api/admin/*` — brute-force ADMIN_KEY không giới hạn | Medium | Accept | Phase 3 |
| 10 | M6: code mẫu không khớp cấu trúc try/except thật của `_insert_with_race_guard` | Medium | Accept (gộp vào thiết kế lại #2) | Phase 2 |
| 11 | Field `_lock` mới chặn đường nâng cấp Redis đã ghi chú sẵn, không có cảnh báo | Medium | Accept | Phase 1 |

### Whole-Plan Consistency Sweep
- Files reread: plan.md, phase-01 đến phase-05 (toàn bộ, sau khi áp dụng 11 finding).
- Decision deltas checked: 11 (lock reuse qua `reuse_lock` param; M6 thêm `SlotTakenError` +
  check-and-insert atomic; M5 tách try lồng nhau fail-open khi parse lỗi; `add_token` thêm
  vào `_JSON_LOCK`; M1 chèn sau cancel/info thay vì trước; `tests/conftest.py` bắt buộc
  không còn điều kiện; M8 áp dụng cho `/api/admin/*`, bỏ `_RATE_LIMITED_PATHS` set riêng;
  M9 thêm `_AUDIT_LOCK`; M7 thêm `isinstance` check).
- Reconciled stale references: 2 (plan.md bảng Phase 3 thiếu `tests/conftest.py` — đã thêm;
  phase-03's Risk Assessment cũ về "test rate-limit ảnh hưởng lẫn nhau, nếu phát hiện thì
  thêm fixture" đã lỗi thời sau khi conftest.py trở thành bắt buộc — đã xoá đoạn đó, thay
  bằng risk note mới về admin rate limit).
- Unresolved contradictions: 0.

## Dependencies

Không phụ thuộc plan khác đang mở. Không blocked bởi plan nào trong `plans/`.

## Acceptance Criteria (toàn plan)

- [x] Cả 5 phase có test mới, fail trước khi sửa, pass sau khi sửa (TDD) — xác nhận qua báo
  cáo từng subagent.
- [x] `pytest tests/ -v` toàn bộ pass — 92 passed, 1 skipped (skip có tài liệu: thiếu
  Postgres local, kế thừa từ plan C1-C5). Xác nhận qua code review độc lập, score 9/10.
- [x] App chạy được không lỗi import/syntax —
  `python3.10 -c "import app, safety, storage, booking, chatbot, reminder_worker, triage,
  push, calendar_ics"` clean.
- [x] `ISSUES.md`: đánh dấu `[x]` cho M1,M2,M3,M5,M6,M7,M8,M9,L1,L3. M4/L2 GIỮ `[ ]` kèm ghi
  chú "đóng bằng ghi chú, không fix" (chính xác hơn đánh dấu `[x]` giả — 2 mục này thực sự
  KHÔNG được sửa code, chỉ là quyết định có chủ đích bỏ qua). KHÔNG đụng các mục đã `[x]` từ
  trước (Critical/High).
- [x] Không thay đổi hành vi nghiệp vụ ngoài phạm vi các issue này — code review độc lập xác
  nhận không có M4 (connection pooling)/L2 (xác minh SĐT) code nào bị âm thầm thêm vào.
