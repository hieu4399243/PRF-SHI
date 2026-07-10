---
phase: 5
title: "H8 Audit Log Name Redaction"
status: pending
priority: P2
dependencies: []
---

# Phase 5: H8 — Tên bệnh nhân không được ẩn trước khi ghi audit log

## Overview

`chatbot.handle_message()` ghi audit TOÀN BỘ tin nhắn người dùng qua
`safety.audit(session_id, "user", message, {"state": sess["state"]})` NGAY ĐẦU hàm, trước
khi biết tin nhắn đó là gì. `safety.mask_pii()` chỉ ẩn phone/email/CCCD bằng regex — không
có cách nào phát hiện "đây là tên người" bằng regex. Khi state hiện tại là `ASK_NAME` (bot
vừa hỏi tên, người dùng đang nhập tên), toàn bộ nội dung message CHÍNH LÀ tên bệnh nhân —
được ghi thẳng vào `audit_log.jsonl` không ẩn.

## Requirements

- Functional: khi state (TRƯỚC lúc xử lý message hiện tại — chính là state mà message này
  đang trả lời) là `ASK_NAME`, audit log phải ghi placeholder đã ẩn thay vì tên thật.
- Non-functional: KHÔNG đổi `patient_name` lưu trong `sess`/appointment (vẫn lưu tên thật để
  hiển thị/xác nhận lịch hẹn cho đúng người — chỉ ẩn ở audit log, không ẩn ở luồng nghiệp
  vụ). KHÔNG đổi chữ ký `safety.audit()` (giữ nguyên, chỉ đổi giá trị `message` truyền vào
  tại 1 call site).

## Architecture

Sửa `chatbot.py` `handle_message()`, ngay tại dòng ghi audit đầu hàm:
```python
def handle_message(session_id: str, raw_message: str):
    sess = get_session(session_id)
    sess["_id"] = session_id
    message = (raw_message or "").strip()

    # --- Ghi audit (đã ẩn PII) ---
    # State ASK_NAME: message chính là tên bệnh nhân -> mask_pii() không bắt được
    # (không phải phone/email/CCCD) -> ẩn thủ công trước khi ghi log.
    logged_message = "[TÊN ĐÃ ẨN]" if sess["state"] == "ASK_NAME" else message
    safety.audit(session_id, "user", logged_message, {"state": sess["state"]})
    ...
```
Chỉ 1 điểm sửa — dùng `sess["state"]` TRƯỚC khi bất kỳ logic định tuyến nào chạy (đúng vị
trí hiện tại của dòng audit, không di chuyển).

## Related Code Files

- Modify: `chatbot.py` (`handle_message`, dòng ghi audit đầu hàm)
- Create: `tests/test_chatbot_audit.py`

## Implementation Steps (TDD)

1. **Đọc trước**: `chatbot.py` xung quanh dòng `safety.audit(session_id, "user", message,
   {"state": sess["state"]})` (đầu `handle_message`) để xác nhận vị trí chính xác — số dòng
   có thể lệch so với lần đọc trước do các phase khác không đụng file này (H8 là phase duy
   nhất sửa `chatbot.py` trong plan này) nhưng vẫn nên đọc lại để chắc chắn.
2. **Red** — viết `tests/test_chatbot_audit.py`:
   - `test_audit_redacts_message_in_ask_name_state(monkeypatch)`: monkeypatch
     `safety.audit` để ghi lại tham số được gọi (list capture). Đưa 1 session vào state
     `ASK_NAME` (gọi `chatbot.get_session(sid)` rồi set `sess["state"] = "ASK_NAME"` trực
     tiếp, hoặc lái qua flow thật tới bước hỏi tên — chọn cách đơn giản hơn: set trực tiếp
     để test nhanh và cô lập). Gọi `chatbot.handle_message(sid, "Nguyễn Văn A")` → assert
     lệnh gọi `safety.audit` đầu tiên (role="user") có `message == "[TÊN ĐÃ ẨN]"`, KHÔNG
     chứa chuỗi `"Nguyễn Văn A"`.
   - `test_audit_keeps_message_in_other_states(monkeypatch)`: session ở state khác (vd
     `"TRIAGE"`), gọi `handle_message(sid, "tôi bị đau răng")` → assert audit ghi ĐÚNG
     message gốc (regression — không ẩn quá tay các state khác).
   - `test_patient_name_still_stored_correctly(monkeypatch)`: xác nhận
     `sess["patient_name"]` VẪN được set đúng tên thật sau khi xử lý message ở state
     `ASK_NAME` (mask chỉ ảnh hưởng audit log, không ảnh hưởng dữ liệu nghiệp vụ).
   - Chạy `pytest tests/test_chatbot_audit.py -v` → xác nhận fail đúng chỗ (test redact
     fail vì hiện tại ghi tên thật).
3. **Green** — sửa `chatbot.py` theo Architecture.
4. Chạy lại → toàn bộ pass.
5. Verify thủ công: chạy 1 lượt hội thoại thật qua `python3.10 -c "..."` gọi
   `chatbot.start(sid)` rồi dẫn tới state `ASK_NAME`, gửi tên giả, đọc `audit_log.jsonl`
   dòng cuối, xác nhận chứa `"[TÊN ĐÃ ẨN]"` không chứa tên vừa gửi.

## Success Criteria

- [ ] `tests/test_chatbot_audit.py` pass toàn bộ.
- [ ] Audit log KHÔNG còn chứa tên bệnh nhân thật khi state là `ASK_NAME`.
- [ ] `patient_name` lưu trong session/appointment KHÔNG bị ảnh hưởng (vẫn là tên thật).
- [ ] Các state khác (TRIAGE, ASK_PHONE, v.v.) audit log giữ nguyên hành vi cũ.

## Risk Assessment

- **Chỉ redact đúng 1 state (`ASK_NAME`)** — nếu sau này thêm luồng nhập tên khác (vd sửa
  tên sau khi đặt lịch), phase này KHÔNG tự động bắt được — ngoài phạm vi hiện tại (chưa có
  luồng đó trong codebase, xác nhận qua grep `"ASK_NAME"` chỉ có 2 chỗ dùng). Nếu tương lai
  thêm state nhập tên mới, cần bổ sung riêng.
- **`ASK_PHONE`/`CANCEL_ASK_PHONE` không cần xử lý ở phase này** — số điện thoại đã được
  `mask_pii()` regex bắt đúng (đã hoạt động từ trước), không phải lỗ hổng H8 nhắm tới.
