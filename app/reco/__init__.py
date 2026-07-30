"""
Engine gợi ý dịch vụ nha khoa (REC-01/02) — cửa vào duy nhất là `recommend()`.

    history.py     đọc lịch sử điều trị + bảng đồng xuất hiện + độ phổ biến
    features.py    trích feature vector (hàm thuần)
    rules.py       sinh tín hiệu + gộp điểm noisy-OR (hàm thuần)
    reasons.py     câu lý do từ reason_code (template)
    llm_reason.py  LLM viết lại câu lý do (chỉ câu chữ, không đổi thứ hạng)

Luồng: lịch sử -> feature -> tín hiệu -> điểm -> lọc an toàn -> top-3 -> lý do -> log.

Thiết kế đầy đủ + truy vết Jira/Confluence: docs/patient-recommendation-design.md
"""

import time
import uuid
from datetime import date, datetime

from ..core import storage
from ..core.catalog import DEPARTMENTS, service_meta

# Nhóm tuổi giả định khi bệnh nhân chưa khai năm sinh — CHỈ dùng cho bộ lọc điều
# kiện, không dùng để cộng điểm theo tuổi.
DEFAULT_AGE_GROUP = "adult"
from . import features as features_mod
from . import history, llm_reason, reasons, rules

# Ghi vào recommendation_log.model_version -> đổi bộ luật thì tăng version để
# phân tích sau này biết con số đến từ phiên bản nào.
MODEL_VERSION = "rules-v1"

# TC-REC-002: dưới 3 lượt điều trị thì không đủ dữ liệu cá nhân hoá.
COLD_START_MIN_VISITS = 3

DEFAULT_LIMIT = 3

TRIGGERS = ("booking_page", "chatbot", "dentist_view")

# Chống chỉ định theo dị ứng: {mã dị ứng: [mã dịch vụ bị loại]}.
# CỐ TÌNH ĐỂ RỖNG — spec có feature `allergy_flags` nhưng KHÔNG có bảng ánh xạ
# dị ứng -> dịch vụ, và đây là quyết định y tế, không được tự bịa. Bộ lọc đã nối
# sẵn, chỉ cần điền bảng khi nha sĩ cung cấp. Xem §18.3 doc thiết kế.
ALLERGY_CONTRAINDICATIONS = {}


def _passes_filters(code, features, dismissed, upcoming):
    """Bộ lọc an toàn — SEQ 4.5. Trả (ok, lý do bị loại)."""
    if code not in DEPARTMENTS:
        return False, "khong_trong_danh_muc"

    # TC-REC-004: đã bấm "Không quan tâm" -> không hiện lại lần sau.
    if code in dismissed:
        return False, "da_bo_qua"

    # Đã có lịch hẹn sắp tới cho đúng dịch vụ này -> gợi ý là dư thừa.
    if code in upcoming:
        return False, "da_co_lich_hen"

    months = features_mod.months_since_service(features, code)
    if months is not None:
        due, _months, cycle = features_mod.is_recurring_due(features, code)
        if not cycle:
            # Dịch vụ không định kỳ mà đã làm -> không gợi ý lại (trồng implant,
            # điều trị tủy, nhổ răng... không phải việc làm lại theo chu kỳ).
            return False, "da_lam_va_khong_dinh_ky"
        if not due:
            # Dịch vụ định kỳ nhưng chưa tới chu kỳ.
            return False, "chua_toi_chu_ky"

    age_group = features.get("age_group")
    allowed_ages = service_meta(code)["age_groups"]
    if age_group:
        if age_group not in allowed_ages:
            return False, "khong_dung_nhom_tuoi"
    elif DEFAULT_AGE_GROUP not in allowed_ages:
        # KHÔNG biết tuổi: xét điều kiện như người trưởng thành. Chỉ loại những
        # dịch vụ mà người trưởng thành không dùng ("Nha khoa trẻ em") — đủ để
        # bệnh nhân chưa khai năm sinh không bị gợi ý dịch vụ dành cho trẻ, mà
        # KHÔNG loại oan các dịch vụ chỉ đơn giản là không dành cho trẻ em (thẩm
        # mỹ, chỉnh nha, phục hình). Điểm cộng theo nhóm tuổi vẫn cần biết tuổi.
        return False, "thieu_du_lieu_tuoi"

    for flag in features.get("allergy_flags") or []:
        if code in ALLERGY_CONTRAINDICATIONS.get(flag, ()):
            return False, "chong_chi_dinh_di_ung"

    return True, None


def _top_up(items, popular, features, dismissed, upcoming, limit):
    """Bù cho đủ `limit` gợi ý bằng dịch vụ phổ biến.

    TC-REC-001 đòi ĐÚNG 3 gợi ý cho bệnh nhân có lịch sử, TC-REC-002 đòi đủ 3 cả
    ở cold-start. Card bù vẫn trung thực: lý do của nó là "nhiều bệnh nhân lựa
    chọn" kèm tỉ lệ thật, không phải điểm cá nhân hoá bịa ra.
    """
    have = {r["service_code"] for r in items}
    ranked = sorted(popular.items(), key=lambda kv: (-kv[1], kv[0]))
    # Độ phổ biến chỉ biết tới các dịch vụ ĐÃ TỪNG được dùng. Phòng khám mới (hoặc
    # lịch sử mỏng) thì bảng này không đủ 3 dịch vụ -> bù tiếp theo thứ tự danh mục
    # với share 0, để cold-start luôn trả đủ 3 như TC-REC-002 yêu cầu.
    ranked += [(code, 0.0) for code in DEPARTMENTS if code not in popular]
    for code, share in ranked:
        if len(items) >= limit:
            break
        if code in have:
            continue
        ok, _why = _passes_filters(code, features, dismissed, upcoming)
        if not ok:
            continue
        # `share` (tỉ lệ bệnh nhân từng dùng dịch vụ) KHÔNG phải độ phù hợp: 88%
        # bệnh nhân đi khám tổng quát không có nghĩa dịch vụ đó phù hợp 88% với
        # riêng người này. Quy về đúng thang điểm của bộ luật (W_POPULAR_FACTOR)
        # để "% phù hợp" giữa các card so sánh được với nhau.
        confidence = min(rules.CONFIDENCE_CAP, rules.W_POPULAR_FACTOR * share)
        signal = {"service_code": code, "weight": confidence,
                  "reason_code": "popular", "ctx": {"percent": round(share * 100)}}
        items.append({
            "service_code": code,
            "confidence": round(confidence, 4),
            "fit_percent": int(round(confidence * 100)),
            "reason_code": "popular",
            "urgency": "low",
            "signals": [signal],
            "is_filler": True,
        })
        have.add(code)

    # Sắp lại toàn bộ để "% phù hợp" giảm dần trên UI (card bù luôn có điểm thấp
    # hơn card cá nhân hoá nhờ W_POPULAR_FACTOR, nên không chen lên trên được).
    items.sort(key=lambda r: (-r["confidence"], r["service_code"]))
    return items


def recommend(patient_id=None, patient_phone=None, profile=None,
              trigger="booking_page", limit=DEFAULT_LIMIT, today=None,
              use_llm=None, log=True):
    """Sinh top-N gợi ý dịch vụ cho một bệnh nhân.

    Args:
        patient_id / patient_phone: định danh (dùng OR — xem storage.list_treatments)
        profile: {"birth_year": int|None, "allergies": [str]}
        trigger: 'booking_page' | 'chatbot' | 'dentist_view'
        limit: số gợi ý tối đa (spec: 3)
        today: date, cố định thời gian khi test
        use_llm: None -> theo biến môi trường; False -> chỉ template (dùng cho eval)
        log: có ghi recommendation_log hay không

    Returns:
        dict {items, is_cold_start, empty_reason, rec_log_id, model_version,
              generated_at, latency_ms}
    """
    started = time.perf_counter()
    today = today or date.today()
    if trigger not in TRIGGERS:
        trigger = "booking_page"

    rows = history.recent(patient_id=patient_id, patient_phone=patient_phone)
    features = features_mod.build(rows, profile, today)

    is_cold_start = features["visit_count"] < COLD_START_MIN_VISITS
    popular = history.popularity_cached()

    # Cold-start: KHÔNG dùng đồng xuất hiện (lịch sử quá mỏng để nói "bệnh nhân
    # tương tự"), chỉ độ phổ biến + nhóm tuổi — đúng TC-REC-002.
    cooc = {} if is_cold_start else history.cooccurrence_cached()
    signal_list = rules.signals(features, cooc=cooc,
                                popular=popular if is_cold_start else None)

    scored = rules.score(signal_list)

    dismissed = set(storage.get_patient_preference(patient_id)["dismissed_service_codes"]
                    if patient_id else [])
    upcoming = history.upcoming_service_codes(patient_id=patient_id,
                                              patient_phone=patient_phone,
                                              today=today)

    items = []
    for candidate in scored:
        ok, _why = _passes_filters(candidate["service_code"], features,
                                   dismissed, upcoming)
        if ok:
            items.append(candidate)
        if len(items) >= limit:
            break

    items = _top_up(items, popular, features, dismissed, upcoming, limit)

    # Hoàn thiện payload từng gợi ý: thông tin dịch vụ + lý do + thứ hạng.
    for rank, item in enumerate(items, start=1):
        strongest = item["signals"][0]
        item.update(reasons.service_payload(item["service_code"]))
        item["rank"] = rank
        # Card KHÔNG cá nhân hoá (cold-start hoặc card bù) thì không có "% phù hợp":
        # điểm của chúng đến từ độ phổ biến chung, hiện "5% phù hợp" vừa vô nghĩa
        # vừa trông như lỗi. Wireframe state 4 cũng chỉ hiện thời lượng + giá.
        if is_cold_start or item.get("is_filler"):
            item["fit_percent"] = None
        item["reason_text"] = reasons.render(strongest)
        item["reason_source"] = "template"
        item["reason_detail"] = reasons.render_all(item, features)
        item["doctors"] = [d["name"] for d in _doctors_of(item["service_code"])]

    # LLM chỉ chạm vào reason_text, sau khi thứ hạng đã chốt.
    if use_llm is not False:
        llm_reason.polish(items)

    empty_reason = None
    if not items:
        empty_reason = "all_dismissed" if dismissed else "no_candidate"

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    rec_log_id = uuid.uuid4().hex

    result = {
        "rec_log_id": rec_log_id,
        "items": items,
        "is_cold_start": is_cold_start,
        "empty_reason": empty_reason,
        "cold_start_note": reasons.cold_start_note() if is_cold_start else None,
        "empty_text": reasons.EMPTY_STATE_TEXT if empty_reason else None,
        "model_version": MODEL_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "latency_ms": elapsed_ms,
        "visit_count": features["visit_count"],
    }

    if log and patient_id:
        _write_log(result, patient_id, trigger, features)
    return result


def _doctors_of(service_code):
    """Nha sĩ phụ trách dịch vụ (đọc catalog trực tiếp, không qua booking/)."""
    from ..core.catalog import DOCTORS
    return DOCTORS.get(service_code, [])


def _write_log(result, patient_id, trigger, features):
    """Ghi recommendation_log — BEST-EFFORT.

    Log là dữ liệu phân tích, không phải nghiệp vụ: storage lỗi thì bệnh nhân vẫn
    phải thấy gợi ý. Cùng nguyên tắc với audit log (xem docs/code-standards.md).
    """
    try:
        storage.add_rec_log({
            "rec_log_id": result["rec_log_id"],
            "patient_id": patient_id,
            "generated_at": result["generated_at"],
            "trigger": trigger,
            "model_version": MODEL_VERSION,
            "is_cold_start": result["is_cold_start"],
            "recommendations": [
                {"rank": i["rank"], "service_code": i["service_code"],
                 "confidence": i["confidence"], "reason_code": i["reason_code"],
                 "reason_text": i["reason_text"], "urgency": i["urgency"]}
                for i in result["items"]
            ],
            "latency_ms": result["latency_ms"],
            "feature_snapshot": features_mod.snapshot(features),
        })
    except Exception as exc:  # noqa: BLE001 - log không được làm sập request
        print(f"[reco] CẢNH BÁO: không ghi được recommendation_log: {exc}")


def record_action(rec_log_id, action, service_code=None, rank=None):
    """Ghi hành động của bệnh nhân lên dòng log (book / dismiss / skip_all / view_detail)."""
    try:
        return storage.set_rec_log_action(rec_log_id, action, service_code, rank)
    except Exception as exc:  # noqa: BLE001
        print(f"[reco] CẢNH BÁO: không ghi được hành động gợi ý: {exc}")
        return False
