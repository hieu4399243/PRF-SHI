"""
Bộ luật chấm điểm gợi ý — phần "quy tắc nghiệp vụ tối thiểu" của doc gốc v2.

Mỗi luật sinh ra một TÍN HIỆU độc lập:

    {"service_code", "weight" 0..1, "reason_code", "ctx" (dữ liệu cho câu lý do)}

Nhiều tín hiệu cùng trỏ về một dịch vụ được gộp bằng **noisy-OR**:

    confidence = 1 - Π(1 - wᵢ)   , chặn trần 0.95

Vì sao noisy-OR chứ không phải cộng/lấy max:
  - Cộng thẳng thì 3 tín hiệu yếu (0.4 mỗi cái) vượt 1.0 -> phải kẹp, và kẹp làm
    mất khả năng phân biệt giữa "khá phù hợp" và "rất phù hợp".
  - Lấy max thì thêm bằng chứng KHÔNG làm tăng độ tin cậy, sai trực giác: quá hạn
    tái khám VÀ bệnh nhân tương tự cũng làm, phải chắc hơn chỉ một trong hai.
  - Trần 0.95: hệ thống không bao giờ hứa chắc chắn 100% về một việc y tế.

TOÀN BỘ module này là hàm thuần — không DB, không mạng, không thời gian hệ thống
(ngày "hôm nay" luôn đi vào qua features). Nhờ vậy điểm số tái lập được và eval
chấm lại được đúng con số.
"""

from ..core.catalog import DEPARTMENTS, service_meta
from . import features as feat

# --- Trọng số của từng luật -------------------------------------------------
# Đặt tên hằng thay vì rải số trong code: đây là các con số sẽ phải hiệu chỉnh
# theo feedback của nha sĩ, cần tìm được ở một chỗ.
W_FOLLOWUP_BASE = 0.55        # tái khám vừa quá hạn
W_FOLLOWUP_MAX = 0.85         # quá hạn rất lâu
W_RECURRING = 0.50            # dịch vụ định kỳ tới chu kỳ
W_RECURRING_LATE = 0.15       # cộng thêm khi quá 1.5x chu kỳ
W_SIMILAR_FACTOR = 0.60       # nhân với P(B|A)
W_AGE = 0.25                  # đúng nhóm tuổi (lấy từ age_affinity)
W_POPULAR_FACTOR = 0.20       # nhân với tỉ trọng phổ biến

# Ngưỡng hiển thị: dưới mức này thì thà hiện ít card hơn là hiện card rác.
MIN_CONFIDENCE = 0.25
CONFIDENCE_CAP = 0.95

# --- Chuỗi điều trị chuẩn ---------------------------------------------------
# (dịch vụ đã làm) -> [(dịch vụ tiếp theo, trọng số, tháng tối thiểu, tháng tối đa)]
# Cửa sổ thời gian là bắt buộc: không có nó thì một lần điều trị tủy năm 2020 sẽ
# gợi ý bọc răng sứ mãi mãi.
CARE_PATHWAY = {
    "noi_nha":   [("phuc_hinh", 0.60, 0, 12)],
    "nho_rang":  [("phuc_hinh", 0.55, 2, 18)],
    "nha_chu":   [("kham_tong_quat", 0.50, 3, 12)],
    "sau_rang":  [("kham_tong_quat", 0.35, 6, 24)],
    "chinh_nha": [("kham_tong_quat", 0.30, 6, 24)],
}


def _signal(service_code, weight, reason_code, **ctx):
    return {"service_code": service_code, "weight": round(weight, 4),
            "reason_code": reason_code, "ctx": ctx}


def signals(features, cooc=None, popular=None):
    """Sinh toàn bộ tín hiệu cho một hồ sơ. Trả list (có thể rỗng)."""
    cooc = cooc or {}
    popular = popular or {}
    out = []

    # --- 1. followup_due: nha sĩ đã hẹn tái khám và ngày đó đã trôi qua ------
    for item in features.get("overdue") or []:
        code = item.get("service_code")
        if code not in DEPARTMENTS:
            continue
        cycle = service_meta(code)["recurring_months"] or 6
        # Càng quá hạn càng gấp, nhưng bão hoà ở W_FOLLOWUP_MAX: quá hạn 5 năm
        # không "gấp gáp" hơn quá hạn 1 năm ở mức có ý nghĩa hành động.
        ratio = min(1.0, item.get("overdue_months", 0) / max(cycle, 1))
        weight = W_FOLLOWUP_BASE + (W_FOLLOWUP_MAX - W_FOLLOWUP_BASE) * ratio
        out.append(_signal(code, weight, "followup_due",
                           overdue_months=item.get("overdue_months", 0),
                           due_date=item.get("due_date"),
                           months_since=feat.months_since_service(features, code)))

    # --- 2. past_treatment: dịch vụ định kỳ đã tới chu kỳ -------------------
    for code in features.get("services_used") or []:
        if code not in DEPARTMENTS:
            continue
        due, months, cycle = feat.is_recurring_due(features, code)
        if not due:
            continue
        # Đã có tín hiệu followup_due cho chính dịch vụ này thì bỏ: cùng một sự
        # thật ("tới hạn làm lại") không được tính điểm hai lần.
        if any(s["service_code"] == code and s["reason_code"] == "followup_due"
               for s in out):
            continue
        weight = W_RECURRING
        if months >= cycle * 1.5:
            weight += W_RECURRING_LATE
        out.append(_signal(code, weight, "past_treatment",
                           months_since=months, cycle=cycle))

    # --- 3. care_pathway: bước tiếp theo trong chuỗi điều trị ---------------
    for used in features.get("services_used") or []:
        months = feat.months_since_service(features, used)
        if months is None:
            continue
        for nxt, weight, lo, hi in CARE_PATHWAY.get(used, []):
            if nxt not in DEPARTMENTS:
                continue
            if lo <= months <= hi:
                out.append(_signal(nxt, weight, "care_pathway",
                                   from_service=used, months_since=months))

    # --- 4. similar_patients: đồng xuất hiện trên toàn bộ bệnh nhân ---------
    used_set = set(features.get("services_used") or [])
    best_similar = {}
    for used in used_set:
        for other, value in (cooc.get(used) or {}).items():
            conf, n_a = value
            if other in used_set or other not in DEPARTMENTS:
                continue
            # Giữ tín hiệu MẠNH NHẤT cho mỗi dịch vụ đích: nếu cả "khám tổng quát"
            # và "nha chu" đều dẫn tới "trám răng", đó vẫn là một lý do để gợi ý
            # trám răng, không phải hai.
            if other not in best_similar or conf > best_similar[other][0]:
                best_similar[other] = (conf, n_a, used)
    for code, (conf, n_a, used) in best_similar.items():
        out.append(_signal(code, W_SIMILAR_FACTOR * conf, "similar_patients",
                           percent=round(conf * 100), n_patients=n_a,
                           from_service=used))

    # --- 5. age_group: dịch vụ đặc trưng cho nhóm tuổi ---------------------
    age_group = features.get("age_group")
    if age_group:
        for code in DEPARTMENTS:
            affinity = service_meta(code)["age_affinity"].get(age_group)
            if affinity:
                out.append(_signal(code, min(W_AGE, affinity), "age_group",
                                   age_group=age_group))

    # --- 6. popular: chỉ dùng ở nhánh cold-start (engine truyền popular vào) -
    for code, share in (popular or {}).items():
        if code in DEPARTMENTS and code not in used_set:
            out.append(_signal(code, W_POPULAR_FACTOR * share, "popular",
                               percent=round(share * 100)))

    return out


def _urgency(confidence, service_signals):
    """Nhãn cấp thiết hiển thị trên card ("Cần thiết" cho high)."""
    for s in service_signals:
        if s["reason_code"] == "followup_due":
            cycle = service_meta(s["service_code"])["recurring_months"] or 6
            # Quá hạn bằng cả một chu kỳ nữa = đã bỏ hẳn một lần tái khám.
            if s["ctx"].get("overdue_months", 0) >= cycle:
                return "high"
    if confidence >= 0.6:
        return "medium"
    return "low"


def score(signal_list, min_confidence=MIN_CONFIDENCE):
    """Gộp tín hiệu -> danh sách ứng viên đã xếp hạng.

    Trả list dict: {service_code, confidence, fit_percent, reason_code, urgency,
    signals}. Sắp giảm dần theo confidence; hoà điểm thì sắp theo mã dịch vụ để
    kết quả ỔN ĐỊNH (eval chạy lại phải ra đúng thứ tự cũ).
    """
    by_service = {}
    for s in signal_list:
        by_service.setdefault(s["service_code"], []).append(s)

    out = []
    for code, service_signals in by_service.items():
        product = 1.0
        for s in service_signals:
            product *= (1.0 - max(0.0, min(1.0, s["weight"])))
        confidence = min(CONFIDENCE_CAP, 1.0 - product)
        if confidence < min_confidence:
            continue
        # Tín hiệu mạnh nhất quyết định lý do CHÍNH hiện trên card; toàn bộ tín
        # hiệu được giữ lại cho màn chi tiết REC-02 ("Tại sao AI gợi ý?").
        strongest = max(service_signals, key=lambda s: s["weight"])
        ordered = sorted(service_signals, key=lambda s: s["weight"], reverse=True)
        out.append({
            "service_code": code,
            "confidence": round(confidence, 4),
            "fit_percent": int(round(confidence * 100)),
            "reason_code": strongest["reason_code"],
            "urgency": _urgency(confidence, ordered),
            "signals": ordered,
        })

    out.sort(key=lambda r: (-r["confidence"], r["service_code"]))
    return out
