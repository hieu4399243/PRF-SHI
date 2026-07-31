"""
Đường dẫn thư mục dữ liệu — khai báo MỘT chỗ duy nhất.

Trước đây storage.py, safety.py và push.py mỗi file tự dựng đường dẫn bằng
`os.path.dirname(__file__)`. Khi các module đó chuyển sang thư mục con thì cả ba
âm thầm trỏ sang chỗ khác (app/core/data, app/triage/data...) — kiểu lỗi chỉ lộ
ra lúc chạy thật. Neo vào đây để chuyển file không còn làm lệch dữ liệu.
"""

import os

# app/core/paths.py -> app/  -> app/data/
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

APPOINTMENTS_PATH = os.path.join(DATA_DIR, "appointments.json")
TOKENS_PATH = os.path.join(DATA_DIR, "device_tokens.json")
DOCTORS_PATH = os.path.join(DATA_DIR, "doctors.json")
PATIENTS_PATH = os.path.join(DATA_DIR, "patients.json")
AUDIT_LOG_PATH = os.path.join(DATA_DIR, "audit_log.jsonl")
OUTBOX_DIR = os.path.join(DATA_DIR, "outbox")

# Gợi ý dịch vụ (REC-01/02) — xem docs/patient-recommendation-design.md
TREATMENT_HISTORY_PATH = os.path.join(DATA_DIR, "treatment_history.json")
REC_LOG_PATH = os.path.join(DATA_DIR, "recommendation_log.json")
PATIENT_PREFS_PATH = os.path.join(DATA_DIR, "patient_preference.json")

# Yêu cầu chuyển tiếp sang nhân viên (CB-05) — xem app/chatbot/steps/handoff_step.py
HANDOFF_PATH = os.path.join(DATA_DIR, "handoff_requests.json")
