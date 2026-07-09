---
phase: 4
title: "C4 ICS Auth and Code Security"
status: pending
priority: P1
dependencies: [2]
---

# Phase 4: C4 — `/api/ics/<code>` không xác thực → lộ dữ liệu sức khỏe

## Overview

`GET /api/ics/<code>` (`app.py:77-88`) gọi `booking.get_appointment(code)` không kiểm
tra quyền sở hữu — bất kỳ ai biết/đoán được `code` đều tải được tên bệnh nhân + dịch vụ
nha khoa (dữ liệu sức khỏe nhạy cảm). `booking._generate_code()` dùng `random.choices`
(không phải CSPRNG) → không gian 36^6 ≈ 2.2 tỷ, đoán được bằng brute-force thực tế qua
HTTP nếu không có rate limit (rate limit ngoài phạm vi phase này — thuộc Medium).

**Phụ thuộc Phase 2**: cùng sửa `booking.py`. Phase này bắt đầu SAU khi Phase 2 merge
(tránh 2 agent sửa song song cùng file).

## Requirements

- Functional:
  - Mã lịch hẹn sinh bằng CSPRNG (`secrets`), không đổi format hiển thị (`SHI-XXXXXX`,
    vẫn 6 ký tự A-Z0-9 — không đổi độ dài để không vỡ chỗ nào hiển thị/validate format
    theo pattern cũ, nếu có).
  - `/api/ics/<code>` yêu cầu định danh sở hữu: chỉ trả `.ics` nếu request đến từ cùng
    `session` đã tạo lịch hẹn đó (so `appt["session"]` với `session_id` hiện tại của
    request qua `resolve_sid`), NGOÀI RA client mất session cookie thì không tải được nữa
    — chấp nhận được vì đây đúng model bảo mật "chỉ chủ sở hữu session tải được".
  - Không tìm thấy hoặc không đúng chủ sở hữu → `404` (KHÔNG phân biệt "không tồn tại" vs
    "không có quyền" bằng response khác nhau — tránh lộ thông tin tồn tại của mã).
- Non-functional: không đổi route path `/api/ics/<code>`, không đổi cách app native gọi
  endpoint này (vẫn GET, không cần thêm header — dùng cookie session có sẵn qua
  `resolve_sid`, đã hoạt động cho app native lẫn web theo code hiện tại).

## Architecture

1. `booking.py` `_generate_code()`:
   ```python
   import secrets
   def _generate_code():
       alphabet = string.ascii_uppercase + string.digits
       return "SHI-" + "".join(secrets.choice(alphabet) for _ in range(6))
   ```
   Xoá `import random` nếu không còn dùng nơi khác trong file (grep trước khi xoá).
2. `app.py` route `download_ics`:
   ```python
   @app.route("/api/ics/<code>")
   def download_ics(code):
       data = request.get_json(force=True, silent=True) or {}
       sid = resolve_sid(data)
       appt = booking.get_appointment(code)
       if not appt or appt.get("session") != sid:
           abort(404)
       ...
   ```
   Lưu ý: đây là `GET` route, `request.get_json()` trên GET thường rỗng — `resolve_sid`
   vẫn hoạt động vì nó fallback về `session.get("sid")` (cookie Flask) khi body rỗng, đúng
   luồng web hiện có.

   **[Red team — Accept, Finding "rủi ro nhắm sai đối tượng + plan.md mâu thuẫn"]**
   Xác nhận bằng grep thực tế (`mobile/src/api.js` chỉ gọi `/api/start`, `/api/chat`,
   `/api/register-push`; `mobile/src/calendar.js` ghi thẳng vào lịch máy qua
   `expo-calendar`, KHÔNG gọi HTTP `/api/ics`) — **app native KHÔNG dùng endpoint này**,
   nên rủi ro thật không nằm ở mobile. Rủi ro thật là **web demo**: link `.ics` được sinh
   server-side trong `chatbot.py:449,456` dạng `<a href="/api/ics/{code}">`, và
   `mobile/src/html.js` (renderer HTML cho app) tình cờ strip thẻ `<a>` khi hiển thị — đây
   là LÝ DO THẬT khiến grep `api/ics` trong `mobile/src` ra rỗng, không phải vì app "biết"
   tránh endpoint này. Ghi rõ cơ chế thật này vào báo cáo hoàn thành thay vì chỉ nói "grep
   không thấy".

   Rủi ro UX thật cần chấp nhận có chủ đích: user web xoá cookie / mở link `.ics` ở
   trình duyệt khác / private window / quay lại sau khi cookie hết hạn →
   `resolve_sid()` (`app.py:31-38`) luôn mint `sid` MỚI ngẫu nhiên khi không có cookie →
   không khớp `appt["session"]` → 404 dù là chính chủ. Đây là TRADE-OFF CHẤP NHẬN của
   phase này (đúng mô hình bảo mật "ownership qua session", không phải bug) — KHÔNG xây
   thêm cơ chế signed-token/link-riêng trong phase này (đó là tính năng mới, ngoài phạm vi
   "vá C4"). Ghi rõ residual risk này vào Risk Assessment bên dưới thay vì để ẩn.

## Related Code Files

- Modify: `booking.py` (`_generate_code`)
- Modify: `app.py` (`download_ics`)
- Create: `tests/test_app_ics.py`

## Implementation Steps (TDD)

1. **Trước khi code (đã xác nhận qua red-team review, không cần lặp lại)**: app native
   KHÔNG gọi `/api/ics/<code>` trực tiếp — `mobile/src/calendar.js` dùng `expo-calendar`
   ghi thẳng vào lịch máy, không qua HTTP. Link `.ics` chỉ được người dùng WEB bấm từ HTML
   chat reply (`chatbot.py:449,456`); `mobile/src/html.js` strip thẻ `<a>` nên app native
   không hiển thị/gọi link này. Vì vậy chỉ cần bảo vệ đúng luồng web (cookie session),
   không cần thêm cơ chế `?session=` query param cho app native.
2. **Red** — viết `tests/test_app_ics.py` dùng Flask test client (`app.test_client()`):
   - `test_generate_code_uses_secrets(monkeypatch)`: monkeypatch `secrets.choice` để đếm
     số lần gọi, assert `_generate_code()` gọi `secrets.choice` (không phải
     `random.choices`) đúng 6 lần.
   - `test_ics_requires_ownership()`: tạo 1 appointment qua `booking.book_appointment`
     với `session_id="alice"`, gọi `/api/ics/<code>` bằng test client với cookie session
     KHÁC (`bob`) → assert `404`.
   - `test_ics_allows_owner()`: cùng setup, gọi với cookie session đúng `alice` (dùng
     `client.session_transaction()` để set `session["sid"] = "alice"`) → assert `200` +
     content-type `text/calendar`.
   - `test_ics_unknown_code_returns_404()`: code không tồn tại → `404`.
   - Chạy `pytest tests/test_app_ics.py -v` → fail.
3. **Green** — implement theo Architecture, điều chỉnh theo kết quả bước 1 (grep mobile).
4. Chạy lại → pass.

## Success Criteria

- [ ] `tests/test_app_ics.py` pass, gồm ca ownership-denied + ownership-allowed +
  unknown-code.
- [ ] `_generate_code()` dùng `secrets`, không còn `random.choices` cho mã lịch hẹn.
- [ ] Báo cáo hoàn thành ghi rõ cơ chế thật đã xác nhận: app native không gọi
  `/api/ics` (dùng `expo-calendar` nội bộ), và `mobile/src/html.js` strip thẻ `<a>` là lý
  do link `.ics` không xuất hiện trên app — không phải vì app né endpoint này.

## Risk Assessment

- **[Red team] Rủi ro thật KHÔNG phải app native vỡ** (đã xác nhận app không gọi endpoint
  này qua HTTP) — rủi ro thật là **web user mất cookie session** (xoá cookie, mở link
  `.ics` ở trình duyệt/thiết bị khác, hoặc quay lại sau khi cookie hết hạn) → 404 dù là
  chính chủ đã đặt lịch. CHẤP NHẬN có chủ đích: đây đúng mô hình bảo mật "ownership qua
  session", đánh đổi lấy việc chặn hoàn toàn khả năng đoán/dò mã tải dữ liệu sức khỏe của
  người khác (mục tiêu chính của C4). Không xây thêm cơ chế signed-link trong phase này —
  ngoài phạm vi vá 1 lỗ hổng Critical, có thể làm ở plan riêng nếu cần.
- **Đổi độ dài/entropy mã** không ảnh hưởng vì giữ nguyên format `SHI-XXXXXX` — chỉ đổi
  nguồn ngẫu nhiên, không đổi độ dài chuỗi hiển thị.
- **404 đồng nhất cho "không tồn tại" và "không có quyền"** là chủ đích (chống
  enumeration) — không phải thiếu sót, không cần phân biệt message.
