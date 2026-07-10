---
phase: 3
title: "Update Getting Started And Roadmap Docs"
status: completed
priority: P2
dependencies: [1]
---

# Phase 3: Cập nhật `docs/getting-started-guide.md`, `docs/project-roadmap.md`,
`docs/project-overview-pdr.md`

## Overview

3 file này đã nằm sẵn trong `docs/`. Sau khi Phase 1 dời `hoc/`→`docs/hoc/` và
`BAOCAO_DANHGIA.md`→`docs/BAOCAO_DANHGIA.md`, một số link trong 3 file này CÓ THỂ đã tự
đúng (coincidental non-change), một số khác (đặc biệt link có `../` đi ra ngoài `docs/`) cần
sửa. Đọc kỹ từng file, không sửa mù.

## Requirements

- Functional: mọi link trong 3 file trỏ tới `hoc/`, `BAOCAO_DANHGIA.md`, `eval/results.md`,
  `eval/rubric.md` phải resolve đúng vị trí thật sau Phase 1.
- Non-functional: không viết lại nội dung ngoài đường dẫn/link.

## Architecture

### `docs/project-roadmap.md`
Link đã xác nhận qua grep trước khi viết plan (dòng có thể lệch, đọc lại để xác nhận):
```
[BAOCAO_DANHGIA.md](../BAOCAO_DANHGIA.md)
```
→ (file giờ là anh em cùng cấp trong `docs/`, bỏ `../`):
```
[BAOCAO_DANHGIA.md](BAOCAO_DANHGIA.md)
```

### `docs/project-overview-pdr.md`
Tương tự — 2 chỗ tham chiếu `../BAOCAO_DANHGIA.md` (dòng ~9, ~54, đọc lại xác nhận số dòng
thật) → bỏ `../`.

### `docs/getting-started-guide.md`
File này chứa NHIỀU link `hoc/...` (khoảng 9-10 chỗ). Trước Phase 1, các link này TRỎ TỚI
`hoc/` Ở GỐC REPO — nhưng vì bản thân `getting-started-guide.md` đã nằm trong `docs/`, một
link dạng `hoc/01-...md` (bare, không `../`) từ trong `docs/` vốn dĩ đã trỏ sai (nhắm tới
`docs/hoc/...` chưa tồn tại) HOẶC dùng `../hoc/...md` (trỏ đúng `hoc/` ở gốc, trước Phase 1).
Đọc lại CHÍNH XÁC dạng hiện tại của từng link trước khi kết luận:
- Nếu đang là `../hoc/01-....md` (đi ra ngoài `docs/` tới `hoc/` gốc) → sau Phase 1, `hoc/`
  gốc không còn, target thật là `docs/hoc/` (anh em cùng cấp) → sửa thành `hoc/01-....md`
  (bỏ `../`).
- Nếu đang là `hoc/01-....md` (bare, không `../`) → TRƯỚC Phase 1 đây là link SAI (trỏ
  `docs/hoc/...` chưa tồn tại) — SAU Phase 1 lại tình cờ ĐÚNG. Không sửa, chỉ verify.
- Đọc thực tế file để biết đang ở dạng nào — không suy đoán.

Cũng có prose mention `eval/results.md` (~dòng 225, đọc lại xác nhận) → sửa thành
`docs/eval/results.md`.

`[Red team — Accept, Finding "Phase 3 undercounts hoc/triage_demo.py mentions"]`
**SỬA SỐ LƯỢNG:** có **2 chỗ** (không phải 1) nhắc `hoc/triage_demo.py` — 1 trong code
block ví dụ lệnh (~dòng 285) và 1 trong prose (~dòng 395). Grep xác nhận số lượng thật
trước khi sửa:
```bash
grep -n "triage_demo" docs/getting-started-guide.md
```
Sửa CẢ 2 chỗ, không chỉ 1. Đây là VÍ DỤ MINH HOẠ quy ước đặt tên file thực hành (không phải
link tới file thật tồn tại) — áp dụng cùng quyết định đã chốt ở Phase 1 Bước 6 (quy ước
"file thực hành nằm cùng thư mục bài học" giờ trỏ `docs/hoc/`): đổi `hoc/triage_demo.py` →
`docs/hoc/triage_demo.py` ở cả 2 chỗ, nhất quán với cách `hoc/01-viet-triage-tu-dau.md` đã
tự sửa quy ước này ở Phase 1.

## Related Code Files

- Modify: `docs/getting-started-guide.md`
- Modify: `docs/project-roadmap.md`
- Modify: `docs/project-overview-pdr.md`

## Implementation Steps

1. `grep -n "hoc/\|BAOCAO_DANHGIA\|eval/results\|eval/rubric" docs/getting-started-guide.md
   docs/project-roadmap.md docs/project-overview-pdr.md` — liệt kê toàn bộ vị trí thật.
2. Đọc từng file bằng `Read`, xác nhận dạng link hiện tại của từng match (có `../` hay
   không) trước khi sửa — không suy đoán theo Architecture section nếu thực tế khác.
3. Sửa `docs/project-roadmap.md`, `docs/project-overview-pdr.md` — bỏ `../` khỏi link
   `BAOCAO_DANHGIA.md`.
4. Sửa `docs/getting-started-guide.md` — với mỗi link `hoc/`, phân loại đúng/sai theo logic
   ở Architecture, chỉ sửa chỗ THỰC SỰ sai. Sửa prose `eval/results.md` →
   `docs/eval/results.md`.
5. Verify: resolve thủ công toàn bộ link đã sửa (và các link tình cờ đúng, không sửa) từ vị
   trí thật của từng file (`docs/`), xác nhận trỏ đúng file tồn tại trên đĩa:
   ```bash
   cd docs && for f in BAOCAO_DANHGIA.md eval/results.md hoc/00-muc-luc.md \
     hoc/01-viet-triage-tu-dau.md; do
     test -f "$f" && echo "OK: $f" || echo "MISSING: $f"
   done
   ```

## Success Criteria

- [x] `docs/project-roadmap.md`, `docs/project-overview-pdr.md`: link `BAOCAO_DANHGIA.md`
  không còn `../` (trỏ đúng anh em cùng cấp).
- [x] `docs/getting-started-guide.md`: toàn bộ link `hoc/...` resolve đúng
  `docs/hoc/...md` thật tồn tại (dù đã sửa hay tình cờ đúng từ trước).
- [x] `docs/getting-started-guide.md`: prose `eval/results.md` → `docs/eval/results.md`.
- [x] Verify bằng lệnh resolve thủ công ở bước 5, không chỉ đọc bằng mắt.
- [x] Không viết lại nội dung nào khác ngoài đường dẫn/link.

## Risk Assessment

- **Rủi ro lớn nhất: kết luận nhầm 1 link là "tình cờ đúng" trong khi thực tế nó vẫn sai**
  (hoặc ngược lại, sửa 1 link vốn đã đúng thành sai) — do dạng link thực tế trong file có
  thể khác giả định trong Architecture section (vd file dùng path tuyệt đối, hoặc mix cả
  2 dạng). BẮT BUỘC đọc thực tế từng dòng trước khi sửa, và verify bằng `test -f` sau khi
  sửa — không tin vào suy đoán trong phase file này.
