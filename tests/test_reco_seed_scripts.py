"""
Tests cho 2 script dữ liệu của tính năng gợi ý:

  scripts/backfill_treatment_history.py  — suy lịch sử điều trị từ lịch hẹn đã qua
  scripts/seed_reco_demo.py              — hồ sơ demo để kích hoạt từng reason_code

Chỉ test các hàm THUẦN (`build_records`, `_add_months`): phần ghi xuống storage đã
được phủ ở tests/test_storage.py. Việc lọc dữ liệu ở đây quan trọng vì dữ liệu thật
còn lẫn lịch hẹn của phiên bản CŨ của dự án (mã 'ho_hap', 'tieu_hoa' — thời còn là
phòng khám đa khoa); để lọt vào lịch sử thì engine sẽ gợi ý dịch vụ không tồn tại.

Xem docs/patient-recommendation-design.md §6.4.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import backfill_treatment_history as backfill  # noqa: E402
import seed_reco_demo as seed  # noqa: E402

from app.core.catalog import DEPARTMENTS, service_meta  # noqa: E402

TODAY = date(2026, 7, 30)


def _appt(code="SHI-A00001", status="confirmed", date_str="2026-01-10",
          department_code="kham_tong_quat", phone="0912345678"):
    return {
        "code": code,
        "status": status,
        "date": date_str,
        "department_code": department_code,
        "doctor_id": "bs_tq_01",
        "patient_phone": phone,
    }


# ---------------------------------------------------------------------------
# backfill — bộ lọc
# ---------------------------------------------------------------------------
def test_backfill_nhan_lich_da_qua():
    records, _ = backfill.build_records([_appt()], today=TODAY)
    assert len(records) == 1
    assert records[0]["service_code"] == "kham_tong_quat"
    assert records[0]["appointment_code"] == "SHI-A00001"
    assert records[0]["history_id"] == "th-SHI-A00001"


def test_backfill_bo_qua_lich_chua_toi_ngay():
    """Lịch hẹn tương lai chưa phải lịch sử điều trị."""
    records, skipped = backfill.build_records(
        [_appt(date_str="2026-08-15"), _appt(code="X", date_str=TODAY.isoformat())],
        today=TODAY)
    assert records == []
    assert skipped["chua_qua"] == 2


def test_backfill_bo_qua_lich_da_huy():
    records, skipped = backfill.build_records([_appt(status="cancelled")], today=TODAY)
    assert records == []
    assert skipped["khong_confirmed"] == 1


def test_backfill_bo_qua_ma_dich_vu_khong_con_trong_danh_muc():
    """Dữ liệu còn sót từ phiên bản đa khoa cũ: 'ho_hap', 'tieu_hoa'."""
    records, skipped = backfill.build_records(
        [_appt(department_code="ho_hap"), _appt(code="X", department_code="tieu_hoa")],
        today=TODAY)
    assert records == []
    assert skipped["ma_dv_la"] == 2


def test_backfill_lich_khong_co_sdt_van_vao_lich_su():
    """Không có SĐT thì không gắn được vào bệnh nhân nào, nhưng vẫn phải giữ để
    tính bảng đồng xuất hiện (similar_patients)."""
    records, _ = backfill.build_records([_appt(phone=None)], today=TODAY)
    assert len(records) == 1
    assert records[0]["patient_phone"] is None


def test_backfill_khong_bao_gio_tu_dat_hen_tai_kham():
    """`followup_required` nghĩa là "nha sĩ ĐÃ HẸN tái khám" — một chỉ định của
    người. Dữ liệu lịch hẹn cũ không có thông tin đó, nên backfill phải để False.

    Nếu suy ra từ `recurring_months`, mọi dịch vụ định kỳ đều thành "quá hạn tái
    khám theo chỉ định nha sĩ": luật `followup_due` sẽ nuốt hết `past_treatment`
    và card gợi ý nói sai bản chất lý do."""
    for code in ("kham_tong_quat", "nha_chu", "tham_my", "noi_nha"):
        records, _ = backfill.build_records(
            [_appt(department_code=code, date_str="2026-01-10")], today=TODAY)
        assert records[0]["followup_required"] is False, code
        assert records[0]["followup_due_date"] is None, code


def test_backfill_outcome_luon_success():
    """Không có dữ liệu kết quả điều trị thật -> phỏng đoán 'success'. Test này
    khoá lại phỏng đoán đó để nếu sau này có dữ liệu thật thì phải sửa có ý thức."""
    records, _ = backfill.build_records([_appt()], today=TODAY)
    assert records[0]["outcome"] == "success"


# ---------------------------------------------------------------------------
# _add_months (trong seed) — cộng tháng có kẹp ngày cuối tháng
# ---------------------------------------------------------------------------
def test_add_months_ket_thuc_thang_ngan():
    """31/01 + 1 tháng không được thành 31/02 (ValueError)."""
    assert seed._add_months("2026-01-31", 1) == "2026-02-28"
    assert seed._add_months("2028-01-31", 1) == "2028-02-29"   # năm nhuận


def test_add_months_qua_nam():
    assert seed._add_months("2026-11-15", 6) == "2027-05-15"


def test_add_months_khong_lech_ngay_thuong():
    assert seed._add_months("2026-03-10", 6) == "2026-09-10"


# ---------------------------------------------------------------------------
# seed demo — dữ liệu phải THỰC SỰ kích hoạt được các luật
# ---------------------------------------------------------------------------
def test_seed_history_id_on_dinh():
    """history_id cố định -> chạy lại script không nhân đôi lịch sử."""
    a = {r["history_id"] for r in seed.build_records(TODAY)}
    b = {r["history_id"] for r in seed.build_records(TODAY)}
    assert a == b
    assert len(a) == len(seed.build_records(TODAY))   # không trùng nhau


def test_seed_khong_gan_vao_lich_hen_that():
    """Bản ghi seed phải có appointment_code=None, nếu không sẽ đụng FK tới
    appointments (và giả lịch hẹn không tồn tại)."""
    assert all(r["appointment_code"] is None for r in seed.build_records(TODAY))


def test_seed_chi_dung_ma_dich_vu_that():
    for r in seed.build_records(TODAY):
        assert r["service_code"] in DEPARTMENTS, r["service_code"]


def test_seed_chi_dung_sdt_dai_demo():
    """Toàn bộ SĐT demo phải nằm trong dải 09000001xx để --purge xoá đúng và
    không bao giờ chạm dữ liệu bệnh nhân thật."""
    for r in seed.build_records(TODAY):
        assert r["patient_phone"].startswith(seed.DEMO_PHONE_PREFIX)


def test_seed_co_ho_so_qua_han_tai_kham():
    """Phải có ít nhất 1 hồ sơ quá hạn tái khám, nếu không luật followup_due
    (card mạnh nhất trong wireframe) không có gì để demo."""
    today_iso = TODAY.isoformat()
    qua_han = [r for r in seed.build_records(TODAY)
               if r["followup_due_date"] and r["followup_due_date"] < today_iso]
    assert qua_han


def test_seed_co_ho_so_cold_start():
    """Phải có hồ sơ < 3 lượt để demo nhánh cold-start (TC-REC-002)."""
    from collections import Counter
    counts = Counter(r["patient_phone"] for r in seed.build_records(TODAY))
    assert any(n < 3 for n in counts.values())


def test_seed_du_support_cho_similar_patients():
    """Luật similar_patients cần >= 3 bệnh nhân dùng cùng một dịch vụ mới đủ
    support. Thiếu thì luật im lặng và không demo được."""
    from collections import defaultdict
    by_patient = defaultdict(set)
    for r in seed.build_records(TODAY):
        by_patient[r["patient_phone"]].add(r["service_code"])
    dung_kham_tong_quat = [p for p, s in by_patient.items() if "kham_tong_quat" in s]
    ca_hai = [p for p in dung_kham_tong_quat if "sau_rang" in by_patient[p]]
    assert len(dung_kham_tong_quat) >= 3
    assert len(ca_hai) >= 3


def test_seed_co_ho_so_tre_em():
    """Cần hồ sơ trẻ em để demo luật theo độ tuổi (AC SMMG-65)."""
    assert any(birth_year >= 2014 for _p, _n, birth_year, _v in seed.DEMO_PATIENTS)


def test_seed_chi_dat_hen_tai_kham_o_ho_so_duoc_khai_bao():
    """Chỉ hồ sơ có khai `followup` mới được đặt hẹn tái khám. Nếu đặt cho mọi dịch
    vụ định kỳ thì luật `followup_due` che hết `past_treatment` khi demo."""
    khai_bao = {(p, i) for p, _n, _b, visits in seed.DEMO_PATIENTS
                for i, v in enumerate(visits, start=1) if v[3]}
    for r in seed.build_records(TODAY):
        i = int(r["history_id"].rsplit("-", 1)[1])
        expected = (r["patient_phone"], i) in khai_bao
        assert bool(r["followup_due_date"]) is expected, r["history_id"]


def test_seed_co_ca_followup_due_lan_past_treatment():
    """Bộ hồ sơ demo phải kích hoạt được CẢ HAI luật, nếu không thì một trong hai
    không có gì để chứng minh khi demo."""
    records = seed.build_records(TODAY)
    today_iso = TODAY.isoformat()
    co_followup_qua_han = any(
        r["followup_due_date"] and r["followup_due_date"] < today_iso for r in records)
    co_dich_vu_dinh_ky_qua_chu_ky = any(
        service_meta(r["service_code"])["recurring_months"] and not r["followup_due_date"]
        for r in records)
    assert co_followup_qua_han
    assert co_dich_vu_dinh_ky_qua_chu_ky
