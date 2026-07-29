---
phase: 2
title: Fail-Loud Storage Guards
status: completed
priority: P2
dependencies:
  - 1
---

# Phase 2: Fail-Loud Storage Guards

## Overview

`app/core/storage.py::create_user`/`get_user_by_username`/`get_user_by_id`
khi `not USE_DB` hiện âm thầm trả `True`/`None` (giả vờ thành công/không tìm
thấy) thay vì báo lỗi — silent data loss risk thật (vd `create_user` trả
`True` nhưng KHÔNG lưu gì). Đổi 3 hàm này raise 1 exception rõ ràng khi không
có DB, để caller biết ngay thay vì tưởng thành công.

**Phụ thuộc Phase 1:** `auth.resolve_user_from_token()` (Phase 1, đã bắt
`except Exception` rộng sau red-team) tự động bắt được exception mới này —
Phase 2 KHÔNG cần sửa `auth.py`'s except-clause nữa, chỉ cần 1 test verify.
Đây vẫn là lý do thứ tự phase bắt buộc (Phase 2 dựa vào thiết kế đã chốt của
Phase 1).

**[Red-team 2026-07-30]** 2 finding bổ sung sau review đối kháng (chi tiết ở
`plan.md` § Red Team Review):
- Message lỗi của `UserStoreUnavailableError` không được lộ nguyên văn ra
  public endpoint (`/api/login`, `/api/register`) — hiện `except Exception as
  e: return jsonify({"error": str(e)}), 500` sẽ in thẳng "cần DATABASE_URL
  (Postgres)..." cho bất kỳ ai gọi API, kể cả chưa đăng nhập.
- `auth.create_user_account()` có 1 `except Exception` rộng bao ngoài lời gọi
  `storage.create_user` — cần catch `UserStoreUnavailableError` riêng, re-raise
  nguyên vẹn, tránh bị bọc thành `AuthError` chung chung (hiện unreachable vì
  `get_user_by_username` raise trước, nhưng vá cho chắc — rẻ, đúng nguyên tắc
  không nuốt lỗi âm thầm).

## Requirements

- Functional: `create_user`/`get_user_by_username`/`get_user_by_id` raise
  `storage.UserStoreUnavailableError` (exception mới, kế thừa `Exception`)
  khi `not USE_DB`, thay vì trả `True`/`None`.
- Functional: hành vi khi `USE_DB=True` giữ nguyên 100% (không đổi SQL, không
  đổi return shape khi tìm thấy/không tìm thấy trong DB thật).
- Functional: `auth.resolve_user_from_token()` (Phase 1, đã bắt `Exception`
  rộng) coi `UserStoreUnavailableError` như "chưa đăng nhập" (`None`) — KHÔNG
  cần sửa code, chỉ cần 1 test xác nhận hành vi này giữ đúng.
- Functional: `auth.create_user_account()` catch `storage.UserStoreUnavailableError`
  riêng và re-raise nguyên vẹn (không bọc thành `AuthError`).
- Functional: `main.py::api_login()` và `api_register()` catch
  `storage.UserStoreUnavailableError` riêng, trả message **chung chung** cho
  client (không lộ "DATABASE_URL"/"Postgres"), log chi tiết thật ra server
  console/log.

## Architecture

```python
# app/core/storage.py, gần UserNotFoundError/DuplicateUsernameError hiện có
class UserStoreUnavailableError(Exception):
    """User store cần Postgres (DATABASE_URL) — không có JSON-mode fallback."""
    pass
```

3 hàm đổi từ:
```python
if not USE_DB:
    return True   # hoặc None
```
thành:
```python
if not USE_DB:
    raise UserStoreUnavailableError(
        "User accounts cần DATABASE_URL (Postgres) — không hỗ trợ JSON-file mode."
    )
```

`app/core/auth.py::create_user_account()` — thêm 1 except clause trước
`except Exception as e:` hiện có (dòng ~166-169):
```python
except storage.DuplicateUsernameError:
    raise UserAlreadyExistsError(f"Username '{username}' đã tồn tại")
except storage.UserStoreUnavailableError:
    raise  # re-raise nguyên vẹn, không bọc thành AuthError chung chung
except Exception as e:
    raise AuthError(f"Lỗi tạo user: {e}")
```

`app/main.py::api_login()` — thêm except clause trước `except Exception as e:`
hiện có (dòng ~287-290):
```python
except auth.InvalidCredentialsError:
    return jsonify({"error": "Username hoặc password sai"}), 401
except storage.UserStoreUnavailableError:
    print("[auth] api_login lỗi: user store cần DATABASE_URL nhưng chưa cấu hình")
    return jsonify({"error": "Lỗi hệ thống, vui lòng thử lại sau."}), 500
except Exception as e:
    return jsonify({"error": str(e)}), 500
```

`app/main.py::api_register()` — tương tự, thêm except clause trước
`except Exception as e:` hiện có (dòng ~343-346):
```python
except auth.UserAlreadyExistsError as e:
    return jsonify({"error": str(e)}), 409
except storage.UserStoreUnavailableError:
    print("[auth] api_register lỗi: user store cần DATABASE_URL nhưng chưa cấu hình")
    return jsonify({"error": "Lỗi hệ thống, vui lòng thử lại sau."}), 500
except Exception as e:
    return jsonify({"error": str(e)}), 500
```

## Related Code Files

- Modify: `app/core/storage.py` (thêm `UserStoreUnavailableError`, sửa 3 hàm)
- Modify: `app/core/auth.py` (`create_user_account` — thêm except clause riêng)
- Modify: `app/main.py` (`api_login`, `api_register` — thêm except clause riêng, KHÔNG sửa `resolve_user_from_token`/`require_auth`/các route khác)
- Modify (test, viết trước theo TDD): `tests/test_storage.py`
- Modify (test, viết trước theo TDD): `tests/test_auth_demo.py`
- Modify (test, viết trước theo TDD): `tests/test_app_admin.py` (hoặc file HTTP-level phù hợp)

## Implementation Steps

1. **RED** — thêm vào `tests/test_storage.py` (theo pattern có sẵn trong file:
   `monkeypatch.setattr(storage, "USE_DB", False)`):
   - `test_create_user_raises_without_db` — `pytest.raises(storage.UserStoreUnavailableError)`
   - `test_get_user_by_username_raises_without_db`
   - `test_get_user_by_id_raises_without_db`
   Chạy `pytest tests/test_storage.py -q` — 3 test mới FAIL (exception class
   chưa tồn tại → `AttributeError`), test cũ vẫn pass.
2. **RED** — thêm vào `tests/test_auth_demo.py`:
   - `test_resolve_user_from_token_db_unavailable` — monkeypatch
     `auth.storage.get_user_by_id` để raise `storage.UserStoreUnavailableError`,
     gọi `resolve_user_from_token(valid_token)` → assert trả `None`. (Test này
     có thể PASS ngay từ đầu vì Phase 1 đã bắt `Exception` rộng — chạy để xác
     nhận, không phải để tạo RED; nếu pass ngay, ghi chú trong commit rằng đây
     là regression-lock test, không phải TDD-RED thật.)
   - `test_create_user_account_propagates_store_unavailable` — monkeypatch
     `auth.storage.create_user` raise `storage.UserStoreUnavailableError`,
     gọi `auth.create_user_account(...)` → assert raise đúng
     `storage.UserStoreUnavailableError` (KHÔNG bị bọc thành `auth.AuthError`).
     Test này FAIL trước khi sửa (hiện bị bọc thành `AuthError`).
   Chạy `pytest tests/test_auth_demo.py -q` — xác nhận đúng test nào RED.
3. **RED** — thêm vào `tests/test_app_admin.py` (client HTTP-level, dùng
   `main.app.test_client()`):
   - `test_login_hides_db_config_details_when_unavailable` — monkeypatch
     `main.storage.get_user_by_username`
     (hoặc tương đương chỗ `auth.login` gọi) raise `storage.UserStoreUnavailableError`,
     POST `/api/login` → assert status `500`, assert `"DATABASE_URL"` và
     `"Postgres"` KHÔNG có trong response JSON.
   Chạy `pytest tests/test_app_admin.py -q` — test mới FAIL (hiện lộ nguyên văn).
4. **GREEN** — implement `UserStoreUnavailableError` + sửa 3 hàm trong
   `storage.py`. Chạy `pytest tests/test_storage.py -q` — 3 test bước 1 pass.
5. **GREEN** — sửa `auth.create_user_account()` (thêm except clause riêng).
   Chạy `pytest tests/test_auth_demo.py -q` — tất cả pass.
6. **GREEN** — sửa `main.py::api_login()` và `api_register()` (thêm except
   clause riêng). Chạy `pytest tests/test_app_admin.py -q` — test bước 3 pass.
7. Full suite: `PYTHONPATH=/tmp/shi-pydeps python3.12 -m pytest tests/ -q` —
   so baseline: 4 fail cũ giữ nguyên, không fail mới, số pass tăng đúng bằng
   test mới (Phase 1 + Phase 2 cộng dồn).

## Success Criteria

- [x] `storage.UserStoreUnavailableError` tồn tại, 3 hàm raise đúng khi `not USE_DB`
- [x] Hành vi khi `USE_DB=True` không đổi (không có test nào cho nhánh này bị đỏ)
- [x] `resolve_user_from_token` trả `None` (không crash) khi storage raise `UserStoreUnavailableError`
- [x] `create_user_account` propagate `UserStoreUnavailableError` nguyên vẹn, không bọc thành `AuthError`
- [x] `api_login`/`api_register` trả 500 với message chung chung khi DB chưa cấu hình — không lộ "DATABASE_URL"/"Postgres" ra response
- [x] Full suite: baseline 4 fail giữ nguyên, không fail mới

## Risk Assessment

- **Risk:** nơi nào đó ngoài phạm vi đã grep (bước lập plan) gọi trực tiếp
  `storage.create_user`/`get_user_by_*` mà không qua `auth.py` — sẽ bất ngờ
  nhận exception mới thay vì `True`/`None`. **Mitigation:** đã grep toàn repo
  (`app/`, `scripts/`) trước khi viết plan — chỉ có `auth.py` (2 hàm) và
  `scripts/seed_users.py` (đã tự guard `if not storage.USE_DB` trước khi gọi,
  không bị ảnh hưởng). Nếu implement phát hiện call site khác không có trong
  danh sách này, dừng lại và cập nhật plan trước khi tiếp tục.
- **Risk (rollback coupling):** fix ở Phase 2 nằm trong `storage.py` (file
  riêng của Phase 2) + `auth.py`/`main.py` (except clause mới, không sửa lại
  code Phase 1 đã viết). Vẫn có phụ thuộc 1 chiều: revert riêng Phase 2 an
  toàn (Phase 1's `except Exception` rộng tự nhiên không còn bắt được gì đặc
  biệt, không lỗi import). Nhưng revert riêng Phase 1 mà giữ Phase 2 SẼ lỗi
  (`storage.UserStoreUnavailableError` vẫn được raise nhưng không ai định
  nghĩa nếu storage.py cũng bị revert theo) — nếu cần rollback, rollback theo
  thứ tự ngược: Phase 2 trước, Phase 1 sau.
