# Red Team / Failure Mode Analysis — restructure-app-package plan

Role: Flow Tracer / Failure Mode Analyst. All findings verified against the current
repo state (post 3 prior fix rounds), not the plan's own earlier scout snapshot.

## Finding 1: `scripts/migrate_to_supabase.py` has hardcoded ROOT-relative data paths Phase 3 never audits — silent zero-record migration after the move, undetectable by Phase 3's own verify step

- **Severity:** Critical
- **Location:** Phase 3, section "Architecture" / "Implementation Steps" (migrate_to_supabase.py coverage)
- **Flaw:** `scripts/migrate_to_supabase.py` lines 24-25 define
  `APPTS = os.path.join(ROOT, "appointments.json")` and
  `TOKENS = os.path.join(ROOT, "device_tokens.json")`, where `ROOT` is the **repo root**
  (`os.path.dirname(os.path.dirname(os.path.abspath(__file__)))`). These are NOT import
  statements, so Phase 1's `os.path.dirname(__file__)`-based reasoning (which correctly
  covers `storage.py`/`safety.py`/`push.py`) does not apply, and Phase 3's Architecture
  section only discusses converting `import storage` → `from app import storage` for this
  file. It never mentions `APPTS`/`TOKENS`. After Phase 1's `git mv appointments.json
  device_tokens.json ... app/`, these two constants point at files that no longer exist at
  repo root.
- **Failure scenario:** Someone runs a real Supabase migration in production
  (`DATABASE_URL` set). `storage.USE_DB` is True, so `main()` proceeds past the early-exit
  check, hits `json.load(open(APPTS, ...)) if os.path.exists(APPTS) else []` — `os.path.exists`
  returns False since the file is now at `app/appointments.json`, not repo root — and the
  script silently treats this as "no local data to migrate," printing
  `✅ Đã nạp 0 lịch hẹn (bỏ qua 0 đã có).` — a message that reads as a normal, successful,
  idempotent no-op rather than an error. Real appointment/token data (currently 11
  appointments, non-trivial token entries — verified via `wc -l`/`json.load` on the actual
  files) is silently never migrated. There is no exception, no non-zero exit code, nothing
  to catch in review.
- **Evidence:** `scripts/migrate_to_supabase.py:19-25` (`ROOT`, `sys.path.insert`, `import
  storage`, `APPTS = os.path.join(ROOT, "appointments.json")`, `TOKENS = os.path.join(ROOT,
  "device_tokens.json")`), used at lines 61 and 74 inside `main()`, gated by an early
  `if not storage.USE_DB: sys.exit(1)` at line ~29-31. Phase 3's Architecture section
  (phase-03, lines 55-58) says only "chỉ thấy `import storage` qua grep ban đầu ... áp dụng
  cùng nguyên tắc: `import storage` → `from app import storage`" — no mention of `APPTS`/
  `TOKENS`. Phase 3's own verify step (phase-03 lines 78-80, 98-100) explicitly accepts
  "verify giới hạn (import + syntax) nếu môi trường dev không có Postgres" — and this repo
  environment has no `DATABASE_URL`, meaning the one code path where the bug lives
  (`storage.USE_DB == True` branch) is structurally never exercised by Phase 3's prescribed
  verification, so the bug would ship undetected through this plan's own gate.
- **Suggested fix:** Add an explicit line item to Phase 3's Architecture/checklist for
  `scripts/migrate_to_supabase.py` calling out `APPTS`/`TOKENS` as path constants that must
  change from `os.path.join(ROOT, ...)` to `os.path.join(ROOT, "app", ...)` (or better,
  reuse `storage.APPOINTMENTS_PATH`/`storage.TOKENS_PATH` directly instead of
  re-deriving paths). Require an explicit smoke test (e.g., temporarily point
  `DATABASE_URL` at a throwaway local/test Postgres, or monkeypatch `storage.USE_DB=True`
  in a manual REPL check) that actually reaches the `json.load(open(APPTS...))` line and
  confirms a non-zero record count before considering this file done.

## Finding 2: Phase 1's own Success-Criteria grep for leftover bare imports only matches `^import`, not `^from X import Y` — blind to the exact lazy-import risk the phase calls out as its top risk

- **Severity:** Critical
- **Location:** Phase 1, section "Success Criteria" (verification grep) vs. "Risk Assessment"
- **Flaw:** Phase 1's Success Criteria (phase-01, line 159) gives this as the authoritative
  self-check: `grep -rn "^import \(booking\|chatbot\|safety\|storage\|triage\|push\|
  calendar_ics\|data\|app\|reminder_worker\)\b" app/*.py` must return nothing. This regex
  only matches lines starting with `^import `. But several of the exact cross-module
  imports Phase 1 itself must convert are `from X import Y` style, not `import X`:
  `booking.py:16` (`from data import DOCTORS, DEPARTMENTS, WORK_SLOTS,
  generate_available_slots`), `safety.py:17` (`from triage import _normalize,
  _strip_accents, _contains_word`), `triage.py:20` (`from data import DEPARTMENTS`), and 4
  lazy `from data import ...` occurrences inside `chatbot.py` (lines 309, 335, 350, 448).
  None of these would be caught if left un-converted, because the verification grep never
  looks for `^from`.
- **Failure scenario:** If the implementer misses converting one `from data import
  DEPARTMENTS` line inside `chatbot.py` (a real risk the plan's own Risk Assessment names as
  "rủi ro lớn nhất" for exactly this file, since these are lazy imports scattered inside
  functions, not surfaced by `import app.app`), Phase 1's Success Criteria will report a
  clean pass (empty grep output) even though the bug is present. The failure only manifests
  later, at runtime, when a request routes into the specific chatbot branch containing the
  unconverted `from data import ...` — i.e., exactly the failure mode the phase's Risk
  Assessment describes ("có thể sống sót qua bước verify 4 mà vẫn lỗi khi test suite (Phase
  2) chạy tới nhánh cụ thể đó"), except now the plan's own designated safety net for that
  exact risk doesn't work either.
- **Evidence:** phase-01-package-skeleton-and-core-move.md:159 (grep pattern, `^import`
  only) vs. phase-01 Architecture section listing `from data import ...` / `from triage
  import ...` conversions at lines 72-73, 85-87, 96-98, 106. Contrast with Phase 2's grep
  (phase-02, line 81) which correctly includes both `^import ... \|^from ... import` — the
  asymmetry between Phase 1's and Phase 2's grep patterns confirms Phase 1's is an
  incomplete copy, not an intentional narrower scope.
- **Suggested fix:** Fix the Phase 1 verification grep to also match `^from
  \(booking\|chatbot\|...\) import`, mirroring Phase 2's pattern, before relying on it as a
  pass/fail gate.

## Finding 3: Phase 2's Architecture only documents the aliased `import app as app_module` → `from app import app as app_module` transform; two test files use the bare, unaliased form with in-body references that break under a naive apply of that same pattern

- **Severity:** High
- **Location:** Phase 2, section "Architecture" (conftest.py callout) vs. "Related Code Files"
- **Flaw:** `tests/test_app_admin.py:3` and `tests/test_app_hardening.py:5` both do bare
  `import app` (no alias) and then reference the Flask submodule and its globals directly as
  `app.app.config[...]`, `app.ADMIN_KEY`, `app._default_key_warnings(...)` throughout the
  file body (verified via grep: `test_app_admin.py` lines 7-8, 13, 21, 39, 44;
  `test_app_hardening.py` lines 9-10, 15, 108, 114). Phase 2's Architecture section singles
  out `conftest.py`'s `import app as app_module` → `from app import app as app_module` case
  as "chỗ QUAN TRỌNG NHẤT" and gives a worked example, but never mentions that
  `test_app_admin.py`/`test_app_hardening.py` use a *different* idiom (bare `app`, not
  `app_module`) that needs a *different* replacement: `from app import app` (no alias,
  keeping the local name `app`), not `from app import app as app_module`.
- **Failure scenario:** An implementer pattern-matching off the plan's single worked example
  could either (a) leave `import app` untouched in these two files (since it doesn't
  literally look like `import app as app_module`, it's easy to miss as "already fine"),
  causing `app.app.config[...]` and `app.ADMIN_KEY` to raise `AttributeError`/fail once
  `app/__init__.py` is empty and nothing else in that test file's own import graph has
  forced `app.app` to be registered as a package attribute yet, or (b) mechanically apply
  the shown pattern and rename the import target to `app_module`, silently breaking every
  other line in the file that still says bare `app.` (NameError, since `app` is now
  undefined in that module's namespace). Either way, this is exactly the two files the
  plan's own "checklist, don't improvise" methodology is supposed to prevent errors in, but
  the checklist itself doesn't distinguish the two call patterns.
- **Evidence:** phase-02-update-test-suite-imports.md:56-62 (conftest.py-only worked
  example) vs. `tests/test_app_admin.py:3,7,8,13,21,39,44` and
  `tests/test_app_hardening.py:5,9,10,15,108,114` (bare `app.` usage, grep-verified).
- **Suggested fix:** Add an explicit line item for `test_app_admin.py` and
  `test_app_hardening.py` distinguishing `from app import app` (bare name preserved) from
  `from app import app as app_module` (conftest.py, `test_app_ics.py`), and require a
  diff review confirming the local name used in the import statement matches every
  subsequent reference in that same file.

## Finding 4: Phase 4's grep-based "what to touch" checklist doesn't include the 4 data-file names, so README.md's documentation of `appointments.json`/`audit_log.jsonl` locations goes stale despite being exactly the files Phase 1 calls out as the plan's #1 named risk

- **Severity:** Medium
- **Location:** Phase 4, section "Implementation Steps" step 1 (the grep command used as the
  authoritative checklist)
- **Flaw:** Phase 4's mandated grep (phase-04, lines 61-63) is:
  `grep -rln "app\.py\|booking\.py\|chatbot\.py\|storage\.py\|safety\.py\|triage\.py\|
  data\.py\|push\.py\|reminder_worker\.py\|calendar_ics\.py\|gunicorn app:app\|python
  app\.py" README.md setup.sh docs/*.md .env.example`. This pattern only matches `.py`
  filenames and two specific run commands — it does not include `appointments.json`,
  `device_tokens.json`, `audit_log.jsonl`, or `outbox/`. `README.md` has a section titled
  "## File sinh ra khi chạy" (lines 94-97) stating `appointments.json — lịch hẹn đã đặt.`
  and `audit_log.jsonl — nhật ký hội thoại...` with no path prefix, implying repo root.
  After Phase 1 moves these files into `app/`, this section becomes factually wrong, but
  Phase 4's own checklist mechanism (which the plan explicitly instructs to trust: "Dùng
  danh sách file trả về làm checklist CHÍNH XÁC — chỉ sửa những file thật sự có match,
  không sửa file không cần") will never flag README.md for this reason (it's flagged for
  other `.py`-name matches elsewhere in the file, so the file itself gets opened, but
  nothing in Phase 4's steps directs attention to this specific unmatched section, and the
  plan's Implementation Step 2 explicitly frames the read-through around the Architecture
  table's find-and-replace pairs, none of which cover JSON data paths).
- **Failure scenario:** A developer or ops engineer follows README.md's "File sinh ra khi
  chạy" section to locate `appointments.json` for backup/inspection/debugging after
  deployment, looks at repo root, finds nothing (it's actually at `app/appointments.json`),
  and either concludes data is missing/lost or wastes time investigating a phantom
  incident.
- **Evidence:** `README.md:94-97` (undocumented-by-plan data file paths) vs.
  phase-04-update-root-docs-and-entry-commands.md:61-63 (grep pattern that excludes these
  terms) and plan.md:43-49 (the plan's own stated top risk #2 is specifically about these 4
  data files silently losing their location relationship with code — yet Phase 4 doesn't
  carry that same risk-awareness into the docs-accuracy checklist).
- **Suggested fix:** Extend Phase 4's grep pattern to also include
  `appointments\.json|device_tokens\.json|audit_log\.jsonl|outbox/`, and add
  `docs/codebase-summary.md:63` (which lists all 4 data files together) to the explicit
  Related Code Files checklist rather than leaving it to the generic "sửa nếu grep xác
  nhận" catch-all, since the current grep won't surface it.

## Summary

| # | Severity | Phase | One-line |
|---|----------|-------|----------|
| 1 | Critical | 3 | `migrate_to_supabase.py`'s `APPTS`/`TOKENS` hardcoded ROOT paths unaddressed → silent zero-record production migration, undetectable by Phase 3's own verify step |
| 2 | Critical | 1 | Success-Criteria leftover-import grep only matches `^import`, not `^from X import Y`, blind to the exact lazy-import risk the phase names as its top concern |
| 3 | High | 2 | Bare `import app` + body `app.X` usage in `test_app_admin.py`/`test_app_hardening.py` not distinguished from conftest.py's aliased pattern — risk of NameError/AttributeError |
| 4 | Medium | 4 | Docs-checklist grep excludes data-file names, leaving README.md's data-file location section stale despite being the plan's own top-named risk category |
