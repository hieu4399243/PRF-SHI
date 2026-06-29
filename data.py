"""
Dữ liệu tĩnh cho phòng khám Nha khoa SHI.

Đây là MỘT phòng khám nha khoa. "Khoa" ở đây được hiểu là NHÓM DỊCH VỤ /
loại điều trị nha khoa (sâu răng, nội nha, chỉnh nha...). Triage engine
(xem triage.py) phân loại mô tả triệu chứng tiếng Việt -> đúng nhóm dịch vụ
để hướng người bệnh tới đúng bác sĩ phụ trách.

Trong sản phẩm thật, phần này sẽ được thay bằng cơ sở dữ liệu (DB) thực tế.
"""

from datetime import date, timedelta

# ---------------------------------------------------------------------------
# DANH MỤC DỊCH VỤ NHA KHOA  (mỗi dịch vụ có mã, tên, mô tả và bộ từ khóa)
# Bộ từ khóa được dùng cho "triage engine" (xem triage.py) để phân loại
# triệu chứng tiếng Việt -> đúng dịch vụ.
#
# (Tên biến giữ là DEPARTMENTS để ổn định "data contract" với booking/mobile;
#  về mặt nghiệp vụ đây là các NHÓM DỊCH VỤ trong cùng một phòng khám nha khoa.)
# ---------------------------------------------------------------------------
_SEED_DEPARTMENTS = {
    "kham_tong_quat": {
        "name": "Khám tổng quát & Cạo vôi",
        "desc": "Khám định kỳ, cạo vôi răng, tư vấn vệ sinh răng miệng.",
        "keywords": [
            "khám răng", "khám định kỳ", "kiểm tra răng", "cạo vôi", "lấy cao răng",
            "vôi răng", "cao răng", "vệ sinh răng", "khám tổng quát", "tư vấn răng",
            "mảng bám",
        ],
    },
    "sau_rang": {
        "name": "Trám răng / Sâu răng",
        "desc": "Điều trị sâu răng, trám răng, răng mẻ vỡ.",
        "keywords": [
            "sâu răng", "bị sâu", "lỗ sâu", "trám răng", "hàn răng", "răng mẻ",
            "răng vỡ", "ê buốt khi ăn", "ê buốt", "buốt răng", "đau khi nhai",
            "răng bị đen", "lỗ trên răng", "răng sâu",
        ],
    },
    "noi_nha": {
        "name": "Nội nha (Điều trị tủy)",
        "desc": "Viêm tủy, đau răng dữ dội, áp xe răng.",
        "keywords": [
            "đau răng dữ dội", "nhức răng về đêm", "viêm tủy", "tủy răng", "áp xe răng",
            "áp xe", "đau nhức răng", "răng đau theo nhịp", "đau răng không ngủ được",
            "răng đổi màu", "lấy tủy", "nhức răng", "nhức cả đêm",
        ],
    },
    "nha_chu": {
        "name": "Nha chu (Nướu / Lợi)",
        "desc": "Bệnh lý nướu: viêm lợi, tụt lợi, răng lung lay.",
        "keywords": [
            "chảy máu chân răng", "chảy máu nướu", "chảy máu lợi", "viêm lợi", "viêm nướu",
            "sưng nướu", "sưng lợi", "tụt lợi", "tụt nướu", "răng lung lay", "hôi miệng",
            "nướu", "lợi",
        ],
    },
    "nho_rang": {
        "name": "Tiểu phẫu / Nhổ răng",
        "desc": "Nhổ răng, răng khôn mọc lệch, tiểu phẫu.",
        "keywords": [
            "nhổ răng", "răng khôn", "răng số 8", "răng mọc lệch", "răng mọc ngầm",
            "sưng vùng răng khôn", "đau răng khôn", "nhổ răng khôn", "răng mọc đau",
        ],
    },
    "chinh_nha": {
        "name": "Chỉnh nha (Niềng răng)",
        "desc": "Niềng răng, răng hô, móm, khấp khểnh, lệch khớp cắn.",
        "keywords": [
            "niềng răng", "chỉnh nha", "răng hô", "răng vẩu", "răng móm", "răng khấp khểnh",
            "răng lệch", "răng thưa", "khớp cắn lệch", "mắc cài", "niềng trong suốt",
            "invisalign",
        ],
    },
    "phuc_hinh": {
        "name": "Phục hình / Trồng răng",
        "desc": "Mất răng, trồng răng implant, răng giả, bọc sứ.",
        "keywords": [
            "mất răng", "trồng răng", "implant", "cấy ghép răng", "răng giả", "hàm giả",
            "bọc răng sứ", "bọc sứ", "mão răng", "phục hình", "làm răng sứ", "gãy răng",
        ],
    },
    "tham_my": {
        "name": "Nha khoa thẩm mỹ",
        "desc": "Tẩy trắng răng, dán sứ veneer, thẩm mỹ nụ cười.",
        "keywords": [
            "tẩy trắng răng", "tẩy trắng", "răng ố vàng", "răng vàng", "răng xỉn màu",
            "dán sứ", "veneer", "thẩm mỹ răng", "làm trắng răng", "nụ cười",
        ],
    },
    "nha_nhi": {
        "name": "Nha khoa trẻ em",
        "desc": "Khám và điều trị răng cho trẻ em, răng sữa.",
        "keywords": [
            "răng sữa", "trẻ đau răng", "bé sâu răng", "răng trẻ em", "trám răng cho bé",
            "nhổ răng sữa", "trẻ bị sâu răng", "răng của con", "bé bị đau răng", "răng của bé",
        ],
    },
}

# ---------------------------------------------------------------------------
# DANH SÁCH BÁC SĨ (nha sĩ) theo dịch vụ
# ---------------------------------------------------------------------------
_SEED_DOCTORS = {
    "kham_tong_quat": [
        {"id": "bs_tq_01", "name": "BS. Nguyễn Văn An"},
        {"id": "bs_tq_02", "name": "BS. Trần Thị Bình"},
    ],
    "sau_rang": [
        {"id": "bs_sr_01", "name": "BS. Lê Minh Châu"},
    ],
    "noi_nha": [
        {"id": "bs_nn_01", "name": "BS. Phạm Quốc Dũng"},
    ],
    "nha_chu": [
        {"id": "bs_nc_01", "name": "BS. Hoàng Thị Em"},
    ],
    "nho_rang": [
        {"id": "bs_nhr_01", "name": "BS. Vũ Đình Phúc"},
    ],
    "chinh_nha": [
        {"id": "bs_cn_01", "name": "BS. Đỗ Thị Giang"},
        {"id": "bs_cn_02", "name": "BS. Ngô Văn Hải"},
    ],
    "phuc_hinh": [
        {"id": "bs_ph_01", "name": "BS. Bùi Thị Inh"},
    ],
    "tham_my": [
        {"id": "bs_tm_01", "name": "BS. Dương Văn Khang"},
    ],
    "nha_nhi": [
        {"id": "bs_nhi_01", "name": "BS. Lý Thị Lan"},
    ],
}

# ---------------------------------------------------------------------------
# DANH MỤC ĐANG DÙNG: nạp từ Supabase nếu có DATABASE_URL, ngược lại dùng seed
# tĩnh ở trên (để triage/eval chạy offline). Đổi danh mục online -> restart app.
# ---------------------------------------------------------------------------
def _load_catalog():
    try:
        import storage
        if storage.USE_DB:
            sv = storage.list_services()
            dr = storage.list_doctors()
            if sv:  # DB đã có dữ liệu (đã seed)
                return sv, (dr or _SEED_DOCTORS)
    except Exception:
        pass  # lỗi DB/mạng -> dùng seed tĩnh, không làm app chết
    return _SEED_DEPARTMENTS, _SEED_DOCTORS


DEPARTMENTS, DOCTORS = _load_catalog()

# Khung giờ làm việc mẫu (giờ bắt đầu mỗi slot 30 phút)
WORK_SLOTS = ["08:00", "08:30", "09:00", "09:30", "10:00",
              "14:00", "14:30", "15:00", "15:30", "16:00"]


def generate_available_slots(num_days: int = 5):
    """Sinh khung giờ trống cho vài ngày tới (bỏ qua Chủ nhật).

    Trả về dict: { 'YYYY-MM-DD': ['08:00', '08:30', ...] }
    Trong thực tế dữ liệu này lấy từ lịch thật của bác sĩ.
    """
    slots = {}
    d = date.today() + timedelta(days=1)  # bắt đầu từ ngày mai
    added = 0
    while added < num_days:
        if d.weekday() != 6:  # 6 = Chủ nhật
            slots[d.isoformat()] = list(WORK_SLOTS)
            added += 1
        d += timedelta(days=1)
    return slots
