# Project Roadmap — Production Gaps & Future Directions

## Current Status: Alpha (Demo/PRF Complete)

✅ Completed: Triage engine, state machine, booking, reminders, evaluation, mobile app, Docker Compose setup.

🚀 In Progress: Production hardening.

---

## Production Gaps (Must Resolve Before Live Deployment)

### 1. Webserver & Process Management

**Gap:** Currently uses Flask dev server (`debug=True`).

**Production requirement:** Gunicorn + uwsgi/gunicorn config.

| Issue | Impact | Solution | Effort |
|-------|--------|----------|--------|
| Debug mode on | Security risk; crashes on error | Set `debug=False`; run via gunicorn | 1 day |
| Single process | Can't handle concurrent load | Gunicorn 4+ workers | 1 day |
| No graceful reload | Deploy requires downtime | Gunicorn + systemd/supervisor | 2 days |

**Status:** Docker Compose already uses gunicorn for `web` service; local dev needs migration guide.

---

### 2. Session & Concurrency Model

**Gap:** Sessions stored in-memory dict (`SESSIONS`, limit 2000, TTL 1h).

**Problem:** Doesn't scale beyond single process. Multi-worker gunicorn loses sessions.

| Issue | Blocker? | Solution | Timeline |
|-------|----------|----------|----------|
| In-memory SESSIONS | YES (multi-worker) | Migrate to Redis or Postgres session store | 3–5 days |
| Per-session Lock | Partial | Reacquire from DB/Redis on session load | Included in migration |
| Rate-limit buckets | LOW (few users) | Move to Redis for distributed enforcement | Lower priority |

**Recommended approach:**
1. Add Redis to docker-compose.yml
2. Switch `SESSIONS` to Redis with same TTL/LRU semantics
3. Reacquire `threading.Lock` when loading session (not serializable)
4. Document in deployment guide

**Dependencies:** `redis` Python package

---

### 3. CORS Configuration

**Gap:** Not configured; likely fails if web frontend is on different origin.

**Solution:**

```python
# app/main.py
from flask_cors import CORS

app = Flask(__name__)
CORS(app, 
     origins=os.getenv("CORS_ORIGINS", "http://localhost:5001").split(","),
     supports_credentials=True)
```

Add to `.env.example`:
```env
CORS_ORIGINS=http://localhost:5001,https://api.example.com
```

**Effort:** 2 hours

---

### 4. API_BASE & HTTPS Deployment

**Gap:** Mobile app's `mobile/src/config.js` hardcoded to LAN IP:

```javascript
export const API_BASE = "http://192.168.0.254:5001";
```

**Problem:** Breaks on public internet (no HTTPS, static IP).

**Solution:**

1. **Dev/LAN:** Keep LAN IP; document in `mobile/README.md`
2. **Production:** Replace with HTTPS URL

```javascript
// mobile/src/config.js
const API_BASE = process.env.NODE_ENV === "production"
  ? "https://api.clinicname.com"
  : "http://192.168.0.254:5001";  // Use setup.sh to populate
export { API_BASE };
```

Or use EAS (Expo Application Services) environment variable system.

**Effort:** 1 day (requires SSL cert, DNS, reverse proxy)

---

### 5. Authentication & Admin Key

**Gap:** Admin key is a single static value (hardcoded fallback: `"admin"`).

**Problems:**
- No user management; no audit trail of who accessed what
- Static key easily leaked
- No role separation (all admins have same power)

**Production approach:**

| Phase | Method | Timeline |
|-------|--------|----------|
| **Interim** | Generate random key in `.env`; force HTTPS + header validation | 1 week |
| **Phase 2** | Add admin login table (bcrypt hash) | 2–3 weeks |
| **Phase 3** | RBAC: roles (clinic_owner, doctor, receptionist); audit log | 4 weeks |

**Recommended Phase 1 (quick):**

```python
# app/main.py
ADMIN_KEY = os.getenv("ADMIN_KEY")
if not ADMIN_KEY or ADMIN_KEY == "admin":
    raise ValueError("ADMIN_KEY must be set to a random value in production")

def check_admin_key():
    key = request.headers.get("X-Admin-Key")
    if key != ADMIN_KEY:
        abort(403)
    # Also check request.remote_addr for localhost allowance in dev
```

**Dependencies:** None (for Phase 1)

---

### 6. Database Robustness

**Gap:** Schema auto-creates on startup; no migration versioning.

**Issue:** Adding columns to schema requires manual migration for existing DBs.

**Solution:**

Use **Alembic** or simple versioning:

```python
# app/core/storage.py
SCHEMA_VERSION = 1

def init_schema():
    current = get_schema_version()
    if current < SCHEMA_VERSION:
        # Run migrations
        migrate_v1_to_v2()
        set_schema_version(SCHEMA_VERSION)
```

**Effort:** 2–3 days

---

### 7. Monitoring & Logging

**Gap:** No structured logging; audit log is JSONL only.

**Improvements:**

1. **Structured logs:** Use `python-json-logger` for stdout → ELK/CloudWatch
2. **Metrics:** Prometheus `/metrics` endpoint (request count, latency, errors)
3. **Tracing:** Optional: OpenTelemetry for distributed tracing
4. **Alerting:** PagerDuty/Slack for critical errors

**Timeline:** 3–5 days (non-blocking for MVP)

**Dependencies:** `python-json-logger`, optional: `prometheus-client`

---

### 8. Email & SMS Notifications (Future)

**Gap:** Currently only push + calendar reminders. No email/SMS fallback.

**Requirement:** Some patients may not have app or push enabled.

**Solution (Phase 2):**

| Channel | Provider | Timeline |
|---------|----------|----------|
| Email | SendGrid / AWS SES | 2 weeks |
| SMS | Twilio / Zalo API | 2 weeks |

Adds new methods to `notify/push.py`:

```python
send_email(patient_email, template, context)
send_sms(phone, template, context)
```

---

## Future Enhancements (Out of Scope for MVP)

### 1. LLM Prompt Tuning

**Current:** Hardcoded prompt in `triage/llm.py`

**Future:** 
- A/B test different prompts
- Fine-tune model for dental domain
- Collect feedback from clinic staff

**Timeline:** 3–4 weeks (after launch)

---

### 2. Two-Way Google Calendar Sync (OAuth)

**Current:** One-way (SHI writes `.ics` and quick-add link; no sync back).

**Gap:** If doctor cancels appointment in Google Calendar, SHI doesn't know.

**Solution:**

```python
# app/booking/google_cal.py
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials

def sync_canceled_appointment(event_id):
    # Listen for Google Calendar event deletion
    # Call booking.cancel_appointment() to sync
    pass
```

**Timeline:** 3 weeks (requires OAuth setup, event webhook)

**Complexity:** Medium (webhook handling, rate limits, error recovery)

---

### 3. Parallel LLM Calls in Evaluation

**Current:** `eval/evaluate.py` queries LLM sequentially (~63 calls → 10+ min runtime).

**Optimization:** 
```python
import asyncio
import httpx

async def eval_with_llm_parallel():
    async with httpx.AsyncClient() as client:
        tasks = [classify_with_llm_async(symptom) for symptom in dataset]
        results = await asyncio.gather(*tasks)
```

**Timeline:** 1 week (low priority; blocking only for CI)

**Impact:** Evaluation runtime 10 min → 2 min

---

### 4. Multi-Clinic Support

**Current:** Single clinic, hardcoded `DEPARTMENTS` & `DOCTORS`.

**Future:** Support multiple clinics sharing one backend.

**Architectural changes:**
- Add `clinic_id` to all tables
- Multi-tenant session isolation
- Separate admin dashboards per clinic
- Rate-limit by clinic, not by IP

**Timeline:** 4–6 weeks (major refactor)

**Complexity:** High (schema, data isolation, UX)

---

### 5. Advanced Analytics Dashboard

**Gap:** No analytics for clinic staff (e.g., "which service is most popular?", "what's our appointment show-up rate?").

**Features:**
- Appointment volume by service/doctor/date
- Average booking-to-appointment time
- Patient satisfaction survey
- Triage accuracy feedback loop

**Timeline:** 3–4 weeks

**Tech:** SQL aggregates + React/Grafana dashboard

---

## Prioritized Roadmap (Recommended)

| Priority | Gap/Feature | Effort | Blocker? | Target Date |
|----------|-------------|--------|----------|------------|
| **P0** | Redis session store | 3d | YES (scale) | Week 1–2 |
| **P0** | CORS setup | 2h | MAYBE | Week 1 |
| **P0** | HTTPS & API_BASE migration | 1d | YES (public) | Week 2 |
| **P0** | Secure ADMIN_KEY | 1d | YES (prod) | Week 1 |
| **P0** | Alembic migrations | 2d | Medium | Week 3 |
| **P1** | Structured logging | 3d | Medium | Week 3 |
| **P1** | Email notifications | 2w | Medium | Month 2 |
| **P2** | Two-way Google Calendar | 3w | Low | Month 3 |
| **P3** | Multi-clinic support | 4–6w | Low | Quarter 2 |

---

## Known Limitations (Won't Fix, Out of Scope)

1. **Single clinic only** — architectural limitation; multi-clinic needs rewrite
2. **Vietnamese language only** — NLU dataset/patterns not generalized
3. **No OAuth for clinic staff** — use ADMIN_KEY for now; upgrade if multi-user clinic
4. **No appointment modification** — can only cancel + rebook
5. **No recurring appointments** — each appointment is one-off booking

---

## Success Metrics for Each Phase

### Phase 1: Stability & Scale
- ✅ Multi-worker sessions via Redis (no session loss)
- ✅ 99.5% uptime over 1 week
- ✅ Handle 100 concurrent users
- ✅ HTTPS enabled & API_BASE updated

### Phase 2: Features & Polish
- ✅ Email reminders working (90%+ delivery)
- ✅ Admin login (audit trail of 10+ actions/day)
- ✅ Structured logging (all errors visible in ELK)

### Phase 3: Growth & Insights
- ✅ Two-way Google Calendar (0 missed syncs)
- ✅ Analytics dashboard (clinic staff can see trends)
- ✅ 2+ clinics onboarded

---

## Related Documentation

- **[project-overview-pdr.md](./project-overview-pdr.md)** — requirements & scope
- **[system-architecture.md](./system-architecture.md)** — current design
- **[deployment-guide.md](./deployment-guide.md)** — how to deploy what we have

