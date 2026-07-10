---
phase: 3
title: "H5 ICS Calendar Injection Escaping"
status: pending
priority: P2
dependencies: []
---

# Phase 3: H5 — `.ics` không escape → calendar injection

## Overview

`calendar_ics.build_ics()` nội suy trực tiếp `patient_name`, `department`, `doctor`, `code`
vào các dòng `SUMMARY:`/`DESCRIPTION:` của file `.ics` mà không escape theo chuẩn iCalendar
(RFC 5545 §3.3.11). `patient_name` do người dùng nhập tự do (qua `_ask_name` trong
`chatbot.py`, không giới hạn ký tự ngoài cắt độ dài 60) — nếu chứa `;`, `,`, `\`, hoặc xuống
dòng thật, có thể phá cấu trúc dòng nội dung `.ics`, chèn thêm property/dòng không mong muốn
khi app lịch (Google/Apple/Outlook) parse file.

## Requirements

- Functional: mọi field nội suy vào nội dung `.ics` (summary, description) phải được escape
  đúng chuẩn RFC 5545: `\` → `\\`, `;` → `\;`, `,` → `\,`, xuống dòng → `\n` (chuỗi ký tự
  backslash-n literal, KHÔNG phải ký tự xuống dòng thật) — theo đúng thứ tự (escape
  backslash TRƯỚC để không escape-kép các ký tự vừa thêm).
- Non-functional: Không đổi format file `.ics` cho dữ liệu KHÔNG có ký tự đặc biệt (test
  regression: tên/dịch vụ bình thường phải render y hệt trước/sau fix).

## Architecture

Thêm helper thuần (không phụ thuộc gì ngoài `str`):
```python
def _esc(value) -> str:
    """Escape 1 giá trị theo RFC 5545 §3.3.11 trước khi nội suy vào nội dung .ics."""
    s = str(value)
    s = s.replace("\\", "\\\\")   # backslash TRƯỚC TIÊN
    s = s.replace(";", "\\;")
    s = s.replace(",", "\\,")
    s = s.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")
    return s
```
Áp dụng `_esc(...)` cho MỌI giá trị nội suy vào `summary`/`description` (không phân biệt
"tin cậy" hay "không tin cậy" — escape đồng nhất là đơn giản hơn và an toàn hơn phải nhớ
field nào cần/không cần, đúng KISS):
```python
summary = f"Nha khoa SHI: {_esc(appointment['department'])} - {_esc(appointment['doctor'])}"
description = (
    f"Lịch hẹn tại Nha khoa SHI.\\n"
    f"Mã lịch hẹn: {_esc(appointment['code'])}\\n"
    f"Bệnh nhân: {_esc(appointment.get('patient_name', 'Khách'))}\\n"
    f"Dịch vụ: {_esc(appointment['department'])}\\n"
    f"Bác sĩ: {_esc(appointment['doctor'])}\\n"
    f"Lưu ý: vui lòng đến trước giờ hẹn 15 phút."
)
```
Lưu ý: các `\\n` literal đã có sẵn trong f-string gốc (ngăn cách dòng trong DESCRIPTION) là
escape sequence CHỦ Ý của tác giả gốc (xuống dòng hiển thị trong app lịch), KHÔNG phải lỗi —
giữ nguyên, chỉ bọc thêm `_esc()` quanh phần NỘI SUY biến động.

## Related Code Files

- Modify: `calendar_ics.py` (`build_ics`)
- Create: `tests/test_calendar_ics.py`

## Implementation Steps (TDD)

1. **Red** — viết `tests/test_calendar_ics.py`:
   - `test_build_ics_plain_data_unchanged()`: appointment với dữ liệu bình thường (không ký
     tự đặc biệt) → assert `SUMMARY:`/`DESCRIPTION:` render đúng như mong đợi, không có
     backslash thừa (regression, phải pass cả trước/sau fix).
   - `test_build_ics_escapes_semicolon_comma_backslash()`: `patient_name = "Nguyễn; Văn, A\\B"`
     → assert output chứa `Nguyễn\\; Văn\\, A\\\\B` (dạng đã escape), KHÔNG chứa chuỗi gốc
     chưa escape.
   - `test_build_ics_escapes_newline_in_patient_name()`: `patient_name` chứa ký tự xuống
     dòng thật (`"A\nB"`) → assert output KHÔNG chứa ký tự `\n` thật nằm giữa dòng
     `DESCRIPTION:` (tức là dòng logic `DESCRIPTION:...` khi split theo `\r\n` chỉ chiếm ĐÚNG
     1 dòng vật lý — xuống dòng thật đã bị escape thành literal `\n`, không tạo dòng mới phá
     cấu trúc VEVENT).
   - Chạy `pytest tests/test_calendar_ics.py -v` → xác nhận fail đúng chỗ (2 test escape
     fail, test regression pass vì dữ liệu thường không đổi).
2. **Green** — thêm `_esc()` và áp dụng theo Architecture.
3. Chạy lại → toàn bộ pass.
4. Verify thủ công: gọi `calendar_ics.build_ics(...)` với `patient_name` chứa `;`/`,`/`\n`
   qua `python3.10 -c "..."`, in ra và xác nhận trực quan đúng escape.

## Success Criteria

- [ ] `tests/test_calendar_ics.py` pass toàn bộ.
- [ ] Dữ liệu bình thường (không ký tự đặc biệt) render y hệt trước fix (no-op cho phần lớn
  case thực tế).
- [ ] `;`, `,`, `\`, xuống dòng trong `patient_name` (và các field nội suy khác) đều được
  escape đúng RFC 5545, không phá cấu trúc file `.ics`.

## Risk Assessment

- **Thứ tự escape sai gây escape-kép**: nếu escape `\n` trước `\\` (backslash), chuỗi
  `\n` mới tạo ra sẽ bị escape backslash lần 2 thành `\\n` sai định dạng. Đã thiết kế đúng
  thứ tự trong Architecture (backslash trước tiên) — bước implement PHẢI giữ đúng thứ tự
  này, test `test_build_ics_escapes_newline_in_patient_name` sẽ bắt được nếu làm sai thứ tự.
- **Không đổi hành vi `google_calendar_link()`** — hàm này dùng `urlencode()` (đã tự động
  escape URL-safe), không có lỗ hổng injection tương tự, KHÔNG nằm trong phạm vi phase này.
