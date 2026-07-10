# Red Team Security Adversary Review — plans/260709-2230-fix-high-issues

Role: Security Adversary + Fact Checker. All findings backed by grep/read evidence against
the current repo state.

## Finding 1: Phase 1 architecture omits updating `_confirmed_at` call inside `_insert_with_race_guard`
- **Severity:** Critical
- **Location:** Phase 1, section "Architecture" step 2 (`booking.py`)
- **Flaw:** The plan lists exactly 3 changes for `booking.py`: (a) change `_confirmed_at`
  signature to `_confirmed_at(doctor_id, date_str, time_str)`, (b) update the call inside
  `book_appointment()`, and (c) update the `constraint_name` string match inside
  `_insert_with_race_guard`. It never mentions the second call to `_confirmed_at` that lives
  *inside* `_insert_with_race_guard` itself, and `_insert_with_race_guard`'s signature has no
  `doctor_id` parameter to source it from.
- **Failure scenario:** Two different doctors book the exact same `(date, time)` concurrently
  and the DB race path fires (`UniqueViolation` on `ux_appointments_doctor_slot`). The code
  hits `taken = _confirmed_at(date_str, time_str)` at booking.py:183, now with the new 3-arg
  signature. Called with only 2 positional args, this raises `TypeError`, which propagates as
  an unhandled 500 from the Flask booking route — in the exact concurrency scenario Phase 1
  exists to protect. If instead the implementer naively passes `appointment.get("doctor_id")`
  without also updating unit test coverage, silent wrong-doctor filtering is possible too.
- **Evidence:** Current code, `booking.py:180-188`:
  ```
  constraint_name = getattr(getattr(exc, "diag", None), "constraint_name", None)
  if constraint_name == "ux_appointments_slot":
      taken = _confirmed_at(date_str, time_str)
  ```
  `_insert_with_race_guard` signature, `booking.py:155-156`:
  ```
  def _insert_with_race_guard(appointment, date_str, time_str, patient_phone, retry):
  ```
  Plan text (phase-01, lines 47-49) lists only: *"`_insert_with_race_guard` (hàm C2 đã tạo):
  đổi điều kiện so khớp `constraint_name == "ux_appointments_slot"` thành
  `constraint_name == "ux_appointments_doctor_slot"`."* — no mention of the internal
  `_confirmed_at` call or adding a `doctor_id` parameter.
- **Suggested fix:** Add `doctor_id` (or `appointment.get("doctor_id")`) as an explicit
  parameter to `_insert_with_race_guard` and update the internal `_confirmed_at` call inside
  it to `_confirmed_at(doctor_id, date_str, time_str)`. Add a test that exercises the
  `UniqueViolation` retry branch specifically (not just the happy-path
  "different doctors both succeed" test) to catch this signature mismatch.

## Finding 2: Phase 4 does not close H7 as defined in ISSUES.md — leaves `debug=True, host="0.0.0.0"` unaddressed
- **Severity:** Critical
- **Location:** Phase 4, section "Architecture" (H7 warning)
- **Flaw:** ISSUES.md explicitly scopes H7 to three code locations: `app.py:23,26,160`. Lines
  23/26 are the `SECRET_KEY`/`ADMIN_KEY` defaults (addressed by the plan's print-warning), but
  line 160 area is `app.run(debug=True, host="0.0.0.0", port=5001)` — the Werkzeug debug
  server bound to all network interfaces. The plan's Architecture and Success Criteria for
  Phase 4 only add a startup warning for default keys; `debug=True`/`host="0.0.0.0"` is never
  mentioned or modified anywhere in the phase file.
- **Failure scenario:** If this Flask app is ever run via `python app.py` (not gunicorn) in a
  reachable network context (a plausible demo/staging deployment path given this codebase's
  "1 Flask process" architecture), Werkzeug's interactive debugger is exposed to any host that
  can reach port 5001 on the LAN/network. Triggering any unhandled exception opens a debugger
  console in the browser that allows arbitrary Python code execution (well-known Werkzeug
  debug-console RCE) — full remote code execution on the health-data-holding server.
- **Evidence:** `app.py:164`: `app.run(debug=True, host="0.0.0.0", port=5001)`. `ISSUES.md`
  line 72: `**H7 — SECRET_KEY/ADMIN_KEY mặc định + debug=True trên 0.0.0.0** (app.py:23,26,160)`.
  Plan's Acceptance Criteria (plan.md) claims "Vá 8/9 vấn đề High... (H1-H8)" and Phase 4
  Success Criteria list only key-warning items — no line references line 160/`debug=True`.
- **Suggested fix:** Either gate `debug=True` behind an explicit env var (default off) or at
  minimum bind to `127.0.0.1` by default with an env override for LAN testing, and update the
  Phase 4 Requirements/Architecture/Success Criteria to explicitly cover this, since ISSUES.md
  scopes H7 to include it. If the team decides `debug=True`/`0.0.0.0` is an accepted risk for
  this student project, that must be stated as an explicit decision (per the "Verified
  Decisions"/"User Decisions" project rules) rather than silently dropped from the phase scope
  while still claiming H7 is "vá" (patched).

## Finding 3: `_check_admin()` retains non-constant-time key comparison after "hardening"
- **Severity:** High
- **Location:** Phase 4, section "Architecture" (`_check_admin`)
- **Flaw:** The proposed replacement is `key = request.headers.get("X-Admin-Key", ""); return
  key == ADMIN_KEY`. Python's `==` on strings short-circuits on the first differing byte,
  making it vulnerable to a timing side-channel that can be used to recover `ADMIN_KEY`
  character-by-character over many requests. A phase explicitly named "Admin Auth Hardening"
  that closes the `?key=` query-string leak but leaves this open only forces the attacker to
  use the (now sole) header path — it doesn't eliminate the class of attack.
- **Failure scenario:** An attacker with network access to `/api/admin/appointments` sends
  many requests with guessed `X-Admin-Key` header values, measuring response latency to
  incrementally confirm each correct byte prefix, eventually recovering `ADMIN_KEY` even when
  it is a strong non-default value.
- **Evidence:** Current code, `app.py:103-105`:
  ```
  def _check_admin():
      key = request.headers.get("X-Admin-Key") or request.args.get("key", "")
      return key == ADMIN_KEY
  ```
  Plan's Architecture block (phase-04, lines 41-45) proposes the identical `==` comparison
  pattern, only removing the `request.args.get("key", "")` fallback. `grep -n "compare_digest"
  app.py` returns no matches — no constant-time comparison exists anywhere in the codebase
  today or in the plan's proposed replacement.
- **Suggested fix:** Use `hmac.compare_digest(key, ADMIN_KEY)` in `_check_admin()`. This is a
  1-line change well within the stated scope of "Admin Auth Hardening" and should be added to
  Phase 4's Architecture/Requirements.

## Finding 4: H2 fix only detects transport-level failures, not Expo API application-level ticket errors
- **Severity:** Medium
- **Location:** Phase 2, section "Architecture" (H2 — `push.py` `send_push`)
- **Flaw:** The plan's `failed` counter is only incremented inside the
  `except (urllib.error.URLError, OSError)` branch. The current code already discards the
  Expo API response body (`resp.read()` with no parsing), and the plan's replacement keeps
  that pattern — it does not parse the JSON response to detect per-message ticket errors
  (Expo returns HTTP 200 with a JSON array of `{"status": "error", "message": ..., "details":
  {"error": "DeviceNotRegistered"|...}}` per token for many real-world failure modes:
  unregistered/expired device, malformed token, rate limiting).
- **Failure scenario:** A push token is stale/unregistered (a very common real-world case, not
  a network error). Expo's HTTP call succeeds (200 OK) with a per-ticket error in the body.
  Under the plan's fix, `sent = len(real)` and `failed` stays `0`, so
  `mark_reminder_sent` is called even though the reminder was never actually delivered —
  reproducing the exact H2 symptom ("mất nhắc lịch vĩnh viễn, không retry") the phase claims
  to fix, just via a different trigger than a raw network exception.
- **Evidence:** Current code, `push.py:88-90`:
  ```
  with urllib.request.urlopen(req, timeout=10) as resp:
      resp.read()
      sent = len(real)
  ```
  Plan's Architecture pseudocode (phase-02, lines 62-74) keeps the same
  `try: ... sent = len(real) except (urllib.error.URLError, OSError): ...` structure with no
  response-body parsing added. The phase's Risk Assessment section only documents the
  accepted network-timeout limitation ("Nếu lỗi mạng kéo dài qua giờ hẹn...") — it does not
  mention or accept this broader application-level gap, so it is not a knowingly-scoped
  limitation, just an unexamined one.
- **Suggested fix:** Parse the Expo response JSON and treat any per-ticket
  `"status": "error"` as a failure contributing to the `failed` count, or explicitly document
  this as an accepted scope limitation (matching the network-timeout carve-out already present)
  if the team decides parsing Expo's response format is out of scope for this pass.

## Finding 5: Phase 1 Risk Assessment claim about index tightening safety is unverified for the JSON-file fallback path
- **Severity:** Medium
- **Location:** Phase 1, section "Risk Assessment"
- **Flaw:** The Risk Assessment argues the new `(doctor_id, date, time)` index is strictly
  safer than the old `(date, time)` index and "an toàn để deploy" — true for the Postgres
  path. But `storage.init_schema()` only runs (and only creates any UNIQUE index at all) when
  `USE_DB` is true; the JSON-file fallback path (`DATABASE_URL` unset) has zero DB-level
  uniqueness enforcement in either the old or new design, relying solely on the app-level
  `_confirmed_at` TOCTOU check. The plan's claim of safety is accurate only for the DB path,
  but is stated as a general "safe to deploy" conclusion without that caveat, and the plan
  never verifies `_confirmed_at`'s behavior change doesn't affect JSON-mode race behavior
  (no index exists to fall back on if the app-level check races).
- **Failure scenario:** Not a regression introduced by this plan (pre-existing from C1-C5), but
  the plan's confidence framing ("An toàn để deploy") could mislead a reviewer into believing
  the race condition is closed everywhere, when in JSON/file-storage mode (which the codebase
  explicitly supports per `storage.py:5-7`) two concurrent bookings for the same doctor/slot
  can still both succeed with no DB constraint to catch the race.
- **Evidence:** `storage.py:26-27`: `USE_DB = bool(DATABASE_URL)`;
  `storage.py:105`: `if _schema_ready or not USE_DB: return` (schema/index creation skipped
  entirely when not using DB). Phase 1 plan text never distinguishes DB-mode vs JSON-mode
  guarantees in its Risk Assessment.
- **Suggested fix:** Add an explicit caveat in Phase 1's Risk Assessment noting the JSON-file
  fallback has no DB-level race protection (inherited limitation, not introduced here), so
  reviewers don't over-read the "safe to deploy" conclusion as covering all storage modes.

---

## Fact-Check Summary (sampled claims)

| Claim | File:Line | Result |
|---|---|---|
| `UNIQUE_SLOT_INDEX_SQL` / `ux_appointments_slot` exist | storage.py:92-94 | VERIFIED |
| `_confirmed_at(date_str, time_str)` current 2-arg signature | booking.py:99 | VERIFIED |
| `_insert_with_race_guard` constraint_name check | booking.py:180-182 | VERIFIED |
| 3x `lambda d, t: None`-style 2-arg monkeypatches of `_confirmed_at` in tests | tests/test_booking.py:193,226,245 | VERIFIED (3 call sites, 2 literal `None`, 1 side-effect-recording lambda — same arity) |
| `push.send_push` returns `{"sent","outbox"}`, no `failed` field yet | push.py:96 | VERIFIED |
| `reminder_worker.scan_once` uses `datetime.now()` (naive, host-local) | reminder_worker.py:72 | VERIFIED |
| `reminder_worker._send_for` always calls `mark_reminder_sent` unconditionally | reminder_worker.py:59-65 | VERIFIED |
| `app.py` `_check_admin` accepts header OR `?key=` query string today | app.py:103-105 | VERIFIED |
| `templates/admin.html` only uses `X-Admin-Key` header, never `?key=` | templates/admin.html:149,213-214 | VERIFIED |
| `chatbot.handle_message` audits raw `message` at top, before routing | chatbot.py:120 | VERIFIED |
| Only one name-collecting state (`ASK_NAME`) exists in chatbot.py | chatbot.py:184,386 (grep for "NAME" shows single state) | VERIFIED |
| `tests/test_app_admin.py`, `tests/test_calendar_ics.py`, `tests/test_chatbot_audit.py` do not yet exist (to be created) | `ls tests/` | VERIFIED (absent) |
| ISSUES.md scopes H7 to `app.py:23,26,160` including `debug=True`/`host="0.0.0.0"` | ISSUES.md:72, app.py:164 | VERIFIED — plan's Phase 4 does not address line 160 |
| `hmac.compare_digest` used anywhere for ADMIN_KEY check | app.py (grep) | FAILED (not found) — confirms Finding 3 |
