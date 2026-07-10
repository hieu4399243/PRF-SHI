---
phase: 3
title: "M3M7M8 App Hardening"
status: pending
priority: P3
dependencies: []
---

# Phase 3: M3 + M7 + M8 — Giới hạn body, validate session id, rate limit

## Overview

- **M3**: Flask không giới hạn `MAX_CONTENT_LENGTH` — client gửi body khổng lồ (vd message
  siêu dài) có thể gây DoS bộ nhớ khi Flask parse request.
- **M7**: `resolve_sid()` chấp nhận `session` do client gửi trong JSON body TUỲ Ý (chỉ cần
  không rỗng), không kiểm tra định dạng — giảm nhẹ nhờ entropy uuid4 mặc định nhưng không
  chặn client cố tình gửi giá trị đoán được/cố định.
- **M8**: Không có rate limiting trên endpoint công khai (`/api/start`, `/api/chat`,
  `/api/register-push`, `/api/ics/<code>`) — 1 client có thể spam vô hạn (đã ghi nhận residual
  risk ở C3 khi thêm cap session, giờ đóng nốt).

**[Red team — Accept, Finding "rate limit loại trừ /api/admin/* → brute-force ADMIN_KEY
không giới hạn số lượng"]** Bản nháp đầu cố ý loại `/api/admin/*` khỏi rate limit (lý do:
"đã bảo vệ bằng key riêng"). Nhưng `_check_admin()` (H6) chỉ chống được TIMING attack
(`hmac.compare_digest`), KHÔNG chống được BRUTE-FORCE VỀ SỐ LƯỢNG — không giới hạn số lần
thử admin key thì kẻ tấn công vẫn có thể thử hàng triệu giá trị. Quyết định: mở rộng rate
limit áp dụng cho TẤT CẢ route `/api/*` (kể cả admin), không loại trừ riêng — đơn giản hơn
việc chỉ ghi chú residual risk, và closes hẳn lỗ hổng thay vì chỉ tài liệu hoá nó.

## Requirements

- Functional:
  - M3: Request có `Content-Length` vượt ngưỡng → Flask tự trả `413 Request Entity Too
    Large` (hành vi built-in của Flask khi set `MAX_CONTENT_LENGTH`, không cần code thêm
    ngoài set config).
  - M7: `session` client gửi trong body KHÔNG khớp định dạng uuid4-hex (32 ký tự hex
    thường) → bị bỏ qua, `resolve_sid()` tự mint uuid4 mới (KHÔNG lỗi/reject request, chỉ
    âm thầm thay bằng giá trị an toàn — giữ trải nghiệm mượt cho client hợp lệ vô tình gửi
    sai định dạng).
  - M8: Vượt ngưỡng request/phút theo IP trên MỌI route `/api/*` (kể cả `/api/admin/*` —
    xem quyết định red-team ở Overview) → trả `429 Too Many Requests`.
- Non-functional: Không thêm dependency mới (không Flask-Limiter, không Redis). Ngưỡng
  giới hạn là hằng số cứng trong code (không cần cấu hình qua env — YAGNI, đây là bảo vệ an
  toàn cơ bản không phải tham số vận hành cần tinh chỉnh thường xuyên).

## Architecture

### M3 — MAX_CONTENT_LENGTH
```python
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024  # 64KB — đủ rộng cho tin nhắn text, chặn DoS
```
Đặt ngay sau dòng `app = Flask(__name__)` hiện có.

### M7 — validate format session id
```python
import re

_SID_RE = re.compile(r"^[0-9a-f]{32}$")

def resolve_sid(data=None):
    """Lấy session id từ body JSON (app native) hoặc cookie (web).

    Giá trị client gửi trong body phải đúng định dạng uuid4-hex (32 ký tự hex
    thường) — sai định dạng bị bỏ qua, coi như không gửi, tránh session id
    đoán được/cố định do client tự chọn tuỳ ý.
    """
    data = data or {}
    client_sid = data.get("session")
    if client_sid and (not isinstance(client_sid, str) or not _SID_RE.match(client_sid)):
        client_sid = None
    sid = client_sid or session.get("sid")
    if not sid:
        sid = uuid.uuid4().hex
    session["sid"] = sid
    return sid
```
**[Red team — Accept, Finding "resolve_sid crash trên session không phải string" —
CRITICAL, DoS 500 không cần auth]** `data` đến từ `request.get_json(force=True,
silent=True)` — HOÀN TOÀN không tin cậy, client có thể gửi `{"session": 123}` (số),
`{"session": [1,2,3]}` (list), v.v. `_SID_RE.match(client_sid)` với `client_sid` không phải
`str` sẽ raise `TypeError` ngay lập tức (`re.match` yêu cầu string/bytes), không được Flask
bắt tự động → 500 cho MỌI request `/api/start`/`/api/chat`/`/api/register-push` với 1 dòng
JSON đơn giản, không cần xác thực. PHẢI kiểm tra `isinstance(client_sid, str)` TRƯỚC khi
gọi `.match()` — thứ tự điều kiện trong `and` (short-circuit) đã đặt đúng ở code trên
(`not isinstance(...) or not _SID_RE.match(...)`), không được đảo ngược thứ tự 2 vế.

Lưu ý: `session.get("sid")` (cookie Flask, server tự set) LUÔN đúng định dạng vì chính
`resolve_sid`/`index()` sinh ra bằng `uuid.uuid4().hex` — chỉ cần validate giá trị CLIENT
GỬI TRONG BODY (`data.get("session")`, nguồn không tin cậy), không cần validate cookie.

### M8 — rate limit theo IP cho MỌI route `/api/*`, in-memory, có cap chống DoS-bộ-nhớ cho
chính bộ đếm
```python
import time

_RATE_LOCK = threading.Lock()
_RATE_BUCKETS = OrderedDict()  # ip -> list[timestamp], LRU-cap giống SESSIONS ở chatbot.py
_RATE_LIMIT = 30          # request
_RATE_WINDOW = 60         # giây
_RATE_MAX_IPS = 5000      # trần số IP theo dõi, tránh unbounded growth


def _is_rate_limited(ip):
    now = time.time()
    with _RATE_LOCK:
        bucket = _RATE_BUCKETS.get(ip)
        if bucket is None:
            if len(_RATE_BUCKETS) >= _RATE_MAX_IPS:
                _RATE_BUCKETS.popitem(last=False)  # loại IP cũ nhất
            bucket = []
            _RATE_BUCKETS[ip] = bucket
        else:
            _RATE_BUCKETS.move_to_end(ip)
        bucket[:] = [t for t in bucket if now - t < _RATE_WINDOW]
        if len(bucket) >= _RATE_LIMIT:
            return True
        bucket.append(now)
        return False


@app.before_request
def _rate_limit_guard():
    if not request.path.startswith("/api/"):
        return None  # trang web (/, /admin) không giới hạn
    if _is_rate_limited(request.remote_addr or "unknown"):
        return jsonify({"error": "Quá nhiều yêu cầu, vui lòng thử lại sau."}), 429
    return None
```
`before_request` là hook toàn cục của Flask — áp dụng cho MỌI route `/api/*` (kể cả admin,
theo quyết định red-team ở Overview), route trang web (`/`, `/admin` — chỉ render HTML,
không phải API) đi qua bình thường. Dùng `OrderedDict` + `move_to_end`/`popitem(last=False)`
giống hệt pattern LRU đã dùng cho `chatbot.SESSIONS` (C3) — nhất quán, không phát minh cơ
chế mới.

## Related Code Files

- Modify: `app.py` (thêm `MAX_CONTENT_LENGTH`, sửa `resolve_sid`, thêm rate limit)
- Create: `tests/test_app_hardening.py`
- Create hoặc modify: `tests/conftest.py` — **[Red team — Accept, Finding "reset
  _RATE_BUCKETS chỉ là gợi ý có điều kiện, không bắt buộc"]** BẮT BUỘC thêm fixture
  `autouse=True` xoá `app._RATE_BUCKETS.clear()` TRƯỚC MỖI TEST trong toàn bộ `tests/`
  (không chỉ trong `test_app_hardening.py`) — nếu chưa có `tests/conftest.py`, tạo mới; nếu
  đã có, thêm fixture vào đó. Đây KHÔNG phải "nếu phát hiện vấn đề thì thêm" như bản nháp
  đầu — làm NGAY từ đầu, vì `tests/test_app_ics.py` (đã có từ C4) gọi `/api/ics/<code>`
  nhiều lần trong test suite và giờ route đó nằm trong phạm vi rate limit `/api/*` mới.

## Implementation Steps (TDD)

1. **Đọc trước**: `app.py` hiện tại (đã qua 2 vòng sửa trước — `import` list, vị trí
   `app = Flask(__name__)`, `resolve_sid`, danh sách route) và `tests/conftest.py` nếu đã
   tồn tại (kiểm tra không ghi đè fixture khác) để chèn đúng chỗ.
2. **Red** — `tests/conftest.py` (fixture bắt buộc, viết TRƯỚC các test khác trong bước
   này để mọi test sau đó tự động cô lập):
   ```python
   import pytest
   import app as app_module

   @pytest.fixture(autouse=True)
   def _reset_rate_buckets():
       app_module._RATE_BUCKETS.clear()
       yield
       app_module._RATE_BUCKETS.clear()
   ```
3. **Red** — `tests/test_app_hardening.py` dùng Flask test client (`app.test_client()`):
   - `test_oversized_body_rejected()`: gửi POST `/api/chat` với body lớn hơn
     `MAX_CONTENT_LENGTH` → assert `413`.
   - `test_normal_body_accepted()`: body bình thường → assert KHÔNG phải `413` (regression).
   - `test_resolve_sid_rejects_malformed_client_session()`: gọi `/api/start` với
     `{"session": "not-a-valid-uuid"}` trong body → assert response `session` field trả về
     KHÁC `"not-a-valid-uuid"` (đã bị thay bằng uuid4 mới).
   - `test_resolve_sid_accepts_valid_uuid4_hex()`: gửi `{"session": "<32 hex hợp lệ>"}` →
     assert response giữ nguyên giá trị đó (regression — không phá luồng app native đưa
     session hợp lệ).
   - `test_resolve_sid_rejects_non_string_session()`: **[Red team — Accept, test trực tiếp
     cho fix Critical]** gọi `/api/start` với `{"session": 123}` (số, KHÔNG phải string) →
     assert response `200` (KHÔNG `500`), `session` field trả về là uuid4 hex mới (đã bỏ
     qua giá trị sai kiểu). Lặp lại với `{"session": [1, 2, 3]}` (list) → cùng assert.
   - `test_rate_limit_blocks_after_threshold(monkeypatch)`: monkeypatch `_RATE_LIMIT` xuống
     thấp (vd `3`) để test nhanh, gọi `/api/start` liên tục > ngưỡng từ CÙNG 1 test client
     (cùng IP mặc định của test client) → assert request thứ N+1 trả `429`.
   - `test_rate_limit_applies_to_admin_routes(monkeypatch)`: **[Red team — Accept, ĐẢO
     NGƯỢC ý định test so với bản nháp đầu]** monkeypatch `_RATE_LIMIT` thấp, gọi
     `/api/admin/meta` (kèm header admin đúng) liên tục vượt ngưỡng → assert request thứ
     N+1 trả `429` (rate limit ÁP DỤNG cho route admin, theo quyết định red-team — KHÔNG
     còn loại trừ như bản nháp đầu).
   - Chạy `pytest tests/test_app_hardening.py -v` → xác nhận fail đúng chỗ.
4. **Green** — sửa `app.py` theo Architecture.
5. Chạy lại → toàn bộ pass. Chạy `pytest tests/ -v` TOÀN BỘ (không chỉ file mới) → xác nhận
   fixture `conftest.py` mới không làm regress `tests/test_app_ics.py`/`tests/test_app_admin.py`
   (từ 2 vòng trước, cũng gọi `/api/*` nhiều lần trong 1 lần chạy suite).

## Success Criteria

- [ ] `tests/test_app_hardening.py` pass toàn bộ.
- [ ] `MAX_CONTENT_LENGTH` chặn body khổng lồ (413), không ảnh hưởng body bình thường.
- [ ] `resolve_sid` bỏ qua `session` client gửi sai định dạng HOẶC sai kiểu dữ liệu (không
  phải string), chấp nhận đúng định dạng, KHÔNG BAO GIỜ raise exception.
- [ ] Rate limit chặn spam theo IP trên MỌI route `/api/*`, kể cả `/api/admin/*`.
- [ ] `tests/conftest.py` có fixture `autouse` reset `_RATE_BUCKETS` cho toàn bộ suite.
- [ ] `tests/test_app_ics.py`, `tests/test_app_admin.py` (từ 2 vòng trước) vẫn pass sau khi
  fixture mới được thêm.

## Risk Assessment

- **Rate limit theo `request.remote_addr` chia sẻ IP sau NAT/proxy** — nhiều user thật đứng
  sau cùng 1 IP (mạng công ty, 4G NAT) có thể bị giới hạn chung. Hạn chế CHẤP NHẬN cho quy mô
  đồ án — giải pháp đúng (rate-limit theo session/token xác thực) cần hạ tầng khác, ngoài
  phạm vi. Ngưỡng `30 request/60s` đủ rộng cho 1 user thật dùng bình thường.
- **`app.config["MAX_CONTENT_LENGTH"]` áp dụng cho MỌI request, kể cả admin** — chấp nhận
  được, admin cũng không cần gửi body >64KB cho các thao tác hiện có (hủy lịch chỉ gửi mã).
- **Rate limit áp dụng cả `/api/admin/*`** — admin dashboard (`templates/admin.html`) gọi
  nhiều request liên tiếp khi tải trang (appointments + schedule + meta) trong ngưỡng
  `30/60s` bình thường không có vấn đề, nhưng nếu admin thao tác dồn dập (vd filter liên tục)
  có thể chạm ngưỡng — chấp nhận trade-off này để đóng lỗ hổng brute-force, ngưỡng có thể
  tăng sau nếu admin thật báo gặp `429` khi dùng bình thường (không cần làm ngay, YAGNI).
