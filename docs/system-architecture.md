# System Architecture

## High-Level Overview

SHI is a two-tier system: **Backend** (Flask) and **Frontend** (React Native + minimal web demo), communicating via REST JSON.

```
┌─────────────────────────────────────────────────────────────────┐
│                        Users                                    │
├──────────────────┬──────────────────────────────────────────────┤
│   Web/Desktop    │          Mobile (iOS/Android)                 │
│  (index.html)    │        (Expo, React Native)                   │
│  (localhost)     │        (LAN IP via config.js)                 │
└────────┬─────────┴──────────────────────────────────┬────────────┘
         │                                            │
         │   HTTP /api/* (JSON, session in body)    │
         ▼                                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Backend (Flask)                             │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ State Machine (chatbot/router.py)                        │  │
│  │ ├─ GREET → TRIAGE → CONFIRM_DEPT → PICK_DOCTOR         │  │
│  │ ├─ PICK_DATE → PICK_TIME → ASK_NAME → ASK_PHONE        │  │
│  │ ├─ CONFIRM_BOOKING → DONE                               │  │
│  │ └─ Cancel flow: CANCEL_ASK_PHONE → CANCEL_PICK → ...   │  │
│  └────────┬─────────────────────────────────────────────────┘  │
│           ▼                                                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Business Logic Modules                                   │  │
│  ├─ triage/engine.py (v1/v2/llm engines)                  │  │
│  ├─ booking/service.py (slot management)                  │  │
│  ├─ notify/push.py (Expo integration)                     │  │
│  ├─ triage/safety.py (guardrails + audit log)             │  │
│  └─ core/* (catalog, storage, text utilities)             │  │
│  └─────────────────┬──────────────────────────────────────┘  │
│                    ▼                                            │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Storage Layer (core/storage.py)                         │  │
│  │ ├─ JSON mode (app/data/*)                               │  │
│  │ └─ Postgres/Supabase mode (DATABASE_URL)                │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
         ▲                                            ▲
         │                        ┌──────────────────┘
         │                        │
    File JSON              Postgres 16
    (local)                (Supabase)

         ▲                                            ▲
         │                        ┌──────────────────┘
         └────────────────────────────────────────────
     External Services
     └─ Expo Push Service (push notifications)
     └─ OpenRouter (LLM, optional)
```

---

## State Machine

The chatbot follows a **finite state machine** with 10 states and two entry flows (standard booking + cancellation).

```mermaid
stateDiagram-v2
    [*] --> GREET
    
    GREET --> TRIAGE: describe symptoms
    TRIAGE --> CONFIRM_DEPT: classification done
    CONFIRM_DEPT --> PICK_DOCTOR: confirm service
    CONFIRM_DEPT --> TRIAGE: describe again
    
    PICK_DOCTOR --> PICK_DATE: choose doctor
    PICK_DATE --> PICK_TIME: choose date
    PICK_TIME --> ASK_NAME: choose time
    ASK_NAME --> ASK_PHONE: enter name
    ASK_PHONE --> CONFIRM_BOOKING: enter phone
    
    CONFIRM_BOOKING --> DONE: confirm appointment
    CONFIRM_BOOKING --> CANCEL_CONFIRM: slot conflict
    
    state "Cancellation Flow" as Cancel {
        CANCEL_ASK_PHONE --> CANCEL_PICK: enter phone
        CANCEL_PICK --> CANCEL_CONFIRM: select appointment
        CANCEL_CONFIRM --> [*]: cancel done
    }
    
    DONE --> [*]
    
    note right of GREET
        Guardrails run FIRST (all states):
        1. Reset command
        2. Emergency check (→ 115)
        3. Handoff request
        4. Cancel/stop intent
        5. Service info query
        6. Diagnosis block
    end note
```

**Key features:**

- **Flexible flow:** Users can ask for service info, backtrack, or add symptoms anytime (handled in `chatbot/flex.py`).
- **Guardrail override:** Safety checks run before state handlers (not after).
- **Conflict recovery:** If slot is taken, offer to cancel the old appointment and rebook.

---

## Safety Guardrails (Flowchart)

```mermaid
flowchart TD
    MSG["User Message"] --> AUDIT["🔐 Log (mask PII)"]
    AUDIT --> RESET{"Reset<br/>command?"}
    RESET -->|yes| GREET["▶ Reset session"]
    RESET -->|no| EMERG{"Emergency<br/>signs?"}
    EMERG -->|yes| E115["▶ Advise 115,<br/>stop advising"]
    EMERG -->|no| HANDOFF{"Request<br/>human?"}
    HANDOFF -->|yes| HO["▶ Escalate to staff"]
    HANDOFF -->|no| INTENT{"Cancel/stop<br/>intent?"}
    INTENT -->|yes| SPECIAL["▶ Handle special<br/>intent"]
    INTENT -->|no| DIAG{"Diagnosis<br/>request?"}
    DIAG -->|yes| DENY["▶ Deny diagnosis,<br/>offer booking"]
    DIAG -->|no| ROUTE["State handler<br/>(TRIAGE,<br/>PICK_DOCTOR, ...)"]
    
    GREET --> [*]
    E115 --> [*]
    HO --> [*]
    SPECIAL --> [*]
    DENY --> [*]
    ROUTE --> [*]
```

**Guardrail modules:**

- **Audit log:** `safety.audit()` in `triage/safety.py` — masks phone/email/ID, writes to `app/data/audit_log.jsonl` (rotated @ 5MB)
- **Emergency detection:** Pattern matching (e.g., "mặt sưng", "khó thở", "chảy máu") → advise 115
- **Diagnosis block:** Reject "tôi bị bệnh gì", "kê thuốc gì" → redirect to booking
- **PII protection:** Per Decree 13/2023 (Vietnam data protection law)

---

## Triage Engine (Three Versions)

The triage system has three interchangeable engines that all return the same format. This allows A/B testing and fallback.

### Version Comparison

| Aspect | v1 | v2 | llm |
|--------|----|----|-----|
| **Method** | Rule-based keywords (accent-aware) | Rule-based (accent-insensitive) | LLM (semantic) |
| **Accuracy** | ~85% | ~90% | ~95% |
| **Speed** | <10ms | <10ms | 200-500ms + API |
| **Dependency** | None | None | OpenRouter API |
| **Use case** | Reference/comparison | Demo/fallback | When API available |

### Engine Selection

```python
from app.triage.engine import default_version, classify_symptoms

# Auto-select based on OPENROUTER_API_KEY env var
engine = default_version()  # returns "llm" or "v2"

# Call uniform interface
result = classify_symptoms("đau răng ê buốt")
# result = {
#     "services": [
#         {"id": "filling", "name": "Trám răng", "confidence": 0.95},
#         {"id": "cleaning", "name": "Vệ sinh", "confidence": 0.40},
#     ],
#     "confidence": "high"
# }

confidence = confidence_level(result["services"])  # "high" | "medium" | "low"
```

### LLM Fallback Behavior

LLM call timeout, network error, or JSON parse failure → **silent fallback to v2**:

```python
# classify_symptoms() in engine.py
def classify_symptoms(symptom, engine=None):
    if engine is None:
        engine = default_version()
    
    if engine == "llm":
        result = classify_with_llm(symptom)  # Returns None if error
        if result is None:
            # Fallback to v2 silently
            return classify_with_v2(symptom)
        return result
    else:
        return classify_with_v2(symptom)
```

**Distinction:** `None` (unavailable) vs. `[]` (no match found).

---

## Slot Booking & Conflict Prevention

Appointments are stored with a 3-part key: `(doctor_id, date, time)`. Two slot conflict prevention strategies:

### JSON Mode (Local Development)

- Single process only; uses `_JSON_LOCK` (mutual exclusion)
- `booking/service.py` checks availability, writes atomically with `os.replace()`
- Fallback for multi-process: message appears on screen ("slot taken"); user can cancel old + rebook

### Postgres Mode (Production)

- Multiple workers safe
- Schema has `UNIQUE INDEX ux_appointments_doctor_slot` on `(doctor_id, date, time)`
- DB enforces uniqueness; `storage.SlotTakenError` caught by booking layer
- Transaction isolation (`prepare_threshold=None` for Supabase transaction pooler)

---

## Notification & Reminder Flow

```mermaid
sequenceDiagram
    participant User
    participant Chat as chatbot.py
    participant Book as booking.py
    participant Push as push.py
    participant Expo as Expo Push
    participant ICS as calendar_ics.py
    participant Worker as reminder_worker.py

    User->>Chat: Confirm appointment
    Chat->>Book: book_appointment()
    Book-->>Chat: appointment id
    Chat->>Push: send_push("Booked!")
    Push->>Expo: POST token + message
    Expo-->>Push: ✓
    Chat-->>User: Link .ics + Google Calendar
    
    Note over Worker: Background, 60s interval
    Worker->>Book: Query appointments in 1d, 1h
    Worker->>Push: send_push("Reminder 1d")
    Push->>Expo: POST
    Expo-->>Worker: ✓
    Worker->>Push: send_push("Reminder 1h")
    Push->>Expo: POST
    Expo-->>Worker: ✓
    
    Note over Push: No token → write to outbox
    Push-->>User: app/data/outbox/push_outbox.jsonl
```

**Three reminder channels:**

1. **Push notification** (Expo) — immediate on booking, + scheduled (1d, 1h before)
2. **`.ics` file** — `GET /api/ics/<code>`, add to device calendar (2 VALARM: 1d & 1h)
3. **Google Calendar link** — quick-add form URL

**Deduplication:** `reminders_sent` field ensures each reminder type sends exactly once.

---

## Storage Layer

`core/storage.py` abstracts persistence. One abstraction, two backends, switched by `DATABASE_URL`.

### Schema

**Appointments table:**
- `id` (uuid, PK)
- `doctor_id`, `date`, `time` (UNIQUE INDEX)
- `patient_name`, `phone`
- `service_id`, `created_at`, `status`
- `reminders_sent` (JSON: `{"1d": true, "1h": false}`)

**Device tokens table:**
- `id` (uuid, PK)
- `token` (Expo token)
- `session_id`, `created_at`

**Safety patterns table** (optional, loaded from DB if available):
- For extending guardrail rules without code deploy

Usage patterns and correct/incorrect access examples: **[code-standards.md § Storage Layer](./code-standards.md#storage-layer-corestoragepy)**.

---

## API Endpoints

| Endpoint | Method | Purpose | Auth |
|----------|--------|---------|------|
| `/` | GET | Web demo (index.html) | None |
| `/api/start` | POST | New session | Rate-limit |
| `/api/chat` | POST | Send message, get response | Rate-limit |
| `/api/register-push` | POST | Register Expo token | Rate-limit |
| `/api/ics/<code>` | GET | Download `.ics` file | Session ownership |
| `/admin` | GET | Admin panel HTML | None |
| `/api/admin/appointments` | GET | List appointments | `X-Admin-Key` |
| `/api/admin/schedule` | GET | Doctor working hours | `X-Admin-Key` |
| `/api/admin/meta` | GET | Clinic metadata | `X-Admin-Key` |
| `/api/admin/cancel` | POST | Cancel appointment | `X-Admin-Key` |

**Rate-limiting:** 30 requests per 60 seconds per IP (only `/api/*`).

**Session resolution:**
- **Web:** Flask cookie session (`session["sid"]`)
- **Mobile:** App sends `session` (uuid4-hex) in JSON body; parsed by `resolve_sid(app/main.py)`

---

## Deployment Modes

Three modes — local dev (Flask dev server), Docker Compose (gunicorn + Postgres, 3 services), production (cloud VPS) — differ only in storage backend (`DATABASE_URL`) and session store (in-memory dev vs Redis planned for prod). Full setup steps and the environment-variable reference: **[deployment-guide.md](./deployment-guide.md)**.

---

## Related Documentation

- **[codebase-summary.md](./codebase-summary.md)** — module responsibilities & structure
- **[code-standards.md](./code-standards.md)** — naming, patterns, conventions
- **[deployment-guide.md](./deployment-guide.md)** — setup instructions

