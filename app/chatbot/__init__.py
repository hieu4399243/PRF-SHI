"""
Máy trạng thái hội thoại.

    router.py    cửa vào duy nhất: guardrail + định tuyến theo state
    session.py   phiên hội thoại in-memory (SESSIONS) + TTL + khoá per-session
    reply.py     định dạng response, format ngày, chuẩn hoá số điện thoại
    flex.py      "trả lời linh hoạt" bằng LUẬT: quay lại / đổi bước / kể thêm triệu chứng
    llm_reply.py "trả lời linh hoạt" bằng LLM: viết lại câu ở các nhánh bộ luật bó tay
    steps/       mỗi file là MỘT bước: triage → bác sĩ → ngày giờ → xác nhận → hủy

Luồng state:
    GREET → TRIAGE → CONFIRM_DEPT → PICK_DOCTOR → PICK_DATE → PICK_TIME
          → ASK_NAME → ASK_PHONE → CONFIRM_BOOKING → DONE
    (nhánh hủy: CANCEL_ASK_PHONE → CANCEL_PICK → CANCEL_CONFIRM)

`from app import chatbot` cho ra API mà app.main dùng: start / handle_message.
"""

from .router import (  # noqa: F401
    greeting,
    handle_message,
    start,
    start_with_service,
    stop_booking,
)
from .session import (  # noqa: F401
    MAX_SESSIONS,
    SESSION_TTL_SECONDS,
    SESSIONS,
    get_session,
    new_session,
    reset_in_place,
    reset_session,
)
