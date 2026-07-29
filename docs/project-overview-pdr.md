# SHI — Trợ lý Nha khoa (Dental Clinic Assistant) — Project Overview & PDR

## What is SHI?

**SHI** (Trợ lý Nha khoa) is an AI-powered Vietnamese-language chatbot for a single dental clinic. It helps patients describe dental symptoms → intelligently classifies them into the right service category (triage) → guides booking an appointment → sends appointment reminders via push notification and calendar integration.

This is a **demo project** (PRF-SHI school context) with an integrated AI evaluation system (Precision/Recall/F1 metrics comparing triage rules v1 vs v2).

---

## Problem & Target User

**Problem:**
- Dental clinics need an automated first-contact screening to route patients to the right service (cavity filling, endodontics, periodontology, orthodontics, etc.) without manual triage.
- Patients in Vietnam often struggle to describe symptoms accurately or miss appointments due to lack of reminders.

**Target Users:**
- **Primary:** Vietnamese dental clinic staff & patients
- **Secondary:** Clinic administrators (dashboard to view booked appointments, schedule, metadata)

---

## Core Product Requirements

| Requirement | Acceptance Criteria | Status |
|-------------|-------------------|--------|
| **Understand Vietnamese symptoms** | Bot interprets free-form Vietnamese text (with/without diacritics) to identify dental service category | ✓ Implemented: v1/v2 rule-based + LLM fallback |
| **Guide appointment booking** | Multi-step state machine: triage → dept confirmation → pick doctor → pick date/time → enter name/phone → confirm | ✓ Implemented: 9 states + flex flow |
| **Prevent scheduling conflicts** | Database enforces UNIQUE INDEX on (doctor_id, date, time); app-level atomic writes | ✓ Implemented: JSON + Postgres modes |
| **Safety guardrails** | Block diagnosis/prescription requests; detect emergencies (→ 115); audit all chats (PII-masked) per Decree 13/2023 | ✓ Implemented: `triage/safety.py` |
| **Appointment reminders** | Push notifications (Expo) + `.ics` calendar file (Google/Apple/Outlook) + Google Calendar quick-add link | ✓ Implemented: `notify/worker.py` + `calendar_ics.py` |
| **Mobile client** | React Native (Expo SDK 54) app; works offline for chat UI, syncs to backend via LAN IP | ✓ Implemented: `mobile/` Expo project |
| **Web demo** | Minimal web interface for testing without mobile app | ✓ Implemented: `templates/index.html` |
| **Admin panel** | View appointments, doctor schedule, clinic metadata; cancel bookings | ✓ Implemented: `/admin` + `/api/admin/*` |

---

## Success Metrics

### AI Quality
- **Accuracy:** triage engine correctly identifies service category
- **Precision/Recall:** measure false positives/negatives per service
- **Macro-F1:** weighted average across all 9 services

**Current baselines:** v1 ~85%, v2 ~90%, llm ~95% accuracy — see `eval/results.md` and the engine comparison table in **[system-architecture.md § Triage Engine](./system-architecture.md#triage-engine-three-versions)**.

### User Flow
- **Booking completion rate:** % of users who reach DONE state
- **Appointment show-up rate:** % of booked appointments kept
- **Re-engagement:** % of users returning for follow-up appointments

### System Reliability
- **Uptime:** target 99.5% (production)
- **Latency:** triage response < 500ms (excluding LLM), booking < 200ms
- **Data integrity:** zero appointment double-bookings

---

## Scope Boundaries

### In Scope (Demo/PRF)
- Single clinic (hardcoded 9 services, ~6–8 doctors)
- Vietnamese language natural language understanding
- Local or Supabase database
- Docker Compose for local development
- Evaluation dataset & metrics (eval/)

### Out of Scope (Production Future Work)
- Multi-clinic support (would require tenant isolation, different DB schemas)
- Multi-language (currently Vietnamese-only)
- Two-way Google Calendar sync (OAuth, complex reconciliation)
- Production authentication (currently static ADMIN_KEY)
- Advanced analytics/BI dashboards
- SMS/WhatsApp integration (currently Expo push only)

---

## Architecture at a Glance

- **Backend:** Flask (Python) + optional Postgres/Supabase
- **Frontend:** React Native (Expo) + minimal web demo (HTML/vanilla JS)
- **Communication:** REST JSON over HTTP (mobile app uses LAN IP; desktop uses localhost)
- **Storage:** Pluggable via `core/storage.py` — switches between file JSON (demo) and Postgres (production)
- **Session state:** In-memory dict with per-session lock (fine for single process; needs Redis for multi-worker)

---

## Key Design Principles

1. **Run out-of-the-box** — no mandatory API keys; rule-based v2 works without OpenRouter.
2. **Separate business logic from infrastructure** — `core/` abstraction allows swapping JSON ↔ Postgres without changing `booking/` or `notify/`.
3. **Medical safety first** — guardrails checked before every state transition.
4. **LLM as an upgrade, not a dependency** — LLM timeouts/failures silently fallback to rule-based v2.
5. **Database is source of truth** — no in-memory caching of appointment slots; always check DB at confirmation step.

---

## Non-Functional Requirements

| Attribute | Target | Notes |
|-----------|--------|-------|
| Availability | 99.5% uptime | production; dev may have downtime |
| Response time | < 500ms triage, < 200ms booking | excludes external LLM calls |
| Concurrency | 1 process (dev); 2+ workers @ production | session & slot management needs Redis/DB |
| Data retention | Audit log rotated at 5MB | per Decree 13/2023 |
| PII handling | Masked in audit log | phone/email/ID redacted before logging |
| Language support | Vietnamese (phonetic, diacritics) | handles underspecified text ("toi muon nieng rang") |

---

## Constraints

- **Backend:** Python 3.11+, Flask 3.0.3, gunicorn for production
- **Mobile:** iOS 13+, Android 8+ (Expo SDK 54 requirements)
- **Database:** Postgres 16 (or Supabase compatible pooler mode)
- **LLM:** OpenRouter API (optional; requires API key)
- **Deployment:** Docker Compose (local) or cloud VPS (production)
- **Network:** Mobile & backend must be on same Wi-Fi (LAN IP); desktop uses localhost

---

## Timeline & Phases

| Phase | Goal | Status |
|-------|------|--------|
| **Phase 1: Core chatbot** | Triage engine, state machine, safety guardrails | ✓ Complete |
| **Phase 2: Booking & reminders** | Appointment management, push notifications, .ics export | ✓ Complete |
| **Phase 3: Mobile app** | React Native frontend with Expo | ✓ Complete |
| **Phase 4: Evaluation & tuning** | AI metrics, dataset labeling, v1 vs v2 comparison | ✓ Complete |
| **Phase 5: Production readiness** | Postgres migration, auth hardening, CORS, HTTPS deployment | In progress (see `project-roadmap.md`) |

---

## Related Documentation

- **[system-architecture.md](./system-architecture.md)** — detailed component diagram, state machines, safety flowchart
- **[codebase-summary.md](./codebase-summary.md)** — directory-by-directory module responsibilities
- **[code-standards.md](./code-standards.md)** — naming, import rules, Python conventions
- **[deployment-guide.md](./deployment-guide.md)** — step-by-step local dev, Docker, mobile setup
- **[project-roadmap.md](./project-roadmap.md)** — production gaps and future directions

---

## Links to Key Files

- `README.md` — Setup & quick-start (Vietnamese), links into `docs/`
- `app/main.py` — Flask entry point
- `app/chatbot/router.py` — State machine orchestration
- `app/triage/engine.py` — Triage v1/v2/LLM engines
- `eval/evaluate.py` — AI evaluation metrics
- `mobile/` — React Native source

