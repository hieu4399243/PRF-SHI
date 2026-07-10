---
phase: 2
title: "H2H3H4 Worker Reliability And Timezone"
status: pending
priority: P2
dependencies: []
---

# Phase 2: H2+H3+H4 — Đáng tin cậy của worker + timezone

## Overview

3 vấn đề cùng nằm trong `reminder_worker.py`/`push.py`, gộp 1 phase để tránh 2-3 agent sửa
chồng 1 file:
- **H2**: `_send_for` đánh dấu `reminders_sent` dù push tới token thật thất bại (lỗi mạng) →
  mất nhắc lịch vĩnh viễn, không retry.
- **H3**: `--test` (gửi thử MỌI loại nhắc, bỏ qua thời gian) hiện gọi `_send_for` y hệt luồng
  thật → đánh dấu `reminders_sent` cho lịch hẹn THẬT, làm hỏng dedup thật (chạy `--test` 1
  lần là mọi nhắc lịch thật bị coi "đã gửi" vĩnh viễn).
- **H4**: `datetime.now()` là giờ local của HOST — nếu host chạy UTC (phổ biến trên cloud),
  so sánh với giờ hẹn lưu dạng giờ Việt Nam (naive) sẽ lệch 7 tiếng, nhắc lịch sai giờ hoặc
  không bao giờ đủ điều kiện gửi.

## Requirements

- Functional:
  - H2: push tới token THẬT thất bại do lỗi mạng → KHÔNG đánh dấu `reminders_sent`, để lần
    quét sau (`--watch`/cron `--once`) tự thử lại. Trường hợp KHÔNG có token thật (chỉ ghi
    outbox vì chưa đăng ký thiết bị — không phải lỗi) → vẫn đánh dấu như cũ (không phải lỗi
    cần retry, tránh spam quét vô ích).
  - H3: `--test` gửi push thật (đúng mục đích kiểm thử device) nhưng KHÔNG được ghi
    `reminders_sent` cho bất kỳ lịch hẹn nào.
  - H4: so sánh thời gian trong `scan_once` phải cho kết quả ĐÚNG bất kể múi giờ hệ thống
    host đang chạy (giả lập bằng cách kiểm tra offset UTC+7 tường minh thay vì dựa vào giờ
    hệ thống).
- Non-functional: Không đổi format `reminders_sent` (vẫn là list các `key` string). Không
  đổi cách gọi CLI (`--once`/`--watch`/`--test` vẫn đúng cú pháp cũ).

## Architecture

### H4 — timezone-aware
```python
from zoneinfo import ZoneInfo

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

def _now_vn():
    return datetime.now(VN_TZ)

def _appt_datetime(appt):
    naive = datetime.fromisoformat(f"{appt['date']}T{appt['time']}:00")
    return naive.replace(tzinfo=VN_TZ)
```
Thay `now = datetime.now()` → `now = _now_vn()`, thay chỗ parse `appt_dt` bằng `_appt_datetime(appt)`.
Vì CẢ 2 vế phép so sánh đều gắn tzinfo VN tường minh, kết quả đúng bất kể host chạy timezone
gì (UTC, VN, hay bất kỳ) — không còn phụ thuộc giờ hệ thống.

### H2 — không đánh dấu khi push thật thất bại
`push.py` `send_push()`: thêm field `failed` vào dict trả về, đếm số token THẬT gửi thất
bại do lỗi mạng (phân biệt với `demo`/token giả — token giả LUÔN ghi outbox, không phải lỗi):
```python
def send_push(tokens, title, body, data=None):
    ...
    sent = 0
    failed = 0
    if real:
        messages = [...]
        try:
            ...
            sent = len(real)
        except (urllib.error.URLError, OSError):
            _write_outbox([...])
            failed = len(real)
    return {"sent": sent, "outbox": len(demo), "failed": failed}
```
`reminder_worker.py` `_send_for`: chỉ gọi `booking.mark_reminder_sent` khi `res.get("failed", 0) == 0`.

### H3 — dry_run xuyên suốt scan_once → _send_for
```python
def _send_for(appt, rule, dry_run=False):
    tokens = push.get_tokens(appt.get("session", ""))
    res = push.send_push(tokens, rule["title"], rule["body"],
                          data={"type": "reminder", "key": rule["key"], "code": appt["code"]})
    should_mark = (not dry_run) and res.get("failed", 0) == 0
    if should_mark:
        booking.mark_reminder_sent(appt["code"], rule["key"])
    target = tokens or ["(chưa có thiết bị — ghi outbox)"]
    status = "DRY-RUN" if dry_run else ("SENT" if should_mark else "RETRY-PENDING")
    print(f"  [{status}] {appt['code']} · {rule['key']} -> {target} · {res}")

def scan_once(force=False, dry_run=False):
    now = _now_vn()
    appts = booking.all_appointments()
    n_sent = 0
    for appt in appts:
        try:
            if appt.get("status") != "confirmed":
                continue
            try:
                appt_dt = _appt_datetime(appt)
            except ValueError:
                continue
            already = set(appt.get("reminders_sent", []))
            for rule in _rules(appt):
                if rule["key"] in already:
                    continue
                due_time = appt_dt - rule["before"]
                if force or (now >= due_time and now <= appt_dt):
                    try:
                        _send_for(appt, rule, dry_run=dry_run)
                        n_sent += 1
                    except Exception as e:
                        print(f"  [SEND-ERROR] {appt.get('code','?')} · {rule['key']} · "
                              f"lỗi khi gửi/đánh dấu nhắc lịch: {e}")
        except Exception as e:
            print(f"  [SKIP] {appt.get('code', '?')} · dữ liệu lịch hẹn lỗi: {e}")
            continue
    return n_sent
```

**[Red team — Accept, Finding "code mẫu che mất lớp except ValueError"]** Code mẫu ở trên
viết ĐẦY ĐỦ cả 3 lớp try/except hiện có (không rút gọn bằng `...` như bản nháp trước) —
PHẢI giữ nguyên cấu trúc lồng nhau này khi implement: (1) `except ValueError` RIÊNG quanh
`_appt_datetime` (lỗi parse ngày/giờ → `continue` im lặng, giữ nguyên từ code gốc), (2)
`except Exception` quanh `_send_for` → `[SEND-ERROR]` (từ C5), (3) `except Exception` NGOÀI
CÙNG quanh toàn bộ thân vòng lặp appt → `[SKIP]` (từ C5). Chỉ thêm `dry_run` xuyên suốt,
không đổi/gộp bất kỳ lớp nào trong 3 lớp trên.
`main()`: nhánh `--test` gọi `scan_once(force=True, dry_run=True)` thay vì
`scan_once(force=True)`.

**Giữ nguyên** 2 lớp try/except (C5) và logic `[SKIP]`/`[SEND-ERROR]` đã có — chỉ thêm
`dry_run` xuyên suốt, không đổi cấu trúc lỗi-cô-lập đã build ở phase trước.

## Related Code Files

- Modify: `push.py` (`send_push` — thêm field `failed`)
- Modify: `reminder_worker.py` (`_now_vn`, `_appt_datetime`, `_send_for`, `scan_once`, `main`)
- Modify: `tests/test_reminder_worker.py` (file đã có từ C5, thêm test mới; đọc trước để
  biết cấu trúc hiện tại, tránh trùng lặp fixture/monkeypatch)

## Implementation Steps (TDD)

1. **Đọc trước**: `tests/test_reminder_worker.py` hiện tại (từ plan C1-C5) để biết cách
   monkeypatch `push.send_push`/`booking.mark_reminder_sent` đã dùng, giữ nhất quán style.
2. **Red** — thêm test:
   - `test_send_push_reports_failed_count(monkeypatch)`: monkeypatch
     `urllib.request.urlopen` để raise `URLError`, gọi `push.send_push(["ExponentPushToken[x]"], ...)`
     → assert `res["failed"] == 1`.
   - `test_scan_once_does_not_mark_sent_on_real_push_failure(monkeypatch)`: monkeypatch
     `push.send_push` trả `{"sent":0,"outbox":0,"failed":1}`, monkeypatch
     `booking.mark_reminder_sent` để đếm số lần gọi → gọi `scan_once(force=True)` trên 1
     appt hợp lệ → assert `mark_reminder_sent` KHÔNG được gọi.
   - `test_scan_once_marks_sent_when_no_real_token(monkeypatch)`: monkeypatch
     `push.send_push` trả `{"sent":0,"outbox":1,"failed":0}` (không có token thật, chỉ ghi
     outbox demo — không phải lỗi) → assert `mark_reminder_sent` VẪN được gọi (regression,
     giữ hành vi cũ cho case không phải lỗi).
   - `test_test_mode_does_not_mark_reminders_sent(monkeypatch)`: monkeypatch
     `push.send_push` trả thành công bình thường (`failed:0`), gọi
     `scan_once(force=True, dry_run=True)` → assert `mark_reminder_sent` KHÔNG được gọi dù
     push "thành công" (đúng ý H3: test mode không phá dedup thật).
   - `test_now_vn_is_utc_plus_7()`: assert `_now_vn().utcoffset() == timedelta(hours=7)`.
   - `test_appt_datetime_has_vn_tzinfo()`: `_appt_datetime({"date":"2026-08-01","time":"09:00"})`
     → assert `.tzinfo` khớp `Asia/Ho_Chi_Minh`, và so sánh được với `_now_vn()` không raise
     `TypeError` (naive/aware mismatch) — đây là test regression chính cho H4.
   - Chạy `pytest tests/test_reminder_worker.py -v` → xác nhận fail đúng chỗ.
3. **Green** — sửa `push.py` + `reminder_worker.py` theo Architecture.
4. Chạy lại → toàn bộ pass.
5. Verify thủ công: `python3.10 reminder_worker.py --once` và
   `python3.10 reminder_worker.py --test` trên `appointments.json` thật, xác nhận `--test`
   không đổi nội dung `reminders_sent` trong file (so sánh trước/sau bằng `git diff
   appointments.json` — phải KHÔNG có thay đổi nếu file này đang được git track, hoặc so
   sánh nội dung file trực tiếp).

## Success Criteria

- [ ] `tests/test_reminder_worker.py` pass toàn bộ (test cũ + mới).
- [ ] `push.send_push` trả thêm field `failed` phản ánh đúng số token thật gửi lỗi mạng.
- [ ] `--test` không còn ghi `reminders_sent` cho bất kỳ lịch hẹn nào (verify thủ công).
- [ ] So sánh thời gian dùng `Asia/Ho_Chi_Minh` tường minh, không phụ thuộc giờ hệ thống host.

## Risk Assessment

- **`zoneinfo` cần tzdata trên hệ thống** — Python 3.9+ trên macOS/Linux thường có sẵn tzdata
  hệ thống (`/usr/share/zoneinfo`), `zoneinfo.ZoneInfo("Asia/Ho_Chi_Minh")` hoạt động không
  cần cài thêm gói trên môi trường dev/test đã xác nhận (`python3.10` trên máy này). Nếu môi
  trường production thiếu tzdata (hiếm, một số Docker image tối giản), cần thêm gói
  `tzdata` vào `requirements.txt` — kiểm tra bằng cách chạy thử
  `python3.10 -c "from zoneinfo import ZoneInfo; ZoneInfo('Asia/Ho_Chi_Minh')"` trong bước
  implement; nếu lỗi `ZoneInfoNotFoundError`, thêm `tzdata` vào requirements.txt như một
  phần của phase này (không phải scope creep — cần thiết để H4 hoạt động).
- **H2 thu hẹp phạm vi đã duyệt**: không xây retry-worker đọc outbox — nhắc lịch bị lỗi mạng
  chỉ được thử lại ở LẦN QUÉT KẾ TIẾP của `scan_once` (nếu vẫn trong khung thời gian hợp lệ
  `now <= appt_dt`). Nếu lỗi mạng kéo dài qua giờ hẹn, nhắc đó vĩnh viễn không gửi được —
  đây là giới hạn đã được user chấp nhận, không phải bug sót.
- **[Red team] H2 fix CHỈ bắt lỗi tầng vận chuyển** (`URLError`/`OSError` khi gọi Expo API),
  KHÔNG bắt lỗi tầng ứng dụng của Expo (API trả `HTTP 200` nhưng nội dung từng "ticket" báo
  lỗi, vd token hết hạn `DeviceNotRegistered` — xem `push.py` dòng đọc `resp.read()` hiện
  đang bỏ qua nội dung response). Trường hợp này vẫn bị đánh dấu `reminders_sent` dù thực
  chất không tới được thiết bị — tái hiện lại triệu chứng H2 qua đường khác. CHẤP NHẬN có
  chủ đích: parse ticket-level response của Expo là mở rộng phạm vi thật sự (cần định nghĩa
  thêm xử lý cho `DeviceNotRegistered` — dọn token, vốn là mục Medium riêng trong
  `ISSUES.md`), KHÔNG làm ở phase này. Chỉ ghi nhận residual risk, không code thêm.
