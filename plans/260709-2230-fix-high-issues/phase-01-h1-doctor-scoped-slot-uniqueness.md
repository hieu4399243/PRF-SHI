---
phase: 1
title: "H1 Doctor Scoped Slot Uniqueness"
status: pending
priority: P2
dependencies: []
---

# Phase 1: H1 — Kiểm tra trùng giờ bỏ qua `doctor_id`

## Overview

`_confirmed_at(date_str, time_str)` (và UNIQUE INDEX `ux_appointments_slot` thêm ở plan
trước) chỉ khoá theo `(date, time)` — coi cả phòng khám là 1 ghế. Đặt bác sĩ A giờ X chặn
luôn bác sĩ B giờ X dù 2 bác sĩ khác nhau. **Đã xác nhận với user: đây là bug**, phải khoá
theo `(doctor_id, date, time)`.

## Requirements

- Functional: 2 bệnh nhân đặt CÙNG giờ, CÙNG ngày nhưng KHÁC bác sĩ → cả 2 đều thành công.
  2 bệnh nhân đặt CÙNG giờ, CÙNG ngày, CÙNG bác sĩ → vẫn bị chặn như cũ (không regress hành
  vi chống trùng đã có).
- Non-functional: Giữ nguyên toàn bộ cơ chế bảo vệ race-condition đã xây ở C2 (UNIQUE INDEX
  + bắt `UniqueViolation` + phân biệt theo `constraint_name` + retry khi trùng mã lịch hẹn
  ngẫu nhiên) — chỉ đổi PHẠM VI khoá từ `(date,time)` sang `(doctor_id,date,time)`, không
  đổi kiến trúc.

## Architecture

1. `storage.py`: đổi `UNIQUE_SLOT_INDEX_SQL`. Vì tên constraint cũ `ux_appointments_slot` đã
   có thể tồn tại trong DB (từ lần chạy `init_schema()` trước), phải `DROP INDEX IF EXISTS`
   tên cũ và tạo index mới tên `ux_appointments_doctor_slot`.

   **[Red team — Accept, Finding "combined execute untested trên psycopg3"]** KHÔNG gộp
   `DROP`+`CREATE` vào 1 chuỗi SQL/1 lần `cur.execute()` — psycopg3 (khác psycopg2) xử lý
   multi-statement trong 1 lần execute không đảm bảo, có thể âm thầm lỗi/no-op (bị nuốt bởi
   try/except sẵn có, in cảnh báo nhưng KHÔNG tạo được index — cả fix H1 vô tác dụng mà
   không ai biết). Phải tách 2 lệnh `cur.execute()` riêng biệt.

   **[Red team — Accept, Finding "thứ tự DROP/CREATE rủi ro"]** Thứ tự PHẢI là
   **CREATE index mới TRƯỚC, DROP index cũ SAU** (không phải DROP trước như bản nháp đầu) —
   nếu CREATE fail (do dữ liệu trùng sẵn có theo bộ khoá mới), index CŨ vẫn còn nguyên, ứng
   dụng vẫn có 1 lớp bảo vệ (chặt hơn cần thiết nhưng còn hơn không). Nếu DROP trước mà
   CREATE fail, ứng dụng mất HOÀN TOÀN bảo vệ unique cho tới lần deploy sau:
   ```python
   cur.execute(
       "CREATE UNIQUE INDEX IF NOT EXISTS ux_appointments_doctor_slot "
       "ON appointments (doctor_id, date, time) WHERE status = 'confirmed'"
   )
   cur.execute("DROP INDEX IF EXISTS ux_appointments_slot")
   ```
   Giữ nguyên cơ chế try/except RIÊNG quanh 2 câu lệnh này trong `init_schema()` (đã có từ
   C2) — 1 lỗi migrate không được sập cả app. Nếu implement thấy `DROP` cũng cần nằm trong
   cùng try/except như `CREATE` (để không bị treo index cũ nếu app crash giữa 2 lệnh), giữ
   cả 2 trong 1 khối try — chỉ cần đảm bảo ĐÚNG THỨ TỰ create-rồi-drop.
2. `booking.py`:
   - `_confirmed_at(date_str, time_str)` → đổi chữ ký thành
     `_confirmed_at(doctor_id, date_str, time_str)`, thêm điều kiện lọc
     `a.get("doctor_id") == doctor_id` vào vòng lặp so khớp.
   - `book_appointment()`: đổi lời gọi `_confirmed_at(date_str, time_str)` thành
     `_confirmed_at(doctor_id, date_str, time_str)` (biến `doctor_id` đã có sẵn trong tham
     số hàm — không cần thêm gì).
   - `_insert_with_race_guard` (hàm C2 đã tạo, chữ ký hiện tại:
     `_insert_with_race_guard(appointment, date_str, time_str, patient_phone, retry)`): đổi
     điều kiện so khớp `constraint_name == "ux_appointments_slot"` thành
     `constraint_name == "ux_appointments_doctor_slot"`.

     **[Red team — Accept, Finding "quên sửa lời gọi _confirmed_at bên trong
     _insert_with_race_guard" — CRITICAL, 2 reviewer độc lập xác nhận]** Hàm này CÒN 1 lời
     gọi `_confirmed_at(date_str, time_str)` KHÁC nằm bên trong nó (ở nhánh xử lý
     `UniqueViolation` đúng slot), KHÔNG PHẢI chỉ ở `book_appointment()`. `appointment`
     dict truyền vào `_insert_with_race_guard` đã có sẵn key `"doctor_id"` — lấy
     `doctor_id = appointment.get("doctor_id")` ngay đầu hàm và dùng cho lời gọi
     `_confirmed_at(doctor_id, date_str, time_str)` ở nhánh này. ĐÂY LÀ CHỖ SỬA DỄ BỎ SÓT
     NHẤT trong toàn phase — nếu bỏ sót, đúng lúc 2 request THẬT cùng bác sĩ cùng giờ race
     nhau (chính kịch bản C2/H1 tồn tại để bảo vệ), server trả về lỗi 500 không kiểm soát
     thay vì thông báo "khung giờ đã có người đặt".
3. `tests/test_booking.py` (file đã có từ C2, sửa/thêm test):

   **[Red team — Accept, Finding "đếm sai số chỗ cần sửa lambda" — 2 reviewer độc lập chỉ
   ra số đếm khác nhau, nghĩa là con số cứng không đáng tin]** KHÔNG dựa vào số đếm cố định
   ("3 chỗ" là SAI). Thay vào đó: chạy `grep -n "_confirmed_at" tests/test_booking.py` và
   sửa TẤT CẢ các chỗ stub/monkeypatch hàm này (dù là lambda trực tiếp
   `monkeypatch.setattr(booking, "_confirmed_at", lambda ...)` hay factory helper như
   `confirmed_at_seq(...)` có hàm closure nội bộ `def _f(d, t): ...`) sang nhận đủ 3 tham số
   `(doctor_id, date_str, time_str)`. Đọc kỹ toàn bộ file trước khi sửa, không suy đoán số
   lượng.
   - CẬP NHẬT mọi chỗ dùng chuỗi `"ux_appointments_slot"` (trong `_make_unique_violation(...)`
     và assertion) thành `"ux_appointments_doctor_slot"`.

## Related Code Files

- Modify: `storage.py` (`UNIQUE_SLOT_INDEX_SQL`)
- Modify: `booking.py` (`_confirmed_at`, `book_appointment`, `_insert_with_race_guard`)
- Modify: `tests/test_booking.py` (cập nhật test cũ theo chữ ký mới + thêm test mới)

## Implementation Steps (TDD)

1. **Đọc trước**: `tests/test_booking.py` hiện tại (từ plan C1-C5) để biết chính xác những
   chỗ cần cập nhật chữ ký `_confirmed_at` và tên constraint — KHÔNG đoán, đọc file thật.
2. **Red** — thêm test mới vào `tests/test_booking.py`:
   - `test_confirmed_at_filters_by_doctor_id()`: tạo 2 lịch hẹn `confirmed` cùng
     `(date, time)` nhưng khác `doctor_id` (dùng `storage.add_appointment` trực tiếp hoặc
     mock `storage.list_appointments`), gọi `booking._confirmed_at(doctor_id_A, date, time)`
     → chỉ trả về lịch của bác sĩ A, KHÔNG trả về lịch của bác sĩ B (trước fix, hàm cũ không
     nhận tham số doctor_id nên test này phải fail vì `TypeError` — đúng Red state).
   - `test_book_appointment_different_doctors_same_slot_both_succeed()`: gọi
     `book_appointment` 2 lần, cùng `date_str`/`time_str`, khác `doctor_id` → cả 2 lần đều
     `(True, {...})`.
   - `test_book_appointment_same_doctor_same_slot_blocked()`: gọi `book_appointment` 2 lần
     giống hệt (cùng doctor_id) → lần 2 phải bị chặn như hành vi cũ (regression test, phải
     PASS cả trước và sau fix — xác nhận không phá hành vi C2).
   - `test_schema_uses_doctor_scoped_index()`: assert SQL string chứa
     `ux_appointments_doctor_slot` VÀ chứa `doctor_id` trong mệnh đề `ON appointments (...)`.
   - `test_insert_with_race_guard_uses_doctor_id_on_slot_collision(monkeypatch)`:
     **[Red team — Accept]** test riêng cho đúng chỗ dễ bỏ sót nhất — monkeypatch
     `storage.add_appointment` raise `UniqueViolation` với
     `constraint_name="ux_appointments_doctor_slot"`, monkeypatch `booking._confirmed_at`
     bằng 1 hàm ĐẾM số tham số nhận được (assert nhận đúng 3 tham số, tham số đầu đúng bằng
     `doctor_id` đã truyền vào `book_appointment`) → gọi `book_appointment(...)` → assert
     KHÔNG raise `TypeError`, trả về đúng response "đã có người đặt".
   - Sửa TẤT CẢ chỗ stub `_confirmed_at` cũ (theo grep, không theo số đếm cứng — xem
     Implementation Steps mục 3 ở Architecture) sang nhận 3 tham số NGAY Ở BƯỚC RED (bắt
     buộc, nếu không toàn bộ suite C2 cũ sẽ crash ở collection/chạy trước khi kịp thấy đúng
     Red state của test mới).
   - Chạy `pytest tests/test_booking.py -v` → xác nhận test mới fail đúng chỗ (TypeError vì
     `_confirmed_at` chưa nhận `doctor_id`), test cũ (đã sửa lambda) vẫn pass bình thường.
3. **Green** — sửa `storage.py` + `booking.py` theo Architecture.
4. Chạy lại `pytest tests/test_booking.py -v` → toàn bộ pass (cả test cũ lẫn mới).
5. Chạy `pytest tests/ -v` → không regress các phase khác (chỉ `test_booking.py` bị ảnh
   hưởng).

## Success Criteria

- [ ] `tests/test_booking.py` pass toàn bộ (test cũ đã cập nhật chữ ký + test mới).
- [ ] `_confirmed_at` nhận `doctor_id` làm tham số đầu, lọc đúng.
- [ ] UNIQUE INDEX tên mới `ux_appointments_doctor_slot` trên `(doctor_id, date, time)` được
  tạo TRƯỚC, index cũ `ux_appointments_slot` bị DROP SAU nếu tồn tại (đúng thứ tự fail-safe).
- [ ] `CREATE`/`DROP` là 2 lệnh `cur.execute()` riêng biệt, không gộp chung 1 chuỗi SQL.
- [ ] `_insert_with_race_guard` nhận diện đúng constraint mới Ở CẢ 2 chỗ dùng
  `_confirmed_at` bên trong nó (nhánh gọi từ `book_appointment` VÀ nhánh xử lý
  `UniqueViolation` nội bộ).

## Risk Assessment

- **Rủi ro migrate**: nếu Postgres thật đã chạy `init_schema()` với index cũ VÀ đã có dữ
  liệu (dù cùng giờ khác bác sĩ, giờ hợp lệ theo khoá mới) thì `DROP INDEX IF EXISTS` an
  toàn (không có ràng buộc dữ liệu bị vi phạm khi DROP). Rủi ro ngược lại (dữ liệu vi phạm
  khoá MỚI dù không vi phạm khoá cũ) không xảy ra về mặt logic: khoá mới CHẶT hơn (thêm
  doctor_id) nên any dữ liệu hợp lệ với khoá cũ vẫn hợp lệ với khoá mới (không có cách nào 2
  bản ghi trùng `(doctor_id,date,time)` mà không trùng `(date,time)`). An toàn để deploy.
- **[Red team] Chế độ JSON-fallback (`USE_DB=False`) không có bảo vệ DB-level dù trước hay
  sau fix này** — `init_schema()`/UNIQUE INDEX chỉ chạy khi `USE_DB=True`
  (`storage.py:26-27,105`). Đây là giới hạn CÓ SẴN từ trước H1/C2, không phải do phase này
  gây ra hay làm tệ hơn — chỉ làm rõ để tránh đọc câu "an toàn để deploy" ở trên như áp dụng
  cho cả JSON mode.
- **[Red team] Rủi ro rollback/downgrade**: nếu sau khi deploy fix này rồi rollback code về
  bản CŨ (check `constraint_name == "ux_appointments_slot"`) trong khi DB đã migrate sang
  tên index MỚI, code cũ sẽ không nhận diện được collision đúng slot nữa → rơi vào nhánh
  "lỗi hệ thống chung" thay vì "khung giờ đã có người đặt". Chấp nhận rủi ro này (nhất quán
  tinh thần "1 process, không xây thêm hạ tầng" đã áp dụng xuyên suốt) — nếu cần rollback
  code, phải kèm bước revert tên index thủ công, ghi chú lại đây cho người vận hành sau này.
- **Không có Postgres local để test thật** — kế thừa hạn chế đã ghi nhận từ C2, verify qua
  monkeypatch + review SQL, ghi rõ trong báo cáo hoàn thành.
- **Test cũ dùng stub sai chữ ký nếu quên sửa** sẽ crash toàn bộ `test_booking.py`, không
  chỉ test mới — đây là lý do bước Red bắt buộc sửa TẤT CẢ chỗ stub (theo grep, không theo
  số đếm) TRƯỚC khi viết test mới, không phải sau.
