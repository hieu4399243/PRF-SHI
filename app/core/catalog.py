"""
Dữ liệu tĩnh cho phòng khám Nha khoa SHI.

Đây là MỘT phòng khám nha khoa. "Khoa" ở đây được hiểu là NHÓM DỊCH VỤ /
loại điều trị nha khoa (sâu răng, nội nha, chỉnh nha...). Triage engine
(xem triage.py) phân loại mô tả triệu chứng tiếng Việt -> đúng nhóm dịch vụ
để hướng người bệnh tới đúng bác sĩ phụ trách.

Trong sản phẩm thật, phần này sẽ được thay bằng cơ sở dữ liệu (DB) thực tế.
"""

import os
from datetime import date, datetime, timedelta

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
            # bổ sung: từ vựng khám/vệ sinh định kỳ
            "đánh bóng răng", "đánh bóng", "vệ sinh răng miệng", "khám răng miệng",
            "kiểm tra răng tổng quát", "chải răng", "chăm sóc răng", "gói khám",
            "khám tổng thể", "tư vấn răng miệng", "định kỳ",
        ],
    },
    "sau_rang": {
        "name": "Trám răng / Sâu răng",
        "desc": "Điều trị sâu răng, trám răng, răng mẻ vỡ.",
        "keywords": [
            "sâu răng", "bị sâu", "lỗ sâu", "trám răng", "trám lại", "hàn răng",
            "răng mẻ", "bị mẻ", "răng vỡ", "ê buốt khi ăn", "ê buốt", "buốt răng",
            "đau khi nhai", "đau khi ăn", "cộm", "răng bị đen", "lỗ trên răng",
            "răng sâu", "đau răng", "răng đau",
            # bổ sung: mẻ vỡ, giắt thức ăn, miếng trám bong
            "trám", "hàn lại", "miếng trám", "bị vỡ", "vỡ một mảnh", "sứt mẻ",
            "cộm khi nhai", "giắt", "thức ăn giắt", "răng có lỗ", "răng bị mẻ",
        ],
    },
    "noi_nha": {
        "name": "Nội nha (Điều trị tủy)",
        "desc": "Viêm tủy, đau răng dữ dội, áp xe răng.",
        "keywords": [
            "đau răng dữ dội", "nhức răng về đêm", "viêm tủy", "tủy răng", "áp xe răng",
            "áp xe", "đau nhức răng", "răng đau theo nhịp", "đau răng không ngủ được",
            "răng đổi màu", "lấy tủy", "nhức răng", "nhức cả đêm", "đau răng", "răng đau",
            # bổ sung: chữa tủy, chết tủy, mưng mủ, đau tự phát
            "chữa tủy", "điều trị tủy", "chết tủy", "răng chết tủy", "nội nha",
            "mưng mủ", "có mủ", "sưng mủ", "đau nhói", "đau tự phát", "đau buốt",
            "kháng sinh", "nhức về đêm",
        ],
    },
    "nha_chu": {
        "name": "Nha chu (Nướu / Lợi)",
        "desc": "Bệnh lý nướu: viêm lợi, tụt lợi, răng lung lay.",
        "keywords": [
            "chảy máu chân răng", "chảy máu nướu", "chảy máu lợi", "viêm lợi", "viêm nướu",
            "sưng nướu", "sưng lợi", "tụt lợi", "tụt nướu", "răng lung lay", "hôi miệng",
            "nướu", "lợi",
            # bổ sung: nha chu, túi nha chu, chảy máu khi đánh răng
            "nha chu", "viêm nha chu", "túi nha chu", "chảy máu khi đánh răng",
            "lung lay", "kẽ lợi", "chân răng hở", "lẫn máu", "túi mủ",
            "cạo vôi sâu", "dưới nướu", "chỉ nha khoa",
        ],
    },
    "nho_rang": {
        "name": "Tiểu phẫu / Nhổ răng",
        "desc": "Nhổ răng, răng khôn mọc lệch, tiểu phẫu.",
        "keywords": [
            "nhổ răng", "răng khôn", "răng số 8", "răng mọc lệch", "răng mọc ngầm",
            "sưng vùng răng khôn", "đau răng khôn", "nhổ răng khôn", "răng mọc đau",
            # bổ sung: tiểu phẫu, răng thừa, lợi trùm, chân răng sót
            "nhổ", "tiểu phẫu", "nhổ bớt răng", "răng thừa", "răng hỏng",
            "lợi trùm", "viêm lợi trùm", "chân răng sót", "chân răng còn sót",
            "mọc đâm ngang", "gây tê",
        ],
    },
    "chinh_nha": {
        "name": "Chỉnh nha (Niềng răng)",
        "desc": "Niềng răng, răng hô, móm, khấp khểnh, lệch khớp cắn.",
        "keywords": [
            "niềng răng", "chỉnh nha", "răng hô", "răng vẩu", "răng móm", "răng khấp khểnh",
            "răng lệch", "răng thưa", "khớp cắn lệch", "mắc cài", "niềng trong suốt",
            "invisalign",
            # bổ sung: khớp cắn, chen chúc, khay trong suốt, nắn chỉnh
            "niềng", "khớp cắn", "khớp cắn ngược", "cắn ngược", "cắn không khớp",
            "răng chen chúc", "chen chúc", "nắn chỉnh", "răng chìa", "chìa ra ngoài",
            "khay trong suốt", "hàm hô", "hàm móm", "răng mọc chen",
            "đưa ra trước", "mặt bị lệch", "lệch một bên",
        ],
    },
    "phuc_hinh": {
        "name": "Phục hình / Trồng răng",
        "desc": "Mất răng, trồng răng implant, răng giả, bọc sứ.",
        "keywords": [
            "mất răng", "trồng răng", "implant", "cấy ghép răng", "răng giả", "hàm giả",
            "bọc răng sứ", "bọc sứ", "mão răng", "phục hình", "làm răng sứ", "gãy răng",
            # bổ sung: cầu răng, mão, tiêu xương, rụng răng
            "cầu răng", "bọc mão", "mão", "cấy ghép", "tiêu xương", "rụng răng",
            "rụng mất răng", "rụng mất", "răng đã mất", "mất răng lâu năm", "răng sứ",
        ],
    },
    "tham_my": {
        "name": "Nha khoa thẩm mỹ",
        "desc": "Tẩy trắng răng, dán sứ veneer, thẩm mỹ nụ cười.",
        "keywords": [
            "tẩy trắng răng", "tẩy trắng", "răng ố vàng", "răng vàng", "răng xỉn màu",
            "dán sứ", "veneer", "thẩm mỹ răng", "làm trắng răng", "nụ cười",
            # bổ sung: ngả màu, đốm trắng, dán veneer, thẩm mỹ
            "dán veneer", "thẩm mỹ", "răng ngả màu", "ngả màu", "xỉn màu",
            "đốm trắng", "trắng sáng", "hình dáng răng", "làm đẹp nụ cười",
            "nhiễm kháng sinh",
        ],
    },
    "nha_nhi": {
        "name": "Nha khoa trẻ em",
        "desc": "Khám và điều trị răng cho trẻ em, răng sữa.",
        "keywords": [
            "răng sữa", "trẻ đau răng", "bé sâu răng", "răng trẻ em", "trám răng cho bé",
            "nhổ răng sữa", "trẻ bị sâu răng", "răng của con", "bé bị đau răng", "răng của bé",
            "con tôi", "bé", "trẻ", "em bé",
            # bổ sung: từ vựng RIÊNG của nha khoa trẻ em (không trùng chuyên khoa khác)
            "sún răng", "sún", "mút tay", "tráng fluor", "fluor", "hàm sữa",
            "cho bé", "cho con", "cho trẻ", "răng vĩnh viễn", "nha khoa trẻ em",
            "phòng khám thân thiện",
        ],
    },
}

# ---------------------------------------------------------------------------
# MÔ TẢ ĐẦY ĐỦ CHO TỪNG DỊCH VỤ — dùng để trả lời câu hỏi "X là khám gì / là gì".
# Khóa theo MÃ dịch vụ (ổn định dù danh mục nạp từ DB hay seed) nên overlay được
# lên cả hai chế độ mà không cần thêm cột trên Supabase. Thiếu mã -> fallback 'desc'.
# ---------------------------------------------------------------------------
SERVICE_INFO = {
    "kham_tong_quat":
        "Khám tổng quát & cạo vôi là kiểm tra sức khỏe răng miệng định kỳ: bác sĩ soi "
        "toàn bộ răng – nướu, lấy cao/vôi răng, đánh bóng và tư vấn cách vệ sinh. Nên làm "
        "khoảng 6 tháng/lần để phát hiện sớm sâu răng, viêm nướu.",
    "sau_rang":
        "Trám răng / sâu răng là điều trị các lỗ sâu, răng mẻ vỡ hoặc ê buốt: bác sĩ làm "
        "sạch phần mô sâu rồi trám lại bằng vật liệu thẩm mỹ để phục hồi hình dạng và khả "
        "năng ăn nhai của răng.",
    "noi_nha":
        "Nội nha (điều trị tủy) xử lý khi tủy răng bị viêm/nhiễm trùng gây đau nhức dữ dội, "
        "ê buốt kéo dài hoặc áp xe: bác sĩ lấy tủy, làm sạch và trám bít ống tủy để giữ lại "
        "răng thật thay vì phải nhổ.",
    "nha_chu":
        "Nha chu điều trị bệnh lý ở nướu/lợi và mô quanh răng: chảy máu chân răng, sưng "
        "nướu, tụt lợi, răng lung lay, hôi miệng — bằng cạo vôi sâu, làm sạch túi nha chu "
        "và hướng dẫn chăm sóc.",
    "nho_rang":
        "Tiểu phẫu / nhổ răng gồm nhổ răng hư không giữ được, răng khôn mọc lệch/mọc ngầm "
        "và các tiểu phẫu vùng miệng, được thực hiện nhẹ nhàng có gây tê.",
    "chinh_nha":
        "Chỉnh nha (niềng răng) sắp xếp lại răng hô, móm, khấp khểnh, thưa hoặc lệch khớp "
        "cắn bằng mắc cài hoặc khay trong suốt (Invisalign) để có hàm răng đều và khớp cắn "
        "đúng.",
    "phuc_hinh":
        "Phục hình / trồng răng phục hồi răng đã mất hoặc hư nặng: cấy ghép Implant, làm "
        "cầu răng, răng giả tháo lắp hoặc bọc răng sứ, giúp ăn nhai và thẩm mỹ.",
    "tham_my":
        "Nha khoa thẩm mỹ giúp răng trắng đẹp hơn: tẩy trắng răng, dán sứ Veneer và chỉnh "
        "sửa hình dáng răng để cải thiện nụ cười.",
    "nha_nhi":
        "Nha khoa trẻ em khám và điều trị cho bé: sâu răng sữa, trám/nhổ răng sữa và hướng "
        "dẫn chăm sóc răng cho trẻ trong môi trường thân thiện.",
}


# ---------------------------------------------------------------------------
# NHÓM TUỔI — feature `age_group` của engine gợi ý (SEQ 4.opt.1).
# AC SMMG-65 yêu cầu gợi ý dựa trên "lịch sử điều trị / tình trạng / độ tuổi".
# ---------------------------------------------------------------------------
AGE_GROUPS = ("child", "teen", "adult", "senior")


def age_group_of(birth_year, today=None):
    """Đổi năm sinh -> nhóm tuổi. None nếu không biết năm sinh (hoặc vô lý).

    Không biết tuổi KHÁC với "người lớn": trả None để engine bỏ qua các luật theo
    tuổi, thay vì mặc định 'adult' rồi gợi ý sai cho trẻ em.
    """
    if not birth_year:
        return None
    year = (today or date.today()).year
    try:
        age = year - int(birth_year)
    except (TypeError, ValueError):
        return None
    if age < 0 or age > 120:      # dữ liệu nhập sai -> coi như không biết
        return None
    if age < 13:
        return "child"
    if age < 18:
        return "teen"
    if age < 60:
        return "adult"
    return "senior"


# ---------------------------------------------------------------------------
# THÔNG TIN VẬN HÀNH CỦA DỊCH VỤ — thời lượng, giá, chu kỳ, nhóm tuổi phù hợp.
#
# Khoá theo MÃ dịch vụ và overlay lên danh mục (giống SERVICE_INFO) nên không cần
# thêm cột trên Supabase. Dùng cho:
#   - modal chi tiết REC-02 (TC-REC-007 đòi hiện thời lượng + giá cơ bản)
#   - state cold-start (hiện "30 phút · từ 200k" thay cho % phù hợp)
#   - luật `past_treatment` (recurring_months) và luật/bộ lọc theo tuổi (age_groups)
#
# `recurring_months`: chu kỳ khuyến nghị. CHỈ đặt cho dịch vụ có tính định kỳ —
# thiếu khoá này nghĩa là dịch vụ KHÔNG được gợi ý lặp lại (không ai cần trồng
# implant định kỳ).
# `age_groups`: nhóm tuổi được phép gợi ý. `age_affinity`: điểm cộng khi đúng nhóm.
#
# ⚠️ GIÁ Ở ĐÂY LÀ SỐ MINH HOẠ, chưa phải bảng giá thật của phòng khám — xem §18
# docs/patient-recommendation-design.md.
# ---------------------------------------------------------------------------
DEFAULT_SERVICE_META = {
    "duration_min": 30,
    "price_from": None,
    "price_to": None,
    "recurring_months": None,
    "age_groups": AGE_GROUPS,
    "age_affinity": {},
}

SERVICE_META = {
    "kham_tong_quat": {"duration_min": 30, "price_from": 200_000, "price_to": 350_000,
                       "recurring_months": 6},
    "sau_rang":       {"duration_min": 45, "price_from": 300_000, "price_to": 800_000},
    "noi_nha":        {"duration_min": 60, "price_from": 1_500_000, "price_to": 4_000_000},
    "nha_chu":        {"duration_min": 45, "price_from": 500_000, "price_to": 2_000_000,
                       "recurring_months": 3},
    "nho_rang":       {"duration_min": 45, "price_from": 500_000, "price_to": 3_000_000},
    "chinh_nha":      {"duration_min": 60, "price_from": 25_000_000, "price_to": 60_000_000,
                       "age_groups": ("teen", "adult"),
                       "age_affinity": {"teen": 0.25}},
    "phuc_hinh":      {"duration_min": 60, "price_from": 3_000_000, "price_to": 25_000_000,
                       "age_groups": ("adult", "senior"),
                       "age_affinity": {"senior": 0.25}},
    "tham_my":        {"duration_min": 45, "price_from": 1_000_000, "price_to": 8_000_000,
                       "recurring_months": 12,
                       "age_groups": ("teen", "adult", "senior")},
    "nha_nhi":        {"duration_min": 30, "price_from": 200_000, "price_to": 500_000,
                       "recurring_months": 6,
                       "age_groups": ("child",),
                       "age_affinity": {"child": 0.25}},
}


def service_meta(code):
    """Thông tin vận hành của một dịch vụ, đã điền đủ khoá mặc định.

    Danh mục có thể nạp từ Supabase và chứa mã CHƯA có trong SERVICE_META (admin
    thêm dịch vụ mới qua dashboard) -> luôn trả về dict đủ khoá thay vì KeyError.
    """
    return {**DEFAULT_SERVICE_META, **SERVICE_META.get(code, {})}


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
        from . import storage
        if storage.USE_DB:
            sv = storage.list_services()
            dr = storage.list_doctors()
            if sv:  # DB đã có dữ liệu (đã seed)
                return sv, (dr or _SEED_DOCTORS)
    except Exception as exc:
        # lỗi DB/mạng -> dùng seed tĩnh, không làm app chết, NHƯNG phải log lại:
        # nếu không, một query DB bị lỗi thật (vd. sai cột do migrate dở dang)
        # trông giống hệt "DB chưa seed dữ liệu" -> khó phát hiện khi vận hành.
        print(f"[data] CẢNH BÁO: lỗi khi nạp danh mục từ DB, dùng seed tĩnh. Lỗi: {exc}")
    return _SEED_DEPARTMENTS, _SEED_DOCTORS


DEPARTMENTS, DOCTORS = _load_catalog()

# Khung giờ làm việc mẫu (giờ bắt đầu mỗi slot 30 phút)
WORK_SLOTS = ["08:00", "08:30", "09:00", "09:30", "10:00",
              "14:00", "14:30", "15:00", "15:30", "16:00"]


# ---------------------------------------------------------------------------
# GIỜ TRỰC CỦA PHÒNG KHÁM  (dùng cho lời hẹn gọi lại — CB-05 / SMMG-52)
# ---------------------------------------------------------------------------
# CỐ Ý TÁCH KHỎI `WORK_SLOTS`. Bản đầu suy giờ trực từ WORK_SLOTS cho "khỏi lệch
# nhau", nhưng đó là ép sai quan hệ — hai thứ này PHẢI lệch nhau:
#
#   WORK_SLOTS  = các mốc BẮT ĐẦU MỘT CA KHÁM  -> dùng để đặt lịch hẹn
#   giờ trực    = khoảng LỄ TÂN CÓ MẶT nghe máy -> dùng để hẹn gọi lại
#
# Giờ trực luôn RỘNG HƠN: lễ tân vẫn nghe máy lúc 12:30 hay 17:00 dù không có ca
# khám nào bắt đầu lúc đó. Hậu quả của việc gộp: WORK_SLOTS chỉ có 10 slot nên
# suy ra "đóng cửa lúc 10:30", và bệnh nhân nhắn lúc 10:38 sáng thứ 6 — giờ hành
# chính bình thường — bị bot báo "ngoài giờ làm việc, chưa có nhân viên trực".
#
# Đổi giờ trực bằng biến môi trường, KHÔNG phải sửa code:
#   CLINIC_HOURS        "08:00-12:00,13:30-17:30"  (nhiều ca, phân tách bằng dấu phẩy)
#   CLINIC_CLOSED_DAYS  "6" = nghỉ Chủ nhật; "5,6" = nghỉ T7+CN; rỗng = làm cả tuần
#                       (0 = Thứ 2 ... 6 = Chủ nhật, khớp datetime.weekday())
DEFAULT_CLINIC_HOURS = "08:00-12:00,13:30-17:30"
DEFAULT_CLINIC_CLOSED_DAYS = ""  # phòng khám làm cả tuần


def _to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def clinic_periods():
    """Các ca trực trong ngày, dạng [(phút_mở, phút_đóng), ...], đã sắp xếp.

    Cấu hình hỏng (thiếu dấu '-', giờ không parse được, ca rỗng) -> quay về mặc
    định thay vì ném lỗi: một biến môi trường gõ sai không được phép làm chatbot
    y tế chết, và "sai giờ hẹn gọi lại" còn nhẹ hơn "không trả lời được bệnh nhân".
    """
    spec = (os.environ.get("CLINIC_HOURS") or "").strip() or DEFAULT_CLINIC_HOURS
    try:
        periods = []
        for chunk in spec.split(","):
            open_txt, close_txt = chunk.strip().split("-")
            open_, close = _to_minutes(open_txt), _to_minutes(close_txt)
            if not 0 <= open_ < close <= 24 * 60:
                raise ValueError(chunk)
            periods.append((open_, close))
        if not periods:
            raise ValueError(spec)
        return sorted(periods)
    except (ValueError, AttributeError):
        print(f"[catalog] CẢNH BÁO: CLINIC_HOURS không hợp lệ ({spec!r}), "
              f"dùng mặc định {DEFAULT_CLINIC_HOURS}.")
        return sorted(
            (_to_minutes(a), _to_minutes(b))
            for a, b in (c.split("-") for c in DEFAULT_CLINIC_HOURS.split(","))
        )


def clinic_closed_days():
    """Các thứ trong tuần phòng khám nghỉ, dạng set (0 = Thứ 2 ... 6 = Chủ nhật)."""
    spec = os.environ.get("CLINIC_CLOSED_DAYS")
    if spec is None:
        spec = DEFAULT_CLINIC_CLOSED_DAYS
    days = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            day = int(part)
        except ValueError:
            continue  # rác trong cấu hình -> bỏ qua phần đó, không làm sập
        if 0 <= day <= 6:
            days.add(day)
    return days


def is_working_time(when) -> bool:
    """Thời điểm `when` (datetime) có nằm trong giờ trực của phòng khám không?"""
    if when.weekday() in clinic_closed_days():
        return False
    minutes = when.hour * 60 + when.minute
    return any(open_ <= minutes < close for open_, close in clinic_periods())


def next_working_time(when):
    """Mốc mở cửa GẦN NHẤT kể từ `when`. Trả về datetime.

    Dùng cho lời hẹn gọi lại khi bệnh nhân nhắn ngoài giờ. Đang trong giờ trực
    thì trả về chính `when` (gọi lại được ngay).
    """
    periods = clinic_periods()
    closed = clinic_closed_days()
    cursor = when
    for _ in range(9):  # đủ vượt qua cả tuần nghỉ dài nhất còn có ngày mở cửa
        if cursor.weekday() not in closed:
            minutes = cursor.hour * 60 + cursor.minute
            for open_, close in periods:
                if minutes < open_:
                    return cursor.replace(hour=open_ // 60, minute=open_ % 60,
                                          second=0, microsecond=0)
                if open_ <= minutes < close:
                    return cursor.replace(second=0, microsecond=0)
        # Hết giờ trong ngày -> thử đầu ngày hôm sau.
        cursor = (cursor + timedelta(days=1)).replace(hour=0, minute=0,
                                                      second=0, microsecond=0)
    return cursor


def generate_available_slots(num_days: int = 5, now=None):
    """Sinh khung giờ trống cho hôm nay (phần còn lại) + `num_days` ngày tới.

    Trả về dict: { 'YYYY-MM-DD': ['08:00', '08:30', ...] }
    Trong thực tế dữ liệu này lấy từ lịch thật của bác sĩ.
    `now` (datetime) để cố định thời gian khi test.

    Hôm nay CỐ Ý được tính vào: nha sĩ chỉ ghi được kết quả khám cho lịch hẹn đã
    tới ngày (`chua_toi_ngay` trong doctor_api._treatment_blocker). Nếu ngày sớm
    nhất đặt được là ngày mai thì mọi lịch đặt qua app đều nằm ở tương lai, không
    lịch nào ghi được kết quả, `treatment_history` rỗng vĩnh viễn và màn gợi ý kẹt
    ở cold-start — đứt ngay mắt xích đầu của luồng đặt lịch -> khám -> gợi ý.
    Khung giờ đã trôi qua trong ngày thì không hiện, nên vẫn không đặt được lịch
    vào quá khứ; hết giờ làm thì hôm nay biến mất khỏi danh sách như trước.
    """
    slots = {}
    now = now or datetime.now()
    today = now.date()
    if today.weekday() != 6:
        hhmm = now.strftime("%H:%M")
        remaining = [s for s in WORK_SLOTS if s > hhmm]
        if remaining:
            slots[today.isoformat()] = remaining

    d = today + timedelta(days=1)
    added = 0
    while added < num_days:
        if d.weekday() != 6:  # 6 = Chủ nhật
            slots[d.isoformat()] = list(WORK_SLOTS)
            added += 1
        d += timedelta(days=1)
    return slots
