# Deployment Guide

## Quick Start Overview

Three ways to run SHI:

1. **Local dev (Flask dev server)** — quickest for testing
2. **Docker Compose (gunicorn + Postgres)** — closest to production
3. **Production (cloud VPS)** — for public deployment

---

## Local Development Setup

### Prerequisites

- Python 3.11+
- Node.js 18+ (for mobile app)
- macOS/Linux or WSL (Windows Subsystem for Linux)

### Backend Setup

```bash
# 1. Clone & navigate
cd PRF-SHI

# 2. Python venv
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 3. Install dependencies (includes pytest for local testing)
pip install -r requirements-dev.txt

# 4. Setup environment
cp .env.example .env
# Edit .env: set SECRET_KEY, OPENROUTER_API_KEY (optional)
# Leave DATABASE_URL empty for file JSON mode
```

### Run Backend

**Terminal 1: Flask dev server**

```bash
export PORT=5001
python -m app.main
# API available at http://localhost:5001
# Web demo at http://localhost:5001/
```

**Terminal 2 (optional): Appointment reminder worker**

```bash
# In another terminal with venv activated
python -m app.notify.worker --watch
# Watches for reminders every 60s
```

### Test Backend

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_chatbot_router.py -v

# Run with coverage
pytest --cov=app
```

---

## Docker Compose Setup (Recommended for Demo)

### Prerequisites

- Docker & Docker Compose installed
- 2GB free disk space
- Port 5001 free (or modify compose file)

### Setup

```bash
cd PRF-SHI

# 1. Prepare environment
cp .env.docker.example .env

# 2. Set required values in .env
# Edit .env:
#   POSTGRES_PASSWORD=<random-password>
#   SECRET_KEY=<random-hex-string>
#   JWT_EXPIRATION_HOURS=24
#   SECURE_COOKIE=false  (set true behind HTTPS)
#   OPENROUTER_API_KEY=<optional>

# 3. Build & start services
docker compose up --build -d

# 4. Initialize user database (first run only)
# Must run BEFORE first login; creates admin + doctor accounts
docker compose exec web python -m scripts.seed_users

# 5. Verify services are running
docker compose ps
# Should show: db, web, worker all in "running" state with (healthy)
```

**Important:** Step 4 (`seed_users.py`) is required before the app is usable with auth. This creates one admin account (`username=admin, password=test123`), 11 doctor accounts, and five named sample patients (`nguyen_thi_mai`, …).

**Recommendation data is not seeded — it is earned through the app.** A patient's `visit_count` only grows when a dentist records a completed visit, so the path on a fresh deploy is: book appointments through the chatbot widget → log in as that dentist at `/doctor` → **Lịch làm việc trong ngày** → **Ghi kết quả** on each slot → click the patient's name to open their profile and see the recommendations. Three recorded visits is the cold-start threshold (`reco.COLD_START_MIN_VISITS`). Today is inside the booking window, so all three can be done in one sitting.

`scripts/seed_reco_demo.py` (the old `bn101..bn108` demo fixtures) still exists for `eval/`, but is deliberately **not** part of the deploy flow any more: it manufactures a treatment history nobody actually performed and hides the one link — dentist records the visit — that this deploy needs to prove works.

### Monitoring Logs

```bash
# View combined logs
docker compose logs -f

# View specific service
docker compose logs -f web
docker compose logs -f worker

# Clear old logs & restart
docker compose down
docker compose up -d
```

### Authentication & First-Run Setup

**BEFORE using admin or doctor login**, seed the user database (Postgres only):

```bash
# Initialize admin + doctor user accounts
docker compose exec web python -m scripts.seed_users
# Output: "✓ Seeded 1 admin + 11 doctors (idempotent)"

# Log in to /login:
#   Admin: username=admin, password=test123
#   Doctor: username=doctor_id (e.g., doctor_1), password=test123
```

**Important notes:**
- `seed_users.py` is **Postgres-only** (no JSON fallback). Requires `DATABASE_URL` to be set.
- Script is **idempotent** — safe to run multiple times.
- Passwords are demo defaults; **change them in production** (update directly in database or implement password reset flow).
- First visit to `/login` or `/admin` auto-redirects to login form if not authenticated.

### Stop & Cleanup

```bash
# Stop containers (keep data)
docker compose stop

# Stop & remove containers
docker compose down

# Remove everything including database
docker compose down -v
```

### Access Services

- **Backend API:** http://localhost:5001
- **Web demo & chat:** http://localhost:5001/
- **Login:** http://localhost:5001/login
- **Admin panel:** http://localhost:5001/admin (JWT auth required)
- **Doctor dashboard:** http://localhost:5001/doctor-dashboard (JWT auth required)
- **Database:** Inside container at `db:5432` (not directly accessible from host)

### Connect from Local Tools

To use DB tools from your machine (e.g., pgAdmin), expose Postgres:

```yaml
# docker-compose.yml — add to db service:
services:
  db:
    ports:
      - "5432:5432"  # Now accessible as localhost:5432
```

Then connect:
```bash
psql -h localhost -U shi -W
# Password: (what you set in POSTGRES_PASSWORD)
```

---

## Mobile App Setup (Expo)

### Prerequisites

- Node.js 18+
- Expo Go app (iOS App Store or Google Play)
- Same Wi-Fi as backend machine

### Setup & Run

```bash
cd mobile

# 1. Install dependencies
npm install

# 2. Update backend IP (if not using setup.sh)
# Edit mobile/src/config.js:
#   export const API_BASE = "http://<your-machine-ip>:5001";

# Find your machine's IP:
# macOS: ipconfig getifaddr en0
# Linux: hostname -I

# 3. Start Expo
npx expo start -c  # -c clears cache

# 4. Scan QR code with Expo Go app on phone
```

### Automated Setup (macOS/Linux)

```bash
# From repo root
./setup.sh

# Interactive menu:
# 1. Setup backend → cwd .venv install + configure
# 2. Setup mobile → cwd mobile npm install + find IP
# 3. Update IP → re-scan LAN IP, update config.js
```

One-liner if already setup:
```bash
./setup.sh ip  # Re-detect & update IP only
```

### Network Requirements

- Phone and laptop **must be on same Wi-Fi**
- Backend IP must be reachable (ping from phone's command line to test)
- Firewall must allow port 5001 (usually open on home Wi-Fi)

### Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "Cannot connect to http://..." | Wrong IP in config.js | Run `./setup.sh ip` |
| Blank screen after QR scan | Old cached IP | Clear Expo cache: `expo start -c` |
| 503 errors | Backend not running | Check `python -m app.main` is running |
| App crashes on startup | Missing env vars | Check `.env` has all required keys |

---

## Environment Variables Reference

### Core Settings

| Variable | Example | Required? | Purpose |
|----------|---------|-----------|---------|
| `SECRET_KEY` | `abc123...` (random hex) | YES (prod) | Flask session encryption + JWT signing key |
| `DATABASE_URL` | `postgresql://...` | NO (Postgres) | Postgres/Supabase; omit for JSON mode. **REQUIRED for auth** (user accounts need DB) |

### Authentication (New)

| Variable | Example | Default | Purpose |
|----------|---------|---------|---------|
| `JWT_EXPIRATION_HOURS` | `24` | `24` | JWT token lifetime in hours |
| `SECURE_COOKIE` | `true` or `false` | `false` | Set `true` behind HTTPS; enables secure flag on auth_token cookie |

### LLM Integration (Optional)

| Variable | Example | Purpose |
|----------|---------|---------|
| `OPENROUTER_API_KEY` | `sk-or-v1-...` | LLM provider key (get at https://openrouter.ai/keys) |
| `LLM_MODEL` | `google/gemini-2.5-flash-lite` | Which model to use |
| `LLM_ENABLED` | `1` | Set to `0` to disable LLM (use v2 rule-based) |
| `LLM_TIMEOUT` | `8` | Max seconds to wait for LLM response |

### Docker Compose Only

| Variable | Purpose |
|----------|---------|
| `POSTGRES_DB` | Database name (default: `shi`) |
| `POSTGRES_USER` | DB user (default: `shi`) |
| `POSTGRES_PASSWORD` | DB password (required, no default) |

---

## Production Deployment

### Pre-Deployment Checklist

- [ ] `SECRET_KEY` is a random hex string (used for JWT signing + Flask sessions)
- [ ] `DATABASE_URL` points to production Postgres/Supabase (REQUIRED for auth)
- [ ] `JWT_EXPIRATION_HOURS` set appropriately (default 24)
- [ ] `SECURE_COOKIE=true` set (only behind HTTPS)
- [ ] User database seeded: `python -m scripts.seed_users` (or admin/doctor accounts created manually)
- [ ] Recommendation demo verified through the app, not seeded: book → **Ghi kết quả** at `/doctor` → patient profile (see "Recommendation data is not seeded" above)
- [ ] `OPENROUTER_API_KEY` set (if using LLM)
- [ ] Mobile app `config.js` points to production HTTPS URL (not LAN IP)
- [ ] **Reverse proxy (Nginx/Caddy) configured** — docker-compose binds to `127.0.0.1:5001` (localhost-only); public access requires reverse proxy on port 80/443
- [ ] SSL certificate configured (HTTPS required for production)
- [ ] Backups enabled for database
- [ ] Monitoring & alerting setup (optional but recommended)

### Deploy on Cloud VPS (Example: DigitalOcean, AWS EC2)

#### Option A: Docker Compose (Simplest)

```bash
# On VPS
ssh root@your-vps-ip

# Install Docker & Docker Compose
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
apt-get install -y docker-compose

# Clone repo
git clone https://github.com/your-org/PRF-SHI.git
cd PRF-SHI

# Prepare env
cat > .env << EOF
POSTGRES_PASSWORD=$(openssl rand -base64 32)
SECRET_KEY=$(openssl rand -hex 32)
JWT_EXPIRATION_HOURS=24
SECURE_COOKIE=true
OPENROUTER_API_KEY=<your-key>
EOF

# Start services
docker compose up -d

# Initialize user database (one-time)
docker compose exec web python -m scripts.seed_users

# Verify all services healthy
docker compose ps  # All should show (healthy)

# Enable auto-restart on reboot
docker compose config --resolve-image-digests > docker-compose.prod.yml
# (Or use systemd service)
```

**Important:** Docker Compose binds the `web` service to `127.0.0.1:5001` (localhost-only). This is **intentional** — you must place a reverse proxy (Nginx, Caddy, etc.) in front on ports 80/443. See "Reverse Proxy" section below.

#### Option B: Systemd Service (Manual Gunicorn)

```bash
# Create systemd service file
cat > /etc/systemd/system/shi-backend.service << 'EOF'
[Unit]
Description=SHI Backend (Flask + Gunicorn)
After=network.target

[Service]
Type=notify
User=www-data
WorkingDirectory=/opt/shi
Environment="PATH=/opt/shi/.venv/bin"
ExecStart=/opt/shi/.venv/bin/gunicorn \
  --workers 4 \
  --worker-class sync \
  --bind 0.0.0.0:5001 \
  --timeout 30 \
  app.main:app

Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Enable & start
systemctl daemon-reload
systemctl enable shi-backend
systemctl start shi-backend
systemctl status shi-backend
```

### Reverse Proxy (Nginx) — REQUIRED for Docker Compose

**Why:** Docker Compose's `web` service binds to `127.0.0.1:5001` (localhost-only, not publicly accessible). A reverse proxy on the public interface handles HTTPS termination and routes requests to the app.

Use Nginx to handle HTTPS and route traffic to gunicorn:

```nginx
# /etc/nginx/sites-available/shi
server {
    listen 80;
    server_name api.clinicname.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.clinicname.com;

    ssl_certificate /etc/letsencrypt/live/api.clinicname.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.clinicname.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Obtain SSL cert:
```bash
apt-get install certbot python3-certbot-nginx
certbot certonly --nginx -d api.clinicname.com
# Auto-renews; enable renewal timer:
systemctl enable certbot.timer
```

### Update Mobile App

Edit `mobile/src/config.js`:

```javascript
export const API_BASE = "https://api.clinicname.com";
```

Rebuild & deploy via EAS:
```bash
cd mobile
eas build --platform ios --wait
eas build --platform android --wait
eas submit -p ios
eas submit -p android
```

---

## Database Migration (JSON → Postgres)

If you started with JSON but want to migrate to Postgres:

```bash
# 1. Ensure Postgres/Supabase is running and accessible
export DATABASE_URL="postgresql://user:pass@host/dbname"

# 2. Run migration script
.venv/bin/python scripts/migrate_to_supabase.py

# 3. Verify data was migrated
.venv/bin/python -c "from app.core.storage import Storage; s = Storage(); print(s.appointment_list())"

# 4. Update .env to use Postgres going forward
# (Set DATABASE_URL permanently)
```

---

## Monitoring & Health Checks

### Health Endpoint

Add to `app/main.py`:

```python
@app.route("/api/health", methods=["GET"])
def health():
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "version": "0.1.0"
    }, 200
```

Monitor:
```bash
curl -s http://localhost:5001/api/health | jq
```

### Logs

**Local:**
```bash
# Flask dev server logs appear on terminal
# Worker logs: separate terminal running `python -m app.notify.worker`
```

**Docker:**
```bash
docker compose logs -f web
docker compose logs -f worker
```

**Production (systemd):**
```bash
journalctl -u shi-backend -f  # View live logs
journalctl -u shi-backend --since "1 hour ago"  # Last hour
```

### Cleanup & Maintenance

**Rotate audit log:**
```bash
# Automatic (5MB rotation built-in), but you can manually reset:
rm -f app/data/audit_log.jsonl
```

**Clean stale appointments:**
```bash
.venv/bin/python scripts/clean_stale_appointments.py
```

**Backup database:**
```bash
# Postgres dump
pg_dump -h localhost -U shi -d shi > backup.sql

# Restore
psql -h localhost -U shi < backup.sql
```

---

## Troubleshooting

### Backend Won't Start

```bash
# Check Python version
python --version  # Should be 3.11+

# Check venv
which python  # Should show .venv/bin/python

# Check dependencies
pip list | grep Flask

# Try restarting with debug
export FLASK_ENV=development
export FLASK_DEBUG=1
python -m app.main
```

### Database Connection Issues

```bash
# Test connection string
export DATABASE_URL="postgresql://shi:password@localhost/shi"
python -c "from app.core.storage import Storage; Storage().init_schema(); print('OK')"

# Check Postgres is running
docker compose ps db  # or
psql -h localhost -U shi -c "\l"
```

### Mobile App Network Issues

```bash
# On phone, test backend IP connectivity
ping 192.168.x.x  # Should get responses

# On backend machine, verify port is listening
lsof -i :5001  # macOS/Linux
netstat -an | grep 5001  # Windows

# Firewall: ensure port 5001 is open
```

### Rate-Limit Issues

If you see `429 Too Many Requests`:

```python
# Adjust rate-limit in app/main.py
rate_limiter = RateLimiter(
    lambda: request.remote_addr,
    max_requests=50,  # Increase from 30
    window_seconds=60
)
```

---

## Related Documentation

- **[project-overview-pdr.md](./project-overview-pdr.md)** — what SHI does
- **[system-architecture.md](./system-architecture.md)** — how it's built
- **[project-roadmap.md](./project-roadmap.md)** — production gaps to address

