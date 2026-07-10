# Red Team Review — plans/260710-1000-fix-medium-low-issues (Security Adversary / Fact Checker)

## Finding 1: M10 session lock is bypassed on the `/reset` command path
- **Severity:** Critical
- **Location:** Phase 1, section "M10 — khoá per-session cho field-level write"
- **Flaw:** The plan proposes `sess = get_session(session_id)` then `with sess["_lock"]: ... (entire body)`. `handle_message()`'s existing `/reset` branch (chatbot.py:127-134) calls `reset_session(session_id)` followed by `sess = get_session(session_id)` **inside** that same body — reassigning the local `sess` variable to a brand-new dict (with a brand-new, unlocked `threading.Lock`) created by `_new_session()`. Python's `with expr:` evaluates `expr` once at entry; reassigning `sess` afterward does not change which lock object is held/released. The rest of the function then mutates the **new** dict's fields (`sess["_id"]`, `sess["state"]`) while only holding the **old, now-orphaned** lock.
- **Failure scenario:** User sends "/reset" (or "làm lại", a common Vietnamese phrase) followed immediately by a second concurrent request for the same `session_id` (double-submit/tab-kép, the exact scenario M10 is meant to fix). The second request calls `get_session()`, gets the same new dict, and acquires its lock — which nobody is holding — and proceeds to interleave field writes with the first (still in-flight) request that is mutating the same dict without holding its lock. This exactly reproduces the M10 bug for the reset path, and does so silently: no exception, no deadlock, just corrupted session state (e.g., `state` flipping between GREET and whatever the second call set).
- **Evidence:** `chatbot.py:127-134`:
  ```
  if low in {"/reset", "bắt đầu lại", "làm lại"}:
      reset_session(session_id)
      sess = get_session(session_id)
      sess["_id"] = session_id
      resp = greeting()
      sess["state"] = resp["state"]
      ...
      return resp
  ```
  Phase 1 plan (phase-01…, lines 68-79) explicitly says to wrap "TOÀN BỘ thân hàm hiện có, chỉ THỤT LỀ THÊM 1 CẤP, không đổi logic" — i.e., it instructs a naive re-indent that does not account for this internal `sess` reassignment.
- **Suggested fix:** Do not reassign `sess` inside the locked block; or capture `lock = sess["_lock"]` once at function entry and reuse it explicitly (`with lock:`), and make `reset_session()`/`_new_session()` preserve the original lock object when re-creating a session for the same id, OR restructure the reset branch to mutate the existing dict in place rather than swapping to a new one. The plan's TDD test suite (`test_concurrent_handle_message_same_session_serialized`) does not cover the `/reset` path, so this bug would ship undetected.

## Finding 2: M7 session-id regex crashes on non-string client input (unauthenticated DoS)
- **Severity:** Critical
- **Location:** Phase 3, section "M7 — validate format session id"
- **Flaw:** `resolve_sid()` calls `_SID_RE.match(client_sid)` without first checking `isinstance(client_sid, str)`. `data` comes from `request.get_json(force=True, silent=True)` (app.py:73/82/92) — fully attacker-controlled JSON. If `session` is a truthy non-string (e.g. an int, list, or dict), `re.Pattern.match()` raises `TypeError: expected string or bytes-like object`, which is not caught anywhere in `resolve_sid()` or in the calling routes.
- **Failure scenario:** Any unauthenticated client POSTs `{"session": 1}` to `/api/start`, `/api/chat`, or `/api/register-push` → unhandled `TypeError` propagates out of the Flask view function → Flask returns 500 for that request (and depending on debug settings could leak a traceback). This is a single-request, zero-cost DoS/crash against every public endpoint that calls `resolve_sid()`, introduced by a "hardening" fix meant to reduce attack surface, not add one.
- **Evidence:** Plan phase-03…, lines 53-68 (proposed `resolve_sid`) has `if client_sid and not _SID_RE.match(client_sid):` with no type check. Confirmed `data.get("session")` is attacker-supplied JSON at `app.py:73,82,92` (`data = request.get_json(force=True, silent=True) or {}`).
- **Suggested fix:** `if client_sid and (not isinstance(client_sid, str) or not _SID_RE.match(client_sid)): client_sid = None`. Add a corresponding test with a non-string `session` value (e.g. `{"session": 123}`) — the plan's own test list only covers `"not-a-valid-uuid"` (a string), so this class of input is untested.

## Finding 3: New Expo ticket-parsing code can crash `send_push`, breaking already-successful bookings
- **Severity:** High
- **Location:** Phase 2, section "M5 — parse ticket Expo + xoá token hết hạn"
- **Flaw:** The new code wraps `json.loads(resp.read())` and the `zip(real, tickets)` loop (which calls `storage.remove_token(token)`) inside the *same* `try` block that only catches `(urllib.error.URLError, OSError)`. `json.loads` can raise `json.JSONDecodeError` (a `ValueError`, not caught), and `storage.remove_token` can raise arbitrary storage/DB exceptions (also not caught) if `USE_DB` and the DB is briefly unavailable. Neither is a subclass of `URLError`/`OSError`.
- **Failure scenario:** `push.send_push()` is called synchronously and **without any try/except at the call site** from `chatbot.py:483` (booking confirmation) and `chatbot.py:624` (cancel confirmation) — both inside `handle_message()`, which by this point has already committed the appointment via `storage.add_appointment`/`booking._insert_with_race_guard`. If Expo returns a malformed/non-JSON body (e.g., a gateway error page with HTTP 200, or truncated response) or `storage.remove_token` hits a transient DB error, the exception propagates all the way up through `handle_message()` to the Flask route, returning a 500 to the patient — even though their appointment was already successfully booked in the database. This directly contradicts the plan's own stated design principle quoted in its Risk Assessment ("audit/push lỗi không được làm gián đoạn nghiệp vụ" / push errors must not interrupt the booking).
- **Evidence:** Plan phase-02…, lines 133-148 (single `try`/`except (urllib.error.URLError, OSError)` wrapping `json.loads` + `zip` loop + `storage.remove_token`). Call sites confirmed unguarded: `chatbot.py:483` (`push.send_push(tokens, title=..., ...)` — no surrounding try/except) and `chatbot.py:624`.
- **Suggested fix:** Wrap the JSON-parsing/ticket-processing section in its own `try/except Exception`, falling back to the existing network-failure handling (`_write_outbox` + `failed = len(real)`) on any parse/processing error, not just `URLError`/`OSError`. Also wrap the individual `storage.remove_token(token)` call so one bad token removal doesn't abort processing of the remaining tickets.

## Finding 4: Audit log rotation is an unlocked check-then-act race across concurrent sessions
- **Severity:** High
- **Location:** Phase 4, section "Architecture" (`_rotate_audit_log_if_needed` + `audit`)
- **Flaw:** `_rotate_audit_log_if_needed()` checks `os.path.getsize(AUDIT_LOG_PATH) >= AUDIT_LOG_MAX_BYTES` and then calls `os.replace(...)`, immediately followed (unguarded) by `open(AUDIT_LOG_PATH, "a")` in `audit()`. No lock protects this sequence. `safety.audit()` is called at least twice per `handle_message()` turn (chatbot.py:123 for user message, chatbot.py:211/133/139/150/158/169 for bot replies) from potentially many concurrent sessions simultaneously. Phase 1's new per-session lock (M10) only serializes calls for the *same* session id — it does nothing to serialize `audit()` calls across *different* concurrent sessions, which is the exact scenario that triggers this race.
- **Failure scenario:** Two threads handling two different sessions both call `audit()` when the log is at/over the size threshold. Both see `size >= AUDIT_LOG_MAX_BYTES` and both call `os.replace(AUDIT_LOG_PATH, rotated_path)`. Depending on interleaving, one thread's `os.replace` can execute between another thread's rotation check and its `open(..., "a")` call — that thread's subsequent write lands in the just-renamed `.1` backup file (via its already-resolved path, POSIX rename semantics keep the open call targeting whatever path currently resolves to `AUDIT_LOG_PATH` at open-time) or two threads can race to overwrite the same `.1`, silently discarding entries that were supposed to be preserved in the backup. Net effect: silent audit log entry loss/misplacement under concurrent load — undermining the very robustness (M9) this phase claims to deliver.
- **Evidence:** Phase 4 plan, lines 44-51 (`_rotate_audit_log_if_needed`) and lines 54-66 (`audit`), no `Lock` introduced anywhere in the file (`grep -n "Lock" safety.py` confirms none exists currently). Compare with Phase 2's explicit recognition of the analogous JSON read-modify-write race, fixed with `_JSON_LOCK` — Phase 4 does not apply the same treatment despite equally concurrent access.
- **Suggested fix:** Introduce a `threading.Lock` (e.g., `_AUDIT_LOCK`) around the rotate-check + open + write sequence in `audit()`, mirroring the `_JSON_LOCK` pattern already adopted in Phase 2.

## Finding 5: M8 rate limiting explicitly exempts `/api/admin/*`, leaving the admin key unthrottled against brute force
- **Severity:** Medium
- **Location:** Phase 3, section "M8 — rate limit theo IP" and Requirements ("không áp dụng cho `/api/admin/*`, đã bảo vệ bằng key riêng")
- **Flaw:** `_check_admin()` compares the `X-Admin-Key` header via `hmac.compare_digest` (constant-time, good) but there is no attempt limiting on any admin route. The new `_rate_limit_guard()` hook explicitly excludes every path not in `_RATE_LIMITED_PATHS` (and not `/api/ics/*`), which means all of `/api/admin/appointments`, `/api/admin/schedule`, `/api/admin/meta`, `/api/admin/cancel` remain completely unthrottled.
- **Failure scenario:** An attacker who can send unlimited requests can brute-force or credential-stuff `X-Admin-Key` against `/api/admin/meta` (a cheap, side-effect-free GET) with no rate limit, no lockout, and no alerting — the constant-time comparison only prevents *timing* attacks, it does nothing against raw guess-rate. This phase is titled "App Hardening" and explicitly targets rate limiting (M8) as a residual risk from C3, yet leaves the highest-privilege endpoint family completely outside its scope.
- **Evidence:** Phase 3 plan lines 33 ("không áp dụng cho `/api/admin/*`, đã bảo vệ bằng key riêng"), lines 84-114 (`_RATE_LIMITED_PATHS` set + `_rate_limit_guard`); confirmed in `app.py:125-129` (`_check_admin`) that the only protection is `hmac.compare_digest`, no attempt counter, no lockout.
- **Suggested fix:** At minimum, apply the same IP-based rate limiter (or a stricter threshold) to `/api/admin/*` routes — constant-time comparison and rate limiting solve different threats (timing side-channel vs. brute-force volume) and are not substitutes for each other. If deliberately out of scope, this should be called out as a residual risk in `ISSUES.md`/plan rather than silently declared "protected."

## Finding 6: New universal M1 guardrail is inserted ahead of existing cancel-intent/info-question handling with no analysis or test of the interaction
- **Severity:** Medium
- **Location:** Phase 1, section "M1 — guardrail chẩn đoán áp dụng mọi state trừ TRIAGE"
- **Flaw:** The plan places the new diagnosis guardrail "Thêm ngay sau khối `needs_human_handoff` ... TRƯỚC phần định tuyến theo state" — i.e., immediately after the handoff check (chatbot.py:143-151) and therefore *before* the existing cancel-intent check (`chatbot.py:155-160`, active in `TRIAGE`/`CONFIRM_DEPT`/`DONE`) and the info-question check (`chatbot.py:164-171`, same states). Both of those existing checks currently run in `CONFIRM_DEPT`/`DONE` (non-TRIAGE states the new guardrail also targets).
- **Failure scenario:** In `CONFIRM_DEPT` or `DONE` state, a legitimate info-question that happens to also satisfy `safety.is_diagnosis_request()` wording (e.g. phrasing referencing "có nguy hiểm không" / "có sao không" — both literal entries in `DIAGNOSIS_REQUEST_PATTERNS`, safety.py:66-68 — commonly used when asking generically "trồng răng có nguy hiểm không?") will now be intercepted by the new guardrail and answered with a generic disclaimer instead of the existing, more useful `_describe_service` info-question flow, silently changing behavior for a whole class of previously-working queries. The plan's own test list (phase-01…, lines 100-108) only exercises `PICK_TIME`, never `CONFIRM_DEPT`/`DONE` — the exact states where this ordering collision with pre-existing checks (cancel-intent, info-question) can occur — so this regression would not be caught by the prescribed TDD tests.
- **Evidence:** Phase 1 plan lines 41-53 (insertion point); `chatbot.py:143-171` (existing handoff → cancel-intent → info-question ordering, all before state routing); `safety.py:66-68` (`_SEED_DIAGNOSIS_REQUEST_PATTERNS` includes `"có nguy hiểm không"`, `"có sao không"` — generic phrases plausibly used in service-info questions, not only personal-diagnosis requests).
- **Suggested fix:** Either place the guardrail after the cancel-intent/info-question blocks (so existing, more specific intent handling still gets first refusal in `CONFIRM_DEPT`/`DONE`), or add explicit tests exercising `CONFIRM_DEPT`/`DONE` states with messages that trigger both an info-question trigger and a diagnosis pattern to pin down the intended precedence before shipping.

---

## Fact-Check Summary (Fact Checker role)

| Claim | Status |
|---|---|
| `chatbot.py` `SESSIONS`/`_SESSIONS_LOCK`/`_new_session`/`get_session`/`reset_session` as described | VERIFIED (chatbot.py:31-83) |
| `handle_message` signature and early-return structure (emergency/handoff/cancel/info/reset) | VERIFIED (chatbot.py:113-212) |
| `_do_triage` calls `safety.is_diagnosis_request` | VERIFIED (chatbot.py:218-221) |
| `booking._insert_with_race_guard` catches `psycopg.errors.UniqueViolation`, checks `constraint_name == "ux_appointments_doctor_slot"` | VERIFIED (booking.py:162-206) |
| `storage.py` JSON-mode functions (`add_appointment`, `set_reminder_sent`, `set_status`, `add_token`, `get_tokens`, `_json_load`/`_json_save`, `USE_DB`, `APPOINTMENTS_PATH`, `TOKENS_PATH`) | VERIFIED (storage.py:27-306) |
| `push.send_push` current structure (real/demo split, `_write_outbox`, `except (urllib.error.URLError, OSError)`) | VERIFIED (push.py:58-98) |
| `push.send_push` called unguarded from `chatbot.py` | VERIFIED (chatbot.py:483, chatbot.py:624 — no surrounding try/except) |
| `app.py` `resolve_sid`, `/api/start`, `/api/chat`, `/api/register-push` use `request.get_json(force=True, silent=True)` | VERIFIED (app.py:53-96) |
| `app.py` `_check_admin` uses `hmac.compare_digest`, admin routes call it individually | VERIFIED (app.py:125-176) |
| `safety.py` `audit()` / `AUDIT_LOG_PATH`, no existing lock | VERIFIED (safety.py:18,148,158 — no `Lock`/`threading` in file) |
| `safety.DIAGNOSIS_REQUEST_PATTERNS` includes "có nguy hiểm không", "có sao không" | VERIFIED (safety.py:66-68) |
| `triage.info_question_service`/`is_info_question`/`_INFO_TRIGGERS` | VERIFIED (triage.py:117-134,172-176) |

