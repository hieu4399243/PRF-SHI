---
phase: 1
title: Extract Auth Helper
status: completed
priority: P2
dependencies: []
---

# Phase 1: Extract Auth Helper

## Overview

Gộp logic "đọc cookie `auth_token` → `verify_jwt` → `get_user_by_id`" — hiện
lặp lại tay 6 lần — thành 1 helper thuần trong `app/core/auth.py`. Giữ
nguyên cách xử lý fail (redirect vs JSON 401/403) ở từng call site vì đó là
khác biệt hợp lý, không phải trùng lặp.

**[Red-team 2026-07-30]** 2 quyết định sau khi review đối kháng (chi tiết ở
`plan.md` § Red Team Review):
1. Helper bắt **`Exception` rộng** (không chỉ `AuthError`) — khớp với hành vi
   fail-safe cũ của `_check_admin`/`_get_current_doctor` (vốn dùng
   `except Exception`). Lý do: nếu chỉ bắt `AuthError`, một lỗi bất ngờ (vd
   Postgres transient error) sẽ văng thành Flask 500 thay vì gracefully coi
   như "chưa đăng nhập" — regression thật, 3 reviewer độc lập phát hiện.
2. **Thay đổi contract có chủ đích:** `require_auth`/`api_me` trước đây phân
   biệt 401 (token invalid) vs 404 (token hợp lệ nhưng user đã bị xóa khỏi
   DB). Sau refactor, cả 2 case đều thành 401 vì helper trả `None` đồng nhất.
   Chấp nhận đổi vì: (a) không có test nào khóa hành vi 404 lại
   (`grep -rn "User không tồn tại" tests/` → rỗng), (b) case hiếm (token còn
   hạn nhưng user bị xóa), (c) client xử lý 401/404 như nhau (redirect login).

## Requirements

- Functional: hành vi HTTP của mọi route auth-gated giữ nguyên, NGOẠI TRỪ
  thay đổi có chủ đích ở trên (404→401 khi user không tồn tại dù token hợp lệ).
- Functional: `admin_api.py::_check_admin()` và `doctor_api.py::_get_current_doctor()`
  **phải giữ nguyên tên hàm** — `tests/test_doctor_api.py` monkeypatch trực
  tiếp `doctor_api_module._get_current_doctor`, đổi tên sẽ phá test.
- Functional: helper phải bắt `Exception` rộng (không chỉ `AuthError`) —
  bất kỳ lỗi nào trong quá trình verify/lookup đều coi như "chưa đăng nhập",
  không để lộ 500/stack trace.
- Non-functional: không đổi cơ chế JWT/bcrypt/cookie; không đổi
  `require_auth()` decorator's public signature (`allowed_roles=None`).

## Architecture

Thêm vào `app/core/auth.py` (không import Flask ở đây — giữ `core/` framework-agnostic,
nhận `request` object đã có sẵn từ caller, không import `flask.request` trực tiếp
trong `auth.py` để tránh lệch với module-boundary rule hiện tại):

```python
def resolve_user_from_token(token: str | None):
    """Đọc token, verify, load user. Trả None nếu bất kỳ bước nào fail
    (không token, token invalid/expired, user không tồn tại, lỗi storage
    bất kỳ kể cả khi chưa cấu hình DB). Không raise — bắt Exception rộng
    có chủ đích, khớp hành vi fail-safe cũ của _check_admin/_get_current_doctor.
    """
    if not token:
        return None
    try:
        payload = verify_jwt(token)
        return storage.get_user_by_id(payload["sub"])
    except Exception:
        return None
```

Vì except-clause đã rộng (`Exception`, không chỉ `AuthError`), Phase 2 KHÔNG
cần sửa lại hàm này khi thêm `storage.UserStoreUnavailableError` — exception
mới đó tự động bị bắt. Phase 2 chỉ cần 1 test xác nhận điều này (xem
`phase-02-fail-loud-storage-guards.md`).

Từng call site refactor như sau (giữ nguyên hành vi fail, chỉ thay phần lookup;
`require_auth`/`api_me` đổi 404→401 cho case "token hợp lệ nhưng user không
tồn tại" — xem Overview § quyết định 2):

- `app/main.py::require_auth()` decorator (dòng ~80-98): thay 3 dòng
  `token = ...`, `payload = auth.verify_jwt(token)`, `user = storage.get_user_by_id(...)`
  bằng `user = auth.resolve_user_from_token(request.cookies.get("auth_token"))`;
  bỏ nhánh `except auth.AuthError` (helper không raise nữa); `user is None` →
  401 "Chưa login" (gộp cả 2 case cũ); `allowed_roles` check giữ nguyên → 403.
- `app/main.py::login_page()` (dòng ~166-180): tương tự, thay bằng 1 dòng gọi
  helper, giữ nguyên if/elif redirect theo role.
- `app/main.py::admin_page()` (dòng ~242-254): tương tự.
- `app/main.py::api_login()`: KHÔNG đổi (không đọc token, chỉ set cookie).
- `app/main.py::api_me()` (dòng ~349-371): tương tự, `user is None` → 401
  "Chưa login" (gộp case cũ 404 "User không tồn tại" vào 401).
- `app/admin_api.py::_check_admin()`: thân hàm đổi thành gọi helper, kiểm tra
  `user and user["role"] == "admin"`; **giữ nguyên tên hàm và signature**
  (không tham số, trả `bool`).
- `app/doctor_api.py::_get_current_doctor()`: thân hàm đổi thành gọi helper,
  kiểm tra `user and user.get("role") == "doctor" and user.get("doctor_id")`,
  trả `user` hoặc `None`; **giữ nguyên tên hàm và signature**.

## Related Code Files

- Modify: `app/core/auth.py` (thêm `resolve_user_from_token`)
- Modify: `app/main.py` (4 call site: `require_auth`, `login_page`, `admin_page`, `api_me` — không đổi `api_login`/`api_logout`/`api_register`)
- Modify: `app/admin_api.py` (`_check_admin`)
- Modify: `app/doctor_api.py` (`_get_current_doctor`)
- Modify (test, viết trước theo TDD): `tests/test_auth_demo.py` — thêm test cho `resolve_user_from_token`

## Implementation Steps

1. **RED** — thêm vào `tests/test_auth_demo.py` các test thật (dùng `assert`,
   không `print`) cho hàm mới, trước khi nó tồn tại (sẽ fail với `AttributeError`):
   - `test_resolve_user_from_token_no_token` — `auth.resolve_user_from_token(None)` → `None`.
   - `test_resolve_user_from_token_invalid_token` — token rác (`"not-a-jwt"`) → `None`.
   - `test_resolve_user_from_token_expired` — dùng pattern có sẵn trong
     `test_auth_demo.py::test_expired_token_rejected` (tự build JWT hết hạn
     bằng `jwt.encode` trực tiếp với `exp` quá khứ) → `None`.
   - `test_resolve_user_from_token_valid` — monkeypatch `auth.storage.get_user_by_id`
     trả 1 dict user giả (không cần Postgres thật), tạo token hợp lệ bằng
     `auth.generate_jwt(...)` → hàm trả đúng dict đó.
   - `test_resolve_user_from_token_unexpected_storage_error` — monkeypatch
     `auth.storage.get_user_by_id` để raise 1 exception generic (vd
     `RuntimeError("boom")`, không phải `AuthError`) → assert hàm vẫn trả
     `None`, không propagate. Test này khóa lại quyết định "bắt Exception
     rộng" ở trên — không được xóa/làm yếu khi Phase 2 chạy.
   Chạy `pytest tests/test_auth_demo.py -q` — xác nhận 5 test mới FAIL (hàm
   chưa tồn tại), test cũ trong file vẫn pass.
2. **GREEN** — implement `resolve_user_from_token` trong `app/core/auth.py`
   như thiết kế trên (chú ý: `except Exception`, không phải `except AuthError`).
   Chạy lại `pytest tests/test_auth_demo.py -q` — 5 test mới phải pass, không
   test nào trong file cũ bị đỏ thêm.
3. Refactor `app/main.py` — 4 call site (`require_auth`, `login_page`,
   `admin_page`, `api_me`) dùng `auth.resolve_user_from_token`. Sau mỗi call
   site, chạy `pytest tests/test_app_admin.py tests/test_app_hardening.py
   tests/test_app_ics.py -q` để bắt regression sớm (một số sẽ vẫn fail do
   baseline không-Postgres đã ghi ở `plan.md` — so sánh đúng bằng số/tên fail
   với baseline, không phải bằng 0 fail).
4. Refactor `app/admin_api.py::_check_admin()`. Chạy `pytest tests/test_app_admin.py -q`.
5. Refactor `app/doctor_api.py::_get_current_doctor()`. Chạy `pytest tests/test_doctor_api.py -q`
   — đặc biệt xác nhận `test_doctor_schedule_requires_date` và
   `test_doctor_appointments_force_current_doctor` (dùng `monkeypatch.setattr(doctor_api_module, "_get_current_doctor", ...)`)
   vẫn pass nguyên vẹn — đây là bằng chứng tên hàm/signature không đổi.
6. Full suite: `PYTHONPATH=/tmp/shi-pydeps python3.12 -m pytest tests/ -q` —
   so với baseline `175 passed, 4 failed, 1 skipped`: số pass phải TĂNG thêm
   đúng số test mới ở bước 1, 4 fail baseline không đổi tên/số lượng, không
   fail mới nào phát sinh.

## Success Criteria

- [x] `auth.resolve_user_from_token()` tồn tại, có 5 test pass (no-token, invalid, expired, valid, unexpected-storage-error)
- [x] 6 bản logic auth-check trùng lặp trong `main.py`/`admin_api.py`/`doctor_api.py` giảm còn 0 (chỉ còn 1 định nghĩa trong `auth.py`) — verify bằng `grep -c "verify_jwt" app/main.py app/admin_api.py app/doctor_api.py` = 0 cho cả 3 file (helper nằm ngoài, trong `app/core/auth.py`)
- [x] `_check_admin()` và `_get_current_doctor()` giữ nguyên tên + signature
- [x] `tests/test_doctor_api.py` (monkeypatch-based) pass không đổi
- [x] Full suite: baseline 4 fail giữ nguyên (tên/lý do), không fail mới, số pass tăng đúng bằng test mới thêm ở Phase 1

## Risk Assessment

- **Risk (đã phát hiện qua red-team, đã fix trong thiết kế trên):** nếu helper
  chỉ bắt `AuthError` (thiết kế ban đầu trước red-team), một lỗi bất ngờ (vd
  Postgres transient error) sẽ propagate thành Flask 500 thay vì graceful
  401/None như code cũ (`_check_admin`/`_get_current_doctor` vốn dùng
  `except Exception` rộng) — vi phạm chính yêu cầu "giữ nguyên hành vi HTTP".
  **Mitigation:** helper dùng `except Exception` rộng (xem Architecture),
  khóa lại bằng `test_resolve_user_from_token_unexpected_storage_error`.
- **Risk:** quên 1 trong 6 call site → vẫn còn duplicate sót lại.
  **Mitigation:** bước 6 dùng `grep -c "verify_jwt"` làm acceptance check
  định lượng, không dựa vào đọc mắt.
