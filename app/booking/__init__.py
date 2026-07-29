"""
Đặt lịch hẹn.

    service.py        đặt / hủy / tra cứu lịch, tính khung giờ còn trống
    calendar_ics.py   sinh file .ics + link Google Calendar (không cần OAuth)

`from app import booking` cho ra API của service.py:

    booking.book_appointment(...)
"""

from .service import *  # noqa: F401,F403
from .service import (  # noqa: F401  — tên bắt đầu bằng "_" không đi qua "*"
    _confirmed_at,
    _generate_code,
    _insert_with_race_guard,
)
