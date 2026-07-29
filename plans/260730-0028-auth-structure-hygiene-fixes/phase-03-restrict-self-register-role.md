---
phase: 3
title: Restrict Self-Register Role
status: completed
priority: P2
dependencies:
  - 2
---

# Phase 3: Restrict Self-Register Role

## Overview

`POST /api/register` (public, không cần auth) hiện chấp nhận `role` bất kỳ
trong `["admin", "doctor", "guest"]` từ request body — cho phép bất kỳ ai tự
tạo tài khoản `admin`. `app/templates/login.html` (form tự đăng ký) chỉ
expose UI cho `guest`/`doctor` — không có option `admin`. Sửa backend khớp
đúng với UI: chỉ chấp nhận `guest`/`doctor` qua self-register; `admin` chỉ
tạo được qua `scripts/seed_users.py` hoặc thao tác trực tiếp trên DB.

**[Red-team 2026-07-30]** Mở rộng scope sau review đối kháng (chi tiết ở
`plan.md` § Red Team Review): chỉ chặn `role=admin` là KHÔNG đủ — `doctor_id`
gửi kèm khi `role=doctor` không được validate, và `doctor_id` lộ công khai
qua chatbot không cần login (`app/chatbot/steps/doctor_step.py`) + bảng
`users` không có UNIQUE constraint trên `doctor_id`
(`app/core/storage.py:107-116`). Kẻ tấn công có thể tự đăng ký `role=doctor`
với `doctor_id` **thật** của 1 bác sĩ đang hành nghề → mạo danh, đọc được
`patient_name`/`patient_phone` qua `/api/doctor/appointments` v.v. Phase này
giờ validate `doctor_id` khớp catalog thật VÀ chưa bị user nào khác claim.

**Phụ thuộc Phase 2:** việc check "doctor_id đã bị claim chưa" cần đọc bảng
`users` — dùng cùng convention fail-loud của Phase 2
(`storage.UserStoreUnavailableError` khi không có DB). Vì tự-đăng-ký-doctor
vốn đã cần DB (qua `create_user_account`), thêm phụ thuộc này không giảm khả
năng chạy độc lập trong thực tế — chỉ hình thức hóa lại thứ tự đã ghi ở
`plan.md` (Phase 1 → 2 → 3, plan.md đã luôn nói vậy dù bản nháp phase-03 ban
đầu ghi nhầm "độc lập" — sửa lại cho khớp).

## Requirements

- Functional: `POST /api/register` với `role=admin` → `400 {"error": "Role
  không hợp lệ"}` (dùng lại message lỗi hiện có, không tạo message mới).
- Functional: `role=guest` tiếp tục hoạt động y hệt trước (không đổi).
- Functional: `role=doctor` — thêm 2 điều kiện mới:
  1. `doctor_id` phải khớp 1 bác sĩ thật trong catalog (`booking.all_doctors()`)
     → sai/thiếu → `400 {"error": "doctor_id không hợp lệ"}`.
  2. `doctor_id` đó chưa được user nào khác claim → đã bị claim →
     `409 {"error": "doctor_id đã được đăng ký"}`.
- Functional: `role` thiếu (không có key `role` trong body) → mặc định
  `"guest"` (hành vi hiện tại của `data.get("role", "guest")`). LƯU Ý: `role`
  là chuỗi rỗng (`""`) KHÔNG được default — vẫn đi thẳng vào check
  `role not in [...]` → `400`, giống hệt hành vi hiện tại (không đổi gì ở
  đây, chỉ làm rõ để tránh hiểu nhầm "rỗng → guest").
- Non-functional: KHÔNG sửa `app/templates/login.html` (UI đã đúng, chỉ
  backend cần khớp theo).

## Architecture

`app/core/storage.py` — thêm 1 hàm mới, cùng pattern với `get_user_by_username`
(fail-loud khi không có DB, theo Phase 2):

```python
def get_user_by_doctor_id(doctor_id):
    """Lấy user (role=doctor) đã claim doctor_id này. Trả None nếu chưa ai claim.

    Raises:
        UserStoreUnavailableError: không có DATABASE_URL.
    """
    if not USE_DB:
        raise UserStoreUnavailableError(
            "User accounts cần DATABASE_URL (Postgres) — không hỗ trợ JSON-file mode."
        )
    init_schema()
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, username, password_hash, role, email, doctor_id, created_at, updated_at "
            "FROM users WHERE doctor_id = %s AND role = 'doctor'",
            (doctor_id,),
        )
        row = cur.fetchone()
        if row:
            return {
                "id": row[0], "username": row[1], "password_hash": row[2],
                "role": row[3], "email": row[4], "doctor_id": row[5],
                "created_at": row[6], "updated_at": row[7],
            }
    return None
```

`app/main.py::api_register()` — đổi role-check + thêm validate `doctor_id`
(sau dòng role-check hiện có, trước khi gọi `auth.create_user_account`):

```python
# Role check (đổi từ ["admin","doctor","guest"]):
if role not in ["guest", "doctor"]:
    return jsonify({"error": "Role không hợp lệ"}), 400

# Validate doctor_id khi role=doctor (MỚI):
if role == "doctor":
    if not doctor_id or not any(d["id"] == doctor_id for d in booking.all_doctors()):
        return jsonify({"error": "doctor_id không hợp lệ"}), 400
    try:
        if storage.get_user_by_doctor_id(doctor_id):
            return jsonify({"error": "doctor_id đã được đăng ký"}), 409
    except storage.UserStoreUnavailableError:
        pass  # để create_user_account bên dưới raise lỗi rõ ràng (Phase 2 xử lý)
```

`booking` đã được import sẵn ở `app/main.py:23`
(`from .booking import service as booking`) — không cần import mới.

## Related Code Files

- Modify: `app/core/storage.py` (thêm `get_user_by_doctor_id`)
- Modify: `app/main.py` (dòng ~327, hàm `api_register` — role check + doctor_id validate)
- Modify (test, viết trước theo TDD): `tests/test_storage.py`
- Modify (test, viết trước theo TDD): `tests/test_app_admin.py` (hoặc file
  mới nếu muốn tách riêng auth-route test — quyết định lúc implement dựa vào
  độ dài file hiện tại, ưu tiên thêm vào file có sẵn nếu <400 dòng theo
  code-standards.md)

## Implementation Steps

1. **RED** — thêm vào `tests/test_storage.py`:
   - `test_get_user_by_doctor_id_raises_without_db` — `pytest.raises(storage.UserStoreUnavailableError)`.
   - `test_get_user_by_doctor_id_returns_none_when_unclaimed` (cần `USE_DB=True`
     + DB thật hoặc skip nếu không có — theo pattern `test_auth_demo.py` check
     `storage.USE_DB` trước khi chạy phần cần DB thật).
   Chạy `pytest tests/test_storage.py -q` — test đầu FAIL (hàm chưa tồn tại).
2. **RED** — thêm test HTTP-level vào `tests/test_app_admin.py` (dùng
   `client = main.app.test_client()`, pattern có sẵn trong `_client()`):
   - `test_register_rejects_admin_role` — POST `/api/register` với
     `role="admin"` → assert `400`, assert `"error"` trong response.
   - `test_register_rejects_invalid_doctor_id` — POST với `role="doctor"`,
     `doctor_id="khong-ton-tai"` → assert `400`, message "doctor_id không hợp lệ".
   - `test_register_rejects_missing_doctor_id_for_doctor_role` — POST với
     `role="doctor"`, không có `doctor_id` → assert `400`.
   - `test_register_allows_guest_role` — POST với `role="guest"` → assert
     KHÔNG phải 400 với message "Role không hợp lệ" (môi trường không DB có
     thể trả 500 "Lỗi hệ thống..." từ Phase 2 — đó KHÔNG phải fail của test
     này, chỉ assert response không bị chặn bởi role-validation).
   - `test_register_allows_valid_doctor_id` — monkeypatch
     `main.booking.all_doctors` trả 1 doctor giả (vd `[{"id": "bs_test_01", ...}]`),
     POST với `role="doctor"`, `doctor_id="bs_test_01"` → assert response
     KHÔNG phải 400 "doctor_id không hợp lệ" (có thể 500/409 tùy môi trường
     DB — chỉ assert qua được validate doctor_id).
   Chạy `pytest tests/test_app_admin.py -q` — xác nhận đúng những test cần
   FAIL (role=admin hiện được chấp nhận; doctor_id hiện không được validate).
3. **GREEN** — thêm `storage.get_user_by_doctor_id`. Chạy `pytest
   tests/test_storage.py -q` — pass.
4. **GREEN** — sửa `app/main.py::api_register()` (role check + doctor_id
   validate). Chạy `pytest tests/test_app_admin.py -q` — tất cả pass.
5. Full suite: `PYTHONPATH=/tmp/shi-pydeps python3.12 -m pytest tests/ -q` —
   so baseline: 4 fail cũ giữ nguyên, không fail mới, số pass tăng đúng bằng
   test mới (cộng dồn cả 3 phase).

## Success Criteria

- [x] `POST /api/register` với `role=admin` → 400 "Role không hợp lệ"
- [x] `role=doctor` với `doctor_id` không có trong catalog → 400 "doctor_id không hợp lệ"
- [x] `role=doctor` với `doctor_id` đã bị user khác claim → 409 "doctor_id đã được đăng ký"
- [x] `role=guest` không bị ảnh hưởng bởi thay đổi này
- [x] `app/templates/login.html` không bị sửa
- [x] Full suite: baseline 4 fail giữ nguyên, không fail mới

## Risk Assessment

- **Risk:** nếu có test/script/tool nào khác (ngoài `login.html`) dựa vào
  việc tự đăng ký `role=admin` qua `/api/register` (vd script setup demo cũ),
  sẽ break. **Mitigation:** đã grep `api/register` toàn repo lúc lập plan —
  chỉ `login.html` gọi endpoint này, không có script/test nào khác phụ thuộc
  `role=admin` qua route này (`scripts/seed_users.py` tạo admin bằng cách gọi
  thẳng `storage.create_user`, không qua HTTP endpoint).
- **Risk (còn lại sau fix, chấp nhận được):** validate `doctor_id` chỉ chặn
  được việc claim `doctor_id` đã có người dùng — không chặn "race" 2 request
  đồng thời cùng `doctor_id` chưa ai claim (TOCTOU giữa check và insert, vì
  không có UNIQUE constraint DB-level). Ngoài scope P2 hygiene fix này (cần
  migration thêm UNIQUE constraint, item riêng nếu muốn triệt để) — ghi nhận
  làm known-limitation, không phải regression so với trước khi có phase này.
