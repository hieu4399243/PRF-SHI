"""
Suy ra `treatment_history` từ các lịch hẹn ĐÃ QUA — chạy một lần khi bật tính năng gợi ý.

Engine gợi ý (REC-01/02) đọc lịch sử ĐIỀU TRỊ, nhưng dự án chỉ có lịch HẸN. Script
này lấp khoảng trống đó cho dữ liệu đã tồn tại; từ nay về sau nha sĩ tạo bản ghi
điều trị qua `POST /api/doctor/treatment`.

Quy ước suy diễn (và giới hạn của nó):

  - Chỉ nhận lịch `status='confirmed'` có `date` < hôm nay. Đây là PHỎNG ĐOÁN
    "đã hẹn và tới ngày thì coi như đã khám" — dự án không có dữ liệu check-in
    nên không thể phân biệt bệnh nhân đã đến với bệnh nhân vắng mặt (no-show).
  - `outcome` luôn là 'success': không có dữ liệu kết quả điều trị thật.
  - `followup_required` LUÔN là False. `followup_required` mang nghĩa "nha sĩ đã
    hẹn tái khám" — một CHỈ ĐỊNH của người, và dữ liệu cũ không có thông tin đó.
    Nếu suy nó ra từ `recurring_months` thì mọi dịch vụ định kỳ đều thành "quá hạn
    tái khám theo chỉ định nha sĩ", luật `followup_due` sẽ nuốt hết luật
    `past_treatment` và card gợi ý nói sai bản chất. Việc gợi ý theo chu kỳ đã do
    luật `past_treatment` lo. Từ nay nha sĩ đặt hẹn tái khám qua
    `POST /api/doctor/treatment`.
  - Bỏ qua lịch có `department_code` không còn trong danh mục (dữ liệu từ phiên
    bản cũ của dự án, vd. 'ho_hap', 'tieu_hoa').

Chạy:
    ./.venv/bin/python scripts/backfill_treatment_history.py --dry-run
    ./.venv/bin/python scripts/backfill_treatment_history.py
"""

import argparse
import os
import sys
from datetime import date, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.core import storage  # noqa: E402
from app.core.catalog import DEPARTMENTS  # noqa: E402


def _resolve_patient_id(phone):
    """Tìm HỒ SƠ bệnh nhân (bảng `patients`) theo SĐT. None nếu chưa có hồ sơ.

    `patients.phone` là UNIQUE nên khớp chính xác. Không tìm thấy thì bản ghi lịch
    sử vẫn được giữ và neo theo SĐT — engine gộp lịch sử theo (patient_id OR phone).
    """
    if not phone:
        return None
    try:
        for p in storage.list_patients():
            if (p.get("phone") or "").strip() == phone:
                return p.get("id")
    except Exception as exc:  # noqa: BLE001 - thiếu DB/bảng thì bỏ qua, không chặn backfill
        print(f"[backfill] Không tra được hồ sơ bệnh nhân theo SĐT: {exc}")
    return None


def build_records(appointments, today=None):
    """Đổi danh sách lịch hẹn -> danh sách bản ghi điều trị. Hàm thuần, test được."""
    today = (today or date.today()).isoformat()
    now = datetime.now().isoformat(timespec="seconds")
    records, skipped = [], {"chua_qua": 0, "khong_confirmed": 0, "ma_dv_la": 0}

    for appt in appointments:
        if appt.get("status") != "confirmed":
            skipped["khong_confirmed"] += 1
            continue
        appt_date = appt.get("date") or ""
        if appt_date >= today:
            skipped["chua_qua"] += 1
            continue
        code = appt.get("department_code")
        if code not in DEPARTMENTS:
            skipped["ma_dv_la"] += 1
            continue

        phone = appt.get("patient_phone") or None
        records.append({
            "history_id": f"th-{appt['code']}",
            "appointment_code": appt["code"],
            "patient_id": _resolve_patient_id(phone),
            "patient_phone": phone,
            "service_code": code,
            "doctor_id": appt.get("doctor_id"),
            "treatment_date": appt_date,
            "outcome": "success",
            "followup_required": False,
            "followup_due_date": None,
            "patient_rating": None,
            "created_at": now,
        })
    return records, skipped


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="chỉ in ra, không ghi vào storage")
    args = parser.parse_args()

    print(f"[backfill] Chế độ lưu trữ: "
          f"{'Postgres/Supabase' if storage.USE_DB else 'file JSON (local)'}")

    appointments = storage.list_appointments()
    records, skipped = build_records(appointments)

    print(f"[backfill] {len(appointments)} lịch hẹn -> {len(records)} bản ghi điều trị.")
    print(f"[backfill] Bỏ qua: {skipped['chua_qua']} chưa tới ngày, "
          f"{skipped['khong_confirmed']} không phải 'confirmed', "
          f"{skipped['ma_dv_la']} mã dịch vụ không còn trong danh mục.")

    if args.dry_run:
        for r in records[:10]:
            print(f"    {r['treatment_date']}  {r['service_code']:<16} "
                  f"{r['patient_phone'] or '(không SĐT)':<12}")
        if len(records) > 10:
            print(f"    ... và {len(records) - 10} bản ghi nữa")
        print("[backfill] --dry-run: KHÔNG ghi gì.")
        return

    added = sum(1 for r in records if storage.add_treatment(r))
    print(f"[backfill] Đã thêm {added} bản ghi mới, "
          f"{len(records) - added} bản ghi đã tồn tại (bỏ qua).")
    no_phone = sum(1 for r in records if not r["patient_phone"])
    if no_phone:
        print(f"[backfill] ⚠️  {no_phone} bản ghi không có SĐT -> không gắn được vào "
              "bệnh nhân nào, chỉ dùng cho bảng đồng xuất hiện (similar_patients).")


if __name__ == "__main__":
    main()
