---
phase: 5
title: "L3 Reminder Overdue Logging"
status: pending
priority: P3
dependencies: []
---

# Phase 5: L3 — Nhắc lịch quá hạn bị bỏ qua âm thầm

## Overview

`scan_once()` chỉ gửi nhắc khi `force or (now >= due_time and now <= appt_dt)`. Nếu
`now > appt_dt` (đã qua giờ hẹn — vd worker `--watch` bị dừng lâu rồi khởi động lại, hoặc
`--once` không chạy đúng lịch cron) và nhắc chưa từng gửi, điều kiện này KHÔNG BAO GIỜ đúng
nữa cho reminder đó — bị bỏ qua VĨNH VIỄN, hoàn toàn im lặng, không log gì để biết.

## Requirements

- Functional: khi 1 reminder bị bỏ qua vì đã quá giờ hẹn (`now > appt_dt`, chưa gửi, không
  phải `force`), in 1 dòng log rõ ràng để observability — KHÔNG gửi nhắc trễ (gửi "nhắc còn
  1 ngày" sau khi đã khám xong là vô nghĩa/gây khó hiểu cho bệnh nhân — quyết định nghiệp vụ
  giữ nguyên, chỉ thêm log).
- Non-functional: Không đổi hành vi gửi/không-gửi hiện có, không đổi `n_sent` return value
  (reminder bị bỏ qua do quá hạn KHÔNG tính vào `n_sent`, giữ nguyên).

## Architecture

Trong `scan_once()`, vòng lặp `for rule in _rules(appt):` hiện tại:
```python
                if force or (now >= due_time and now <= appt_dt):
                    try:
                        _send_for(appt, rule, dry_run=dry_run)
                        n_sent += 1
                    except Exception as e:
                        print(f"  [SEND-ERROR] ...")
```
Thêm nhánh `elif` để log riêng trường hợp quá hạn (không gộp vào `[SKIP]`/`[SEND-ERROR]` đã
có — đó là lỗi dữ liệu/lỗi gửi, còn đây là "đúng dữ liệu, đúng logic, chỉ là quá muộn"):
```python
                if force or (now >= due_time and now <= appt_dt):
                    try:
                        _send_for(appt, rule, dry_run=dry_run)
                        n_sent += 1
                    except Exception as e:
                        print(f"  [SEND-ERROR] {appt.get('code','?')} · {rule['key']} · "
                              f"lỗi khi gửi/đánh dấu nhắc lịch: {e}")
                elif not force and now > appt_dt:
                    print(f"  [EXPIRED] {appt.get('code','?')} · {rule['key']} · "
                          f"bỏ qua vì đã quá giờ hẹn (không gửi nhắc trễ)")
```
`not force` để tránh log `[EXPIRED]` sai khi chạy `--test` (`force=True` luôn gửi, không có
khái niệm "quá hạn" trong chế độ test).

## Related Code Files

- Modify: `reminder_worker.py` (`scan_once`)
- Modify: `tests/test_reminder_worker.py` (file đã có từ 2 vòng trước — đọc trước, thêm
  test mới)

## Implementation Steps (TDD)

1. **Đọc trước**: `reminder_worker.py` hiện tại (cấu trúc `scan_once` sau các lần sửa C5/H4)
   để chèn đúng vị trí `elif`, và `tests/test_reminder_worker.py` để biết style monkeypatch
   đã dùng.
2. **Red** — thêm vào `tests/test_reminder_worker.py`:
   - `test_scan_once_logs_expired_reminder(monkeypatch, capsys)`: tạo 1 appointment với
     `date`/`time` trong QUÁ KHỨ (so với `_now_vn()` thật, hoặc monkeypatch `_now_vn` để trả
     giá trị cố định sau `appt_dt`), reminder chưa có trong `reminders_sent`, gọi
     `scan_once(force=False)` → assert output (`capsys.readouterr()`) chứa `[EXPIRED]`, VÀ
     `push.send_push` (monkeypatch để đếm lời gọi) KHÔNG được gọi cho reminder đó (không gửi
     trễ).
   - `test_scan_once_test_mode_does_not_log_expired()`: cùng setup nhưng gọi
     `scan_once(force=True, dry_run=True)` → assert output KHÔNG chứa `[EXPIRED]` (vì
     `force=True` gửi luôn, không rơi vào nhánh quá hạn).
   - Chạy `pytest tests/test_reminder_worker.py -v` → xác nhận test `[EXPIRED]` fail đúng
     chỗ (hiện tại không có log này).
3. **Green** — sửa `reminder_worker.py` theo Architecture.
4. Chạy lại → toàn bộ pass (test cũ từ C5/H4 + 2 test mới).

## Success Criteria

- [ ] `tests/test_reminder_worker.py` pass toàn bộ.
- [ ] Reminder quá hạn được log `[EXPIRED]`, KHÔNG được gửi.
- [ ] `force=True` (`--test`) không bị log `[EXPIRED]` sai.
- [ ] `n_sent` không tính reminder quá hạn (giữ nguyên hành vi cũ).

## Risk Assessment

- **Không đổi quyết định nghiệp vụ "không gửi nhắc trễ"** — chỉ thêm observability, đây là
  fix Low-severity đúng bản chất (không phải bug ảnh hưởng người dùng, chỉ khó debug/vận
  hành khi không biết vì sao 1 reminder "biến mất"). Không mở rộng thành tính năng "gửi
  nhắc trễ có điều chỉnh nội dung" — ngoài phạm vi, không được yêu cầu.
