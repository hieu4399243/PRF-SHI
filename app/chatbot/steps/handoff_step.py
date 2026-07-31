"""
Bước HANDOFF — chuyển tiếp sang nhân viên thật (CB-05 / SMMG-52).

Trước đây bot chỉ nói "Tôi sẽ chuyển bạn tới nhân viên kèm toàn bộ nội dung trao
đổi" rồi... không có gì xảy ra: không bản ghi nào được tạo, không nhân viên nào
nhìn thấy, và lượt kế tiếp còn rơi vào nhánh `else` của router nên bệnh nhân
nhận lại LỜI CHÀO như phiên mới. Module này biến lời hứa đó thành việc thật:

    1. tạo bản ghi `handoff_requests` kèm SNAPSHOT toàn bộ hội thoại;
    2. trả lời khác nhau TRONG GIỜ và NGOÀI GIỜ làm việc (ngoài giờ thì hẹn gọi
       lại vào mốc mở cửa gần nhất, và xin số điện thoại nếu chưa có);
    3. giữ state HANDOFF cho các lượt sau, nối tiếp mọi câu bệnh nhân gõ thêm
       vào transcript để nhân viên tiếp nhận không thiếu ngữ cảnh.

Hai đường vào, cố ý giữ cả hai:
  - `reason="patient_request"` — bệnh nhân đòi gặp người thật. Router bắt bằng
    `safety.needs_human_handoff()` (từ khoá, luôn chạy được kể cả khi LLM tắt),
    còn `llm_reply.answer()` bắt bằng ngữ nghĩa những câu từ khoá bỏ sót.
  - `reason="bot_stuck"` — bot tự nhận ra mình không giải quyết được và CHỦ ĐỘNG
    đề nghị (`llm_reply.is_stuck()`).
"""

import re
import secrets
import string
from datetime import datetime

from ...core import storage
from ...core.catalog import is_working_time, next_working_time
from ...core.text import normalize, strip_accents
from ...triage import nlu, safety
from ..reply import normalize_phone, reply

# Lý do tạo yêu cầu — khớp cột `reason` của bảng handoff_requests.
PATIENT_REQUEST = "patient_request"
BOT_STUCK = "bot_stuck"

_WEEKDAY_LABEL = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]


def _generate_code():
    alphabet = string.ascii_uppercase + string.digits
    return "HO-" + "".join(secrets.choice(alphabet) for _ in range(6))


def _callback_label(when) -> str:
    """'Thứ 2, 03/08 lúc 08:00' — mốc gọi lại, viết cho bệnh nhân đọc."""
    return (f"{_WEEKDAY_LABEL[when.weekday()]}, {when.day:02d}/{when.month:02d} "
            f"lúc {when.hour:02d}:{when.minute:02d}")


def create_request(sess, reason, now=None):
    """Ghi bản ghi chuyển tiếp cho phiên hiện tại. Trả về dict bản ghi.

    `now` chỉ để test bơm thời điểm cố định; chạy thật luôn dùng giờ hệ thống.

    Không bao giờ raise: storage hỏng (mất DB, file khoá) thì vẫn phải trả về một
    bản ghi để bot kịp trấn an bệnh nhân — mất bản ghi còn hơn mất luôn câu trả
    lời. Trường hợp đó `code` là None và lượt sau sẽ không nối được transcript.
    """
    now = now or datetime.now()
    session_id = sess.get("_id") or ""
    within = is_working_time(now)
    callback_at = None if within else next_working_time(now).isoformat(timespec="minutes")

    entry = {
        "code": _generate_code(),
        "session_id": session_id,
        "reason": reason,
        "status": "new",
        "created_at": now.isoformat(timespec="seconds"),
        "within_hours": within,
        "callback_at": callback_at,
        # Tên/SĐT đi RIÊNG chứ không nằm trong transcript: transcript lấy từ audit
        # log nên đã bị ẩn PII (xem safety.session_transcript). Nhân viên cần gọi
        # lại được thì phải có số thật ở đây.
        "patient_name": sess.get("patient_name") or "",
        "patient_phone": sess.get("patient_phone") or "",
        "last_message": (sess.get("user_turns") or [""])[-1],
        "transcript": safety.session_transcript(session_id),
        "handled_at": None,
        "handled_by": None,
    }
    try:
        storage.add_handoff(entry)
    except Exception as exc:  # noqa: BLE001 - xem docstring
        print(f"[handoff] CẢNH BÁO: không ghi được yêu cầu chuyển tiếp: {exc}")
        entry["code"] = None
    return entry


def start_handoff(sess, reason=PATIENT_REQUEST, now=None):
    """Chuyển hội thoại sang trạng thái chờ nhân viên và trả lời bệnh nhân."""
    entry = create_request(sess, reason, now=now)
    sess["handoff_code"] = entry["code"]
    sess["stuck_turns"] = 0

    opener = ("Mình chưa hỗ trợ được đúng điều bạn cần. " if reason == BOT_STUCK
              else "")

    if entry["within_hours"]:
        text = (opener + "Mình đã chuyển bạn tới <b>nhân viên phòng khám</b> kèm "
                "toàn bộ nội dung trao đổi để được hỗ trợ trực tiếp. ☎️")
    else:
        # Ngoài giờ: KHÔNG hứa "chờ trong giây lát" khi không có ai trực.
        when = _callback_label(datetime.fromisoformat(entry["callback_at"]))
        text = (opener + "Hiện đã <b>ngoài giờ làm việc</b> nên chưa có nhân viên "
                "trực. Mình đã <b>ghi nhận yêu cầu</b> của bạn kèm toàn bộ nội dung "
                f"trao đổi, phòng khám sẽ <b>gọi lại cho bạn vào {when}</b>.")
    if entry["code"]:
        text += f"<br><span class='muted'>Mã yêu cầu: <b>{entry['code']}</b></span>"

    # XIN SỐ LIÊN HỆ Ở CẢ HAI NHÁNH — không chỉ ngoài giờ.
    # Khung chat này KHÔNG có phía nhân viên trả lời trực tiếp: họ đọc yêu cầu ở
    # trang /admin/handoff rồi liên hệ ra ngoài. Nên thiếu số điện thoại nghĩa là
    # yêu cầu tới tay nhân viên mà họ KHÔNG có cách nào liên hệ lại — bệnh nhân
    # ngồi chờ một cuộc gọi không bao giờ đến. Trước đây chỉ nhánh ngoài giờ hỏi.
    if not entry["patient_phone"]:
        sess["state"] = "HANDOFF_ASK_CONTACT"
        return reply(
            text + "<br><br>Bạn để lại <b>tên và số điện thoại</b> để nhân viên "
            "liên hệ giúp mình nhé.<br><i>Ví dụ: Minh Hiếu - 0912345678</i>",
            state="HANDOFF_ASK_CONTACT",
        )
    return reply(text + "<br>" + _contact_note(entry), state="HANDOFF")


def maybe_escalate(sess, wants_handoff):
    """Nhánh fallback vừa chạy xong -> có cần đụng tới nhân viên không?

    Trả về response, hoặc None để bước gọi dùng câu trả lời của nó. Hai điều
    kiện, mỗi cái đắp cho điểm yếu của cái kia — và CỐ Ý xử lý khác nhau:

      - `wants_handoff` (LLM đọc được ý muốn gặp người thật, dù diễn đạt vòng vo)
        -> CHUYỂN LUÔN. Bệnh nhân đã nói rõ ý mình, hỏi lại "có chắc không" chỉ
        làm người đang bực thêm bực.
      - `llm_reply.is_stuck()` (đếm số lượt liên tiếp bộ luật bó tay) -> chỉ ĐỀ
        NGHỊ, để bệnh nhân chọn. Đây là suy đoán của bot chứ không phải yêu cầu
        của họ; ticket cũng ghi "chủ động ĐỀ XUẤT chuyển tiếp", và người đang
        muốn tự đặt lịch mà bị đẩy sang hàng chờ nhân viên là tệ hơn.
    """
    from .. import llm_reply

    if wants_handoff:
        return start_handoff(sess, PATIENT_REQUEST)
    if llm_reply.is_stuck(sess):
        return offer_handoff(sess)
    return None


def offer_handoff(sess):
    """Bot tự thấy mình loay hoay -> HỎI xem có muốn chuyển nhân viên không."""
    # Đặt lại bộ đếm ngay: nếu không, người dùng trả lời "không" xong là lượt
    # kế tiếp lại bị hỏi y hệt câu này.
    sess["stuck_turns"] = 0
    # Nhớ chỗ đang đứng để nếu họ từ chối thì quay lại đúng bước, không mất ngữ cảnh.
    sess["handoff_offer_from"] = sess.get("state") or "TRIAGE"
    return reply(
        "Hình như mình chưa hỗ trợ được đúng điều bạn cần. Bạn có muốn mình "
        "<b>chuyển sang nhân viên phòng khám</b> để được hỗ trợ trực tiếp không?",
        options=[
            {"label": "☎️ Vâng, chuyển cho nhân viên", "value": "yes"},
            {"label": "🔁 Không, mình thử lại", "value": "no"},
        ],
        state="HANDOFF_OFFER",
    )


def handoff_offer(sess, message):
    """Trả lời cho lời đề nghị chuyển tiếp ở `offer_handoff()`."""
    from ...triage import nlu
    from .. import flex

    low = message.strip().lower()
    if low == "yes" or nlu.is_affirmative(message):
        return start_handoff(sess, BOT_STUCK)
    if low == "no" or nlu.is_negative(message):
        return flex.goto_step(sess, sess.get("handoff_offer_from") or "TRIAGE",
                              prefix="Được, mình thử lại nhé. ")
    # Gõ thứ khác = họ đã bỏ qua lời đề nghị và nói tiếp việc của mình -> đừng
    # ép trả lời có/không, quay về bước cũ rồi xử lý câu đó như bình thường.
    from ..router import _HANDLERS

    back = sess.get("handoff_offer_from") or "TRIAGE"
    sess["state"] = back
    handler = _HANDLERS.get(back)
    return handler(sess, message) if handler else flex.goto_step(sess, back)


_PHONE_IN_TEXT_RE = re.compile(r"(?:\+84|84|0)\s*(?:\d[\s.\-]*){8,10}")

# Chữ dẫn quanh SĐT, bỏ đi thì phần còn lại mới là tên.
# CỐ Ý KHÔNG có "minh/mình", "em", "anh", "chị": chúng vừa là đại từ vừa là TÊN
# người rất phổ biến. Bản đầu có "minh" và biến "Minh Hiếu - 09..." thành "Hiếu".
# Thà sót một chữ thừa trong tên còn hơn cắt mất tên thật của bệnh nhân.
_CONTACT_NOISE_RE = re.compile(
    r"\b(tên|ten|là|la|tôi|toi|sđt|sdt|số|so|điện|dien|thoại|thoai|"
    r"nhé|nhe|gọi|goi|liên|lien|hệ|he)\b",
    re.IGNORECASE)


def _parse_contact(message: str):
    """Tách (tên, sđt) từ MỘT câu kiểu "Minh Hiếu - 0912345678".

    Bắt SĐT trước rồi coi phần còn lại là tên: số điện thoại có khuôn dạng chặt
    chẽ, còn tên người Việt thì không — làm ngược lại sẽ phải đoán mò.
    Tên trả về có thể là "" (họ chỉ gõ mỗi số); SĐT "" nghĩa là chưa hợp lệ.
    """
    raw = message or ""
    match = _PHONE_IN_TEXT_RE.search(raw)
    if not match:
        return "", ""
    phone = normalize_phone(match.group(0))
    if not phone:
        return "", ""

    leftover = (raw[:match.start()] + " " + raw[match.end():])
    leftover = _CONTACT_NOISE_RE.sub(" ", leftover)
    name = " ".join(re.sub(r"[^\w\sÀ-ỹ]", " ", leftover).split())
    return name.title(), phone


def _looks_like_name(text: str) -> bool:
    """Câu này có vẻ là TÊN NGƯỜI (chứ không phải câu hỏi hay câu nói vu vơ)?

    Cố ý chặt: đoán nhầm một câu hỏi thành tên thì nhân viên gọi điện gặp "Giờ
    Tôi Phải Làm Gì", còn đoán sót thì cùng lắm hỏi lại một lượt.
    """
    words = (text or "").split()
    if not 1 <= len(words) <= 5 or len(text) > 40:
        return False
    if "?" in text or _asks_status(text):
        return False
    return all(re.fullmatch(r"[A-Za-zÀ-ỹ]+", w) for w in words)


def handoff_ask_contact(sess, message):
    """Nhận TÊN + SĐT để nhân viên liên hệ lại."""
    # Lượt này CHÍNH LÀ PII -> ghi nhãn ẩn vào transcript, và KHÔNG cho nó đè lên
    # `last_message` (cột "Câu cuối" ở trang nhân viên phải giữ câu bệnh nhân
    # thật sự nói, không phải cái nhãn này).
    _record(sess, "user", "[LIÊN HỆ ĐÃ ẨN]", update_last=False)

    if nlu.wants_stop(message):
        return reply(
            "Không sao, mình vẫn giữ yêu cầu của bạn nhé. Nhân viên sẽ xem toàn bộ "
            "nội dung trao đổi — nếu cần liên hệ lại thì bạn nhắn số điện thoại vào "
            "đây bất cứ lúc nào.",
            state="HANDOFF",
        )

    name, phone = _parse_contact(message)
    if not phone:
        # Người ta hay gõ TÊN TRƯỚC rồi mới tới SỐ ở lượt sau. Bản đầu vứt luôn
        # cái tên đó đi, nên bệnh nhân "đã nhập tên rồi" mà bản ghi vẫn trống tên.
        if _looks_like_name(message):
            sess["pending_contact_name"] = message.strip().title()
            return reply(
                f"Cảm ơn bạn <b>{sess['pending_contact_name']}</b>. Bạn cho mình xin "
                "thêm <b>số điện thoại</b> để nhân viên gọi lại nhé "
                "<i>(dạng 0xxxxxxxxx)</i>.",
                state="HANDOFF_ASK_CONTACT",
            )
        # Họ đang HỎI chứ không phải gõ nhầm số ("giờ tôi phải làm gì?") -> trả lời
        # câu hỏi trước, đừng dội lại "số điện thoại chưa đúng định dạng".
        lead = ("Nhân viên phòng khám sẽ đọc lại toàn bộ trao đổi rồi liên hệ với "
                "bạn, nên mình cần một số để họ gọi được. " if _asks_status(message)
                else "Mình chưa đọc được số điện thoại. ")
        return reply(
            lead + "Bạn để lại giúp mình theo dạng <b>Tên - 0xxxxxxxxx</b> nhé "
            "<i>(hoặc gõ “thôi” nếu không muốn để lại)</i>.",
            state="HANDOFF_ASK_CONTACT",
        )

    sess["patient_phone"] = phone
    # Tên lấy theo thứ tự: tên gõ CÙNG lượt này > tên đã gõ ở lượt trước > tên có
    # sẵn trong phiên (từ lịch hẹn đang đặt dở).
    name = name or sess.pop("pending_contact_name", "") or sess.get("patient_name") or ""
    if name:
        sess["patient_name"] = name
    _save_contact(sess, name, phone)

    who = f" <b>{sess['patient_name']}</b>" if sess.get("patient_name") else ""
    return reply(
        f"Cảm ơn bạn{who}, mình đã gửi kèm số <b>{phone}</b> cho nhân viên. Họ sẽ "
        "liên hệ lại với bạn. Trong lúc chờ, bạn cứ nhắn thêm nếu có gì cần bổ sung.",
        state="HANDOFF",
    )


# Câu HỎI VỀ TÌNH TRẠNG chờ, không phải thông tin mới. Khớp không dấu.
_ASKS_STATUS = (
    "bao lau", "bao gio", "khi nao", "con lau", "sao lau", "lau qua", "lau the",
    "den luot", "toi luot", "the nao roi", "sao roi", "van chua", "chua thay",
    "co ai", "khong thay ai", "dang cho", "cho bao lau",
    # "Giờ tôi phải làm gì", "sao tôi biết để liên hệ" — không phải thông tin mới
    # mà là hỏi CHUYỆN GÌ XẢY RA TIẾP THEO. Trả lời bằng trạng thái thật mới đúng.
    "phai lam gi", "lam gi tiep", "lam gi bay gio", "tiep theo", "roi sao nua",
    "lien he", "lien lac", "goi cho toi", "bang cach nao",
)


def _asks_status(message: str) -> bool:
    low = strip_accents(normalize(message))
    return any(phrase in low for phrase in _ASKS_STATUS)


def handoff_wait(sess, message):
    """Lượt tin nhắn khi đang CHỜ nhân viên.

    Bug 1 (đã sửa trước): state HANDOFF không có handler nên rơi vào nhánh `else`
    của router và bệnh nhân bị chào lại từ đầu giữa lúc đang chờ người thật.

    Bug 2: sửa xong bug 1 thì mọi tin nhắn lại nhận CHUNG MỘT câu "Mình đã ghi
    nhận thêm nội dung này". Bệnh nhân hỏi "có ai đó hỗ trợ không" — tức vẫn
    đang hỏi ĐÚNG câu đã hỏi lúc đầu — mà nhận lại câu đó thì nghe như bot coi
    lời cầu cứu là một mẩu thông tin để lưu trữ. Hai loại tin nhắn ở đây khác
    nhau về bản chất và phải trả lời khác nhau:

      - HỎI LẠI về tình trạng ("có ai không", "bao lâu nữa") -> báo TRẠNG THÁI
        THẬT của yêu cầu (mã, đã có người nhận chưa, ngoài giờ thì mốc gọi lại);
      - KỂ THÊM thông tin -> mới là "đã ghi nhận".
    """
    _record(sess, "user", message)
    if safety.needs_human_handoff(message) or _asks_status(message):
        return _status_reply(sess)
    return reply(
        "Mình đã ghi nhận thêm nội dung này và chuyển tới nhân viên nhé. Bạn chờ "
        "một chút, hoặc gõ <b>“làm lại”</b> nếu muốn quay về đặt lịch với mình.",
        state="HANDOFF",
    )


def _status_reply(sess):
    """Báo tình trạng THẬT của yêu cầu đang chờ.

    Đọc lại bản ghi thay vì đọc thuộc lòng một câu: nhân viên có thể đã bấm tiếp
    nhận ở trang quản trị, và lúc đó bảo bệnh nhân "chờ chút nhé" là nói sai.
    Không nêu thời gian chờ ước lượng — hệ thống không biết, và hứa hão còn tệ
    hơn im lặng.
    """
    code = sess.get("handoff_code")
    entry = None
    if code:
        try:
            entry = storage.get_handoff(code)
        except Exception as exc:  # noqa: BLE001 - mất bản ghi không được chặn hội thoại
            print(f"[handoff] CẢNH BÁO: không đọc được yêu cầu {code}: {exc}")

    ref = f"<br><span class='muted'>Mã yêu cầu: <b>{code}</b></span>" if code else ""
    # Nêu luôn SỐ nhân viên sẽ gọi: "sao tôi biết để liên hệ" hầu như luôn là câu
    # hỏi kế tiếp, trả lời sẵn còn hơn để bệnh nhân phải hỏi.
    contact = _contact_note(entry)
    if contact:
        ref += "<br>" + contact
    elif entry:
        # Chưa có số mà bệnh nhân đang hỏi cách liên hệ -> quay lại xin cho bằng được.
        sess["state"] = "HANDOFF_ASK_CONTACT"
        return reply(
            "Yêu cầu của bạn <b>đang chờ nhân viên tiếp nhận</b>. Nhưng mình chưa có "
            "số liên hệ của bạn nên nhân viên chưa gọi lại được — bạn để lại <b>tên "
            "và số điện thoại</b> giúp mình nhé.<br><i>Ví dụ: Minh Hiếu - 0912345678</i>"
            + ref,
            state="HANDOFF_ASK_CONTACT")

    if entry and entry.get("status") == "handled":
        return reply(
            "Có nhé — <b>nhân viên đã tiếp nhận</b> yêu cầu của bạn và đang xem lại "
            "toàn bộ nội dung trao đổi. Bạn chờ họ liên hệ giúp mình nhé." + ref,
            state="HANDOFF")

    if entry and not entry.get("within_hours") and entry.get("callback_at"):
        when = _callback_label(datetime.fromisoformat(entry["callback_at"]))
        return reply(
            "Có nhé, yêu cầu của bạn <b>đã được ghi nhận</b>. Hiện đang ngoài giờ "
            f"làm việc nên chưa có nhân viên trực — phòng khám sẽ <b>gọi lại cho "
            f"bạn vào {when}</b>." + ref,
            state="HANDOFF")

    return reply(
        "Có nhé — yêu cầu của bạn <b>đang chờ nhân viên phòng khám tiếp nhận</b>, "
        "và họ đã có toàn bộ nội dung bạn trao đổi với mình. Bạn chờ giúp mình một "
        "chút nhé." + ref,
        state="HANDOFF")


def _record(sess, role, message, update_last=True):
    """Nối 1 lượt vào transcript của yêu cầu đang mở (nếu có). Lỗi thì bỏ qua."""
    code = sess.get("handoff_code")
    if not code:
        return
    try:
        storage.append_handoff_message(code, role, safety.mask_pii(message),
                                       update_last=update_last)
    except Exception as exc:  # noqa: BLE001 - ghi bổ sung không được chặn hội thoại
        print(f"[handoff] CẢNH BÁO: không nối được transcript {code}: {exc}")


def _save_contact(sess, name, phone):
    """Ghi tên + SĐT liên hệ lên bản ghi đã tạo."""
    code = sess.get("handoff_code")
    if not code:
        return
    try:
        storage.set_handoff_contact(code, name, phone)
    except Exception as exc:  # noqa: BLE001
        print(f"[handoff] CẢNH BÁO: không ghi được liên hệ cho {code}: {exc}")


def _contact_note(entry) -> str:
    """Câu cho bệnh nhân biết nhân viên sẽ gọi vào SỐ NÀO — trả lời sẵn câu
    "sao tôi biết để liên hệ" trước khi họ phải hỏi."""
    phone = (entry or {}).get("patient_phone")
    return (f"<span class='muted'>Nhân viên sẽ liên hệ bạn qua số <b>{phone}</b>.</span>"
            if phone else "")


__all__ = ["BOT_STUCK", "PATIENT_REQUEST", "create_request", "handoff_ask_contact",
           "handoff_offer", "handoff_wait", "maybe_escalate", "offer_handoff",
           "start_handoff"]
