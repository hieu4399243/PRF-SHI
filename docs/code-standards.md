# Code Standards & Conventions

## Module Boundary Rule

The single most important rule: **dependencies flow downward only**.

```
main.py (auth entry)
  ↓ ┌─────────────────┐
  ├→ chatbot/ (orchestration)
  ├→ admin_api.py (Blueprint, admin endpoints)
  ├→ doctor_api.py (Blueprint, doctor endpoints)
  │
  ├→ triage/, booking/, notify/ (business logic, import from core only)
  │
  └→ core/ (infrastructure — NO upward imports)
```

- **`core/`** (auth, storage, catalog, text, paths) has zero imports from any other app module
- **`triage/`, `booking/`, `notify/`** may only import from `core/`; never from each other
- **`admin_api.py`, `doctor_api.py`** are Blueprints at app level (alongside main.py); they import core + business modules
- **`chatbot/`** orchestrates business modules (triage, booking, notify)
- **`main.py`** sits at top; registers blueprints, handles login/logout routes, enforces `require_auth()` decorator

**Why:** Prevents circular dependencies; enables independent testing; makes public contracts explicit. Auth isolation in `core/` means login/token logic stays testable without the state machine.

---

## Naming Conventions

### Python Modules & Functions

| Category | Style | Example |
|----------|-------|---------|
| **Module** | `snake_case.py` | `chatbot_router.py`, `triage_engine.py` |
| **Function** | `snake_case` | `classify_symptoms()`, `book_appointment()` |
| **Class** | `PascalCase` | `DuplicateCodeError`, `SlotTakenError` (exceptions — the codebase is otherwise functional, not class-based) |
| **Constant** | `UPPER_SNAKE_CASE` | `DEPARTMENTS`, `DOCTORS`, `LLM_TIMEOUT` |
| **Private function** | `_snake_case` | `_confirmed_at()`, `_insert_with_race_guard()` |

### Environment Variables

| Purpose | Format | Example |
|---------|--------|---------|
| **Database** | `DATABASE_URL` | `postgresql://...` |
| **API credentials** | `*_API_KEY` | `OPENROUTER_API_KEY` |
| **Configuration** | `UPPER_SNAKE_CASE` | `LLM_MODEL`, `LLM_TIMEOUT`, `SECRET_KEY` |

### Data Fields

Match the existing JSON/database schema:

| Domain | Fields | Case |
|--------|--------|------|
| **User** | `id`, `username`, `password_hash`, `role`, `email`, `doctor_id`, `created_at`, `updated_at` | `snake_case` |
| **Appointment** | `id`, `doctor_id`, `date`, `time`, `patient_name`, `phone` | `snake_case` |
| **Service/Department** | `id`, `name`, `description` | `snake_case` |
| **Triage result** | `services`, `confidence` | `snake_case` |
| **JWT token** | `sub` (user_id), `username`, `role`, `iat`, `exp` | `snake_case` |

---

## Vietnamese Language Handling

### Text Normalization

Always strip accents (diacritics) before **rule-based matching**:

```python
from app.core.text import strip_accents, normalize

# Input: "toi muon nieng rang" (no accents) or "tôi muốn niềng răng" (with)
symptom = strip_accents(normalize(user_input))
# Result: "toi muon nieng rang" → matches rule-based keyword
```

**When NOT to strip:** LLM input (send original Vietnamese for semantic understanding).

### Phone Normalization

```python
from app.chatbot.reply import normalize_phone

phone = normalize_phone("+84 9 1234 5678")
# Result: "0912345678" (Vietnamese format)
```

### Domain Terminology

Keep in Vietnamese where they're central to the business model:

- Service names: "Sâu răng", "Nội nha", "Nha chu", "Chỉnh nha" (not "Cavity", "Endodontics", ...)
- Guardrail messages: Vietnamese, with a tone that's professional yet conversational
- Audit log: Vietnamese text (but phone/email/ID redacted)

---

## Session & Concurrency

### Acquire Per-Session Lock

Every message handler must acquire the session lock:

```python
from app.chatbot.session import get_session

session = get_session(sid)
with session["_lock"]:
    # Mutate session state
    session["state"] = "TRIAGE"
    session["dept"] = "sâu răng"
```

**Why:** Prevents race conditions if two requests arrive for the same session.

### In-Memory vs. Persistent

- **In-memory:** Session dict (SESSIONS global), TTL 1 hour, max 2000 sessions
- **Fallback for multi-worker:** Needs Redis/DB (mark with `# TODO: scale to Redis`)

---

## Error Handling & Fallback

### LLM Call Never Throws

`triage/engine.py:classify_with_llm()` (backed by the low-level HTTP client in `triage/llm.py`) always returns `None` or a result, never raises:

```python
def classify_with_llm(symptom):
    try:
        # Call OpenRouter
        ...
        return result
    except (Timeout, JSONDecodeError, ValueError):
        # Silent fail, caller handles None
        return None
```

Caller decides: `None` → retry with v2, or inform user.

### Database Errors Propagate

Storage layer errors should propagate (not caught in `push.py` or `booking.py`):

```python
# booking/service.py
def book_appointment(...):
    try:
        storage.add_appointment(appt)
    except SlotTakenError:
        # Conflict; let caller handle (chatbot shows "slot taken")
        raise
```

### Audit Log Writes Are Best-Effort

If audit log write fails, do NOT fail the entire request:

```python
try:
    safety.audit(session_id, "user", user_msg)
except OSError:
    # Fallback outbox or silent; never crash
    pass
```

---

## Testing Patterns

### One Test File Per Module

- `app/triage/engine.py` → `tests/test_triage_engine.py`
- `app/booking/service.py` → `tests/test_booking_service.py`
- `app/chatbot/router.py` → `tests/test_chatbot_router.py`

### Fixtures & Mocking

Use pytest fixtures for shared setup:

```python
@pytest.fixture
def session():
    return create_test_session()

def test_triage_step(session):
    # session is already in TRIAGE state
    ...
```

Mock external calls (OpenRouter, Expo):

```python
def test_triage_llm_timeout(mocker):
    mocker.patch('app.triage.llm.call_openrouter', side_effect=Timeout)
    result = classify_symptoms("đau răng")
    assert result is not None  # v2 fallback worked
```

### Run All Tests

```bash
.venv/bin/pytest                 # all tests
.venv/bin/pytest tests/test_chatbot_router.py  # single file
.venv/bin/pytest -v --tb=short   # verbose output
```

---

## Storage Layer (`core/storage.py`)

`storage.py` is a module of functions (not a class) — the `USE_DB` flag, set from `DATABASE_URL`, switches every function between JSON-file and Postgres backends internally.

### Always Use the Module's Functions

Never open files or connect to DB directly:

```python
# Correct
from app.core import storage
storage.add_appointment(appt)
storage.list_appointments()

# Wrong
import json
with open("app/data/appointments.json") as f:
    ...
```

### Auto-Fallback to JSON

If `DATABASE_URL` is unset, `USE_DB` is `False` and every function reads/writes local JSON. No code changes needed to switch backends — only the env var.

### Schema Initialization

Always call `storage.init_schema()` on startup (idempotent) — creates Postgres tables when `USE_DB`, otherwise a no-op for JSON files.

---

## Python Style (PEP 8)

- **Line length:** 100 characters (soft limit; OK to exceed for URLs/strings)
- **Imports:** Group standard library, third-party, local; `import x` before `from x import y`
- **Docstrings:** Use """ triple quotes; first line is one-line summary
- **Type hints:** Encouraged but not required for demo project
- **f-strings:** Preferred over `%` or `.format()`

Example:

```python
def confidence_level(results: list) -> str:
    """
    Map triage match scores to a confidence label.

    Args:
        results: service matches from classify_symptoms()

    Returns:
        "high" | "medium" | "low"
    """
    if not results:
        return "low"
    return "high" if results[0]["confidence"] >= 0.8 else "medium"
```

---

## Commit Conventions

- **Format:** `type: brief description` (conventional commits, no AI references)
- **Types:** `feat:` (new feature), `fix:` (bug fix), `refactor:` (reorganize), `test:`, `docs:`, `chore:`

Examples:
- `feat: add negation detection in triage engine`
- `fix: prevent duplicate appointment reminders`
- `refactor: move text utilities to core/text.py`

---

## Configuration & Secrets

### `.env` File (Git-Ignored)

Sensitive values go in `.env` only:

```env
DATABASE_URL=postgresql://...
SECRET_KEY=<random-hex>  # Also used as JWT signing key
JWT_EXPIRATION_HOURS=24
SECURE_COOKIE=false  # Set true behind HTTPS
OPENROUTER_API_KEY=sk-or-v1-...
```

### Environment-Based Selection

Use env vars to select behavior without code changes:

```python
# Don't hardcode
if use_llm:
    ...

# Instead
import os
llm_enabled = os.getenv("LLM_ENABLED", "1") == "1"
if llm_enabled and os.getenv("OPENROUTER_API_KEY"):
    ...
```

### Default Values

Demo-safe defaults (app still works without secrets):

```python
SECRET_KEY = os.getenv("SECRET_KEY", "dev-key-change-in-prod")
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))
SECURE_COOKIE = os.getenv("SECURE_COOKIE", "false").lower() == "true"
LLM_ENABLED = os.getenv("LLM_ENABLED", "1") == "1"
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "8"))
```

**Production rule:** 
- Always set random `SECRET_KEY` (used for JWT signing + Flask session encryption)
- Set `SECURE_COOKIE=true` when deploying behind HTTPS

---

## Documentation in Code

### Docstrings

Use for public functions & classes:

```python
def mask_pii(text: str) -> str:
    """
    Mask personally identifiable information (phone, email, ID).
    
    Per Decree 13/2023, audit logs must redact PII.
    Regex patterns match Vietnamese phone numbers and email.
    
    Args:
        text: Chat message (Vietnamese)
    
    Returns:
        Same text with phone/email/ID replaced by [REDACTED]
    """
```

### Inline Comments

Use for non-obvious logic (not for obvious code):

```python
# Good
with session["_lock"]:
    # Prevent concurrent mutations of session state
    session["state"] = new_state

# Avoid
result = []  # Initialize empty list
```

### TODO Comments

Mark scale/production concerns with code location, not with phase/audit labels:

```python
# TODO: session in-memory dict needs Redis when scaling to 2+ workers
SESSIONS = OrderedDict()
```

---

## Related Documentation

- **[codebase-summary.md](./codebase-summary.md)** — module responsibilities & imports
- **[project-overview-pdr.md](./project-overview-pdr.md)** — design principles & requirements

