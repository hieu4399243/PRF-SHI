---
phase: 2
title: "M2M5M6 Storage And Push Reliability"
status: pending
priority: P3
dependencies: []
---

# Phase 2: M2 + M5 + M6 — JSON atomic write/lock, dọn token Expo hết hạn, chống trùng mã ở JSON mode

## Overview

- **M2**: Chế độ JSON (`USE_DB=False`) đọc-sửa-ghi không khoá (race giữa request đồng thời)
  và `_json_save()` ghi trực tiếp đè file (không atomic — process chết giữa chừng làm hỏng
  toàn bộ file JSON).
- **M5**: Token Expo hết hạn (app gỡ cài đặt, đổi máy...) không bao giờ bị xoá khỏi
  `device_tokens`; phản hồi API Expo (`HTTP 200` nhưng từng "ticket" có thể báo lỗi, vd
  `DeviceNotRegistered`) bị bỏ qua hoàn toàn — không cập nhật `failed` (residual risk đã ghi
  ở H2, đóng nốt ở phase này).
- **M6**: Mã lịch hẹn trùng (do `_generate_code()` sinh trùng ngẫu nhiên, rất hiếm nhưng có
  thể) đã được xử lý ở nhánh Postgres (retry qua `UniqueViolation`/`appointments_pkey` từ
  C2/H1), nhưng nhánh JSON hoàn toàn KHÔNG kiểm tra — `storage.add_appointment()` (JSON) chỉ
  `append` thẳng, có thể tạo 2 bản ghi cùng `code`, `get_appointment(code)` sau đó luôn trả
  về bản ĐẦU TIÊN tìm thấy (dữ liệu trùng âm thầm, sai lệch khi tra cứu/hủy).

## Requirements

- Functional:
  - M2: Nhiều request JSON-mode ghi đồng thời không làm mất dữ liệu của nhau (serialize qua
    khoá). File JSON không bao giờ ở trạng thái nửa-ghi (atomic write — luôn hoặc là bản cũ
    nguyên vẹn, hoặc bản mới nguyên vẹn, không có trạng thái trung gian đọc được).
  - M5: `push.send_push()` xoá token khỏi storage khi Expo báo `DeviceNotRegistered` cho
    token đó. `failed` phản ánh CẢ lỗi mạng (đã có từ H2) LẪN lỗi ticket cấp ứng dụng (mới).
    Lỗi khi PARSE ticket KHÔNG được làm crash `send_push` (fail-open — coi như đã gửi).
  - M6: **Cả 2 dạng trùng** ở JSON mode đều phải bị chặn: (a) trùng `code` (như bản nháp
    đầu), VÀ (b) trùng SLOT `(doctor_id, date, time)` — đây là race chính mà UNIQUE INDEX
    Postgres (`ux_appointments_doctor_slot`) chặn ở tầng DB, JSON mode KHÔNG có tầng đó nên
    phải tự làm atomic bằng khoá.
- Non-functional: Không đổi `USE_DB` selection logic. Không đổi format file JSON hiện có
  (`appointments.json`, `device_tokens.json`). Nhánh Postgres của `storage.py` KHÔNG bị đụng
  (M2/M6 chỉ sửa nhánh JSON; M5 sửa cả 2 nhánh vì `remove_token` cần hoạt động ở cả Postgres
  lẫn JSON).

## Architecture

### M2 — atomic write + lock cho nhánh JSON
```python
import threading

_JSON_LOCK = threading.Lock()

def _json_save(path, data):
    """Ghi atomic: viết ra file tạm cùng thư mục rồi os.replace() — không bao
    giờ để lại file nửa-ghi nếu process chết giữa chừng."""
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)
```

**[Red team — Accept, Finding "add_token không được khoá dù remove_token mới có khoá" —
High]** Bọc `_JSON_LOCK` quanh MỖI hàm JSON-mode làm đọc-sửa-ghi — KHÔNG chỉ 3 hàm bản
nháp đầu liệt kê, mà TẤT CẢ: `add_appointment`, `set_reminder_sent`, `set_status`,
`add_token` (hàm ĐÃ CÓ TỪ TRƯỚC, bản nháp đầu bỏ sót), `remove_token` (hàm mới, M5). Thiếu
khoá ở `add_token` trong khi `remove_token` có khoá tạo ra race: `/api/register-push` (gọi
`add_token` không khoá) chạy đồng thời với `push.send_push` dọn token hết hạn (gọi
`remove_token` có khoá) trên CÙNG `device_tokens.json` có thể mất cập nhật của 1 trong 2.

### M6 — phát hiện trùng CODE và trùng SLOT ở JSON mode (atomic dưới khoá)

**[Red team — Accept, Finding "M6 không thực sự đóng race trùng giờ ở JSON mode" —
CRITICAL, 2 reviewer độc lập chỉ ra]** Bản nháp đầu CHỈ phát hiện trùng `code` — nhưng race
CHÍNH mà M6 phải đóng là 2 request đặt CÙNG bác sĩ, CÙNG ngày giờ gần như đồng thời (đây
chính là race mà UNIQUE INDEX `ux_appointments_doctor_slot` chặn ở Postgres — JSON mode
KHÔNG có tầng DB nào tương đương). `booking.book_appointment()` gọi `_confirmed_at(...)`
kiểm tra TRƯỚC khi gọi `storage.add_appointment` — nếu kiểm tra đó chạy NGOÀI khoá, 2 request
vẫn có thể cùng pass check rồi cùng insert thành công với 2 `code` khác nhau. Phải làm
CHECK-VÀ-INSERT atomic dưới CÙNG 1 lần giữ `_JSON_LOCK`, y hệt cách UNIQUE INDEX làm ở
Postgres (kiểm tra và ghi trong cùng 1 transaction).

Thêm 2 exception nhẹ trong `storage.py`:
```python
class DuplicateCodeError(Exception):
    """Mã lịch hẹn đã tồn tại (JSON mode) — tương đương UniqueViolation trên
    appointments_pkey ở Postgres."""


class SlotTakenError(Exception):
    """Khung giờ (doctor_id, date, time) đã có lịch 'confirmed' khác (JSON mode)
    — tương đương UNIQUE INDEX ux_appointments_doctor_slot ở Postgres."""
    def __init__(self, existing):
        super().__init__(existing.get("code"))
        self.existing = existing
```
`add_appointment` (nhánh JSON) kiểm tra CẢ 2 loại trùng TRONG lúc giữ khoá, TRƯỚC KHI ghi:
```python
def add_appointment(appt):
    appt.setdefault("reminders_sent", [])
    if USE_DB:
        ...  # không đổi
        return
    with _JSON_LOCK:
        items = _json_load(APPOINTMENTS_PATH, [])
        if any(a["code"] == appt["code"] for a in items):
            raise DuplicateCodeError(appt["code"])
        if appt.get("status") == "confirmed":
            for a in items:
                if (a.get("status") == "confirmed"
                        and a.get("doctor_id") == appt.get("doctor_id")
                        and a.get("date") == appt.get("date")
                        and a.get("time") == appt.get("time")):
                    raise SlotTakenError(a)
        items.append(appt)
        _json_save(APPOINTMENTS_PATH, items)
```
Vì toàn bộ "đọc danh sách → kiểm tra 2 loại trùng → ghi" nằm TRONG `with _JSON_LOCK:`, 2
thread gọi đồng thời không thể cùng vượt qua kiểm tra — thread thứ 2 luôn thấy bản ghi của
thread thứ nhất đã có trong `items` (vì phải chờ thread nhất nhả khoá trước khi đọc).

**[Red team — Accept, Finding "code mẫu M6 không khớp cấu trúc except thật của
_insert_with_race_guard"]** `booking._insert_with_race_guard` HIỆN TẠI (đọc từ
`booking.py`, KHÔNG suy đoán) có cấu trúc: 1 khối `try: storage.add_appointment(appointment)`
theo sau bởi ĐÚNG 1 khối `except Exception as exc:` (import `psycopg` bên trong, kiểm tra
`isinstance`, nhánh theo `constraint_name`, cuối cùng là nhánh retry-vì-trùng-code). KHÔNG
có `else:` — khi `add_appointment` không raise, hàm rơi thẳng xuống dòng
`return True, appointment` nằm SAU toàn bộ khối try/except (đọc code thật để xác nhận vị
trí chính xác dòng này trước khi sửa).

Thêm 2 khối `except` MỚI, đặt TRƯỚC khối `except Exception as exc:` hiện có (thứ tự quan
trọng — Python khớp theo thứ tự khai báo, đặt sau sẽ không bao giờ được chạm tới vì
`Exception` đã bắt hết trước):
```python
def _insert_with_race_guard(appointment, date_str, time_str, patient_phone, retry):
    doctor_id = appointment.get("doctor_id")
    try:
        storage.add_appointment(appointment)
    except storage.SlotTakenError as exc:
        taken = exc.existing
        if patient_phone and taken.get("patient_phone") == patient_phone:
            return False, {"duplicate": True, "existing": taken,
                           "error": "Bạn đã đặt lịch vào khung giờ này rồi."}
        return False, {"error": "Khung giờ này vừa có người đặt. "
                                "Vui lòng chọn giờ khác."}
    except storage.DuplicateCodeError:
        if not retry:
            return False, {"error": "Lỗi hệ thống, vui lòng thử lại."}
        appointment = dict(appointment, code=_generate_code())
        return _insert_with_race_guard(appointment, date_str, time_str,
                                       patient_phone, retry=False)
    except Exception as exc:
        ...  # nhánh psycopg.errors.UniqueViolation HIỆN CÓ, giữ nguyên 100% nội dung,
             # CHỈ di chuyển xuống dưới 2 khối except mới, không sửa logic bên trong
    return True, appointment  # dòng có sẵn, KHÔNG viết lại, chỉ xác nhận vị trí
```
`SlotTakenError` mang sẵn `existing` (bản ghi thắng race) trong exception — KHÔNG cần gọi
lại `_confirmed_at` như nhánh Postgres phải làm (Postgres không trả kèm bản ghi trong lỗi
`UniqueViolation`, JSON mode có thể tiện lợi hơn vì tự thiết kế exception mang theo dữ
liệu — tận dụng, không bắt buộc gọi lại query).

### M5 — parse ticket Expo + xoá token hết hạn (fail-open khi parse lỗi)
`storage.py` thêm hàm `remove_token(token)` (xoá theo token, không cần session — token là
định danh thiết bị, hết hạn thì hết hạn ở mọi session), BỌC `_JSON_LOCK` cho nhánh JSON
(xem M2):
```python
def remove_token(token):
    if USE_DB:
        init_schema()
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM device_tokens WHERE token = %s", (token,))
            conn.commit()
        return
    with _JSON_LOCK:
        data = _json_load(TOKENS_PATH, {})
        changed = False
        for sess_id, tokens in list(data.items()):
            if token in tokens:
                tokens.remove(token)
                changed = True
        if changed:
            _json_save(TOKENS_PATH, data)
```

**[Red team — Accept, Finding "parse ticket Expo có thể crash send_push, xuyên qua booking
ĐÃ THÀNH CÔNG" — CRITICAL, 2 reviewer độc lập chỉ ra]** Bản nháp đầu đặt `json.loads(...)` +
vòng lặp ticket TRONG cùng khối `try` chỉ bắt `(urllib.error.URLError, OSError)` — nếu Expo
trả body không phải JSON hợp lệ (`JSONDecodeError`) hoặc cấu trúc bất ngờ
(`AttributeError`/`KeyError`), exception KHÔNG bị bắt, lan lên `push.send_push()` (được gọi
KHÔNG có try/except bao quanh từ `chatbot.py`, SAU KHI lịch hẹn đã `storage.add_appointment`
thành công) → crash `/api/chat` với 500 dù lịch hẹn đã đặt xong trong DB. Phải cô lập phần
PARSE TICKET (không thiết yếu cho việc gửi push, chỉ là tối ưu dọn token) khỏi phần GỌI HTTP
(thiết yếu, giữ nguyên xử lý lỗi mạng hiện có):
```python
        try:
            req = urllib.request.Request(
                EXPO_PUSH_URL,
                data=json.dumps(messages).encode("utf-8"),
                headers={"Content-Type": "application/json",
                         "Accept": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                body_raw = resp.read()
            # HTTP call thành công (không network error) -> mặc định coi là đã gửi.
            sent = len(real)
            failed = 0
            # Parse ticket là TỐI ƯU (dọn token hết hạn) — lỗi ở đây KHÔNG được
            # đổi kết luận "đã gửi thành công" ở trên (fail-open, không crash).
            try:
                body = json.loads(body_raw)
                tickets = body.get("data", [])
                ticket_failed = 0
                for token, ticket in zip(real, tickets):
                    if ticket.get("status") == "error":
                        ticket_failed += 1
                        if ticket.get("details", {}).get("error") == "DeviceNotRegistered":
                            try:
                                storage.remove_token(token)
                            except Exception:
                                pass  # dọn token lỗi không được ảnh hưởng kết quả gửi
                sent = len(real) - ticket_failed
                failed = ticket_failed
            except Exception:
                pass  # không parse được ticket -> giữ nguyên sent/failed đã tính ở trên
                      # (coi như thành công vì HTTP đã 200, không đoán mò per-ticket)
        except (urllib.error.URLError, OSError):
            _write_outbox([{"to": t, "title": title, "body": body,
                            "data": data or {}, "error": "network"} for t in real])
            failed = len(real)
```
Nếu `len(tickets) != len(real)` (Expo trả thiếu) — `zip()` tự động cắt theo list ngắn hơn,
không raise, chấp nhận bỏ sót vài ticket thay vì crash toàn bộ gửi push.

## Related Code Files

- Modify: `storage.py` (`_json_save`, `add_appointment`, `set_reminder_sent`, `set_status`,
  `add_token`, thêm `_JSON_LOCK`, `DuplicateCodeError`, `SlotTakenError`, `remove_token`)
- Modify: `push.py` (`send_push` — parse ticket response, fail-open khi parse lỗi)
- Modify: `booking.py` (`_insert_with_race_guard` — thêm nhánh `SlotTakenError` +
  `DuplicateCodeError`)
- Create: `tests/test_storage.py` (M2, M6 phần storage)
- Create: `tests/test_push.py` (M5)
- Modify: `tests/test_booking.py` (thêm test M6 phần booking — file đã có, đọc trước khi sửa)

## Implementation Steps (TDD)

1. **Đọc trước**: `storage.py` toàn bộ nhánh JSON hiện tại (`_json_load`, `_json_save`,
   `add_appointment`, `set_reminder_sent`, `set_status`, `get_tokens`, `add_token`) và
   `booking.py`'s `_insert_with_race_guard` (đọc CHÍNH XÁC cấu trúc try/except hiện tại —
   chỉ 1 khối `except Exception as exc:`, không có `else:`, dòng `return True, appointment`
   nằm sau toàn bộ try/except) để chèn đúng chỗ, không suy đoán theo pseudocode.
2. **Red** — `tests/test_storage.py`:
   - `test_json_save_is_atomic(tmp_path, monkeypatch)`: monkeypatch
     `APPOINTMENTS_PATH`/dùng file tạm, gọi `_json_save` với dữ liệu lớn, assert file tạm
     `.tmp` KHÔNG còn tồn tại sau khi gọi xong (đã `os.replace` dọn sạch), và nội dung file
     đích đúng dữ liệu mới.
   - `test_add_appointment_json_detects_duplicate_code(monkeypatch)`: monkeypatch
     `USE_DB=False`, gọi `storage.add_appointment` 2 lần với CÙNG `code` → lần 2 raise
     `storage.DuplicateCodeError`.
   - `test_add_appointment_json_detects_slot_collision(monkeypatch)`: **[Red team —
     Accept]** monkeypatch `USE_DB=False`, gọi `storage.add_appointment` với 1 appointment
     `status="confirmed"` cho `(doctor_id="d1", date="2026-08-01", time="09:00")`, sau đó
     gọi LẦN 2 với `code` KHÁC nhưng CÙNG `(doctor_id, date, time)` → lần 2 raise
     `storage.SlotTakenError`, exception mang `existing` = bản ghi đầu tiên.
   - `test_add_appointment_json_allows_different_doctor_same_slot(monkeypatch)`:
     regression — CÙNG `(date, time)` nhưng KHÁC `doctor_id` → CẢ 2 lần đều thành công,
     không raise (khớp semantics `ux_appointments_doctor_slot` — khoá theo cả doctor_id).
   - `test_json_operations_thread_safe(monkeypatch)`: N thread gọi
     `storage.add_appointment` đồng thời với `code`/slot khác nhau đôi một → assert
     `len(storage.list_appointments()) == N` (không mất bản ghi do race ghi đè).
   - `test_concurrent_same_slot_only_one_succeeds(monkeypatch)`: **[Red team — Accept, test
     trực tiếp cho fix Critical M6]** N thread (vd 10) cùng gọi `storage.add_appointment`
     với CÙNG `(doctor_id, date, time)`, `status="confirmed"`, `code` khác nhau (dùng
     `concurrent.futures.ThreadPoolExecutor`, bắt exception từng thread) → assert ĐÚNG 1
     thread thành công (không raise), (N-1) thread còn lại đều raise `SlotTakenError`.
   - `test_remove_token_json_mode(monkeypatch)`: thêm token qua `add_token`, gọi
     `remove_token(token)` → assert `get_tokens(session_id)` không còn token đó.
   - `test_add_token_and_remove_token_thread_safe(monkeypatch)`: **[Red team — Accept]**
     N thread gọi `add_token` với token khác nhau CÙNG lúc 1 thread gọi `remove_token` cho 1
     token đã biết trước → assert không mất token nào khác ngoài token bị remove (xác nhận
     `add_token` đã được đưa vào `_JSON_LOCK`, không còn race với `remove_token`).
   - Chạy `pytest tests/test_storage.py -v` → xác nhận fail đúng chỗ.
3. **Red** — `tests/test_push.py`:
   - `test_send_push_removes_token_on_device_not_registered(monkeypatch)`: monkeypatch
     `urllib.request.urlopen` trả response JSON có 1 ticket
     `{"status":"error","details":{"error":"DeviceNotRegistered"}}`, monkeypatch
     `storage.remove_token` để đếm lời gọi → gọi `push.send_push(["ExponentPushToken[x]"],
     ...)` → assert `storage.remove_token` được gọi đúng token đó, `res["failed"] == 1`.
   - `test_send_push_ok_ticket_does_not_remove_token(monkeypatch)`: ticket
     `{"status":"ok"}` → assert `remove_token` KHÔNG được gọi, `res["failed"] == 0`.
   - `test_send_push_survives_malformed_ticket_response(monkeypatch)`: **[Red team — Accept,
     test trực tiếp cho fix Critical M5]** monkeypatch `urllib.request.urlopen` trả về body
     KHÔNG phải JSON hợp lệ (vd `b"not json"`) → gọi `push.send_push(["ExponentPushToken[x]"],
     ...)` → assert KHÔNG raise exception, `res["sent"] == 1`, `res["failed"] == 0`
     (fail-open: HTTP đã 200 nên coi là gửi thành công, không đoán per-ticket).
   - Chạy `pytest tests/test_push.py -v` → xác nhận fail đúng chỗ.
4. **Red** — thêm vào `tests/test_booking.py`:
   - `test_book_appointment_json_mode_retries_on_duplicate_code(monkeypatch)`: monkeypatch
     `storage.USE_DB = False`, monkeypatch `storage.add_appointment` raise
     `storage.DuplicateCodeError` lần đầu, thành công lần 2 → assert `book_appointment` trả
     `(True, {...})` với `code` KHÁC lần thử đầu (đã regenerate).
   - `test_book_appointment_json_mode_slot_taken(monkeypatch)`: **[Red team — Accept]**
     monkeypatch `storage.add_appointment` raise `storage.SlotTakenError(existing_appt)` →
     assert `book_appointment` trả `(False, {"error": "Khung giờ này vừa có người đặt...")`
     (hoặc `duplicate=True` nếu cùng SĐT), KHÔNG raise, KHÔNG gọi `_generate_code` lại.
   - Chạy `pytest tests/test_booking.py -v` → xác nhận fail đúng chỗ.
5. **Green** — sửa `storage.py`, `push.py`, `booking.py` theo Architecture.
6. Chạy lại toàn bộ 3 file test → pass. Chạy `pytest tests/ -v` → không regress
   `tests/test_booking.py`/`tests/test_reminder_worker.py` (từ vòng trước, cũng đụng
   `storage.py`/`push.py`/`booking.py` gián tiếp).

## Success Criteria

- [ ] `tests/test_storage.py`, `tests/test_push.py` pass toàn bộ; `tests/test_booking.py`
  pass cả test cũ lẫn mới.
- [ ] `_json_save` atomic (temp file + `os.replace`), TẤT CẢ thao tác JSON đọc-sửa-ghi
  (kể cả `add_token` đã có từ trước) bọc `_JSON_LOCK`.
- [ ] JSON mode phát hiện CẢ trùng `code` LẪN trùng slot `(doctor_id, date, time)` — race
  chính đã đóng, không chỉ 1 nửa vấn đề.
- [ ] `test_concurrent_same_slot_only_one_succeeds` pass — xác nhận bằng test thật (không
  chỉ đọc code) rằng race đã đóng.
- [ ] `push.send_push` xoá token khi Expo báo `DeviceNotRegistered`, `failed` phản ánh cả
  lỗi mạng lẫn lỗi ticket, và KHÔNG BAO GIỜ raise exception ra ngoài (kể cả khi Expo trả
  body không parse được).

## Risk Assessment

- **`_JSON_LOCK` là khoá TRONG-PROCESS** (threading.Lock), không bảo vệ nếu chạy nhiều
  process/worker cùng ghi 1 file JSON — nhất quán với quyết định "1 process" đã chốt xuyên
  suốt 2 plan trước, không phải regression mới.
- **Zip cắt ngắn khi Expo trả thiếu ticket** — chấp nhận bỏ sót thay vì crash, đã nêu rõ ở
  Architecture. Nếu cần xử lý chặt hơn (log cảnh báo khi `len(tickets) != len(real)`), có
  thể thêm dễ dàng nhưng KHÔNG bắt buộc cho scope M5 hiện tại.
- **`DuplicateCodeError`/`SlotTakenError` là exception mới, không kế thừa `psycopg.errors`**
  — cố ý, để JSON mode không phụ thuộc `psycopg` (giữ đúng thiết kế "JSON mode chạy được
  không cần cài psycopg" đã có từ đầu dự án). `_insert_with_race_guard` phải bắt RIÊNG 2
  exception này TRƯỚC nhánh `except Exception` chung — sai thứ tự sẽ khiến chúng lọt vào
  nhánh xử lý `psycopg.errors.UniqueViolation` (sẽ raise lại do `isinstance` check fail),
  làm mất khả năng retry/phản hồi đúng.
- **Kiểm tra slot-taken trong `add_appointment` chỉ áp dụng khi `appt.get("status") ==
  "confirmed"`** — khớp đúng semantics UNIQUE INDEX Postgres (`WHERE status='confirmed'`),
  không chặn nhầm lịch đã `cancelled` (được phép trùng slot với lịch mới, vì slot đã trống
  lại sau khi hủy).
