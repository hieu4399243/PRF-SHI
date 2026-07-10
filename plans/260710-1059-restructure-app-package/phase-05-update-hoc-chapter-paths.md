---
phase: 5
title: "Update Hoc Chapter Paths"
status: pending
priority: P3
dependencies: [1]
---

# Phase 5: Cập nhật đường dẫn file trong `hoc/*.md` (10 bài học)

## Overview

`hoc/` là 10 bài học từng bước hướng dẫn dựng từng file (`hoc/01-viet-triage-tu-dau.md` →
`triage.py`, `hoc/02-data.md` → `data.py`, v.v.), hiện dạy "tạo file X.py ở thư mục gốc dự
án". Sau Phase 1, các file này nằm trong `app/`. Theo quyết định user: **CHỈ cập nhật đường
dẫn file được nhắc tới trong bài, KHÔNG viết lại nội dung giảng dạy** (giữ nguyên cách giải
thích khái niệm, code mẫu, thứ tự các bước dạy).

**PHỤ THUỘC Phase 1**: cần biết chính xác cấu trúc mới trước khi sửa đường dẫn.

## Requirements

- Functional: mọi câu trong `hoc/*.md` nói "tạo file `X.py`" / "mở file `X.py`" / lệnh
  `python X.py` để chạy thử phải trỏ đúng `app/X.py` / `python -m app.X`.
- Non-functional: KHÔNG đổi nội dung sư phạm (giải thích khái niệm, ví dụ minh hoạ, bài tập
  — nếu có). Đây là sửa ĐƯỜNG DẪN, không phải viết lại bài giảng.

## Architecture

Ánh xạ 10 bài học ↔ file (đã xác nhận qua `ls hoc/`, tên bài không nhất thiết khớp 1-1 tên
file — đọc từng bài để xác nhận file nào bài đó thực sự nói tới trước khi sửa):

| File bài học | File code liên quan (dự đoán từ tên bài — XÁC NHẬN LẠI khi đọc) |
|---|---|
| `hoc/00-muc-luc.md` | Mục lục — có thể liệt kê tên file các bài khác, cần rà theo |
| `hoc/01-viet-triage-tu-dau.md` | `triage.py` → `app/triage.py` |
| `hoc/02-data.md` | `data.py` → `app/data.py` |
| `hoc/03-safety.md` | `safety.py` → `app/safety.py` |
| `hoc/04-booking.md` | `booking.py` → `app/booking.py` |
| `hoc/05-push.md` | `push.py` → `app/push.py` |
| `hoc/06-chatbot.md` | `chatbot.py` → `app/chatbot.py` |
| `hoc/07-app.md` | `app.py` → `app/app.py`, lệnh chạy `python app.py` → `python -m app.app` |
| `hoc/08-storage-calendar-reminder.md` | `storage.py`, `calendar_ics.py`,
  `reminder_worker.py` → `app/storage.py`, `app/calendar_ics.py`, `app/reminder_worker.py`,
  lệnh `python reminder_worker.py ...` → `python -m app.reminder_worker ...` |
| `hoc/09-admin.md` | Có thể liên quan `app.py`/`templates/admin.html` → xác nhận khi đọc,
  `templates/admin.html` → `app/templates/admin.html` nếu có nhắc |

## Related Code Files

- Modify: `hoc/00-muc-luc.md` đến `hoc/09-admin.md` (10 file) — CHỈ những file thực sự có
  tham chiếu đường dẫn cần sửa (đọc từng file để xác nhận, không sửa mù theo bảng trên nếu
  đọc thấy không khớp)

## Implementation Steps

1. **Đọc TỪNG file `hoc/*.md`** (10 file, theo thứ tự 00→09) — xác nhận đúng file code nào
   bài đó thực sự nhắc tới (bảng Architecture chỉ là dự đoán ban đầu từ tên bài, KHÔNG phải
   sự thật tuyệt đối — vd `hoc/08-storage-calendar-reminder.md` có thể gộp cả 3 file hoặc
   chỉ 1-2, đọc mới biết chắc).
2. Grep trong mỗi file để tìm chính xác các chỗ nhắc đường dẫn/lệnh chạy:
   ```bash
   grep -n "\.py\b\|python [a-z_]*\.py\|templates/" hoc/0X-ten-bai.md
   ```
3. Với mỗi match, XÁC NHẬN đây là tham chiếu ĐƯỜNG DẪN THẬT (cần sửa) hay chỉ là tên biến/
   khái niệm trong văn bản giải thích (KHÔNG sửa) — vd câu "file `triage.py` chứa hàm
   `classify_symptoms`" là tham chiếu đường dẫn thật (sửa thành `app/triage.py`), nhưng câu
   giải thích khái niệm dùng từ "triage" không kèm `.py` thì không liên quan.
4. Sửa CHỈ phần đường dẫn/lệnh chạy, giữ nguyên 100% câu chữ giảng dạy còn lại xung quanh.
5. Sau khi sửa cả 10 file, đọc lướt lại toàn bộ `hoc/00-muc-luc.md` (mục lục) để xác nhận
   không có đường dẫn nào sai sót còn sót lại.
6. **[Red team — Accept, Finding "không có bước THỰC SỰ chạy lệnh trong hoc/*.md để xác
   nhận, chỉ đọc lại bằng mắt"]** Sau khi sửa `hoc/07-app.md` và
   `hoc/08-storage-calendar-reminder.md` (2 bài có lệnh chạy thực thi, khác các bài chỉ dạy
   viết code), CHẠY THẬT các lệnh vừa sửa (không chỉ đọc lại bằng mắt):
   ```bash
   python3.10 -m app.app &          # từ hoc/07-app.md, chạy nền
   sleep 1 && curl -sf http://127.0.0.1:5001/ > /dev/null && echo "OK: app.py chạy đúng"
   kill %1
   python3.10 -m app.reminder_worker --once   # từ hoc/08-storage-calendar-reminder.md
   ```
   Nếu lệnh trong bài học không khớp CHÍNH XÁC với lệnh chạy thật (typo, thiếu `-m`, sai tên
   module), sửa lại bài học cho khớp — không chỉ tin vào việc đọc lại bằng mắt.

## Success Criteria

- [ ] Cả 10 file `hoc/*.md` đã rà soát (đọc thật, không suy đoán).
- [ ] Mọi đường dẫn file `.py`/lệnh chạy được nhắc trong bài đã cập nhật sang `app/` /
  `python -m app.X`.
- [ ] Nội dung giảng dạy (giải thích khái niệm, code mẫu, thứ tự bước dạy) giữ nguyên
  100% — chỉ đường dẫn/lệnh thay đổi.
- [ ] `hoc/00-muc-luc.md` không còn đường dẫn lỗi thời nếu có liệt kê đường dẫn file.
- [ ] Lệnh chạy trong `hoc/07-app.md`/`hoc/08-storage-calendar-reminder.md` đã CHẠY THẬT
  (không chỉ đọc lại), khớp chính xác với lệnh thực thi thành công.

## Risk Assessment

- **Sửa nhầm thành viết lại nội dung sư phạm thay vì chỉ sửa đường dẫn** — nếu không cẩn
  thận, dễ "tiện tay" diễn đạt lại câu văn khi sửa đường dẫn trong câu đó. PHẢI giữ nguyên
  cấu trúc câu, chỉ thay cụm đường dẫn/lệnh, đúng theo quyết định user (không viết lại nội
  dung).
- **10 file học liệu KHÔNG có test tự động kiểm tra tính đúng đắn** (khác các phase code) —
  verify CHỈ có thể làm bằng đọc lại thủ công, không có cách nào "chạy test" xác nhận đường
  dẫn trong markdown đúng. Cẩn thận đọc kỹ là biện pháp duy nhất, không có gate tự động.
