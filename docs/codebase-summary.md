# Codebase Summary — Module Breakdown

## Directory Structure

```
PRF-SHI/
├── app/                    Backend Flask application
├── mobile/                 React Native (Expo) frontend
├── eval/                   AI evaluation system
├── scripts/                Utility scripts
├── tests/                  Pytest test suite
├── README.md              Setup & quick-start (Vietnamese), links into docs/
├── requirements.txt       Python dependencies
├── docker-compose.yml     Local Postgres + gunicorn orchestration
└── Dockerfile             Container image
```

---

## Backend Module Breakdown (`app/`)

### Core Infrastructure (`app/core/`)

| Module | Responsibility | Key Functions/Classes |
|--------|-----------------|----------------------|
| **`catalog.py`** | Clinic data: 9 dental services, doctors, working hours | `DEPARTMENTS`, `DOCTORS`, `generate_available_slots()` |
| **`storage.py`** | Pluggable persistence layer (JSON ↔ Postgres), module-level functions (no class) | `init_schema()`, `add_appointment()`, `list_appointments()`, `add_token()` |
| **`text.py`** | Vietnamese text utilities: accent removal, normalization | `strip_accents()`, `normalize()` |
| **`paths.py`** | Data directory & audit log path declarations | `DATA_DIR`, `AUDIT_LOG_PATH` |

**Design rule:** `core/` has zero upward imports. All other modules depend on it; nothing depends upward.

---

### Chatbot State Machine (`app/chatbot/`)

Orchestrates multi-turn conversation flow and delegates to triage/booking/safety.

| Module | Responsibility | Key Functions |
|--------|-----------------|----------------|
| **`router.py`** | Central state dispatcher; guardrail execution | `handle_message()`, state → handler mapping |
| **`session.py`** | In-memory session store (SESSIONS dict); TTL + per-session lock | `new_session()`, `get_session()`, `reset_session()`, `_evict_if_full_locked()` |
| **`reply.py`** | Format bot responses; date formatting; phone normalization | `reply()`, `format_date()`, `normalize_phone()` |
| **`flex.py`** | "Flexible reply": detect backtrack, symptom change, info requests | `flex_intent()`, `maybe_new_symptom()`, `symptom_ack()` |
| **`steps/triage_step.py`** | TRIAGE & CONFIRM_DEPT states | Calls `triage.classify_symptoms()` |
| **`steps/doctor_step.py`** | PICK_DOCTOR state | Lists doctors for chosen service |
| **`steps/schedule_step.py`** | PICK_DATE & PICK_TIME states | Queries available slots |
| **`steps/confirm_step.py`** | ASK_NAME → ASK_PHONE → CONFIRM_BOOKING | Validates phone; calls `booking.book_appointment()` |
| **`steps/cancel_step.py`** | Cancellation flow: CANCEL_ASK_PHONE → CANCEL_PICK → CANCEL_CONFIRM | |

---

### Triage Engine (`app/triage/`)

Classifies patient symptoms into dental services. Three interchangeable engines sharing one output format.

| Module | Responsibility | Key Functions |
|--------|-----------------|----------------|
| **`engine.py`** | Main triage dispatcher; engine selection (v1/v2/llm); LLM call + fallback | `classify_symptoms()`, `confidence_level()`, `default_version()`, `classify_with_llm()` (returns `None` on error/timeout) |
| **`llm.py`** | Low-level OpenRouter HTTP client (used by `engine.classify_with_llm()`) | `chat()`, `chat_json()`, `is_enabled()` |
| **`nlu.py`** | Natural language understanding: match dates, times, doctor names, intent | `match_date()`, `match_time()`, `match_doctor()`, `wants_change()`, `is_affirmative()` |
| **`safety.py`** | Medical guardrails: PII masking, emergency detection, diagnosis block, audit log | `check_emergency()`, `mask_pii()`, `audit()` |

**Engine selection:**
- `OPENROUTER_API_KEY` env var → `llm` (semantic understanding)
- Otherwise → `v2` (rule-based, accent-insensitive)

**Fallback behavior:**
- LLM timeout/error → returns `None` → `classify_symptoms()` retries with v2
- Distinguishes `None` (unavailable) from `[]` (no match)

---

### Booking Service (`app/booking/`)

Manages appointment data and calendar export.

| Module | Responsibility | Key Functions |
|--------|-----------------|----------------|
| **`service.py`** | Book, cancel, lookup appointments; check slot availability | `book_appointment()`, `get_available_dates()`, `get_available_times()`, `cancel_appointment()` |
| **`calendar_ics.py`** | Generate `.ics` file with 2 VALARM reminders (1d, 1h before) | `build_ics()`, `google_calendar_link()` |

**Slot conflict prevention:**
- JSON mode: `_JSON_LOCK` (single-process atomic write)
- Postgres mode: `UNIQUE INDEX ux_appointments_doctor_slot` on (doctor_id, date, time)

---

### Notifications (`app/notify/`)

Sends appointment confirmations and reminders.

| Module | Responsibility | Key Functions |
|--------|-----------------|----------------|
| **`push.py`** | Expo Push Service integration; no-token fallback to outbox | `send_push()`, logs to `app/data/outbox/push_outbox.jsonl` if token missing |
| **`worker.py`** | Background reminder job: scan upcoming appointments, send 1-day & 1-hour reminders | `python -m app.notify.worker --watch` (60s polling), `--test`, `--once` (cron) |

**Delivery tracking:**
- `reminders_sent` field prevents duplicate reminders
- Outbox JSONL for testing without live Expo token

---

### API & Web (`app/main.py` & `app/templates/`)

| File | Responsibility |
|------|-----------------|
| **`main.py`** | Flask app entry; REST `/api/*` endpoints; rate-limit (30 req/60s IP); session resolution |
| **`templates/index.html`** | Web demo (fallback UI; mobile app is primary) |
| **`templates/admin.html`** | Admin panel: view appointments, schedule, metadata; cancel bookings |

**Session resolution:**
- Web: Flask cookie session
- Mobile: app sends `session` (uuid4-hex) in JSON body; resolved by `resolve_sid()`

---

### Data Storage (`app/data/`)

Runtime data files (generated, not committed):

```
app/data/
├── appointments.json       Booked appointments (JSON mode)
├── device_tokens.json      Expo push tokens (JSON mode)
├── audit_log.jsonl         Chat audit log (rotated @ 5MB, PII-masked)
└── outbox/
    └── push_outbox.jsonl   Failed push notifications
```

---

## Mobile App (`mobile/`)

React Native + Expo SDK 54.

| File/Dir | Purpose |
|----------|---------|
| **`src/config.js`** | Backend API URL (`API_BASE`); must be LAN IP for dev |
| **`src/api.js`** | HTTP client; calls `/api/start`, `/api/chat`, `/api/register-push` |
| **`src/calendar.js`** | Parses `.ics` file; integrates with device calendar |
| **`src/notify.js`** | Expo push notification handler |
| **`src/usePush.js`** | React hook: register device token on app startup |
| **`src/html.js`** | HTML rendering fallback (debug) |

**Network requirement:** Mobile & backend must share Wi-Fi (app uses LAN IP, not DNS).

---

## Evaluation System (`eval/`)

AI quality metrics for triage engine comparison.

| File | Purpose |
|------|---------|
| **`dataset.jsonl`** | Labeled test set: symptom → expected service |
| **`dataset_complex.jsonl`** | Edge cases: negation, metaphor, typos |
| **`dataset_negation.jsonl`** | Negation handling ("I don't have...") |
| **`dataset_heldout.jsonl`** | Held-out test set (not used in training) |
| **`evaluate.py`** | Runner: Accuracy, Precision, Recall, Macro-F1 for v1 vs v2 vs llm |
| **`results.md`** | Output table of metrics & analysis |

**Run:** `.venv/bin/python eval/evaluate.py --llm` (~63 API calls if LLM enabled).

---

## Utility Scripts (`scripts/`)

| Script | Purpose |
|--------|---------|
| **`migrate_to_supabase.py`** | Migrate JSON → Postgres/Supabase |
| **`clean_stale_appointments.py`** | Remove expired/invalid bookings |
| **`try_llm.py`** | Interactive LLM testing or suite of edge cases |

---

## Test Suite (`tests/`)

Pytest test files covering business logic & integration.

| Test File | Covers |
|-----------|--------|
| **`test_triage_*.py`** | Triage engines (v1, v2, LLM), negation, NLU |
| **`test_booking_*.py`** | Appointment creation, conflict detection, cancellation |
| **`test_chatbot_*.py`** | State machine, session locks, guardrails |
| **`test_safety_*.py`** | Emergency detection, PII masking, audit log |
| **`test_push_*.py`** | Expo push formatting, outbox fallback |
| **`test_storage_*.py`** | JSON & Postgres backends, schema initialization |
| **`test_app_*.py`** | Flask routes, rate-limit, admin auth |

**Run:** `.venv/bin/pytest`

---

## Import Dependency Map

```
┌─────────────────────┐
│   main.py (Flask)   │  top-level entry
└──────────┬──────────┘
           │
    ┌──────┴──────┐
    │             │
┌───▼──────┐  ┌──┴────────┐
│ chatbot/ │  │ templates │
└───┬──────┘  └───────────┘
    │
 ┌──┼──────────────┬──────────────┐
 │  │              │              │
┌┴──▼──┐  ┌───────▼──┐  ┌────────▼──┐  ┌────────────┐
│triage│  │ booking/ │  │ notify/   │  │ core/      │
└──────┘  └──────────┘  └───────────┘  │(no upward) │
                                        └────────────┘
```

**Core rule:** `core/` has no imports from other app modules; all others import from `core/`.

---

## Python Style Conventions

- **Naming:** `snake_case` for functions/variables, `PascalCase` for classes
- **Vietnamese strings:** UTF-8 encoded; domain-specific terms kept in Vietnamese (e.g., "sâu răng", "chỉnh nha")
- **Text normalization:** Always pass Vietnamese input through `text.remove_accents()` for rule-based matching
- **Error handling:** Explicit exceptions; LLM module never raises (returns `None`)
- **Session/state:** Always acquire per-session lock before mutation
- **Database:** Always use `core/storage.py` abstraction; never directly open files

---

## Related Documentation

- **[system-architecture.md](./system-architecture.md)** — visual diagrams & flow details
- **[code-standards.md](./code-standards.md)** — best practices & enforced patterns
- **[deployment-guide.md](./deployment-guide.md)** — how to run locally & in production

