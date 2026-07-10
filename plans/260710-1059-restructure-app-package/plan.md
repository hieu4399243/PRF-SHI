---
title: "Restructure repo: move backend into app/ package"
description: "Dời 10 file .py logic nghiệp vụ (+ templates/ + data files) từ gốc repo vào package app/, cập nhật toàn bộ import/entry-command/tài liệu liên quan."
status: completed
priority: P2
branch: "main"
tags: ["restructure", "tdd"]
blockedBy: []
blocks: []
created: "2026-07-10T03:59:25.962Z"
createdBy: "ck:plan"
source: skill
---

# Restructure repo: move backend into app/ package

## Overview

Repo hiện có 10 file `.py` logic nghiệp vụ (2748 dòng) nằm PHẲNG ở gốc repo, không có
package Python nào — không "chuyên nghiệp" theo chuẩn dự án Flask thông thường. Plan này
dời toàn bộ vào package `app/`, giữ nguyên 100% hành vi (không đổi API, không đổi business
logic), chỉ đổi VỊ TRÍ FILE + IMPORT + LỆNH CHẠY.

**Quyết định đã chốt với user:**
1. Tên package: **`app/`**.
2. `hoc/*.md` (10 bài học từng bước): **cập nhật đường dẫn file trong cả 10 bài**, KHÔNG viết
   lại nội dung giảng dạy.

## 10 file di chuyển vào `app/`

`app.py`, `booking.py`, `calendar_ics.py`, `chatbot.py`, `data.py`, `push.py`,
`reminder_worker.py`, `safety.py`, `storage.py`, `triage.py` — giữ NGUYÊN TÊN FILE (không
đổi tên, vd KHÔNG đổi `app.py` → `server.py`, dù `app/app.py` hơi lặp tên — quyết định giữ
tên cũ để khớp với `hoc/07-app.md` đang dạy đúng tên file này, tránh gây nhầm giữa tên
chương học và tên file thật).

## 2 rủi ro kỹ thuật ẩn đã phát hiện qua scout (PHẢI xử lý, không phải optional)

1. **`Flask(__name__)` tự suy ra `templates/` theo vị trí file `app.py`.** Nếu dời `app.py`
   vào `app/` mà KHÔNG dời `templates/` theo, mọi `render_template("index.html")`/
   `render_template("admin.html")` sẽ lỗi (Flask tìm `app/templates/`, không tìm thấy).
   **Fix: dời `templates/` → `app/templates/` cùng lúc.**
2. **`storage.py`/`safety.py`/`push.py` dùng `os.path.dirname(__file__)` để định vị
   `appointments.json`/`device_tokens.json`/`audit_log.jsonl`/`outbox/`.** Nếu dời code mà
   KHÔNG dời data files theo, app sẽ ÂM THẦM tạo file dữ liệu MỚI RỖNG bên trong `app/`, mất
   hết dữ liệu cũ, KHÔNG báo lỗi gì (silent data loss — nguy hiểm hơn cả lỗi 500).
   **Fix: dời 4 thứ này (`appointments.json`, `device_tokens.json`, `audit_log.jsonl`,
   `outbox/`) vào `app/` cùng code — giữ nguyên logic `os.path.dirname(__file__)` không cần
   sửa gì, vì quan hệ tương đối giữa code và data không đổi.**

## Cách chạy sau khi restructure (đổi so với trước)

- Web server: `python app.py` → **`python -m app.app`**
- Worker nhắc lịch: `python reminder_worker.py --watch` → **`python -m app.reminder_worker --watch`**
- Deploy: `gunicorn app:app` → **`gunicorn app.app:app`**
- Eval: `python eval/evaluate.py` — KHÔNG đổi lệnh (đã dùng `sys.path.insert` để import từ
  gốc, chỉ đổi NỘI DUNG import bên trong file, xem Phase 3).
- Scripts: `python scripts/clean_stale_appointments.py` — KHÔNG đổi lệnh, tương tự.

## Phases

| Phase | Name | Phụ thuộc | File(s) touched | Status |
|-------|------|-----------|------------------|--------|
| 1 | [Package Skeleton And Core Move](./phase-01-package-skeleton-and-core-move.md) | Không | 10 file `.py` + `templates/` + 4 data file → `app/` (di chuyển + sửa import nội bộ) | Completed |
| 2 | [Update Test Suite Imports](./phase-02-update-test-suite-imports.md) | Phase 1 | `tests/*.py` (14 file test + `conftest.py`) | Completed |
| 3 | [Update Eval And Scripts Imports](./phase-03-update-eval-and-scripts-imports.md) | Phase 1 | `eval/evaluate.py`, `scripts/*.py` | Completed |
| 4 | [Update Root Docs And Entry Commands](./phase-04-update-root-docs-and-entry-commands.md) | Phase 1 | `README.md`, `setup.sh`, `docs/*.md`, `.env.example`, `BAOCAO_DOAN.md`, `BAOCAO_DANHGIA.md` | Completed |
| 5 | [Update Hoc Chapter Paths](./phase-05-update-hoc-chapter-paths.md) | Phase 1 | `hoc/*.md` (10 file) | Completed |

**Phase 1 PHẢI xong trước — Phase 2, 3, 4, 5 chạy song song sau đó** (đều phụ thuộc package
`app/` đã tồn tại, nhưng không đụng file của nhau: tests/ vs eval+scripts vs docs+README vs
hoc/ — 4 nhóm file hoàn toàn tách biệt).

## Test Infrastructure (TDD cho một pure-refactor)

Đây là thuần tái cấu trúc (không có hành vi mới) — 93 test (92 passed + 1 skipped) đã có từ
3 vòng fix trước ĐÃ LÀ bộ hồi quy đầy đủ cho hành vi hiện tại. Áp dụng TDD đúng tinh thần
cho refactor: **Red** = xác nhận baseline (92 passed, 1 skipped TRƯỚC khi đổi gì), **Green**
= sau khi dời + sửa import xong, CHẠY LẠI TOÀN BỘ SUITE, phải pass 100% giống hệt baseline
(không viết test mới — không có hành vi mới để test). Interpreter: `python3.10` (đã xác nhận
từ 3 vòng trước có đủ flask/psycopg/dotenv/pytest).

## Red Team Review

### Session — 2026-07-10
**Findings:** 10 unique sau dedupe (từ 3 reviewer: Security Adversary/Fact Checker,
Failure Mode Analyst/Flow Tracer, Assumption Destroyer/Scope Auditor — 1 finding Critical
(`scripts/migrate_to_supabase.py` tự tính path riêng) được CẢ 3 reviewer độc lập cùng bắt).
**Severity breakdown:** 2 Critical, 2 High, 6 Medium.
**Kết quả:** Tất cả 10 finding Accept, không finding nào bị reject.

| # | Finding | Severity | Disposition | Applied To |
|---|---------|----------|-------------|------------|
| 1 | `migrate_to_supabase.py` tự tính `APPTS`/`TOKENS` độc lập với `storage.py`, `os.path.exists()` guard làm âm thầm coi như "0 bản ghi" | Critical | Accept | Phase 3 |
| 2 | Grep Success Criteria Phase 1 chỉ khớp `^import`, mù trước `^from X import Y` — đúng loại rủi ro Phase 1 tự gọi "lớn nhất" | Critical | Accept | Phase 1 |
| 3 | `BAOCAO_DOAN.md`/`BAOCAO_DANHGIA.md` (báo cáo chấm điểm) có sơ đồ thư mục/đường dẫn gốc, không thuộc phạm vi phase nào | High | Accept | Phase 4 |
| 4 | Phase 2 chỉ mẫu hoá import CÓ alias, bỏ sót 2 file test dùng import KHÔNG alias | High | Accept | Phase 2 |
| 5 | Kiểm tra toàn vẹn data Phase 1 chỉ "len > 0" bằng mắt, không so khớp chính xác | Medium | Accept | Phase 1 |
| 6 | `git mv outbox` chỉ dời file đã track, file chưa track (nếu có) bị bỏ lại | Medium | Accept | Phase 1 |
| 7 | `.env.example` chỉ kiểm bằng grep, không đọc toàn bộ như `setup.sh` | Medium | Accept | Phase 4 |
| 8 | Phase 5 không có bước THỰC SỰ chạy lệnh trong hoc/*.md, chỉ đọc lại bằng mắt | Medium | Accept | Phase 5 |
| 9 | Grep checklist Phase 4 không bao gồm tên data file — README mục "File sinh ra khi chạy" sai vị trí âm thầm | Medium | Accept | Phase 4 |
| 10 | Phase 4 không có bước kiểm tra ngược (bắt sót — under-correction) | Medium | Accept | Phase 4 |

### Whole-Plan Consistency Sweep
- Files reread: plan.md, phase-01 đến phase-05 (toàn bộ, sau khi áp dụng 10 finding).
- Decision deltas checked: 10 (grep Phase 1 mở rộng khớp `from`; baseline data-count chính
  xác thay vì `len>0`; kiểm tra `git status --ignored` cho outbox; 2 nhóm import
  alias/non-alias ở Phase 2; `migrate_to_supabase.py` dùng lại `storage.APPOINTMENTS_PATH`/
  `TOKENS_PATH` thay vì tự tính; `BAOCAO_*.md` thêm vào Phase 4; `.env.example` đọc toàn bộ;
  grep Phase 4 thêm tên data file; bước hậu-kiểm Phase 4; bước chạy lệnh thật Phase 5).
- Reconciled stale references: 2 (plan.md ghi sai "98 test" — sửa thành "93 test (92
  passed + 1 skipped)" khớp số liệu dùng xuyên suốt các phase; bảng Phase 4 trong plan.md
  thiếu `BAOCAO_*.md` trong cột File(s) touched — đã thêm).
- Unresolved contradictions: 0.

## Dependencies

Không phụ thuộc plan khác đang mở. Không blocked bởi plan nào trong `plans/`.

## Acceptance Criteria (toàn plan)

- [x] `python3.10 -m pytest tests/ -v` pass 100% giống hệt baseline (92 passed, 1 skipped)
  SAU khi restructure — không có test nào bị xoá/sửa nội dung assert, chỉ sửa import. Xác
  nhận qua code review độc lập (diff line-by-line từng file so với `HEAD`, không chỉ tin
  "renamed" trong `git status`).
- [x] `python3.10 -m app.app` khởi động được, in đúng dòng `[storage] Chế độ lưu trữ:
  file JSON (local)`, không lỗi import/template — xác nhận qua `curl` HTTP 200 thật.
- [x] `python3.10 -m app.reminder_worker --once` chạy được, đọc đúng `appointments.json`
  hiện có (không tạo file rỗng mới) — số lượng lịch hẹn khớp CHÍNH XÁC baseline (11).
- [x] `python3.10 eval/evaluate.py` chạy được (dùng `python3.10` thay vì `./.venv/bin/python`
  vì môi trường này không có `.venv`, xem Test Infrastructure).
- [x] `README.md`, `setup.sh`, `docs/*.md`, `hoc/*.md` không còn tham chiếu đường dẫn file cũ
  — 1 chỗ sót thật (`hoc/09-admin.md`, red-team's Phase 5 implementer báo nhầm "không cần
  sửa") được code review độc lập bắt và đã fix.
- [x] KHÔNG đổi bất kỳ hành vi nghiệp vụ nào — code review độc lập diff từng file xác nhận
  CHỈ đổi dòng import, không đổi logic.
- [x] `git mv` được dùng cho các thao tác di chuyển file (giữ lịch sử git) — `git status`
  xác nhận toàn bộ hiển thị `renamed:`/`R`/`RM`, không phải `deleted:`+`new file:` tách rời.
