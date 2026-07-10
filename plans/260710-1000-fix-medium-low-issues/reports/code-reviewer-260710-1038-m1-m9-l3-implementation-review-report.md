# Code Review: M1-M9 + L3 Implementation (5-Phase Parallel Round)

## Score: 9/10

Code changes are correct, match the red-team-reviewed spec in every phase file almost
line-for-line, and pass the full test suite with the exact expected count (92 passed, 1
skipped). The only real gap is a documentation/tracking-doc omission (ISSUES.md
checkboxes), not a code defect.

## Verification method

Read plan.md + all 5 phase-*.md files, then read every changed file's actual `git diff`
(chatbot.py, storage.py, booking.py, push.py, app.py, safety.py, reminder_worker.py,
tests/conftest.py) line-by-line against the phase specs — not the subagents' self-reports
(no implementation reports exist yet in `reports/`, only pre-implementation red-team plan
reviews). Ran `python3.10 -m pytest tests/ -v` and the full-module-graph import check.

## Test run results

```
92 passed, 1 skipped in 0.21s
```
Skip is `test_concurrent_booking_only_one_wins_real_postgres` (documented, no local
Postgres) — matches expectation exactly. Import check
(`python3.10 -c "import app, safety, storage, booking, chatbot, reminder_worker, triage,
push, calendar_ics"`) succeeds with no errors (only expected demo-key stdout warnings).

## Critical Findings

None. No trust-boundary defects, no data loss, no breaking changes to public contracts
beyond the explicitly-documented M8 admin-route rate limiting.

## Red-team-accepted requirement verification (read code, not claims)

1. **M10 lock reuse** — `chatbot.py:39-51` (`_new_session(reuse_lock=None)`),
   `get_session()` TTL-expiry branch (`chatbot.py:73-76`) and `reset_session()`
   (`chatbot.py:85-90`) both pass the old dict's `_lock` into `_new_session(reuse_lock=...)`.
   Confirmed correct, including a subtle correctness point not explicitly called out in
   the plan: in the `/reset` early-return branch inside `handle_message()`
   (`chatbot.py:135-141`), `reset_session(session_id)` is called *while the calling thread
   still holds* `sess["_lock"]` from the enclosing `with` block. Because `reuse_lock`
   passes the SAME Lock object through to the new dict, this does not deadlock (the same
   lock is already held once, not re-acquired) and the `with` statement's exit correctly
   releases that same object. `tests/test_chatbot_session_lock.py` exercises this with
   real `threading.Thread`s (`test_concurrent_handle_message_same_session_serialized`,
   `test_different_sessions_not_blocked_by_each_other`) — genuine, not phantom, tests.
2. **M1 guardrail position** — `chatbot.py:203-211`: confirmed AFTER the cancel-intent
   block (`chatbot.py:191-197`) AND AFTER the info-question block
   (`chatbot.py:199-206`), state preserved (`state=sess["state"]`), before state routing.
   `tests/test_chatbot_guardrail.py` includes the two red-team-mandated overlap tests
   (does not swallow cancel-intent / info-question).
3. **M6 atomicity** — `storage.py:244-258`: both `DuplicateCodeError` and `SlotTakenError`
   checks happen inside `with _JSON_LOCK:`, before `items.append`. `SlotTakenError` only
   fires when `appt.get("status") == "confirmed"`, matching the Postgres partial unique
   index semantics. `test_concurrent_same_slot_only_one_succeeds` in `tests/test_storage.py`
   uses a real `ThreadPoolExecutor` with 10 workers and asserts exactly 1 succeeds — genuine
   race test, not just a code-reading claim.
4. **M2 add_token locking** — `storage.py:339-347`: `add_token` is now wrapped in
   `_JSON_LOCK`, confirmed via diff (was previously unlocked). `remove_token` also locked.
   `test_add_token_and_remove_token_thread_safe` exercises this concurrently.
5. **M5 fail-open ticket parsing** — `push.py:90-114`: the entire `json.loads` +
   ticket-iteration block is wrapped in its own inner `try/except Exception: pass`,
   nested inside the outer `try` that only catches `(urllib.error.URLError, OSError)` for
   the network call itself. `sent`/`failed` are pre-computed optimistically before the
   inner try, so a parse failure leaves them at the "assume success" values.
   `test_send_push_survives_malformed_ticket_response` monkeypatches `urlopen` to return
   non-JSON bytes and asserts no exception + `sent==1, failed==0` — genuine test of the
   exact critical finding.
6. **M7 isinstance short-circuit** — `app.py:66`:
   `if client_sid and (not isinstance(client_sid, str) or not _SID_RE.match(client_sid)):`
   — `isinstance` check is evaluated before `.match()` due to `or` short-circuit, exactly
   as specified; not inverted. `test_resolve_sid_rejects_non_string_session` covers both
   `int` and `list` inputs and asserts `200` (not `500`).
7. **M8 admin coverage** — `app.py:106-112`: `_rate_limit_guard()` gates on
   `request.path.startswith("/api/")` with no admin-specific exemption;
   `test_rate_limit_applies_to_admin_routes` confirms `/api/admin/meta` gets 429'd once
   over threshold. `tests/test_app_admin.py` (pre-existing) and `tests/test_app_ics.py`
   (pre-existing) both still pass thanks to the new `tests/conftest.py` autouse fixture
   clearing `_RATE_BUCKETS` per test.
8. **M9 audit lock** — `safety.py:165-172`: `_rotate_audit_log_if_needed()` call and the
   `open(...).write(...)` are both inside `with _AUDIT_LOCK:`. Outer `except Exception:`
   (not just `OSError`) wraps the whole block, matching spec.

## booking.py except-clause ordering (M6 wiring)

`booking.py:181-198`: `except storage.SlotTakenError` and `except storage.DuplicateCodeError`
are both declared BEFORE the pre-existing `except Exception as exc:` block, which is
otherwise untouched (psycopg UniqueViolation handling preserved verbatim, just pushed
down). Correct Python except-ordering; the new custom exceptions will never fall through
to the generic handler.

## Scope check

- No M4 (connection pooling / `WHERE` clause) changes found anywhere in the diff —
  correctly deferred per user decision.
- No L2 (phone-number existence verification) changes found — correctly rejected per user
  decision.
- L1 (constant-time admin key comparison) correctly identified as already fixed by a
  prior round (H6) — `app.py:129` already uses `hmac.compare_digest`; only the ISSUES.md
  note was added, no redundant code touch.
- `git diff --stat` shows exactly the 5 phases' declared file ownership (chatbot.py;
  storage.py/booking.py/push.py; app.py; safety.py; reminder_worker.py) plus their
  matching test files — no cross-phase file collisions, no unrelated files touched.

## Warnings (non-blocking, but should be addressed before considering this round "done")

1. **ISSUES.md not updated per plan.md's own Acceptance Criteria** (Medium — process gap,
   not a code defect). `plan.md` explicitly requires: "ISSUES.md: đánh dấu `[x]` cho
   M1,M2,M3,M5,M6,M7,M8,M9,L1,L3... M4/L2 đánh dấu `[x]` kèm ghi chú." The actual
   `git diff ISSUES.md` only checks off L1 (which was already fixed by a prior round, not
   this one). The Medium section (`ISSUES.md:117-126`) and the L3 line
   (`ISSUES.md:136`) remain `[ ]` unchecked despite all 9 Medium + L3 fixes being
   correctly implemented and tested. Root cause: no phase file's "Related Code Files"
   listed `ISSUES.md`, so no subagent had ownership of this cross-cutting bookkeeping
   task (see saved memory `plan-level-acceptance-criteria-orphaned`). **Action:** update
   `ISSUES.md` checkboxes for M1,M2,M3,M5,M6,M7,M8,M9,L3 (and add the M4/L2 "closed, no
   code" notes) before marking this plan complete.
2. **Tracked data files polluted by test/import runs** (Low). `git status` shows
   `audit_log.jsonl` and `outbox/push_outbox.jsonl` as modified — diffing them shows dozens
   of new lines from running the test suite / import checks against the real (non-tmp)
   `AUDIT_LOG_PATH`/outbox paths, not from the source-code changes themselves. This is
   pre-existing repo hygiene debt (these generated files are tracked in git at all), not
   introduced by this round's logic, but if committed alongside this round it adds noise
   unrelated to the fix. Recommend `git checkout -- audit_log.jsonl outbox/push_outbox.jsonl`
   before committing, and separately consider `.gitignore`-ing these generated artifacts
   (out of scope for this round, flagging for awareness only).

## Suggestions (informational)

- None beyond the two warnings above — the implementation is unusually faithful to a
  detailed, red-team-amended spec; I found no deviations in the 6 code files reviewed.

## Unresolved Questions

- None. All 8 red-team-accepted critical/high requirements verified against actual code
  (not self-reports), all explicitly-excluded scope items (M4, L2) confirmed absent, and
  L1's "already fixed" claim confirmed by reading `app.py:129`.

## Stop-and-ask-user gate

No side effects requiring a stop-and-ask-user gate. The one item that could be argued to
need lead attention before "done" sign-off is the ISSUES.md tracking gap (Warning #1) —
it's a documentation completeness issue, not a behavioral regression, but it means the
plan's own acceptance criteria are not yet 100% satisfied.
