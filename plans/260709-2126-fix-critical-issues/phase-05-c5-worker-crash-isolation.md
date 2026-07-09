---
phase: 5
title: "C5 Worker Crash Isolation"
status: pending
priority: P1
dependencies: []
---

# Phase 5: C5 — Worker `--watch` chết khi gặp 1 bản ghi lỗi

## Overview

`reminder_worker.scan_once()` lặp qua `booking.all_appointments()`, gọi `_rules(appt)` và
`_send_for(appt, rule)` không try/except. Một lịch hẹn thiếu field (`appt['time']`,
`appt['department']`, `appt["code"]`...) → `KeyError` không bắt → toàn bộ vòng lặp dừng →
`--watch` (chạy nền vô hạn) chết hẳn → KHÔNG ai nhận nhắc lịch nữa cho tới khi restart thủ
công.

## Requirements

- Functional: 1 bản ghi appointment lỗi (thiếu field / sai định dạng) không được làm dừng
  việc xử lý các bản ghi còn lại trong cùng lần quét, và không được làm crash `--watch`
  loop.
- Non-functional: không nuốt lỗi im lặng hoàn toàn — phải log ra để dev biết bản ghi nào
  lỗi (in ra `stdout` như các log khác trong file, nhất quán với style hiện có, không thêm
  logging framework mới — YAGNI).

## Architecture

Bọc try/except quanh xử lý MỘT appointment trong `scan_once()` (không bọc quanh từng
`rule` riêng lẻ — nếu 1 appt lỗi ở field cấp appointment như `appt['date']`, tất cả rule
của appt đó đều sẽ lỗi giống nhau, bọc theo appt là đủ và đơn giản hơn bọc theo rule).

**[Red team — Accept, Finding "nuốt lỗi mark_reminder_sent gây gửi lặp"]** Thêm 1 lớp
try/except THỨ HAI, hẹp hơn, chỉ quanh `_send_for(appt, rule)`: nếu `push.send_push` GỬI
THÀNH CÔNG nhưng `booking.mark_reminder_sent` sau đó lỗi (vd DB hiccup — cùng loại vấn đề
H2/H3 đã ghi riêng trong `ISSUES.md`), log chung `[SKIP]` sẽ khiến lỗi này lẫn với "dữ
liệu hỏng", và vì `reminders_sent` chưa được cập nhật, nhắc lịch đó bị coi là "chưa gửi" →
gửi lại mỗi 60s trong `--watch` vô thời hạn, làm phiền bệnh nhân. Tách log message
(`[SEND-ERROR]` khác `[SKIP]`) để phân biệt 2 loại lỗi khi debug — không sửa hành vi dedup
(đó là H2/H3, ngoài phạm vi phase này):

```python
def scan_once(force=False):
    now = datetime.now()
    appts = booking.all_appointments()
    n_sent = 0
    for appt in appts:
        try:
            if appt.get("status") != "confirmed":
                continue
            try:
                appt_dt = datetime.fromisoformat(f"{appt['date']}T{appt['time']}:00")
            except ValueError:
                continue
            already = set(appt.get("reminders_sent", []))
            for rule in _rules(appt):
                if rule["key"] in already:
                    continue
                due_time = appt_dt - rule["before"]
                if force or (now >= due_time and now <= appt_dt):
                    try:
                        _send_for(appt, rule)
                        n_sent += 1
                    except Exception as e:
                        print(f"  [SEND-ERROR] {appt.get('code','?')} · {rule['key']} · "
                              f"lỗi khi gửi/đánh dấu nhắc lịch: {e}")
        except Exception as e:
            print(f"  [SKIP] {appt.get('code', '?')} · dữ liệu lịch hẹn lỗi: {e}")
            continue
    return n_sent
```

Try/except NGOÀI (`[SKIP]`) bọc phần đọc field appt (`appt_dt`, `_rules(appt)`) — lỗi dữ
liệu bản ghi, bắt `Exception` rộng vì mục tiêu là "1 bản ghi lỗi không giết cả vòng lặp"
bất kể loại lỗi gì. Try/except TRONG (`[SEND-ERROR]`) chỉ bọc `_send_for` — lỗi khi
gửi/đánh dấu — để 2 dòng log không lẫn vào nhau khi debug. Loop `--watch` ở `main()` không
cần sửa — nó chỉ gọi `scan_once()` mỗi 60s, giờ `scan_once` tự cô lập lỗi per-record nên
không còn propagate lên `main()`.

## Related Code Files

- Modify: `reminder_worker.py` (`scan_once`)
- Create: `tests/test_reminder_worker.py`

## Implementation Steps (TDD)

1. **Red** — viết `tests/test_reminder_worker.py`:
   - `test_scan_once_skips_broken_record(monkeypatch)`: monkeypatch
     `booking.all_appointments` để trả về list gồm 2 appointment — 1 bản ghi thiếu field
     `time` (thiếu key → gây `KeyError` trong `f"{appt['date']}T{appt['time']}:00"`) và 1
     bản ghi hợp lệ đúng hạn nhắc (dùng `force=True` để không cần canh giờ thật). Cũng
     monkeypatch `push.send_push` và `booking.mark_reminder_sent` để không gọi network
     thật. Gọi `reminder_worker.scan_once(force=True)` → assert KHÔNG raise exception, và
     bản ghi hợp lệ vẫn được xử lý (`push.send_push` được gọi đúng 1 lần cho bản ghi tốt).
   - `test_scan_once_returns_count_excluding_broken()`: assert `n_sent` chỉ đếm bản ghi
     xử lý thành công, không đếm bản ghi lỗi.
   - `test_scan_once_logs_send_error_separately(monkeypatch, capsys)`: **[Red team —
     Accept]** monkeypatch `booking.mark_reminder_sent` để raise exception (giả lập DB
     hiccup) trong khi `push.send_push` vẫn trả về bình thường; gọi `scan_once(force=True)`
     trên 1 appointment hợp lệ → assert KHÔNG raise, và output (`capsys.readouterr()`)
     chứa `[SEND-ERROR]` chứ KHÔNG chứa `[SKIP]` cho bản ghi đó (phân biệt được lỗi
     gửi/đánh dấu với lỗi dữ liệu).
   - Chạy `pytest tests/test_reminder_worker.py -v` → fail (hiện tại raise `KeyError`
     làm test crash).
2. **Green** — bọc try/except như Architecture.
3. Chạy lại → pass.
4. Verify thủ công: `python reminder_worker.py --once` trên `appointments.json` thật của
   repo (đã có sẵn) → không lỗi, in ra log bình thường.

## Success Criteria

- [ ] `tests/test_reminder_worker.py` pass.
- [ ] 1 bản ghi lỗi DỮ LIỆU in ra dòng `[SKIP] ...` và KHÔNG dừng xử lý các bản ghi còn lại.
- [ ] 1 lỗi khi GỬI/ĐÁNH DẤU (sau khi đọc dữ liệu appt thành công) in ra dòng
  `[SEND-ERROR] ...`, phân biệt được với `[SKIP]` qua log.
- [ ] `python reminder_worker.py --once` chạy sạch trên dữ liệu thật hiện có trong repo.

## Risk Assessment

- **Bắt `Exception` quá rộng có thể che giấu bug thật** (vd lỗi code trong `_send_for`
  không liên quan tới dữ liệu appt). Chấp nhận trade-off này vì mục tiêu chính là "worker
  nền không được chết" — log dòng `[SKIP]` vẫn giữ khả năng debug qua log, không phải
  nuốt lỗi hoàn toàn im lặng.
- Không đổi hành vi dedup (`reminders_sent`) — chỉ thêm cô lập lỗi, không đụng H2/H3
  (đánh dấu đã gửi dù thất bại / `--test` phá dedup thật) — các mục đó là High, ngoài
  phạm vi phase này.
