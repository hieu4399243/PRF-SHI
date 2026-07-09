# Parallel Codebase Audit — Trợ lý Nha khoa SHI

Date: 2026-07-09 · Branch: main · Method: 5 parallel `code-reviewer` agents (auth · data-integrity · safety · conversation-state · worker). Top items re-verified against source by controller.

Severity: 🔴 Critical (block prod) · 🟠 High · 🟡 Medium · 🟢 Low. Status: CONFIRMED = code read; PLAUSIBLE = inferred/env-dependent.

## 🔴 Critical

| # | Finding | File:line | Status | Failure scenario |
|---|---------|-----------|--------|------------------|
| C1 | Emergency & diagnosis detection accent-SENSITIVE while triage accent-INSENSITIVE | `safety.py:111-114`, `:117-120` | CONFIRMED | No-accent "kho tho nang"/"co giat"/"dot quy" → `check_emergency`=False → no 115 advice. Life-safety. |
| C2 | Double-booking TOCTOU, no DB unique constraint/txn | `booking.py:126` → `storage.py:160`; schema `storage.py:44-59` (only `code` PK) | CONFIRMED | Two concurrent confirms same slot → two `confirmed` appts. |
| C3 | `SESSIONS` unbounded + client-controlled keys → memory DoS | `chatbot.py:16`, `app.py:34` | CONFIRMED | Unauth loop `/api/start` w/ random `session` → OOM. No TTL/cap/rate-limit. |
| C4 | Unauthenticated `/api/ics/<code>` IDOR → health PII leak | `app.py:77-88`; code gen `booking.py:66-67` uses `random` not `secrets`, `SHI-`+6 | CONFIRMED | Predictable/enumerable code → downloads patient name + dental service (NĐ 13/2023 sensitive PII). Phone NOT in .ics. |
| C5 | `--watch` loop dies on any per-item exception | `reminder_worker.py:88` (no try/except); only `ValueError` caught `:79` | CONFIRMED | Malformed appt (missing field) → KeyError → all reminders stop for everyone. |

## 🟠 High

| # | Finding | File:line | Status |
|---|---------|-----------|--------|
| H1 | Slot conflict ignores `doctor_id` — whole clinic = 1 chair | `booking.py:98-105` (date+time only) | CONFIRMED (bug or spec — see Q3) |
| H2 | Reminder marked sent even when push fails → lost forever | `push.py:91-94` swallows err; `reminder_worker.py:65` marks unconditionally | CONFIRMED |
| H3 | `--test` mutates prod dedup → real reminders permanently suppressed | `reminder_worker.py:98` `scan_once(force=True)` writes `reminders_sent` | CONFIRMED |
| H4 | Naive local-time vs VN appt tz → UTC host fires ~7h off | `reminder_worker.py:72` `datetime.now()` naive | CONFIRMED (env-dependent) |
| H5 | `.ics` injection via unescaped `patient_name` (2 reviewers) | `calendar_ics.py:29,56-57`; `chatbot.py:362` keeps internal `\r\n` | CONFIRMED |
| H6 | Admin key accepted via `?key=` → leaks in logs/history/Referer | `app.py:97` | CONFIRMED |
| H7 | Default `SECRET_KEY`/`ADMIN_KEY` + `debug=True` on `0.0.0.0` | `app.py:23,26,160` | CONFIRMED (documented gap) |
| H8 | Patient name never redacted before audit log | `safety.py:45-57` (phone/email/CCCD only); `chatbot.py:79` logs ASK_NAME raw | CONFIRMED |
| H9 | In-memory sessions break under multi-worker/restart | `chatbot.py:16` | CONFIRMED (documented gap) |

## 🟡 Medium
- Diagnosis check only runs in TRIAGE state, unblocked elsewhere — `chatbot.py:177`.
- JSON backend read-modify-write races + non-atomic save (dev mode) — `storage.py:124-126,156-226`.
- No `MAX_CONTENT_LENGTH` → large-message CPU/disk DoS — `app.py:62`.
- Connection-per-call + full-table scans every booking (no WHERE) — `storage.py:39,132-139`; `booking._confirmed_at` etc.
- Expo `DeviceNotRegistered` tokens never pruned; HTTP-200 ticket errors ignored — `push.py:88-90` (no delete path in storage).
- Code collision uncaught → 500 (DB IntegrityError) / silent dup (JSON) — `booking.py:66`, `storage.py:160`.
- Client-supplied `session` takeover, mitigated by uuid4 entropy — `app.py:34`.
- No rate limiting on public endpoints.
- Audit log: no rotation, naive-tz timestamp, only catches `OSError` (TypeError on bad meta crashes turn) — `safety.py:137-150`.
- Session mutation not locked (threaded Flask) → torn state on overlapping turns — `chatbot.py`.

## 🟢 Low
- Non-constant-time admin key compare (`==`) — `app.py:98` (use `hmac.compare_digest`).
- Over-permissive phone: accepts well-formed non-existent numbers — `chatbot.py:601-611`.
- Past-due reminders skipped silently (wide windows self-heal) — `reminder_worker.py:88`.

## ✅ Verified non-issues
- Option-index/non-numeric picks: all string-matched, no IndexError — `chatbot.py:272,300,315,336,530`.
- Stale/unknown session id → fresh GREET, no crash.
- Guardrail fail-safe fallback works: empty/err DB → code seed, never empty — `safety.py:82-99`.
- Admin-cancel 404 message accurate — `booking.py:90-95`, `app.py:153`.
- `admin.html` embeds no secret; key typed by user, sent as `X-Admin-Key` header — `templates/admin.html:76,149`.

## Suggested fix order (highest value first)
1. C1 — reuse `triage._strip_accents`/`_normalize`/`_contains_word` in `check_emergency`+`is_diagnosis_request`; add bare-term patterns ("khó thở","sưng mặt","chảy máu nhiều"). Move diagnosis check to per-turn block (fixes Medium too).
2. H5 — escape RFC5545 values (`\ ; , \n`) + strip control chars from `patient_name` at `_ask_name`.
3. C5/H2/H3 — per-item try/except in worker loop; mark sent only on delivery success; make `--test` not persist dedup.
4. C4 — `secrets.token_urlsafe` as ICS download key or require session ownership; add rate limit.
5. H1 — add `doctor_id` to `_confirmed_at` match (confirm intent first).
6. C2 — unique partial index `WHERE status='confirmed'` on `(doctor_id,date,time)` + catch IntegrityError.
7. C3/H9 — cap+TTL/LRU on SESSIONS or move to Redis; stop unbounded creation from client-supplied id.
8. H4 — timezone-aware datetimes (Asia/Ho_Chi_Minh) in worker.
9. H8 — redact name on audited copy in ASK_NAME.
10. H6/H7 — header-only admin key, fail-closed on unset secrets, `debug=False` in prod.

## Unresolved questions
1. Prod topology — single Flask worker or gunicorn multi-worker? (decides if C3/H9 already break).
2. Is `DATABASE_URL` always set in prod? (makes JSON races dev-only).
3. Intended booking model — one slot per doctor, or one per clinic-wide time? (decides if H1 is bug or spec).
4. Is anything expected to consume `outbox/push_outbox.jsonl` (retry job)? If not, H2 has no recovery path.
