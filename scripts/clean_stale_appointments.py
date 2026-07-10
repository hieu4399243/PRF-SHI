"""
Dọn lịch hẹn 'rác' trong Supabase — các bản ghi có doctor_id KHÔNG thuộc danh mục
bác sĩ nha khoa hiện tại (di sản từ phiên bản đa khoa cũ: Hô hấp/Tiêu hóa...), và
tùy chọn xóa các bản ghi test theo tên bệnh nhân.

Chỉ chạy khi USE_DB=True (có DATABASE_URL). Mặc định chạy chế độ "khô" (dry-run):
chỉ liệt kê, KHÔNG xóa. Thêm cờ --apply để xóa thật.

    ./.venv/bin/python scripts/clean_stale_appointments.py            # xem trước
    ./.venv/bin/python scripts/clean_stale_appointments.py --apply    # xóa thật
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import storage
from app.data import DOCTORS

# Tên bệnh nhân của các bản ghi test cần dọn (khớp chính xác).
TEST_PATIENT_NAMES = {"Bệnh nhân Test"}


def main():
    apply = "--apply" in sys.argv
    if not storage.USE_DB:
        print("USE_DB=False — đang dùng file JSON, script này chỉ dành cho Supabase.")
        return

    valid_ids = {d["id"] for docs in DOCTORS.values() for d in docs}
    appts = storage.list_appointments()

    stale = [a for a in appts if a.get("doctor_id") not in valid_ids]
    tests = [a for a in appts if a.get("doctor_id") in valid_ids
             and a.get("patient_name") in TEST_PATIENT_NAMES]
    victims = stale + tests
    codes = [a["code"] for a in victims]

    print(f"Tổng lịch: {len(appts)}")
    print(f"  - Rác (doctor_id không phải nha khoa): {len(stale)}")
    print(f"  - Bản ghi test ({', '.join(TEST_PATIENT_NAMES)}): {len(tests)}")
    print(f"  => Sẽ xóa: {len(victims)} bản ghi")
    for a in victims:
        print(f"       {a['code']}  {a['date']} {a['time']}  {a.get('department')}  "
              f"{a.get('doctor')}  ({a.get('patient_name')})")

    if not victims:
        print("Không có gì để xóa. ✅")
        return
    if not apply:
        print("\n(Chạy khô — chưa xóa. Thêm --apply để xóa thật.)")
        return

    storage.init_schema()
    with storage._connect() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM appointments WHERE code = ANY(%s)", (codes,))
        deleted = cur.rowcount
        conn.commit()
    print(f"\nĐã xóa {deleted} bản ghi khỏi Supabase. ✅")


if __name__ == "__main__":
    main()
