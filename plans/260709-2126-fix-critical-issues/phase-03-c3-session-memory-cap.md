---
phase: 3
title: "C3 Session Memory Cap"
status: pending
priority: P1
dependencies: []
---

# Phase 3: C3 — `SESSIONS` không giới hạn + key client tự chọn → DoS bộ nhớ

## Overview

`chatbot.SESSIONS = {}` (dict thường, in-memory) không TTL/cap. `app.resolve_sid()` chấp
nhận `session` do client tự gửi trong body → client có thể tạo vô hạn entry → OOM.

**Quyết định đã chốt**: production chạy 1 Flask process → fix bằng cap + TTL trong
process hiện tại (LRU-style eviction), KHÔNG cần Redis/store ngoài. Giữ nguyên
`chatbot.SESSIONS` là dict (không đổi kiểu dữ liệu để tránh phải sửa mọi nơi truy cập
`SESSIONS[sid]` trực tiếp trong `chatbot.py`) nhưng bọc thêm giới hạn kích thước + tuổi.

## Requirements

- Functional:
  - Số session tối đa trong bộ nhớ bị chặn trần (constant, không cần cấu hình qua env —
    YAGNI, đây là giá trị an toàn cứng, không phải tham số vận hành).
  - Session cũ nhất (theo lần truy cập gần nhất, không phải lần tạo) bị loại bỏ khi vượt
    trần, hoặc hết hạn theo TTL.
  - `get_session()` / `reset_session()` vẫn giữ nguyên chữ ký và hành vi trả về cho
    session hợp lệ.
- Non-functional: không đổi cấu trúc dict nội bộ 1 session (state machine hiện tại dùng
  trực tiếp `SESSIONS[sid]["state"] = ...` ở nhiều chỗ trong `chatbot.py` — không được vỡ).

## Architecture

Thay `SESSIONS = {}` bằng `collections.OrderedDict` (built-in, không thêm dependency —
DRY/KISS, không cần cài `cachetools`). Thêm hằng số:

```python
_MAX_SESSIONS = 2000
_SESSION_TTL_SECONDS = 3600  # 1 giờ không hoạt động -> hết hạn
```

`get_session(session_id)`:
1. Nếu `session_id` có trong `SESSIONS` và chưa hết hạn (so `time.time()` với
   `_last_seen` lưu trong session) → cập nhật `_last_seen`, `move_to_end()` (đưa lên cuối
   = mới nhất), trả về.
2. Nếu có nhưng hết hạn → coi như mới, tạo lại (giống hành vi `reset_session`).
3. Nếu không có → tạo mới. Trước khi insert, nếu `len(SESSIONS) >= _MAX_SESSIONS`:
   `SESSIONS.popitem(last=False)` (loại session cũ nhất — `OrderedDict` giữ thứ tự
   insert/`move_to_end`, nên phần tử đầu luôn là ít-truy-cập-gần-đây-nhất = LRU thật).

`_new_session()` thêm field nội bộ `_last_seen: time.time()` — không phải dữ liệu nghiệp
vụ, chỉ dùng cho eviction, đặt tên `_` prefix để phân biệt field nghiệp vụ.

Không sửa `app.resolve_sid()` — client vẫn tự chọn `session` id, nhưng giờ không thể
OOM vì tổng số entry bị chặn trần cứng bất kể client gửi gì.

**[Red team — Accept, Finding "reset_session desync LRU"]** `reset_session(session_id)`
(gọi từ `chatbot.py:63,84`, luôn trên session ĐÃ tồn tại) hiện gán thẳng
`SESSIONS[session_id] = _new_session()`. Với `OrderedDict`, gán lại giá trị của key đã có
KHÔNG di chuyển key đó xuống cuối (không cập nhật thứ tự). Kết quả: 1 session vừa được
reset (hoạt động gần nhất) vẫn nằm ở vị trí cũ trong thứ tự LRU → có thể bị
`popitem(last=False)` loại bỏ TRƯỚC các session rảnh thật, ngược với yêu cầu "session cũ
nhất theo lần truy cập gần nhất bị loại bỏ". Fix: `reset_session()` phải tạo session mới
rồi gọi `SESSIONS.move_to_end(session_id)` (hoặc xoá key cũ rồi insert lại) để đưa nó lên
vị trí mới nhất, giống hệt luồng `get_session()`.

**[Red team — Accept, Finding "eviction race + eviction-DoS"]** Chuỗi
check-membership → `move_to_end()`/quyết định evict → `popitem()` → insert trong
`get_session()` gồm nhiều lệnh riêng lẻ, KHÔNG atomic. "1 Flask process" (đã chốt với
user) không đồng nghĩa "1 thread" — 1 process với nhiều thread (vd deploy sau này bằng
`gunicorn --workers 1 --threads N`, vẫn thoả đúng quyết định "1 process") vẫn có thể chạy
2 request đồng thời cùng lúc gọi `get_session()`. Thêm `threading.Lock()` module-level
(`_SESSIONS_LOCK = threading.Lock()`) bọc quanh toàn bộ thân `get_session()` (đọc + evict +
ghi) và `reset_session()` — chi phí rẻ, loại bỏ hẳn phụ thuộc vào giả định số luồng chưa
được enforce ở đâu trong repo (không có Procfile/gunicorn config xác nhận).

Về rủi ro "cap biến OOM-DoS thành eviction-DoS" (1 client gọi `/api/start` ~2000 lần đá
văng mọi session hợp lệ khác): đây là trade-off đã biết, KHÔNG fix bằng rate-limit trong
phase này (rate-limit endpoint công khai đã là mục Medium riêng trong `ISSUES.md`, ngoài
phạm vi "chỉ fix Critical"). Ghi rõ vào Risk Assessment bên dưới thay vì để ẩn.

## Related Code Files

- Modify: `chatbot.py` (`SESSIONS`, `_new_session`, `get_session`, `reset_session`)
- Create: `tests/test_chatbot_sessions.py`

## Implementation Steps (TDD)

1. **Red** — viết `tests/test_chatbot_sessions.py`:
   - `test_session_cap_evicts_oldest()`: set `chatbot._MAX_SESSIONS` thấp (monkeypatch,
     vd `5`) để test nhanh, tạo `_MAX_SESSIONS + 1` session khác nhau qua `get_session()`,
     assert `len(chatbot.SESSIONS) <= _MAX_SESSIONS` VÀ session đầu tiên tạo ra đã bị evict
     (`session_id_0 not in chatbot.SESSIONS`).
   - `test_session_ttl_expires()`: tạo session, monkeypatch `time.time` (hoặc set
     `_last_seen` trực tiếp về quá khứ xa hơn `_SESSION_TTL_SECONDS`), gọi lại
     `get_session(same_id)` → assert trả về session MỚI (state reset về `GREET`), không
     phải object cũ.
   - `test_get_session_refreshes_recency()`: tạo session A rồi B (A cũ hơn), truy cập lại
     A (`get_session(a_id)`), sau đó lấp đầy tới cap → assert A KHÔNG bị evict trước B (vì
     A vừa được truy cập lại = mới nhất theo LRU), B mới bị evict nếu cap chạm tới B.
   - `test_reset_session_refreshes_recency()`: **[Red team — Accept]** tạo session A rồi
     B, gọi `reset_session(a_id)`, sau đó lấp đầy tới cap → assert A KHÔNG bị evict trước
     B (reset phải đưa A lên vị trí mới nhất, không giữ vị trí cũ).
   - `test_get_session_thread_safe(monkeypatch hoặc threading thật)`: **[Red team —
     Accept]** chạy N thread gọi `get_session()` đồng thời với N id khác nhau (vd
     `concurrent.futures.ThreadPoolExecutor`), assert `len(SESSIONS)` cuối cùng đúng bằng
     N (không mất session nào do race), và không có exception nào raise từ thread.
   - Chạy `pytest tests/test_chatbot_sessions.py -v` → fail (chưa có cap/TTL).
2. **Green** — implement theo Architecture ở trên.
3. Chạy lại → pass. Chạy thêm 1 smoke test thủ công: `python -c "import chatbot;
   [chatbot.get_session(f's{i}') for i in range(3000)]; print(len(chatbot.SESSIONS))"` →
   phải in ra `<= 2000`.

## Success Criteria

- [ ] `tests/test_chatbot_sessions.py` pass (cap, TTL, LRU recency).
- [ ] `len(chatbot.SESSIONS)` không bao giờ vượt `_MAX_SESSIONS` sau smoke test 3000 session.
- [ ] Toàn bộ code hiện có trong `chatbot.py` truy cập `SESSIONS[sid][...]` trực tiếp vẫn
  chạy đúng (không đổi shape của value trong dict, chỉ đổi kiểu container ngoài +
  thêm field `_last_seen`).

## Risk Assessment

- **Đổi `dict` → `OrderedDict` có thể vỡ code khác nếu có chỗ dựa vào `dict` cụ thể**
  (vd `isinstance(SESSIONS, dict)`). Giảm thiểu: `OrderedDict` là subclass của `dict`,
  `isinstance` vẫn `True`; grep toàn repo `SESSIONS` trước khi sửa để xác nhận không có
  usage lạ ngoài `chatbot.py`.
- **TTL cứng 3600s có thể cắt ngang hội thoại thật đang dở** nếu user để chat quá 1 giờ
  không thao tác — chấp nhận được, đây là trade-off DoS-protection vs UX đã nêu trong
  `ISSUES.md`, không phải regression mới.
- **[Red team] Eviction-DoS còn tồn tại sau fix này**: cap chặn OOM nhưng không chặn 1
  client gọi `/api/start` liên tục để đá văng session hợp lệ của người khác (LRU luôn
  evict session lâu-không-hoạt-động-nhất, session của attacker luôn "mới nhất"). Đây là
  residual risk CHẤP NHẬN có chủ đích trong phase này — fix đúng (rate limit) thuộc mục
  Medium riêng trong `ISSUES.md`, không fix ở đây để tránh phình phạm vi ngoài 5 Critical.
- **[Red team] Giả định "1 process" không được enforce ở đâu trong repo** (không
  Procfile/gunicorn config/wsgi entrypoint). Thêm comment cảnh báo ngay tại khai báo
  `SESSIONS`/`_MAX_SESSIONS` trong `chatbot.py`: nếu deploy sau này dùng nhiều worker
  process (không phải nhiều thread — đã có lock cho trường hợp đó), mỗi worker có
  `SESSIONS` riêng, nhân đôi trần bộ nhớ theo số worker. Không xây cơ chế phát hiện
  runtime (over-engineering cho scope này) — chỉ cần comment rõ ràng để dev tương lai
  không bất ngờ.
