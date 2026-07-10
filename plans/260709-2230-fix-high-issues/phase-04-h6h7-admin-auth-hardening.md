---
phase: 4
title: "H6H7 Admin Auth Hardening"
status: pending
priority: P2
dependencies: []
---

# Phase 4: H6+H7 — Khoá admin qua query string + secret mặc định

## Overview

- **H6**: `_check_admin()` chấp nhận khoá qua `?key=` (query string) NGOÀI header
  `X-Admin-Key` — query string bị log lại trong access log server, lịch sử trình duyệt,
  header `Referer` khi điều hướng sang trang khác → lộ khoá admin.
- **H7**: `SECRET_KEY`/`ADMIN_KEY` mặc định (`"shi-nha-khoa-demo-key"`/`"shi-admin-demo"`)
  không cảnh báo gì khi chạy — nếu deploy production quên set biến môi trường, admin panel
  và session Flask dùng khoá đoán được. Đã ghi trong docs nhưng ISSUES.md yêu cầu "nhắc lại
  vì nghiêm trọng" → thêm cảnh báo runtime.

**Đã xác nhận qua đọc `templates/admin.html`**: UI admin CHỈ dùng header `X-Admin-Key`
(`fetch(path, {headers:{"X-Admin-Key":KEY}})`), KHÔNG dùng `?key=` ở bất kỳ đâu — bỏ hỗ trợ
query string KHÔNG làm vỡ UI admin hiện có.

**[Red team — Accept, Finding "claim '?key= không ai dùng' bị doc mâu thuẫn"]** Xác nhận
CHƯA đầy đủ — `docs/getting-started-guide.md` (dòng ~136-138) có ví dụ curl "Test nhanh
bằng dòng lệnh" DÙNG `?key=` (`curl ".../api/admin/appointments?status=confirmed&key=shi-admin-demo"`).
Đây là workflow test đã tài liệu hoá, không phải "không ai dùng". Phase này PHẢI cập nhật
doc đó sang dùng header (xem Related Code Files), nếu không dev/người chấm bài theo hướng
dẫn cũ sẽ gặp `401` không rõ lý do.

## Requirements

- Functional:
  - H6: `_check_admin()` chỉ chấp nhận header `X-Admin-Key`, so sánh bằng
    `hmac.compare_digest` (constant-time). Request dùng `?key=` (không kèm header đúng)
    phải bị từ chối (401), y hệt như không cung cấp khoá.
  - H7: khi app khởi động (module load, chạy cả khi import bởi gunicorn lẫn `python app.py`
    trực tiếp), nếu `SECRET_KEY` hoặc `ADMIN_KEY` vẫn là giá trị demo mặc định → in cảnh báo
    rõ ràng ra stdout. THÊM: khi chạy trực tiếp (`if __name__ == "__main__":`) với
    `debug=True`+`host="0.0.0.0"`, in cảnh báo riêng về rủi ro RCE qua Werkzeug debugger.
    KHÔNG chặn app chạy (vẫn phải chạy được cho demo/dev — chỉ cảnh báo, không phải
    hard-fail, đúng như tinh thần "đã ghi trong docs, nhắc lại" chứ không phải yêu cầu đổi
    hành vi mặc định).
- Non-functional: Không đổi route path, không đổi response shape cho request ĐÃ dùng đúng
  header (hành vi thành công giữ nguyên 100%).

## Architecture

```python
def _check_admin():
    """Chỉ chấp nhận khoá qua header X-Admin-Key — query string bị log lại
    (access log, lịch sử trình duyệt, Referer) nên không còn được chấp nhận."""
    key = request.headers.get("X-Admin-Key", "")
    return hmac.compare_digest(key, ADMIN_KEY)
```
**[Red team — Accept, Finding "so sánh không constant-time"]** Dùng `hmac.compare_digest`
thay vì `==` — so sánh key bằng `==` dừng ngay khi gặp ký tự đầu tiên sai (short-circuit),
tạo kênh side-channel qua thời gian phản hồi để dò từng ký tự của `ADMIN_KEY`. Thêm
`import hmac` ở đầu `app.py`. Việc bỏ `?key=` chỉ đóng 1 đường lộ khoá (log/Referer), không
tự động vá lỗ hổng timing này — phải sửa cả hai trong cùng phase "hardening".

**[Red team — Accept, Finding "comment cũ vẫn nói còn hỗ trợ ?key="]** Comment banner phía
trên `_check_admin()` (hiện tại: "Bảo vệ bằng khóa ADMIN_KEY (header 'X-Admin-Key' hoặc
query '?key=')") PHẢI cập nhật, bỏ phần "hoặc query '?key='" — nếu để nguyên, người sau đọc
comment sẽ tưởng `?key=` vẫn hoạt động và có thể vô tình thêm lại (tái tạo H6).

Cảnh báo H7 tách thành hàm THUẦN (không side-effect ngoài print), đặt ngay sau khai báo
`ADMIN_KEY`:
```python
ADMIN_KEY = os.environ.get("ADMIN_KEY", "shi-admin-demo")

_DEFAULT_SECRET_KEY = "shi-nha-khoa-demo-key"
_DEFAULT_ADMIN_KEY = "shi-admin-demo"


def _default_key_warnings(secret_key, admin_key):
    """Trả về danh sách cảnh báo nếu SECRET_KEY/ADMIN_KEY còn giá trị demo mặc định.

    Hàm THUẦN (không print trực tiếp) để test được mà không cần reload module —
    xem Risk Assessment."""
    warnings = []
    if secret_key == _DEFAULT_SECRET_KEY:
        warnings.append("[CẢNH BÁO] SECRET_KEY đang dùng giá trị demo mặc định — "
                         "production PHẢI đặt biến môi trường SECRET_KEY (xem .env.example).")
    if admin_key == _DEFAULT_ADMIN_KEY:
        warnings.append("[CẢNH BÁO] ADMIN_KEY đang dùng giá trị demo mặc định — "
                         "production PHẢI đặt biến môi trường ADMIN_KEY (xem .env.example).")
    return warnings


for _w in _default_key_warnings(app.secret_key, ADMIN_KEY):
    print(_w)
```

**[Red team — Accept, Finding "H7 bỏ sót debug=True/host=0.0.0.0 — CRITICAL, 2 reviewer độc
lập xác nhận"]** `ISSUES.md` định nghĩa H7 gồm CẢ 3 phần: `SECRET_KEY` mặc định, `ADMIN_KEY`
mặc định, VÀ `app.run(debug=True, host="0.0.0.0", ...)` (`app.py:167` hiện tại — cửa RCE qua
Werkzeug interactive debugger nếu ai đó gây exception được trên máy nghe ở `0.0.0.0`). Bản
nháp đầu CHỈ cảnh báo 2 key, bỏ sót phần debug — nếu không sửa, `ISSUES.md` sẽ bị đánh dấu
H7 `[x]` xong dù phần rủi ro RCE thật sự vẫn còn nguyên. Thêm cảnh báo tương tự trong khối
`if __name__ == "__main__":` (KHÔNG đổi `debug=True` mặc định — vẫn cần tiện cho demo local,
chỉ cảnh báo khi cấu hình nguy hiểm này chạy):
```python
if __name__ == "__main__":
    if os.environ.get("FLASK_DEBUG_WARN_SUPPRESS") != "1":
        print("[CẢNH BÁO] Đang chạy debug=True trên host=0.0.0.0 — Werkzeug interactive "
              "debugger có thể bị khai thác từ xa (RCE) nếu máy này lộ ra mạng ngoài. "
              "Production PHẢI tắt debug (đặt debug=False) hoặc bind 127.0.0.1.")
    app.run(debug=True, host="0.0.0.0", port=5001)
```
`FLASK_DEBUG_WARN_SUPPRESS` chỉ để test không bị làm phiền bởi output — không phải cấu hình
production thật, không cần tài liệu hoá cho end-user, chỉ dùng nội bộ trong
`tests/test_app_admin.py` nếu cần.

## Related Code Files

- Modify: `app.py` (`_check_admin` + comment banner, `_default_key_warnings`, cảnh báo
  `debug=True`)
- Modify: `docs/getting-started-guide.md` (ví dụ curl admin đổi từ `?key=` sang header
  `X-Admin-Key`) — **[Red team — Accept]**
- Create: `tests/test_app_admin.py`

## Implementation Steps (TDD)

1. **Đọc trước**: `docs/getting-started-guide.md` quanh dòng ~136-138 để xác định chính xác
   đoạn curl dùng `?key=` cần sửa.
2. **Red** — viết `tests/test_app_admin.py` dùng Flask test client (`app.test_client()`):
   - `test_admin_rejects_query_string_key()`: gọi
     `client.get("/api/admin/appointments?key=<ADMIN_KEY thật>")` KHÔNG kèm header → assert
     `401` (trước fix, phải fail vì hiện tại query string vẫn được chấp nhận → response sẽ
     là `200`, đúng Red state).
   - `test_admin_accepts_header_key()`: gọi với header `X-Admin-Key` đúng, KHÔNG có query
     string → assert `200` (regression, phải pass cả trước/sau fix — xác nhận không phá
     luồng admin.html đang dùng).
   - `test_admin_rejects_wrong_or_missing_key()`: không header, không query → `401`.
   - `test_default_key_warnings_pure_function()`: **[Red team — Accept, thay thế cách test
     `importlib.reload` cũ]** gọi TRỰC TIẾP `app._default_key_warnings("shi-nha-khoa-demo-key",
     "shi-admin-demo")` (tham số = đúng giá trị demo mặc định) → assert kết quả là list chứa
     2 message, mỗi message chứa "SECRET_KEY" và "ADMIN_KEY" tương ứng. Gọi lại với tham số
     KHÁC giá trị demo (vd `"custom-secret", "custom-admin"`) → assert list rỗng. Test hàm
     THUẦN trực tiếp — KHÔNG dùng `importlib.reload(app)`, KHÔNG cần patch `os.environ`,
     tránh hoàn toàn rủi ro rò rỉ state module-global qua các test khác trong cùng session
     pytest (test C4 cũ `tests/test_app_ics.py` cũng import `app` — reload sẽ ảnh hưởng
     chéo).
   - Chạy `pytest tests/test_app_admin.py -v` → xác nhận fail đúng chỗ.
3. **Green** — sửa `app.py` theo Architecture (bao gồm comment banner + cảnh báo debug) và
   `docs/getting-started-guide.md`.
4. Chạy lại → toàn bộ pass.
5. Chạy `pytest tests/test_app_ics.py -v` (test C4 cũ, cũng dùng Flask test client trên
   `app.py`) → xác nhận KHÔNG regress (test C4 không liên quan tới admin, nhưng cùng file
   `app.py` nên verify chéo — đặc biệt quan trọng vì Phase này KHÔNG dùng reload module nên
   không có rủi ro rò rỉ state sang test C4).

## Success Criteria

- [ ] `tests/test_app_admin.py` pass toàn bộ.
- [ ] `?key=` không còn được `_check_admin()` chấp nhận dưới bất kỳ hình thức nào.
- [ ] `_check_admin()` dùng `hmac.compare_digest`, không còn `==` thường.
- [ ] Comment banner phía trên `_check_admin()` không còn nhắc tới `?key=`.
- [ ] Header `X-Admin-Key` vẫn hoạt động y hệt cũ (admin.html không cần sửa).
- [ ] `_default_key_warnings()` là hàm thuần, trả đúng cảnh báo cho SECRET_KEY/ADMIN_KEY mặc
  định, test được không cần reload module.
- [ ] Cảnh báo runtime xuất hiện khi chạy `debug=True`+`host=0.0.0.0` qua `if __name__ ==
  "__main__":` — H7 đóng ĐỦ cả 3 phần theo `ISSUES.md` (2 key + debug/host), không chỉ 2 key.
- [ ] `docs/getting-started-guide.md` ví dụ curl admin đã đổi sang header, không còn `?key=`.
- [ ] `tests/test_app_ics.py` (từ C4) vẫn pass — không regress route `/api/ics/<code>`.

## Risk Assessment

- **Breaking change có chủ đích cho `?key=`**: đây là thay đổi public-contract của
  admin API (loại bỏ 1 cách xác thực). Đã xác nhận `templates/admin.html` không dùng cách
  đó, nhưng `docs/getting-started-guide.md` CÓ dùng trong ví dụ test — đã đưa vào scope sửa
  ở phase này (xem Related Code Files), không còn là rủi ro sót lại.
- **Không đổi `debug=True` mặc định** — chỉ cảnh báo, không hard-fail. Nếu user muốn tắt
  debug thật sự cho production, cần tự đặt env riêng hoặc sửa `app.run(...)` — ngoài phạm vi
  "nhắc lại cảnh báo" mà `ISSUES.md`/phase này nhắm tới (không tự ý đổi default hành vi local
  dev đang dùng tốt).
