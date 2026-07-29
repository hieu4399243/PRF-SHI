---
title: Auth/Structure Hygiene Fixes
description: >-
  Consolidate duplicated JWT auth-check logic, make storage user-functions fail
  loudly without Postgres, restrict self-register role to guest/doctor
status: completed
priority: P2
branch: main
tags:
  - auth
  - hygiene
  - tdd
blockedBy: []
blocks: []
created: '2026-07-29T17:35:08.862Z'
createdBy: 'ck:plan'
source: skill
---

# Auth/Structure Hygiene Fixes

## Overview

3 fix nhỏ, độc lập, phát hiện từ `/ask` structure review + brainstorm (xem
`plans/reports/brainstorm-260730-0028-auth-structure-hygiene-fixes-report.md`):

1. Logic auth-check (cookie → verify JWT → lookup user) bị lặp 6 lần across
   `app/main.py` (4 chỗ: `require_auth`, `login_page`, `admin_page`, `api_me`),
   `app/admin_api.py` (1), `app/doctor_api.py` (1).
2. `app/core/storage.py`: `create_user`/`get_user_by_username`/`get_user_by_id`
   khi không có `DATABASE_URL` — âm thầm trả `True`/`None` (giả thành công)
   thay vì báo lỗi rõ ràng → silent data loss risk.
3. `POST /api/register` cho set `role=admin` từ public request — UI
   (`login.html`) chỉ expose `guest`/`doctor`, backend nên khớp đúng. Ngoài
   ra, `doctor_id` cũng không được validate — self-register có thể mạo danh
   bác sĩ thật (xem Phase 3, mở rộng sau red-team).

**Thứ tự bắt buộc: Phase 1 → Phase 2 → Phase 3.** Phase 1 phải xong trước vì nó
tạo điểm tập trung (`auth.resolve_user_from_token`) mà Phase 2 dựa vào để xử lý
exception mới một cách an toàn (xem Phase 2 § Risk Assessment).

**TDD:** mỗi phase viết test thất bại trước (dùng `assert` thật, không phải
`print`-style như `test_auth_demo.py` cũ), rồi implement tới khi xanh.

**Baseline (đã verify trước khi lập plan, môi trường không có `DATABASE_URL`):**
`175 passed, 4 failed, 1 skipped`. 4 fail đã tồn tại từ trước, KHÔNG liên quan
plan này — đừng cố sửa chúng ở đây:
- `test_app_admin.py::test_admin_accepts_with_jwt_cookie` — cần Postgres thật
  đã seed (`scripts/seed_users.py`), fail vì môi trường không có DB.
- `test_app_hardening.py::test_rate_limit_applies_to_admin_routes` — cùng
  nguyên nhân (gọi `_login_admin`).
- `test_chatbot_flex.py::test_quay_lai_tu_buoc_chon_gio` — chatbot flow, không
  liên quan auth.
- `test_chatbot_flex.py::test_parser_ngay_giu_dau_gach_cheo` — phụ thuộc ngày
  hiện tại (rolling date window), không liên quan auth.

Chạy test bằng: `python3.12 -m pip install --target /tmp/shi-pydeps -r
requirements-dev.txt && PYTHONPATH=/tmp/shi-pydeps python3.12 -m pytest
tests/ -q` (máy local Python 3.14 không có wheel `psycopg-binary==3.2.3` —
dùng python3.12 tránh lỗi cài đặt không liên quan).

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [Extract Auth Helper](./phase-01-extract-auth-helper.md) | Completed |
| 2 | [Fail-Loud Storage Guards](./phase-02-fail-loud-storage-guards.md) | Completed |
| 3 | [Restrict Self-Register Role](./phase-03-restrict-self-register-role.md) | Completed |

## Dependencies

Sequential: Phase 2 `blockedBy` Phase 1, Phase 3 `blockedBy` Phase 2 (nội bộ
plan, không phải cross-plan frontmatter — không có plan nào khác trong repo
đang active).

## Red Team Review

### Session — 2026-07-30
**Findings:** 9 sau dedupe từ 3 reviewer (Security Adversary, Assumption
Destroyer, Failure Mode Analyst) — 21 finding thô trước dedupe.
**Severity breakdown:** 3 Critical, 1 High, 5 Medium

| # | Finding | Severity | Disposition | Applied To |
|---|---------|----------|-------------|------------|
| 1 | `resolve_user_from_token` chỉ bắt `AuthError` — hẹp hơn code cũ, lỗi bất ngờ văng 500 thay vì graceful | Critical | Accept | Completed |
| 2 | Helper gộp 401 (token invalid) và 404 (user không tồn tại) — mất phân biệt status code | Critical | Accept (modified — user chọn "chấp nhận gộp thành 401", ghi rõ là thay đổi contract có chủ đích) | Completed |
| 3 | Phase 3 chỉ chặn `role=admin`, không validate `doctor_id` — self-register có thể mạo danh bác sĩ thật | Critical | Accept (modified — user chọn "mở rộng Phase 3", không tách plan riêng) | Completed |
| 4 | Con số "7 call site → 1" sai; thực tế 6 → 0 | High | Accept | Phase 1 |
| 5 | `UserStoreUnavailableError` message lộ "DATABASE_URL"/"Postgres" qua public endpoint | Medium | Accept | Phase 2 |
| 6 | `plan.md` ghi sai tên hàm `resolve_request_user` (đúng: `resolve_user_from_token`) | Medium | Accept | plan.md (Overview, sửa trực tiếp) |
| 7 | `create_user_account`'s broad except có thể bọc `UserStoreUnavailableError` thành `AuthError` chung | Medium | Accept | Phase 2 |
| 8 | Phase 3 mô tả sai "role rỗng → mặc định guest" (code chỉ default khi thiếu key) | Medium | Accept | Phase 3 |
| 9 | Rollback risk: Phase 2 sửa file của Phase 1, chưa ghi chú thứ tự revert | Medium | Accept | Phase 2 |

**User quyết định 2 finding có trade-off thật** (đã hỏi qua `AskUserQuestion`
trước khi apply):
- Finding #2: chấp nhận gộp 401/404 (đơn giản hơn, không có test khóa hành
  vi cũ, case hiếm).
- Finding #3: mở rộng scope Phase 3 ngay (validate `doctor_id` khớp catalog +
  chưa bị claim) thay vì tách thành plan riêng — vá lỗ hổng thật ngay trong
  lần này.

### Whole-Plan Consistency Sweep
- Files reread: `plan.md`, `phase-01-extract-auth-helper.md`,
  `phase-02-fail-loud-storage-guards.md`, `phase-03-restrict-self-register-role.md`.
- Decision deltas checked: 9 (bảng trên) + 1 phát sinh khi sweep — phase-03
  bản nháp trước red-team ghi "Không phụ thuộc Phase 1/2 — độc lập", mâu
  thuẫn với `plan.md`'s "Thứ tự bắt buộc: Phase 1 → Phase 2 → Phase 3" đã có
  từ đầu. Đã sửa: `phase-03`'s frontmatter `dependencies: [2]`, phần Overview
  giải thích rõ lý do phụ thuộc mới (doctor_id uniqueness check cần DB, dùng
  chung convention `UserStoreUnavailableError` của Phase 2).
- Reconciled stale references: tên hàm (`resolve_request_user` →
  `resolve_user_from_token`, 1 chỗ ở `plan.md`), số liệu call-site (7/1 → 6/0,
  4 chỗ across `plan.md` + `phase-01`), mô tả role-default (Phase 3), risk
  note "doctor_id giả — chấp nhận" trong Phase 3 (đã thay bằng risk mới, thấp
  hơn, sau khi validate: chỉ còn TOCTOU race hiếm khi 2 request đồng thời).
- Unresolved contradictions: 0.
