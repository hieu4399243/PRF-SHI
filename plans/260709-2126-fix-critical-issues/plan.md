---
title: "Fix Critical Issues (C1-C5) - ISSUES.md"
description: "Vá 5 vấn đề Critical (an toàn tính mạng, double-booking, DoS bộ nhớ, lộ dữ liệu sức khỏe, worker crash) trong ISSUES.md, TDD, tối đa hoá chạy song song"
status: completed
priority: P1
branch: "main"
tags: ["security", "critical-fix", "tdd"]
blockedBy: []
blocks: []
created: "2026-07-09T14:27:47.922Z"
createdBy: "ck:plan"
source: skill
---

# Fix Critical Issues (C1-C5) - ISSUES.md

## Overview

Vá 5 vấn đề Critical liệt kê trong `ISSUES.md` (audit song song 5 agent, 2026-07-09).
Không đụng High/Medium/Low — ngoài phạm vi yêu cầu. Mỗi phase viết test thất bại trước
(TDD), fix tới khi pass, không thêm tính năng ngoài scope.

**Quyết định đã chốt với user (ảnh hưởng thiết kế C2/C3):**
- Production chạy **1 Flask process duy nhất** → C3 fix bằng cap+TTL in-memory
  (LRU dict), KHÔNG cần Redis (YAGNI).
- Production **luôn có `DATABASE_URL`** (Postgres/Supabase) → C2 chỉ cần fix nhánh
  Postgres (UNIQUE constraint + bắt lỗi). Nhánh JSON giữ nguyên hành vi cũ (chỉ dùng
  dev/demo local, rủi ro race đã biết và chấp nhận — không phải regression mới).

**Ngoài phạm vi (không đụng trong plan này):**
- H1 (trùng giờ bỏ qua `doctor_id`) — chưa xác nhận là bug hay spec đúng. UNIQUE
  constraint ở C2 giữ nguyên semantics hiện tại của `_confirmed_at()`
  (khoá theo `date+time`, KHÔNG theo `doctor_id`) để không âm thầm đổi hành vi nghiệp
  vụ. Nếu sau này xác nhận H1 là bug, sửa riêng ở plan khác.
- Mọi mục High/Medium/Low khác trong `ISSUES.md`.

## Test Infrastructure (mới, cần cho TDD)

Repo chưa có test framework. Thêm tối thiểu:
- `pytest==8.3.3` vào `requirements.txt` (dev dependency, không ảnh hưởng runtime prod).
- Thư mục `tests/` ở root, 1 file test theo mỗi phase (`test_safety.py`,
  `test_booking.py`, `test_chatbot_sessions.py`, `test_app_ics.py`,
  `test_reminder_worker.py`).
- Không thêm CI config, coverage tooling, fixtures phức tạp — chỉ đủ để mỗi phase
  tự chạy `pytest tests/test_x.py -v` và pass. YAGNI.

## Phases

| Phase | Name | File(s) touched | Status | Parallel group |
|-------|------|------------------|--------|-----------------|
| 1 | [C1 Emergency Detection Accents](./phase-01-c1-emergency-detection-accents.md) | `safety.py` | Completed | A (song song) |
| 2 | [C2 Double-Booking Race](./phase-02-c2-double-booking-race.md) | `storage.py`, `booking.py` | Completed | A (song song) |
| 3 | [C3 Session Memory Cap](./phase-03-c3-session-memory-cap.md) | `chatbot.py` | Completed | A (song song) |
| 4 | [C4 ICS Auth and Code Security](./phase-04-c4-ics-auth-and-code-security.md) | `booking.py`, `app.py` | Completed | B (sau Phase 2) |
| 5 | [C5 Worker Crash Isolation](./phase-05-c5-worker-crash-isolation.md) | `reminder_worker.py` | Completed | A (song song) |

## File Ownership / Parallel Execution Rule

`booking.py` bị sửa bởi CẢ Phase 2 và Phase 4 (khác hàm, nhưng cùng file → race
edit nếu chạy song song thật). Theo `orchestration-protocol.md` (tránh parallel
edit cùng file):

- **Group A** (chạy song song, KHÔNG đụng file chung): Phase 1, 2, 3, 5.
- **Group B** (chạy SAU khi Phase 2 merge xong): Phase 4 — vì nó sửa tiếp
  `booking.py` (CHỈ `_generate_code()` — đổi `random` sang `secrets`; kiểm tra quyền sở
  hữu nằm ở route `app.py::download_ics`, KHÔNG sửa `book_appointment`), phải dựa trên bản
  `booking.py` đã có try/except `UniqueViolation` từ Phase 2 (tránh conflict khi cả 2 phase
  cùng sửa hàm khác nhau trong 1 file).

`phase-04` có `dependencies: [2]` trong frontmatter để phản ánh đúng thứ tự này.

## Dependencies

Không phụ thuộc plan khác đang mở. Không blocked bởi plan nào trong `plans/`.

## Red Team Review

### Session — 2026-07-09
**Findings:** 9 unique sau dedupe (từ 3 reviewer: Security Adversary/Fact Checker,
Failure Mode Analyst/Flow Tracer, Assumption Destroyer/Scope Auditor — nhiều finding trùng
lặp giữa các reviewer đã gộp lại).
**Severity breakdown:** 3 Critical, 5 High, 1 Medium.
**Kết quả:** Tất cả 9 finding đều có bằng chứng `file:line` hợp lệ, không finding nào bị
reject. 2 finding được Accept nhưng THU HẸP phạm vi đề xuất gốc để tránh phình phạm vi
ngoài "chỉ fix 5 Critical" (xem cột Disposition).

| # | Finding | Severity | Disposition | Applied To |
|---|---------|----------|-------------|------------|
| 1 | UNIQUE INDEX trong `init_schema()` không try/except — nếu prod đã có dữ liệu trùng sẵn, migrate fail vĩnh viễn → sập toàn app | Critical | Accept | Phase 2 |
| 2 | Handler `UniqueViolation` không phân biệt `ux_appointments_slot` vs `appointments_pkey` (code trùng ngẫu nhiên) → nhánh sai gây `AttributeError` khi đang xử lý exception | Critical | Accept | Phase 2 |
| 3 | Fix C1 chỉ strip-accent pattern, không `_normalize` — pattern từ Supabase (admin-editable, case bất kỳ) so khớp fail âm thầm | Critical | Accept | Phase 1 |
| 4 | Test C2 hoàn toàn monkeypatch, không có test Postgres thật | High | Accept (thu hẹp — chạy nếu có `DATABASE_URL` local, nếu không thì ghi rõ giới hạn trong báo cáo, không được im lặng bỏ qua) | Phase 2 |
| 5 | `plan.md` nói Phase 4 sửa `book_appointment` nhưng thực tế chỉ sửa `download_ics`; Risk Assessment nhắm sai đối tượng (mobile không gọi `/api/ics`, rủi ro thật là web mất cookie) | High | Accept | Phase 4, plan.md |
| 6 | try/except bao trùm `_send_for` — nuốt lỗi `mark_reminder_sent` sau khi gửi thành công → gửi lặp vô hạn, lẫn với lỗi dữ liệu trong log | High | Accept | Phase 5 |
| 7 | `reset_session()` không `move_to_end()` — phá thứ tự LRU, session vừa reset có thể bị evict trước session rảnh thật | High | Accept | Phase 3 |
| 8 | Chuỗi check→evict→insert trong `get_session()` không atomic (race dưới đa luồng); cap không gắn rate-limit → eviction-DoS | High | Accept (thu hẹp — chỉ thêm `threading.Lock`; KHÔNG thêm rate-limit, đã có mục Medium riêng trong `ISSUES.md`) | Phase 3 |
| 9 | Giả định "1 process" không được enforce ở đâu trong repo (không Procfile/gunicorn config) | Medium | Accept (chỉ ghi chú code, không xây enforcement) | Phase 3, plan.md |

### Whole-Plan Consistency Sweep
- Files reread: plan.md, phase-01, phase-02, phase-03, phase-04, phase-05 (toàn bộ, sau
  khi áp dụng 9 finding).
- Decision deltas checked: 9 (đổi tên biến/cơ chế: `psycopg.errors.UniqueViolation` phân
  biệt theo `constraint_name`; `reset_session` dùng `move_to_end`; thêm
  `threading.Lock`; log tách `[SKIP]`/`[SEND-ERROR]`; pattern C1 dùng `_normalize` +
  `_strip_accents`; Phase 4 chỉ sửa `download_ics` không sửa `book_appointment`).
- Reconciled stale references: 1 (plan.md File Ownership section — sửa mô tả sai về
  Phase 4 đụng `book_appointment`; đồng thời sửa `IntegrityError` → `UniqueViolation` cho
  khớp thuật ngữ psycopg thực tế dùng xuyên suốt Phase 2).
- Unresolved contradictions: 0.

## Acceptance Criteria (toàn plan)

- [x] Cả 5 phase có test mới, fail trước khi sửa, pass sau khi sửa (xác nhận qua báo cáo
  từng subagent — Red state quan sát trước khi Green).
- [x] `pytest tests/ -v` toàn bộ pass — 28 passed, 1 skipped (skip có tài liệu: thiếu
  Postgres local cho test race condition thật, chấp nhận theo phase-02).
- [x] App chạy được không lỗi import/syntax — `python3.10 -c "import app, safety, storage,
  booking, chatbot, reminder_worker, triage"` clean.
- [x] `reminder_worker.py --once` chạy được trên `appointments.json` hiện tại không lỗi —
  verify thủ công, output "Quét 1 lần xong, gửi 0 nhắc."
- [x] `ISSUES.md`: đánh dấu `[x]` cho C1-C5 (không đụng High/Medium/Low).
- [x] Không thay đổi hành vi nghiệp vụ ngoài phạm vi 5 issue — xác nhận qua code review độc
  lập (`code-reviewer` subagent): không rate-limit, không sửa H1 doctor_id semantics, không
  đụng `debug=True`/`SECRET_KEY`.
