---
phase: 1
title: "M1M10 Chatbot Guardrail And Session Lock"
status: pending
priority: P3
dependencies: []
---

# Phase 1: M1 + M10 — Guardrail chẩn đoán chỉ chạy ở TRIAGE + session dict không khoá

## Overview

- **M1**: `safety.is_diagnosis_request()` chỉ được gọi bên trong `_do_triage()`
  (`chatbot.py`), tức chỉ áp dụng khi `sess["state"] == "TRIAGE"`. Ở các state khác (đang
  chọn bác sĩ, nhập tên, xác nhận lịch...), nếu người dùng gõ câu hỏi kiểu "bác sĩ ơi tôi bị
  bệnh gì", KHÔNG có disclaimer/chặn nào — request đó chỉ rơi vào xử lý input-không-hợp-lệ
  của state hiện tại, im lặng bỏ qua ý định xin chẩn đoán.
- **M10**: `SESSIONS` (OrderedDict, từ C3) có `_SESSIONS_LOCK` bảo vệ chuỗi
  check→evict→insert trong `get_session()`/`reset_session()` — nhưng đó là khoá cho THAO TÁC
  TRÊN CONTAINER, không bảo vệ việc ĐỌC/GHI CÁC FIELD bên trong 1 session dict cụ thể
  (`sess["state"]`, `sess["date"]`, v.v.) trong lúc `handle_message()` xử lý. 2 request đồng
  thời cho CÙNG 1 session (double-submit, tab kép) có thể interleave ghi field, làm hỏng
  trạng thái hội thoại.

## Requirements

- Functional:
  - M1: Ở MỌI state KHÁC `TRIAGE`, nếu `safety.is_diagnosis_request(message)` là `True`,
    trả về 1 phản hồi disclaimer, GIỮ NGUYÊN state hiện tại (không làm gián đoạn luồng đặt
    lịch đang dở). State `TRIAGE` GIỮ NGUYÊN hành vi cũ (diag_note lồng trong phản hồi
    triage, không tách riêng) — không regress.
  - M10: 2 lời gọi `handle_message()` đồng thời cho CÙNG session phải xử lý TUẦN TỰ (không
    interleave field-write). Các session KHÁC NHAU không bị chặn lẫn nhau (khoá theo từng
    session, không phải khoá toàn cục).
- Non-functional: Không đổi chữ ký `handle_message(session_id, raw_message)`. Không đổi
  cấu trúc dict trả về của bất kỳ response nào.

## Architecture

### M1 — guardrail chẩn đoán áp dụng mọi state trừ TRIAGE

**[Red team — Accept, Finding "vị trí chèn guardrail đụng cancel-intent/info-question" —
2 reviewer độc lập chỉ ra cùng vấn đề]** KHÔNG chèn ngay sau `needs_human_handoff` như bản
nháp đầu — vị trí đó nằm TRƯỚC 2 khối xử lý hiện có cũng active ở state `CONFIRM_DEPT`/
`DONE`: khối "Ý định HỦY lịch" (`_is_cancel_request`) và khối "Câu hỏi thông tin dịch vụ"
(`triage.info_question_service`). `DIAGNOSIS_REQUEST_PATTERNS` chứa cụm chung chung như
"có nguy hiểm không"/"uống thuốc gì" (xem `safety.py`) — 1 câu vừa mang ý định hủy lịch vừa
chứa cụm chẩn đoán (vd "huỷ lịch giúp tôi, tôi phải uống thuốc gì trước khi khám") sẽ bị
guardrail nuốt mất ý định hủy nếu đặt trước.

Đúng vị trí: chèn NGAY SAU khối "Câu hỏi thông tin về dịch vụ" (dòng cuối cùng trước comment
`# --- Định tuyến theo trạng thái ---`), tức là SAU CẢ cancel-intent LẪN info-question,
TRƯỚC định tuyến theo state:
```python
    # --- Câu hỏi thông tin về dịch vụ ("X là khám gì / là gì / gồm gì") ---
    if sess["state"] in {"TRIAGE", "CONFIRM_DEPT", "DONE"}:
        info_code = triage.info_question_service(message)
        if info_code:
            resp = _describe_service(sess, info_code)
            sess["state"] = resp["state"]
            safety.audit(session_id, "bot", resp["reply"],
                         {"state": resp["state"], "intent": "info"})
            return resp

    # --- Chặn yêu cầu chẩn đoán ngoài TRIAGE (TRIAGE tự xử lý inline trong
    # _do_triage, không lặp lại ở đây) ---
    if sess["state"] != "TRIAGE" and safety.is_diagnosis_request(message):
        resp = _reply(
            "Mình không thể chẩn đoán bệnh hay kê đơn thuốc nhé. Mình có thể giúp "
            "bạn chọn đúng dịch vụ nha khoa và đặt lịch khám — bạn tiếp tục ở bước "
            "hiện tại nha.",
            state=sess["state"],
        )
        safety.audit(session_id, "bot", resp["reply"], {"flag": "diagnosis_request"})
        return resp

    # --- Định tuyến theo trạng thái ---
    state = sess["state"]
    ...
```
`state=sess["state"]` (không đổi state) — quan trọng để không làm mất tiến trình đặt lịch
đang dở (vd đang ở `PICK_TIME`, sau cảnh báo vẫn ở lại `PICK_TIME`). State `TRIAGE` bị loại
trừ khỏi điều kiện này nên `_do_triage()`'s cách xử lý `diag_note` cũ giữ nguyên 100%,
không trùng lặp cảnh báo. Vì chèn SAU cancel-intent/info-question, 2 khối đó vẫn được ưu
tiên xử lý trước — guardrail chẩn đoán chỉ áp dụng cho message KHÔNG khớp 2 khối đó.

### M10 — khoá per-session cho field-level write

`_new_session()` thêm tham số `reuse_lock` (mặc định `None`) và field `_lock`:
```python
def _new_session(reuse_lock=None):
    return {
        ...  # các field nghiệp vụ hiện có, không đổi
        "_last_seen": time.time(),
        "_lock": reuse_lock or threading.Lock(),  # xem lý do "reuse_lock" bên dưới
    }
```

**[Red team — Accept, Finding "reset/TTL-expire vô hiệu hoá khoá" — CRITICAL, 3 reviewer
độc lập xác nhận]** Bản nháp đầu chỉ thêm `_lock` vào `_new_session()` mà không xử lý việc
`get_session()` (nhánh TTL hết hạn) và `reset_session()` đều XOÁ dict cũ rồi tạo dict MỚI
với `Lock` MỚI, gán đè lên `SESSIONS[session_id]`. Nếu 1 thread đang giữ khoá của dict CŨ
(giữa chừng xử lý `handle_message`, sắp gọi `/reset`) trong khi thread khác gọi
`get_session()` cho CÙNG session ngay sau khi dict mới đã được gán, thread thứ 2 sẽ lấy
được dict MỚI + khoá MỚI (chưa ai giữ) → 2 thread ghi field đồng thời lên 2 dict "khác
nhau nhưng cùng session_id trong SESSIONS" — đúng bug M10 định ngăn.

Fix: `get_session()`/`reset_session()` PHẢI tái sử dụng CÙNG đối tượng `Lock` khi thay
dict cũ bằng dict mới cho CÙNG `session_id`, để bất kỳ thread nào đã giữ khoá qua tham
chiếu dict cũ vẫn đang giữ ĐÚNG khoá tiếp tục bảo vệ dict mới:
```python
def get_session(session_id: str):
    with _SESSIONS_LOCK:
        existing = SESSIONS.get(session_id)
        if existing is not None:
            if time.time() - existing["_last_seen"] <= _SESSION_TTL_SECONDS:
                existing["_last_seen"] = time.time()
                SESSIONS.move_to_end(session_id)
                return existing
            # Hết hạn -> coi như mới, NHƯNG giữ lại cùng Lock object.
            del SESSIONS[session_id]
            _evict_if_full_locked()
            SESSIONS[session_id] = _new_session(reuse_lock=existing["_lock"])
            return SESSIONS[session_id]

        _evict_if_full_locked()
        SESSIONS[session_id] = _new_session()
        return SESSIONS[session_id]


def reset_session(session_id: str):
    with _SESSIONS_LOCK:
        old = SESSIONS.pop(session_id, None)
        _evict_if_full_locked()
        SESSIONS[session_id] = _new_session(
            reuse_lock=old["_lock"] if old is not None else None
        )
```
Vì `_lock` giờ là CÙNG 1 đối tượng `Lock` xuyên suốt vòng đời của 1 `session_id` (kể cả
qua reset/TTL-expire), `with sess["_lock"]:` trong `handle_message()` (bên dưới) LUÔN đúng
đắn dù `sess` bị đổi thành dict khác giữa chừng — không cần thay đổi cách bọc khoá trong
`handle_message()` so với thiết kế gốc.

`handle_message()` bọc TOÀN BỘ thân hàm (sau khi lấy `sess`) trong `with sess["_lock"]:` —
cách này tự động cover MỌI early-return rải rác trong hàm (emergency/handoff/cancel/info/
guardrail chẩn đoán mới/...) mà không cần sửa từng nhánh riêng lẻ:
```python
def handle_message(session_id: str, raw_message: str):
    sess = get_session(session_id)
    with sess["_lock"]:
        sess["_id"] = session_id
        message = (raw_message or "").strip()
        ...  # TOÀN BỘ thân hàm hiện có, chỉ THỤT LỀ THÊM 1 CẤP, không đổi logic
        return resp
```
Đây là khoá RIÊNG cho từng session (đối tượng `Lock` khác nhau MỖI session_id, nhưng CÙNG
1 đối tượng xuyên suốt vòng đời session đó nhờ `reuse_lock`), KHÁC `_SESSIONS_LOCK` (khoá
chung bảo vệ thao tác trên container `SESSIONS`). 2 request cho 2 session khác nhau không
chờ nhau; chỉ double-submit CÙNG session mới bị serialize.

**[Red team — Accept, Finding "field _lock chặn đường nâng cấp Redis đã ghi chú sẵn"]**
Comment hiện có ở đầu file (`# Bộ nhớ phiên (in-memory). Sản phẩm thật nên dùng Redis/DB.`)
đã ghi nhận hướng nâng cấp tương lai. Thêm 1 dòng chú thích ngay cạnh field `_lock` trong
`_new_session()`: `# _lock KHÔNG serialize được (threading.Lock) — nếu sau này chuyển
SESSIONS sang Redis/DB, phải loại bỏ field này khỏi payload lưu trữ, tái tạo Lock khi đọc
lại.` — chỉ ghi chú, không code thêm gì để hỗ trợ migration thật (ngoài phạm vi).

## Related Code Files

- Modify: `chatbot.py` (`_new_session`, `handle_message` — chỉ thụt lề thêm + 1 khối
  guardrail mới, KHÔNG đổi logic nghiệp vụ nào khác)
- Create: `tests/test_chatbot_guardrail.py` (M1)
- Create: `tests/test_chatbot_session_lock.py` (M10)

## Implementation Steps (TDD)

1. **Đọc trước**: `chatbot.py` toàn bộ hàm `handle_message()` (kể cả các nhánh early-return
   emergency/handoff/cancel/info) để xác nhận vị trí chèn guardrail M1 đúng chỗ (SAU khối
   cancel-intent VÀ SAU khối info-question, TRƯỚC định tuyến state — xem Architecture) và để
   biết chính xác phạm vi cần thụt lề cho M10 — số dòng có thể lệch so với mô tả trên do các
   phase khác không đụng file này.
2. **Red** — `tests/test_chatbot_guardrail.py`:
   - `test_diagnosis_request_blocked_outside_triage()`: đưa session vào state khác TRIAGE
     (vd `PICK_TIME`), gọi `handle_message(sid, "bác sĩ ơi tôi bị bệnh gì")` → assert phản
     hồi chứa disclaimer, `state` KHÔNG đổi (vẫn `PICK_TIME`).
   - `test_diagnosis_request_in_triage_unchanged()`: session ở state `TRIAGE`, gọi
     `handle_message` với câu hỏi chẩn đoán → assert hành vi CŨ giữ nguyên (diag_note lồng
     trong response triage, KHÔNG phải response disclaimer độc lập của guardrail mới —
     kiểm tra bằng cách so sánh với hành vi hiện tại trước khi sửa, ghi lại làm regression
     baseline).
   - `test_diagnosis_guardrail_does_not_override_cancel_intent()`: **[Red team — Accept]**
     session ở state `DONE`, gọi `handle_message` với message vừa khớp `_is_cancel_request`
     VỪA khớp `DIAGNOSIS_REQUEST_PATTERNS` (vd "huỷ lịch giúp tôi, tôi phải uống thuốc gì
     trước khi khám không") → assert response là luồng HỦY LỊCH (`intent: cancel` trong
     audit meta hoặc state chuyển sang nhánh cancel tương ứng), KHÔNG phải response
     disclaimer của guardrail chẩn đoán.
   - `test_diagnosis_guardrail_does_not_override_info_question()`: tương tự, message vừa
     khớp `triage.info_question_service` vừa khớp pattern chẩn đoán → assert response là
     luồng mô tả dịch vụ (`_describe_service`), không phải disclaimer.
   - Chạy `pytest tests/test_chatbot_guardrail.py -v` → xác nhận fail đúng chỗ (test ngoài
     TRIAGE fail vì hiện tại không có disclaimer; 2 test overlap có thể PASS "tình cờ" ở Red
     state vì guardrail chưa tồn tại — chấp nhận, mục đích là bắt regression sau khi Green).
3. **Red** — `tests/test_chatbot_session_lock.py`:
   - `test_new_session_has_lock()`: `chatbot._new_session()` trả dict có key `_lock` là
     instance `threading.Lock`.
   - `test_reset_session_reuses_same_lock_object()`: **[Red team — Accept, test trực tiếp
     cho fix Critical]** lấy `sid = "x"`, gọi `chatbot.get_session(sid)`, lưu lại
     `lock_before = sess["_lock"]`, gọi `chatbot.reset_session(sid)`, lấy lại session mới
     `sess2 = chatbot.get_session(sid)` → assert `sess2["_lock"] is lock_before` (CÙNG đối
     tượng, không phải Lock mới).
   - `test_ttl_expired_session_reuses_same_lock_object(monkeypatch)`: tương tự nhưng ép hết
     hạn TTL (monkeypatch `_last_seen` về quá khứ xa hơn `_SESSION_TTL_SECONDS`) thay vì gọi
     `reset_session` → assert `_lock` vẫn là CÙNG đối tượng sau khi session được coi là hết
     hạn và tạo lại.
   - `test_concurrent_handle_message_same_session_serialized(monkeypatch)`: dùng
     `threading`/`concurrent.futures` gọi `handle_message(sid, msg)` từ 2 thread cùng lúc
     cho CÙNG `sid`, chèn 1 `time.sleep(0.01)` nhân tạo (monkeypatch 1 hàm nội bộ dễ mock,
     vd `_reply`, để tạo cửa sổ race đủ rộng quan sát được) → assert không có exception, và
     field `sess["state"]` cuối cùng nhất quán (không bị 1 trong 2 thread ghi đè dở dang).
   - `test_different_sessions_not_blocked_by_each_other()`: 2 session KHÁC nhau gọi đồng
     thời → assert cả 2 hoàn thành, không timeout/deadlock.
   - Chạy `pytest tests/test_chatbot_session_lock.py -v` → xác nhận fail đúng chỗ (hiện tại
     `_new_session()` không có `_lock`, và `reset_session`/TTL-expire chưa reuse lock).
4. **Green** — sửa `chatbot.py` theo Architecture.
5. Chạy lại cả 2 file test → pass. Chạy `pytest tests/ -v` toàn bộ → không regress
   `tests/test_chatbot_sessions.py`/`tests/test_chatbot_audit.py` (từ 2 vòng trước, cũng
   đụng `chatbot.py`).

## Success Criteria

- [ ] `tests/test_chatbot_guardrail.py` + `tests/test_chatbot_session_lock.py` pass.
- [ ] Guardrail chẩn đoán áp dụng mọi state trừ TRIAGE, chèn SAU cancel-intent/info-question
  (không nuốt mất 2 ý định đó), không đổi state hiện tại.
- [ ] Mỗi session có `threading.Lock` riêng, TÁI SỬ DỤNG xuyên suốt reset/TTL-expire (không
  tạo Lock mới khi thay dict cho cùng session_id).
- [ ] `tests/test_chatbot_sessions.py`, `tests/test_chatbot_audit.py` (từ vòng trước) vẫn
  pass — không regress.

## Risk Assessment

- **Thụt lề toàn bộ `handle_message()` là diff lớn, dễ lỗi cú pháp** (đặc biệt nếu hàm có
  f-string nhiều dòng hoặc comment căn lề theo cột). Bước implement PHẢI đọc kỹ toàn bộ hàm
  trước khi sửa, dùng edit tool theo khối lớn thay vì sửa từng dòng lẻ để tránh lệch thụt lề.
- **Deadlock lý thuyết**: nếu `handle_message` gọi lại chính nó cho CÙNG session (không xảy
  ra trong code hiện tại — xác nhận qua đọc code, không có đệ quy), `with sess["_lock"]:`
  không tái nhập được (`threading.Lock` không phải `RLock`) sẽ treo. Vì không có đường gọi
  đệ quy nào trong `handle_message`/các hàm `_ask_*`/`_pick_*`/`_confirm_*` (tất cả đều xử
  lý xong rồi return, không gọi ngược `handle_message`), rủi ro này không xảy ra trong thực
  tế — nhưng nếu implement phát hiện có đường gọi đệ quy nào, phải đổi `Lock` sang `RLock`.
- **M1 guardrail có thể false-positive** với câu hỏi hợp lệ chứa từ khoá trùng pattern chẩn
  đoán (vd hỏi thông tin dịch vụ tình cờ dùng từ tương tự) — đây là hạn chế CÓ SẴN của
  `safety.is_diagnosis_request()` (rule-based, đã tồn tại từ trước cho state TRIAGE), KHÔNG
  phải lỗi mới do phase này gây ra — chỉ mở rộng phạm vi áp dụng, không đổi độ chính xác của
  hàm phát hiện.
