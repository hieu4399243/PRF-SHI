# Red Team Review: plans/260709-2230-fix-high-issues

Role: Assumption Destroyer / Scope Auditor. Verified plan claims against actual repo state
(booking.py, storage.py, tests/test_booking.py, push.py, reminder_worker.py, app.py,
tests/test_app_ics.py, chatbot.py, calendar_ics.py).

## Finding 1: Phase 1 undercounts monkeypatch sites needing signature update
- **Severity:** High
- **Location:** Phase 1, section "Implementation Steps (TDD)" step 2, bullet "CẬP NHẬT các
  chỗ `monkeypatch.setattr(booking, "_confirmed_at", lambda d, t: None)` (3 chỗ hiện tại)"
- **Flaw:** The plan claims there are "3 chỗ" (3 places) using the literal pattern
  `lambda d, t: None` that need to become `lambda doc, d, t: None`. Grep of the actual file
  shows this exact literal pattern occurs at exactly 2 locations (`tests/test_booking.py:226`
  and `:245`), not 3. Additionally, two OTHER call sites (`tests/test_booking.py:141` and
  `:167`) monkeypatch `_confirmed_at` with `confirmed_at_seq(None, winner)`, a factory whose
  inner closure is defined as `def _f(d, t): return next(it)` (lines 137-138 and 163-164) —
  this closure also hard-codes a 2-argument signature and is never mentioned anywhere in the
  plan text.
- **Failure scenario:** An implementer following the plan literally greps/edits only the
  quoted `lambda d, t: None` string (2 hits), believes the "3 chỗ" count is satisfied by
  fixing... 2, notices a mismatch, and may guess wrong about which third site to fix — or
  worse, never discovers the two `confirmed_at_seq` closures because the plan's search
  target is a different string entirely. After `booking._confirmed_at` becomes a 3-arg
  function, `test_book_appointment_race_condition_...` (whichever tests use
  `confirmed_at_seq`) will raise `TypeError: _f() takes 2 positional arguments but 3 were
  given` at the `_confirmed_at(doctor_id, date_str, time_str)` call inside
  `_insert_with_race_guard`, breaking previously-passing C2 race-condition tests — directly
  contradicting the plan's own Success Criteria ("test cũ đã cập nhật chữ ký + test mới").
- **Evidence:** `tests/test_booking.py:137-138,163-164` define `def _f(d, t): return
  next(it)`; `tests/test_booking.py:226,245` are the only 2 exact matches for
  `lambda d, t: None` (confirmed via `grep -c "lambda d, t: None" tests/test_booking.py` → `2`).
- **Suggested fix:** Change the instruction from "3 chỗ, tìm `lambda d, t: None`" to "grep
  `monkeypatch.setattr(booking, "_confirmed_at"` — 4 call sites total (141, 167, 226, 245);
  the 2 at 141/167 use a `confirmed_at_seq` factory whose inner `_f(d, t)` also needs a
  3rd parameter."

## Finding 2: DROP+CREATE combined into one `cur.execute()` call is never verified against real Postgres/psycopg3, and the plan's own Risk Assessment doesn't cover this failure mode
- **Severity:** High
- **Location:** Phase 1, section "Architecture", item 1 (`UNIQUE_SLOT_INDEX_SQL` SQL block)
- **Flaw:** The plan proposes replacing the single-statement `UNIQUE_SLOT_INDEX_SQL` string
  (currently one `CREATE UNIQUE INDEX` statement, `storage.py:92-94`) with a two-statement
  string (`DROP INDEX IF EXISTS ...; CREATE UNIQUE INDEX ...`), still executed via a single
  `cur.execute(UNIQUE_SLOT_INDEX_SQL)` call (`storage.py:111`) wrapped in the existing
  try/except. The project uses `psycopg[binary]==3.2.3` (`requirements.txt:4`), not
  psycopg2. psycopg3's default execute path is stricter about multi-statement strings than
  psycopg2 was, and the plan's own prior-phase Risk Assessment admits "Không có Postgres
  local để test thật" (no local Postgres to verify against) — `psycopg` isn't even
  importable in the default interpreter here (`python3 -c "import psycopg"` fails with
  ModuleNotFoundError). Nobody has actually executed this exact two-statement string against
  real Postgres.
- **Failure scenario:** If psycopg3 rejects (or silently mis-handles) the combined
  DROP+CREATE string, the try/except at `storage.py:107-125` swallows the exception and
  prints a warning — meaning the entire H1 DB-level fix silently never takes effect in
  production, while the plan's Success Criteria ("UNIQUE INDEX tên mới
  `ux_appointments_doctor_slot`... index cũ bị DROP nếu tồn tại") reports as satisfied purely
  because tests only assert on the SQL string content, never a live execution.
- **Evidence:** Phase 1 plan text: `"DROP INDEX IF EXISTS ux_appointments_slot;\nCREATE
  UNIQUE INDEX IF NOT EXISTS ux_appointments_doctor_slot..."` passed as one
  `UNIQUE_SLOT_INDEX_SQL` string; `storage.py:40-41` shows `import psycopg` (v3, not
  psycopg2); Phase 1's Risk Assessment section discusses only "rủi ro migrate" (duplicate
  data) and explicitly states no local Postgres was available to test with in the prior
  (dependency) plan.
- **Suggested fix:** Split into two separate `cur.execute()` calls (still inside the same
  try/except block) instead of relying on one multi-statement string, and add an explicit
  manual verification step against a real (even throwaway/Supabase free-tier) Postgres
  instance before marking Phase 1 done — the plan currently defers this risk entirely to
  "not testable," which is not equivalent to "safe."

## Finding 3: Combined DROP+CREATE creates a strictly-worse partial-failure state that the Risk Assessment doesn't address
- **Severity:** Medium
- **Location:** Phase 1, section "Risk Assessment", first bullet
- **Flaw:** The Risk Assessment argues DROP is safe ("không có ràng buộc dữ liệu bị vi phạm
  khi DROP") and that the new index is strictly tighter than the old one, concluding "An
  toàn để deploy." This only reasons about each statement in isolation. It does not address
  the compound case: DROP succeeds, then CREATE UNIQUE INDEX fails (e.g. genuine duplicate
  `(doctor_id,date,time)` rows already in production data — a case the plan itself
  acknowledges is possible, since it's the entire justification for wrapping CREATE in
  try/except in the first place). In that compound-failure case, the app is left with ZERO
  unique-slot protection at the DB layer — worse than the pre-fix state, which at minimum
  still had the coarser `(date,time)` index.
- **Failure scenario:** Production has one pre-existing "confirmed" duplicate under the new,
  tighter key (plausible, since duplicates were previously invisible/unconstrained across
  different doctors at the same date+time). Deploy runs `init_schema()`: DROP removes the old
  index immediately; CREATE then fails against the duplicate and is rolled back within the
  try/except. Net result: no unique constraint at all remains in the DB for the remainder of
  that process's lifetime (`_schema_ready` still flips true since only the inner try/except
  fails, not `init_schema()` itself) — silent full regression of the DB-level race protection
  that C2 built, discoverable only by reading the printed warning log line.
- **Evidence:** `storage.py:102-125` (`init_schema`) — `_schema_ready` is set to `True`
  regardless of whether the inner try/except succeeds; the outer function has no
  distinction between "index create failed because data already valid under old key" vs
  "index create failed because DROP already ran and left a gap."
- **Suggested fix:** Either (a) do not DROP the old index until the new one is confirmed
  created (create new index first, drop old one only after success), or (b) explicitly call
  out in the plan/runbook that this migration must be preceded by a duplicate-data audit
  query on production before deploy.

## Finding 4: Phase 4 leaves a stale, contradictory security comment in `app.py`
- **Severity:** Medium
- **Location:** Phase 4, section "Architecture" (new `_check_admin`) — omission relative to
  `app.py:100-102`
- **Flaw:** The plan's new `_check_admin()` only accepts `X-Admin-Key` header, and the plan's
  docstring/comment for the new function says exactly that. But the plan never mentions
  updating the SECTION comment immediately above `_check_admin` in `app.py`
  ("Bảo vệ bằng khóa ADMIN_KEY (header 'X-Admin-Key' hoặc query '?key=')" —
  `app.py:100-101`), which explicitly documents `?key=` as a still-valid auth method. This is
  the exact comment a future maintainer or security auditor reads first when scanning the
  admin section.
- **Failure scenario:** A future contributor reads the un-updated section banner comment,
  believes `?key=` is still a supported (if deprecated) admin auth path, and either
  reintroduces it or writes documentation/tests assuming it works — reintroducing H6.
- **Evidence:** `app.py:100-102` (current, unmodified by this plan's file list):
  `"# Bảo vệ bằng khóa ADMIN_KEY (header 'X-Admin-Key' hoặc query '?key='). Đây là"`. Phase 4
  "Related Code Files" only lists `_check_admin` and the startup-warning insertion point —
  no mention of this banner comment.
- **Suggested fix:** Add updating the `app.py:100-102` comment block to Phase 4's
  Implementation Steps explicitly (remove "hoặc query '?key='").

## Finding 5: Phase 4's chosen test technique (`importlib.reload(app)`) mutates process-global module state shared with `tests/test_app_ics.py`, beyond the single "duplicate endpoint" risk the plan calls out
- **Severity:** Medium
- **Location:** Phase 4, "Implementation Steps (TDD)" step 1, bullet
  `test_startup_warns_on_default_keys`, and "Risk Assessment" second bullet
- **Flaw:** `app.py`'s `ADMIN_KEY` and `app.secret_key` are process-lifetime module globals
  (assigned once at import, `app.py:23,26`), consumed by `_check_admin()` and other
  `/api/admin/*` routes. The plan's chosen test approach monkeypatches `os.environ` to strip
  `SECRET_KEY`/`ADMIN_KEY`, then calls `importlib.reload(app)` to re-run module-level code
  and observe the warning prints. `importlib.reload` re-executes `app.py` top-to-bottom in
  place, permanently rebinding the module's globals (including a brand-new `Flask(__name__)`
  instance) for the remainder of the pytest process — not just for the duration of the test.
  `tests/test_app_ics.py:19` also does `import app as app_module` and fetches
  `app_module.app.test_client()` fresh inside each test (`test_app_ics.py:62,76,89`), so it
  will silently pick up whatever `app` object the last reload left behind, not the one that
  existed when its own module was first imported. The plan's Risk Assessment only discusses
  the "View function mapping is overwriting an existing endpoint" symptom and a fallback
  (extract a pure `_warn_if_default_keys` helper) — it does not identify or guard against the
  broader cross-test-file global-state leak this reload technique causes for the rest of the
  pytest session.
- **Failure scenario:** If test execution order runs `test_app_admin.py`'s reload test before
  `test_app_ics.py`, and any environment in that CI/dev run does set a non-default
  `ADMIN_KEY`/`SECRET_KEY` via `os.environ` at the process level (e.g. a shared `.env` loaded
  once by `python-dotenv` before pytest starts), the reload test's `monkeypatch.delenv(...)`
  causes the reloaded `app` module to fall back to the demo defaults for the rest of the test
  session — even after `monkeypatch` auto-undoes the env change — because the reload already
  captured the stripped-env values into plain module-level string globals that are never
  re-evaluated. Any later test in `test_app_ics.py` (or elsewhere) that implicitly depends on
  a real `ADMIN_KEY` value would then silently run against the demo key instead.
- **Evidence:** `app.py:23,26` (`app.secret_key = ...`, `ADMIN_KEY = ...`, module-level,
  evaluated once at import); `tests/test_app_ics.py:19,62,76,89` (imports `app` module and
  fetches `app_module.app` fresh per test, so it directly observes reload side effects);
  Phase 4 plan's Risk Assessment paragraph only names the endpoint-collision risk and its
  fallback, not the module-global leak risk.
- **Suggested fix:** Use the fallback the plan already describes as an option — extract
  `_warn_if_default_keys(secret_key, admin_key) -> list[str]` as a pure function and unit
  test it directly with fixture arguments — as the PRIMARY approach, not a conditional
  fallback triggered only "nếu gặp lỗi khi implement." This avoids `importlib.reload`
  entirely and removes the cross-file pollution risk.

---

## Summary Table

| # | Title | Severity | Phase |
|---|-------|----------|-------|
| 1 | "3 chỗ" lambda-signature claim undercounts real call sites (misses `confirmed_at_seq` closures) | High | 1 |
| 2 | DROP+CREATE combined into one untested multi-statement `execute()` call on psycopg3 | High | 1 |
| 3 | Combined DROP+CREATE can leave prod with zero unique-slot protection on partial failure | Medium | 1 |
| 4 | Stale `?key=` doc comment left in `app.py` contradicts new `_check_admin` behavior | Medium | 4 |
| 5 | `importlib.reload(app)` test technique leaks process-global state across test files | Medium | 4 |
