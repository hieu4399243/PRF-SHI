"""
Reminder worker — quét lịch hẹn và bắn push nhắc lịch / nhắc ăn uống.

Cách dùng:
    python reminder_worker.py --once     # quét 1 lần (đặt trong cron mỗi 5-15 phút)
    python reminder_worker.py --watch    # chạy nền, tự quét mỗi 60 giây
    python reminder_worker.py --test     # gửi thử MỌI loại nhắc cho mọi lịch (bỏ qua thời gian)

Mỗi lịch hẹn được gửi mỗi loại nhắc đúng 1 lần (lưu trong reminders_sent).
Push gửi tới token đã đăng ký theo session của lịch hẹn (xem push.py).
"""

import sys
import time
from datetime import datetime, timedelta

import booking
import push


def _format_date(iso: str):
    weekdays = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]
    try:
        d = datetime.fromisoformat(iso).date()
        return f"{weekdays[d.weekday()]}, {d.day:02d}/{d.month:02d}"
    except ValueError:
        return iso


# ---------------------------------------------------------------------------
# QUY TẮC NHẮC: (mã, khoảng thời gian trước giờ hẹn, tiêu đề, hàm tạo nội dung)
# ---------------------------------------------------------------------------
def _rules(appt):
    when = f"{appt['time']} {_format_date(appt['date'])}"
    return [
        {
            "key": "remind_1d",
            "before": timedelta(days=1),
            "title": "📅 Nhắc lịch khám (còn 1 ngày)",
            "body": f"Ngày mai bạn có lịch khám {appt['department']} - {appt['doctor']} lúc {when}.",
        },
        {
            "key": "care_eat",
            "before": timedelta(hours=14),  # tối hôm trước
            "title": "🍵 Nhắc chăm sóc sức khỏe",
            "body": "Trước ngày khám: ăn uống điều độ, uống đủ nước, ngủ sớm và "
                    "nhớ mang theo giấy tờ/thuốc đang dùng nhé.",
        },
        {
            "key": "remind_2h",
            "before": timedelta(hours=2),
            "title": "⏰ Sắp tới giờ khám (còn 2 giờ)",
            "body": f"Bạn có lịch khám {appt['department']} - {appt['doctor']} lúc {when}. "
                    "Vui lòng đến trước 15 phút.",
        },
    ]


def _send_for(appt, rule):
    tokens = push.get_tokens(appt.get("session", ""))
    res = push.send_push(
        tokens, rule["title"], rule["body"],
        data={"type": "reminder", "key": rule["key"], "code": appt["code"]},
    )
    booking.mark_reminder_sent(appt["code"], rule["key"])
    target = tokens or ["(chưa có thiết bị — ghi outbox)"]
    print(f"  [SENT] {appt['code']} · {rule['key']} -> {target} · {res}")


def scan_once(force=False):
    """Quét toàn bộ lịch hẹn, gửi các nhắc tới hạn (hoặc tất cả nếu force)."""
    now = datetime.now()
    appts = booking.all_appointments()
    n_sent = 0
    for appt in appts:
        if appt.get("status") != "confirmed":
            continue
        try:
            appt_dt = datetime.fromisoformat(f"{appt['date']}T{appt['time']}:00")
        except ValueError:
            continue
        already = set(appt.get("reminders_sent", []))
        for rule in _rules(appt):
            if rule["key"] in already:
                continue
            due_time = appt_dt - rule["before"]
            # gửi nếu: ép gửi (test), HOẶC đã tới thời điểm nhắc và chưa quá giờ hẹn
            if force or (now >= due_time and now <= appt_dt):
                _send_for(appt, rule)
                n_sent += 1
    return n_sent


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--once"
    if mode == "--test":
        print("== TEST: gửi thử mọi loại nhắc cho mọi lịch hẹn ==")
        total = scan_once(force=True)
        print(f"Hoàn tất. Đã gửi {total} nhắc.")
    elif mode == "--watch":
        print("== WATCH: quét mỗi 60 giây (Ctrl+C để dừng) ==")
        while True:
            t = datetime.now().strftime("%H:%M:%S")
            sent = scan_once()
            print(f"[{t}] quét xong, gửi {sent} nhắc.")
            time.sleep(60)
    else:
        sent = scan_once()
        print(f"Quét 1 lần xong, gửi {sent} nhắc.")


if __name__ == "__main__":
    main()
