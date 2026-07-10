---
phase: 2
title: "Update Docs And Cross References"
status: completed
priority: P2
dependencies: [1]
---

# Phase 2: Cập nhật docs/README tham chiếu path dữ liệu mới

## Overview

Sau khi Phase 1 dời data file vào `app/data/`, sửa toàn bộ prose/mention trong docs và
README trỏ tới vị trí cũ (`app/appointments.json`, `app/device_tokens.json`,
`app/audit_log.jsonl`, `app/outbox/`).

## Requirements

- Functional: mọi mention path trong các file liệt kê dưới đây phản ánh đúng vị trí mới
  `app/data/...`.
- Non-functional: chỉ sửa path/prose liên quan, KHÔNG viết lại nội dung giảng dạy trong
  `docs/hoc/` ngoài phạm vi cần thiết.

## Architecture

### Danh sách file cần đọc lại + sửa (xác nhận qua scout, số dòng có thể lệch — đọc thật)

- `README.md:36,96,97`
- `docs/codebase-summary.md:63`
- `docs/system-architecture.md:65`
- `docs/database-storage-guide.md:7`
- `docs/getting-started-guide.md:100,216,298,378`
- `docs/BAOCAO_DOAN.md:166,282-284`
  `[Red team — Accept, Finding "docs/BAOCAO_DOAN.md:198 false-positive scope line"]`
  (KHÔNG bao gồm dòng 198 — đọc lại xác nhận đây là prose chung "JSONL — audit log, outbox
  push, dataset đánh giá", không có path cụ thể nào để sửa. Bỏ khỏi checklist thao tác.)
- `docs/BAOCAO_DANHGIA.md:173`
- `docs/project-roadmap.md:9`
- `docs/eval/rubric.md:25`
- `scripts/migrate_to_supabase.py:2`
  `[Red team — Accept, Finding "scripts/migrate_to_supabase.py docstring omitted"]`
  (docstring nhắc `appointments.json, device_tokens.json` bare — code đã dùng đúng
  `storage.APPOINTMENTS_PATH`/`TOKENS_PATH`, không cần đổi, CHỈ sửa docstring cho nhất quán.)
- `mobile/README.md:42`
  `[Red team — Accept, Finding "mobile/README.md baseline mischaracterized"]`
  **LƯU Ý ĐÃ SỬA (2 reviewer độc lập cùng bắt):** text hiện tại `../outbox/push_outbox.jsonl`
  KHÔNG PHẢI "đúng nhưng cần tính lại độ sâu" như draft ban đầu — nó ĐÃ SAI TỪ TRƯỚC (thiếu
  segment `app/`, resolve nhầm tới `<gốc repo>/outbox/...` không tồn tại, vì `mobile/` và
  `app/` là 2 thư mục ANH EM ở gốc repo, không phải cha-con). Đây là bug có sẵn, không phải
  do plan này gây ra. Target đúng SAU khi dời:
  `../app/data/outbox/push_outbox.jsonl` (1 cấp `../` từ `mobile/` ra gốc repo, rồi vào
  `app/data/outbox/`).
- `app/booking.py:5` — docstring prose (không phải import), sửa nếu nhắc path file cũ.

### Ngoại lệ cần đánh giá riêng (KHÔNG sửa mù)

- `docs/hoc/05-push.md`, `docs/hoc/08-storage-calendar-reminder.md` — đọc kỹ: nếu mention
  path là VÍ DỤ MINH HOẠ trong code block giảng dạy (không phải path thật học viên sẽ mở),
  cân nhắc để nguyên hoặc chỉ sửa tối thiểu cho nhất quán. Nếu mention path THẬT (hướng dẫn
  học viên mở đúng file trên đĩa để xem), PHẢI sửa thành `app/data/...`.

## Related Code Files

- Modify: `README.md`, `docs/codebase-summary.md`, `docs/system-architecture.md`,
  `docs/database-storage-guide.md`, `docs/getting-started-guide.md`, `docs/BAOCAO_DOAN.md`
  (dòng 166, 282-284 — KHÔNG dòng 198), `docs/BAOCAO_DANHGIA.md`, `docs/project-roadmap.md`,
  `docs/eval/rubric.md`, `mobile/README.md`, `app/booking.py` (docstring only),
  `scripts/migrate_to_supabase.py` (docstring only)
- Modify (đánh giá riêng, có thể không cần sửa): `docs/hoc/05-push.md`,
  `docs/hoc/08-storage-calendar-reminder.md`

## Implementation Steps

1. Grep xác nhận vị trí thật trước khi sửa:
   ```bash
   grep -rn "appointments.json\|device_tokens.json\|audit_log.jsonl\|outbox/push_outbox" \
     README.md docs/ mobile/README.md app/booking.py scripts/migrate_to_supabase.py
   ```
2. Đọc từng file, phân loại: path thật cần sửa vs ví dụ minh hoạ giảng dạy (xem Architecture
   "Ngoại lệ").
3. Sửa từng file — chỉ path, không viết lại nội dung khác.
4. `mobile/README.md`: tính lại đúng số cấp `../` (đọc cấu trúc thư mục thật, không suy
   đoán).
5. Verify: với mỗi path đã sửa, `test -f` (từ vị trí file chứa nó) xác nhận trỏ đúng file
   thật tồn tại trên đĩa.

## Success Criteria

- [x] Toàn bộ file liệt kê ở Architecture (11 file gốc + `scripts/migrate_to_supabase.py`
  bổ sung, trừ `docs/BAOCAO_DOAN.md:198` đã loại) đã đọc lại và xử lý (sửa hoặc xác nhận
  không cần sửa với lý do rõ ràng).
- [x] `mobile/README.md` sửa thành `../app/data/outbox/push_outbox.jsonl` (không phải chỉ
  "tính lại độ sâu" từ bản gốc đã sai — xem Architecture).
- [x] `scripts/migrate_to_supabase.py` docstring đã cập nhật (code không cần đổi).
- [x] Mọi path đã sửa verify resolve đúng file thật (test -f thủ công).
- [x] `docs/hoc/05-push.md`, `docs/hoc/08-storage-calendar-reminder.md` đã đánh giá riêng
  (không sửa mù theo pattern chung).
- [x] Không viết lại nội dung nào khác ngoài path.

## Risk Assessment

- **Nhầm ví dụ minh hoạ giảng dạy với path thật** ở 2 file `hoc/` — đọc ngữ cảnh câu văn
  trước khi quyết định, không áp dụng máy móc find-replace.
- **Tính sai độ sâu `../` ở `mobile/README.md`** — đây là file DUY NHẤT ở ngoài `app/`/
  `docs/` tham chiếu path này, dễ bị tính nhầm nếu không đọc cấu trúc thư mục thật.
