---
phase: 2
title: "Update README And Codebase Summary"
status: completed
priority: P2
dependencies: [1]
---

# Phase 2: Cập nhật `README.md` và `docs/codebase-summary.md`

## Overview

`README.md` ở lại gốc nhưng nhiều mục nó tham chiếu (`hoc/`, `BAOCAO_DANHGIA.md`,
`eval/results.md`, `eval/rubric.md`) đã dời sang `docs/` ở Phase 1 — cập nhật link/prose cho
khớp. `docs/codebase-summary.md` đã Ở SẴN trong `docs/` — chỉ cần VERIFY, không mù sửa.

## Requirements

- Functional: mọi link/prose trong `README.md` trỏ tới file đã dời phải resolve đúng vị trí
  mới. `docs/codebase-summary.md` không còn tham chiếu sai vị trí cũ.
- Non-functional: `README.md` KHÔNG đổi vị trí (vẫn ở gốc). Không viết lại nội dung ngoài
  phần link/đường dẫn.

## Architecture

### Bước 1 — Đọc lại toàn bộ `README.md`
Grep các từ khoá sau để tìm CHÍNH XÁC vị trí hiện tại (số dòng có thể lệch so với lần scout
trước do các round sửa trước đó):
```bash
grep -n "hoc/\|BAOCAO_DANHGIA\|BAOCAO_DOAN\|eval/results\|eval/rubric" README.md
```
Với mỗi match, xác định loại tham chiếu và sửa:
- Link `[...](hoc/...)` hoặc `[...](./hoc/...)` → `docs/hoc/...`
- Link `[...](BAOCAO_DANHGIA.md)` → `docs/BAOCAO_DANHGIA.md`
- Link `[...](BAOCAO_DOAN.md)` → `docs/BAOCAO_DOAN.md`
- Prose mention `eval/results.md` (không phải link, mô tả "chạy xong sẽ ghi vào...") →
  `docs/eval/results.md`
- Prose mention `eval/rubric.md` → `docs/eval/rubric.md`
- Lệnh chạy thật (vd `python eval/evaluate.py`) — KHÔNG đổi, vì `evaluate.py` không di
  chuyển, chỉ output của nó di chuyển (đã xử lý ở Phase 1).

`[Red team — Accept, Finding "README.md:87 mixed command+comment line"]`
**LƯU Ý riêng:** dòng lệnh dạng `./.venv/bin/python eval/evaluate.py   # ... → ghi
eval/results.md` gộp CẢ lệnh chạy thật (không đổi) VÀ path output trong comment (PHẢI đổi
thành `docs/eval/results.md`) trên CÙNG 1 DÒNG — dễ bị bỏ sót nếu áp dụng máy móc quy tắc
"lệnh chạy thật không đổi" cho toàn bộ dòng. Đọc kỹ, chỉ sửa phần comment sau `#`, giữ
nguyên phần lệnh trước đó.

### Bước 2 — Đọc lại toàn bộ `docs/codebase-summary.md`
File này đã nằm trong `docs/`, nên các mention `hoc/`, `eval/rubric.md`, `eval/results.md`,
`BAOCAO_DOAN.md`, `BAOCAO_DANHGIA.md` — NẾU đang viết dạng bare/relative (không có `../`) —
CÓ THỂ đã "tình cờ đúng" sau khi các file đó dời vào `docs/` (coincidental non-change, xem
plan.md phần "Link nội bộ..."). Đọc CHÍNH XÁC từng chỗ, phân loại:
- Nếu ghi `hoc/00-muc-luc.md` (bare, không `../`) và file này đang Ở TRONG `docs/` → sau khi
  `hoc/` dời thành `docs/hoc/`, path này ĐÃ ĐÚNG, không sửa.
- Nếu ghi `../hoc/...` hoặc `../BAOCAO_DANHGIA.md` (có `../` đi ra ngoài `docs/`) → SAI sau
  khi dời (target giờ là anh em cùng cấp), phải bỏ `../`.
- Nếu là bảng liệt kê cấu trúc thư mục cũ (vd liệt kê `hoc/`, `eval/` ở gốc repo như 1 phần
  mô tả kiến trúc tổng thể, không phải markdown link) → sửa prose cho khớp cấu trúc mới.

## Related Code Files

- Modify: `README.md`
- Modify: `docs/codebase-summary.md`

## Implementation Steps

1. `grep -n "hoc/\|BAOCAO_DANHGIA\|BAOCAO_DOAN\|eval/results\|eval/rubric" README.md
   docs/codebase-summary.md` — liệt kê TOÀN BỘ vị trí cần xét trước khi sửa bất kỳ dòng nào.
2. Đọc từng match bằng `Read` (không suy đoán từ grep snippet), phân loại theo Bước 1/2
   (Architecture) ở trên.
3. Sửa `README.md` — chỉ đường dẫn/link, giữ nguyên câu chữ khác.
4. Sửa `docs/codebase-summary.md` — chỉ những chỗ THỰC SỰ sai (có `../` đi ra ngoài `docs/`
   hoặc liệt kê cấu trúc thư mục cũ), KHÔNG sửa những chỗ đã tình cờ đúng.
5. Verify: với mỗi link vừa sửa, resolve thủ công từ vị trí file (README.md ở gốc,
   codebase-summary.md ở `docs/`) xác nhận trỏ đúng file thật tồn tại trên đĩa.

## Success Criteria

- [x] `README.md` không còn link/prose trỏ `hoc/`, `BAOCAO_DANHGIA.md`, `BAOCAO_DOAN.md`,
  `eval/results.md`, `eval/rubric.md` ở vị trí cũ — tất cả trỏ `docs/...`. (Sau code review
  độc lập, sửa thêm dòng 43 — `rubric.md` bare → `docs/eval/rubric.md`.)
- [x] `docs/codebase-summary.md` không còn `../hoc/`, `../BAOCAO_DANHGIA.md`,
  `../BAOCAO_DOAN.md` kiểu đi ra ngoài `docs/` một cách sai lệch. (Sau code review độc lập,
  sửa thêm dòng 54 — `results.md` bare → `docs/eval/results.md`.)
- [x] Mọi link đã sửa verify resolve đúng file thật (test -f thủ công).
- [x] `README.md` vẫn ở gốc repo (không bị `git mv`).
- [x] Không đổi nội dung nào khác ngoài đường dẫn/link.

## Risk Assessment

- **Sửa nhầm "coincidental non-change" thành sai** — rủi ro chính ở `codebase-summary.md`
  (đã nằm trong `docs/`, một số path đã tự đúng). Đọc kỹ, không mù thay thế theo pattern
  cứng nhắc.
- **Bỏ sót mention dạng prose (không phải markdown link `[]()`)** — grep từ khoá bao gồm cả
  chuỗi bare (vd `eval/results.md` không trong `[]()`) để không bỏ sót câu mô tả thường.
