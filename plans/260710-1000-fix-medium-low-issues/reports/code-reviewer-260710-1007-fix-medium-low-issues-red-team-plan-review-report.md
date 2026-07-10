# Red-Team Plan Review: fix-medium-low-issues

Reviewer role: Flow Tracer / Failure Mode Analyst. All findings verified against the
actual current state of the repo (not the plan's paraphrase of it).

## Finding 1: M10 per-session lock is defeated by the existing `/reset` branch inside `handle_message`
- **Severity:** Critical
- **Location:** Phase 1, section "M10 — khoá per-session cho field-level write"
- **Flaw:** The plan wraps the entire body of `handle_message` in `with sess["_lock"]:`,
  claiming this "tự động cover MỌI early-return... không cần sửa từng nhánh riêng lẻ." But
  `handle_message` already contains a branch (chatbot.py:127-134) that calls
  `reset_session(session_id)` and then **reassigns the local variable** `sess = get_session(session_id)`
  to a brand-new dict (with a brand-new, unlocked `Lock`). A `with expr:` statement evaluates
  `expr` once at block entry; reassigning the local name afterward does not change which lock
  object is held. The thread stays holding the *old*, now-orphaned lock while mutating fields
  on the *new* dict that has just been installed in `SESSIONS`.
- **Failure scenario:** Client double-submits (tab kép / retry) `"/reset"` and a normal message
  for the same `session_id` at nearly the same time. Thread A enters `handle_message`, acquires
  lock L_old, hits the `/reset` branch, calls `reset_session()` which replaces
  `SESSIONS[session_id]` with a fresh dict (lock L_new, unlocked), then continues mutating that
  fresh dict's fields (`sess["_id"]`, `sess["state"]`) — still only holding L_old. Thread B,
  arriving concurrently for the same `session_id`, calls `get_session()`, gets the *same* fresh
  dict (already installed by Thread A), and immediately acquires L_new (uncontended) and starts
  mutating the same dict's fields concurrently with Thread A. The exact interleaved-field-write
  race M10 was written to close (chatbot.py:19-23 comment, `sess["state"]`, `sess["date"]`, ...)
  reappears precisely at the reset boundary — the one place where two concurrent requests are
  most likely to race (double "start over" click, or `/reset` racing a stale in-flight message).
- **Evidence:** chatbot.py:113-134 (current `handle_message`/`/reset` branch);
  chatbot.py:78-83 (`reset_session` replaces the dict, does not reuse the old lock);
  phase-01 §"M10", lines 68-79 (the proposed universal `with sess["_lock"]:` wrap, presented as
  sufficient to "tự động cover MỌI early-return").
- **Suggested fix:** Either (a) hold the container-level lock across the reassignment and
  re-enter/re-acquire the *new* dict's lock explicitly after `reset_session`, or (b) make
  `reset_session` mutate the existing dict in place (reset fields, keep the same `_lock`
  object) instead of swapping in a new dict, so any lock already held by an in-flight caller
  stays authoritative for the dict it's protecting.

## Finding 2: M6 "JSON mode identical to Postgres" claim is false — the actual slot double-booking race is not closed
- **Severity:** Critical
- **Location:** Phase 2, section "M6 — phát hiện trùng code ở JSON mode" (and Overview,
  "GIỐNG HỆT luồng Postgres hiện có")
- **Flaw:** The plan only adds duplicate-*code* detection inside `storage.add_appointment`
  (JSON branch), guarded by `_JSON_LOCK`. But the actual race that `_insert_with_race_guard`'s
  Postgres-side `ux_appointments_doctor_slot` UNIQUE INDEX protects against is a *slot*
  double-booking race (two concurrent requests for the same doctor+date+time), not a code
  collision. In `booking.book_appointment()` (booking.py:99-140), the slot-uniqueness check
  `_confirmed_at(doctor_id, date_str, time_str)` runs at line 134, **entirely outside**
  `_JSON_LOCK` and well before `storage.add_appointment()` is ever called. Two concurrent
  requests for the same doctor/date/time in JSON mode will both pass the `_confirmed_at` check
  (neither sees the other's appointment yet), then both proceed to
  `_insert_with_race_guard` → `storage.add_appointment()` with two *different* randomly
  generated codes — no code collision occurs, so the new `DuplicateCodeError` path never
  triggers, and both inserts succeed. Result: two confirmed appointments for the same doctor
  slot in JSON mode, silently.
- **Failure scenario:** Two patients (or one patient double-tapping "Xác nhận đặt lịch")
  simultaneously book the same doctor's 14:00 slot while running in JSON mode (any deployment
  without `DATABASE_URL` set — which the plan's own M2 phase explicitly targets for
  thread-safety hardening, implying concurrent JSON-mode requests are an expected scenario).
  Both get a "🎉 Đặt lịch thành công" response with different appointment codes; the doctor
  now has two patients booked in the same slot, exactly the bug class M2/M6 claim to fix but
  do not.
- **Evidence:** booking.py:132-140 (`_confirmed_at` check outside any lock, before insert);
  booking.py:158-159 (`_insert_with_race_guard` called after the check, `retry=True`);
  phase-02 lines 20-24 (Overview claiming M6 closes JSON's protection gap) and lines 34-36
  (Requirements: "storage.add_appointment() ở JSON mode phát hiện trùng code... GIỐNG HỆT
  luồng Postgres hiện có").
- **Suggested fix:** Either move the slot-uniqueness check inside `_JSON_LOCK` immediately
  before the append in `storage.add_appointment` (re-check `_confirmed_at`-equivalent under
  the lock, not just `code`), or explicitly document in ISSUES.md that M6 only closes the
  code-collision hole and the slot-race remains open in JSON mode — do not mark M6 `[x]` as
  fully resolved/parity-with-Postgres if the actual booking-race is not addressed.

## Finding 3: M5's new Expo ticket-parsing code can raise an uncaught exception that propagates through an already-committed booking, crashing `/api/chat` with a 500 after the DB write succeeded
- **Severity:** Critical
- **Location:** Phase 2, section "M5 — parse ticket Expo + xoá token hết hạn"
- **Flaw:** The proposed `push.send_push()` change parses the Expo HTTP response body with
  `json.loads(resp.read())` and then does `ticket.get("status")` / `ticket.get("details", {})`
  inside the same `try` block, but the surrounding `except` clause only catches
  `(urllib.error.URLError, OSError)` (push.py:92, unchanged per plan). `json.loads` on a
  malformed/non-JSON 200 response raises `json.decoder.JSONDecodeError` (a `ValueError`
  subclass, not caught), and if a ticket element is not a dict (unexpected Expo payload shape),
  `.get()` raises `AttributeError` (also not caught). `push.send_push()` is called directly
  from `chatbot._finalize_booking()` (chatbot.py:481-489) with **no try/except** around it, and
  `_finalize_booking` is invoked from `/api/chat` (app.py: `chat()`) with no try/except either.
  Critically, `storage.add_appointment()` has *already committed* the appointment before
  `push.send_push()` is called (chatbot.py:449-459 happens first).
- **Failure scenario:** Expo's push endpoint has a transient hiccup and returns HTTP 200 with a
  non-JSON body (maintenance page, truncated response, etc. — plausible for any third-party
  HTTP dependency, and explicitly NOT a `URLError`/`OSError` since the connection succeeded).
  The booking has already been written to the DB (or JSON file). `push.send_push` now raises
  `JSONDecodeError`, which propagates unhandled all the way up through `_finalize_booking` →
  `_confirm_booking` → `handle_message` → the Flask `/api/chat` view → a bare 500 response
  (and, without `debug=False` explicitly hardened elsewhere, a stack trace surfaced to the
  client). The user sees a failed request and no confirmation, but the appointment is
  permanently booked in the DB — a state the user cannot see or recover from without contacting
  support, and a data-exposure risk if a traceback leaks storage/db internals in the 500 body.
- **Evidence:** push.py:81-96 (current `send_push`, to be modified per phase-02 lines 129-149,
  keeping the same narrow `except (urllib.error.URLError, OSError):`); chatbot.py:449-489
  (`_finalize_booking`: DB insert commits first, `push.send_push` called with no
  try/except); app.py `chat()` route (no try/except around `chatbot.handle_message`).
- **Suggested fix:** Widen the except clause around the Expo response-parsing block to also
  catch `(json.JSONDecodeError, ValueError, AttributeError, KeyError, TypeError)` (treat any
  malformed-response case the same as a network failure: write to outbox, mark `failed`), so a
  third-party response-shape surprise never crashes an already-successful booking confirmation.

## Finding 4: M1 guardrail insertion point is ambiguous relative to the existing cancel-intent and info-question blocks, with no test covering the interaction
- **Severity:** Medium
- **Location:** Phase 1, section "M1 — guardrail chẩn đoán áp dụng mọi state trừ TRIAGE"
- **Flaw:** The plan instructs inserting the new guardrail "ngay sau khối
  `needs_human_handoff`... TRƯỚC phần định tuyến theo state." In the actual code, there are two
  more universal-ish guardrail blocks between `needs_human_handoff` and the state-routing
  switch: the cancel-intent check (chatbot.py:155-160, `_is_cancel_request`) and the
  info-question check (chatbot.py:164-171, `triage.info_question_service`), both active for
  states `{TRIAGE, CONFIRM_DEPT, DONE}` — the same states M1's guardrail also applies to
  (everything except TRIAGE, which includes CONFIRM_DEPT and DONE). The plan's instruction
  window spans both existing blocks without specifying whether the new guardrail should run
  before or after them, and the Implementation Steps only say to "xác nhận vị trí chèn... đúng
  chỗ" during a read-first step — this is left as an unverified implementer judgment call, not
  a specified behavior, and no test in `test_chatbot_guardrail.py` exercises a message that
  matches both a diagnosis pattern and a cancel/info pattern.
- **Failure scenario:** In state `DONE`, user types `"huỷ lịch hẹn giúp tôi, tôi phải uống
  thuốc gì trước khi khám không"` — this matches `_is_cancel_request` (`"huy lich hen"`) AND
  `safety.is_diagnosis_request` (`"uống thuốc gì"`, confirmed in `_SEED_DIAGNOSIS_REQUEST_PATTERNS`,
  safety.py:67). If the guardrail is inserted before the cancel-check (a plausible, plan-
  consistent placement given the stated "ngay sau needs_human_handoff"), the user's cancel
  intent is silently swallowed by the diagnosis disclaimer instead of starting the cancel flow
  — a real regression with zero test coverage to catch it either way.
- **Evidence:** chatbot.py:142-172 (order of existing guardrail/intent blocks);
  safety.py:65-69 (`_SEED_DIAGNOSIS_REQUEST_PATTERNS` includes "uống thuốc gì"); phase-01
  lines 40-57 (ambiguous insertion instruction, no interaction test in Implementation Steps).
- **Suggested fix:** Explicitly specify insertion point relative to the cancel/info blocks
  (recommend: after both, immediately before state-routing, so explicit intents like
  cancel/info win over the generic diagnosis guardrail), and add a red test asserting that a
  message matching both patterns is routed as cancel/info, not swallowed by the guardrail.

## Finding 5: M8 rate-limiter test isolation is a "risk to watch" instead of a mandated fixture, threatening a flaky/broken full-suite run
- **Severity:** Medium
- **Location:** Phase 3, section "Implementation Steps" step 4 and "Risk Assessment"
- **Flaw:** `_RATE_BUCKETS` is a module-level global (OrderedDict), shared across the entire
  pytest process. The plan's own Risk Assessment acknowledges this ("Test rate-limit có thể
  ảnh hưởng lẫn nhau nếu chạy chung process pytest") but only *conditionally* requires a fix:
  "nếu phát hiện vấn đề này khi implement, thêm fixture." Given the plan's own acceptance
  criterion is `pytest tests/ -v` (the full suite, combining tests from this plan's 5 phases
  plus the two prior Critical/High plans) must pass with no regressions, and `/api/ics/<code>`
  is one of the rate-limited paths (phase-03 lines 84-85, 109-111), any pre-existing test file
  that calls `/api/ics/<code>` repeatedly from the same Flask test client (shared default
  `remote_addr`) more than 30 times within the full-suite run risks tripping the new 429
  guard — a cross-file interaction the plan defers to "if discovered during implementation"
  rather than mandating up front.
- **Failure scenario:** `pytest tests/ -v` (full suite) executes `tests/test_app_ics.py` (from
  a prior plan, unmodified, unaware rate limiting exists) after `tests/test_app_hardening.py`
  in the same process, without any `_RATE_BUCKETS.clear()` between files. If `test_app_ics.py`
  makes >30 requests to ICS-adjacent paths cumulatively with test_app_hardening's leftover
  bucket state, it starts failing with unexpected 429s — a self-inflicted regression in a test
  file this plan explicitly promises not to touch or break (Success Criteria: "tests/test_app_ics.py
  ... vẫn pass").
  requirement.
- **Evidence:** phase-03 lines 78-79 (`_RATE_BUCKETS = OrderedDict()`, module-level, no reset
  hook defined in Architecture); lines 169-174 (Risk Assessment hedges the fix as conditional,
  "nếu phát hiện vấn đề này khi implement"); plan.md line 77 (acceptance criterion: full
  `pytest tests/ -v` must pass with no regression).
- **Suggested fix:** Mandate an autouse fixture (session- or module-scoped, in a shared
  `conftest.py` or at minimum in every test file that exercises rate-limited routes) that
  clears `_RATE_BUCKETS` before each test, rather than leaving it as an "if you notice a
  problem" step.

## Finding 6: `_new_session()`'s `_lock` field makes session dicts unpicklable/unserializable with no migration note, silently locking in the "single in-memory process" architecture
- **Severity:** Medium
- **Location:** Phase 1, section "M10", `_new_session()` change
- **Flaw:** Adding `"_lock": threading.Lock()` to every session dict means `SESSIONS` values
  can never be serialized (pickled, JSON-dumped, sent to Redis, etc.) without first stripping
  the lock. The plan's own module docstring (chatbot.py:19-30) already documents that a future
  move to multi-worker deployment or shared session storage (Redis/DB) is a known, called-out
  future direction ("Sản phẩm thật nên dùng Redis/DB... nếu sau này deploy nhiều worker
  process"). This phase adds a field that actively blocks that migration path (any future
  "serialize session dict to Redis" implementation will crash trying to pickle a `Lock`)
  without a comment flagging the tradeoff, unlike the existing `_MAX_SESSIONS` note which does
  document its single-process limitation.
- **Failure scenario:** Not a runtime bug for the current single-process scope, but a latent
  trap for the next engineer (human or AI agent) who implements the Redis migration already
  flagged as a future direction in this same file — a naive `pickle.dumps(sess)` or
  `json.dumps(sess)` call will crash with `TypeError: cannot pickle '_thread.lock' object`,
  and the cause (a field added by this plan, three plans removed from the migration work) will
  not be obvious without archaeology.
- **Evidence:** chatbot.py:19-30 (existing docstring calling out future Redis/multi-worker
  migration); phase-01 lines 60-67 (`_new_session()` adding `"_lock": threading.Lock()`
  unconditionally, no comment about serialization implications).
- **Suggested fix:** Add a one-line comment on the `_lock` field noting it must be excluded/
  reconstructed if session storage is ever externalized (matches the existing documentation
  standard already set for `_MAX_SESSIONS` in the same file).

## Unresolved Questions
- Should M6 be re-scoped explicitly to "code-collision only" in `ISSUES.md`, or does the user
  want the actual slot-race (Finding 2) fixed in JSON mode as part of this plan's stated intent
  to make JSON parity with Postgres?
- Is a 500 (Finding 3) an acceptable failure mode for `/api/chat` after a successful DB write,
  given no other endpoint in this codebase currently wraps route handlers in a catch-all error
  handler? If the project has a global Flask error handler elsewhere that converts 500s into a
  safe JSON envelope, that would reduce (but not eliminate) the severity of Finding 3.
