# Học dựng dự án Nha khoa SHI — Mục lục

Bộ tài liệu tự học, mỗi file dạy 1 khối, **gõ tới đâu chạy thử tới đó**.

## Thứ tự nên đọc
| # | File | Khối | Vì sao đọc lúc này |
|---|------|------|--------------------|
| 1 | [01-viet-triage-tu-dau.md](01-viet-triage-tu-dau.md) | `triage.py` | Lõi AI, tự chạy độc lập — học Python căn bản |
| 2 | [02-data.md](02-data.md) | `data.py` | Kho dữ liệu: dịch vụ, bác sĩ, khung giờ |
| 3 | [03-safety.md](03-safety.md) | `safety.py` | Lớp an toàn: cấp cứu, PII, audit |
| 4 | [04-booking.md](04-booking.md) | `booking.py` | Đặt lịch, quản lý slot trống |
| 5 | [05-push.md](05-push.md) | `push.py` | Gửi thông báo |
| 6 | [06-chatbot.md](06-chatbot.md) | `chatbot.py` | **Máy trạng thái** nối tất cả (khó nhất) |
| 7 | [07-app.md](07-app.md) | `app.py` | Cửa ngõ API (Flask) |
| 8 | [08-storage-calendar-reminder.md](08-storage-calendar-reminder.md) | 3 file phụ trợ | Lưu trữ, file .ics, worker nhắc |

## Bức tranh tổng (1 tin nhắn đi qua đâu)
```
Người dùng → app.py → chatbot.py → (safety, triage, booking) → data.py / storage.py
                          ↑ nhạc trưởng        ↑ 3 nhân viên        ↑ kho + nơi lưu
```

## Lệnh hay dùng
```bash
cd /Users/hieutm3/Desktop/PRF-SHI
./.venv/bin/python hoc/<file_ban_tao>.py     # chạy file tập
./.venv/bin/python app.py                     # chạy server thật
```

> Quy ước: các file tập bạn tự tạo trong `hoc/` (vd `hoc/triage_demo.py`) để **không
> đụng vào code thật** ở thư mục gốc. Hiểu rồi thì mở file thật đối chiếu.
