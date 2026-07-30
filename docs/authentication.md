# Authentication System — SHI Health Assistant

> **Purpose of this document:** A single-source reference that gives an AI (or human) complete understanding of every authentication-related component without needing to scan source code. Covers architecture, data model, API contracts, access-control patterns, security design, and extension points.

---

## Table of Contents

1. [Overview](#1-overview)
2. [User Model & Roles](#2-user-model--roles)
3. [Technology Stack](#3-technology-stack)
4. [Data Layer — `users` Table](#4-data-layer--users-table)
5. [Core Auth Module (`app/core/auth.py`)](#5-core-auth-module-appcoreAuthpy)
6. [Storage Functions (`app/core/storage.py`)](#6-storage-functions-appcorestoragepy)
7. [HTTP API Endpoints](#7-http-api-endpoints)
8. [Access-Control Patterns](#8-access-control-patterns)
9. [Token & Session Lifecycle](#9-token--session-lifecycle)
10. [Rate Limiting](#10-rate-limiting)
11. [Frontend Integration (`login.html`)](#11-frontend-integration-loginhtml)
12. [Seeding Users (`scripts/seed_users.py`)](#12-seeding-users-scriptsseed_userspy)
13. [Environment Variables & Configuration](#13-environment-variables--configuration)
14. [Security Properties & Known Constraints](#14-security-properties--known-constraints)
15. [Error Reference](#15-error-reference)
16. [Extension Guide](#16-extension-guide)

---

## 1. Overview

SHI uses **stateless JWT authentication** delivered via **HttpOnly cookies**. There are no server-side session stores for auth — each request carries its own signed token. The system supports three user roles (`admin`, `doctor`, `guest`) and two authentication paths:

| Path | Used by |
|------|---------|
| Username + password → JWT cookie | All roles (web browser) |
| Same JWT cookie forwarded | Native mobile app (Expo) via `credentials: 'include'` |

Unauthenticated users (chatbot visitors) are fully supported; they get an anonymous `sid` (session ID) for chatbot state only — **they do not get a JWT token**.

---

## 2. User Model & Roles

### Roles

| Role | Description | Can self-register? | Assigned by |
|------|-------------|--------------------|-------------|
| `guest` | Regular patient / end user | ✅ Yes, via `/api/register` | Self or seed |
| `doctor` | Medical staff with a linked `doctor_id` | ❌ No | `scripts/seed_users.py` only |
| `admin` | Full system administrator | ❌ No | `scripts/seed_users.py` only |

> **Security note:** The `/api/register` endpoint enforces `role = "guest"` server-side. The client cannot escalate to `doctor` or `admin` by sending a different role in the request body.

### User Fields

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `id` | `TEXT` (uuid4 hex) | Yes | Primary key, generated server-side |
| `username` | `TEXT` | Yes | Unique, case-sensitive |
| `password_hash` | `TEXT` | Yes | bcrypt hash, never exposed in API responses |
| `role` | `TEXT` | Yes | `'admin'` \| `'doctor'` \| `'guest'` |
| `email` | `TEXT` | No | Optional contact email |
| `phone` | `TEXT` | No | Optional phone number (guest profile) |
| `address` | `TEXT` | No | Optional address (guest profile) |
| `doctor_id` | `TEXT` FK → `doctors.id` | No | Only set for `role='doctor'`; links user to scheduling data |
| `created_at` | `TEXT` (ISO 8601 UTC) | Yes | Set at creation |
| `updated_at` | `TEXT` (ISO 8601 UTC) | Yes | Updated by `update_user_profile()` |

---

## 3. Technology Stack

| Concern | Library / mechanism |
|---------|---------------------|
| Password hashing | `bcrypt` (cost factor 12) |
| JWT creation & verification | `PyJWT` |
| JWT algorithm | `HS256` (HMAC-SHA256) |
| Token transport | HttpOnly cookie named `auth_token` |
| CSRF mitigation | `SameSite=Lax` on the cookie |
| Storage backend | PostgreSQL (Supabase) when `DATABASE_URL` is set; JSON-file mode does **not** support users |

---

## 4. Data Layer — `users` Table

### DDL (auto-applied by `init_schema()` on first DB request)

```sql
CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,
    username        TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('admin', 'doctor', 'guest')),
    email           TEXT,
    phone           TEXT,
    address         TEXT,
    doctor_id       TEXT REFERENCES doctors(id),
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
-- Safe migration for existing databases:
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone    TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS address  TEXT;
```

### JSON-file mode

When `DATABASE_URL` is **not** set, `USE_DB = False` and **all user-related storage functions return `None` / `False` immediately**. Authentication therefore only works with a PostgreSQL connection. The chatbot and booking features still run in JSON-file mode without any users.

---

## 5. Core Auth Module (`app/core/auth.py`)

### Constants

```python
SECRET_KEY            = os.environ.get("SECRET_KEY", "shi-nha-khoa-demo-key")
JWT_ALGORITHM         = "HS256"
JWT_EXPIRATION_HOURS  = 24
```

### Exception Hierarchy

```
Exception
└── AuthError                  # Base for all auth errors
    ├── InvalidCredentialsError  # Wrong username or password
    └── UserAlreadyExistsError   # Username already taken
```

### Functions

#### `hash_password(password: str) -> str`
- Encodes the plain-text password to UTF-8, generates a bcrypt salt with `rounds=12`, and returns the hash as a decoded UTF-8 string for storage.

#### `verify_password(password: str, password_hash: str) -> bool`
- Both inputs are encoded to bytes before calling `bcrypt.checkpw`. Returns `True` on match.

#### `generate_jwt(user_id, username, role) -> str`
- Creates a JWT with claims:
  - `sub` — user UUID hex
  - `username` — login name
  - `role` — `'admin'` | `'doctor'` | `'guest'`
  - `iat` — issued-at (UTC)
  - `exp` — expiry = `iat + 24h`
- Signed with `HS256` using `SECRET_KEY`.

#### `verify_jwt(token: str) -> dict`
- Decodes and verifies signature + expiry.
- Raises `AuthError("Token hết hạn")` on expiry.
- Raises `AuthError("Token không hợp lệ: ...")` on any other JWT error.
- Returns the full payload dict on success.

#### `create_user_account(username, password, role, email, phone, address, doctor_id) -> dict`
- Checks username uniqueness via `storage.get_user_by_username()` first (application-level guard).
- Generates a UUID hex for `user_id`.
- Hashes the password with `hash_password()`.
- Calls `storage.create_user(...)`.
- Catches `storage.DuplicateUsernameError` (DB-level race condition) and re-raises as `UserAlreadyExistsError`.
- Returns a user info dict (no `password_hash`).

#### `login(username, password) -> dict`
- Fetches user by username; raises `InvalidCredentialsError` if not found (prevents username enumeration — same error as wrong password).
- Verifies password with `verify_password()`.
- Calls `generate_jwt()` and returns `{"token": ..., "user": {...}}`.

---

## 6. Storage Functions (`app/core/storage.py`)

All user functions are no-ops in JSON mode (`USE_DB = False`).

### `create_user(user_id, username, password_hash, role, email, phone, address, doctor_id)`
- Inserts a new row into `users`.
- Raises `DuplicateUsernameError` if the `UNIQUE` constraint on `username` fires.

### `get_user_by_username(username) -> dict | None`
- `SELECT` by `username`.
- Returns a full user dict including `password_hash` (needed by `auth.login`).

### `get_user_by_id(user_id) -> dict | None`
- `SELECT` by primary key `id`.
- Used by every request middleware to convert JWT `sub` claim into a live user object.
- Returns all fields; callers omit `password_hash` before returning to clients.

### `update_user_profile(user_id, email, phone, address) -> bool`
- `UPDATE users SET email, phone, address, updated_at WHERE id`.
- Returns `True` if one row was updated.
- Called by `PUT /api/profile`.

---

## 7. HTTP API Endpoints

All endpoints live in `app/main.py` unless noted.

### `POST /api/login`

**Request body (JSON):**
```json
{ "username": "string", "password": "string" }
```

**Success `200`:**
```json
{
  "ok": true,
  "user": { "id": "...", "username": "...", "role": "guest" },
  "message": "Chào mừng ...!"
}
```
Sets `Set-Cookie: auth_token=<JWT>; HttpOnly; SameSite=Lax; Max-Age=86400`.

**Errors:**
| Status | Condition |
|--------|-----------|
| `400` | Missing username or password |
| `401` | Wrong credentials (`InvalidCredentialsError`) |
| `500` | Unexpected server error |

---

### `POST /api/logout`

No body required. Clears `auth_token` cookie (`Max-Age=0`).

**Success `200`:**
```json
{ "ok": true, "message": "Đã đăng xuất" }
```

---

### `POST /api/register`

Self-service registration for **guest** users only. Role is always forced to `"guest"` server-side.

**Request body (JSON):**
```json
{
  "username": "string",   // required
  "password": "string",   // required, min 6 chars
  "email":    "string",   // optional
  "phone":    "string",   // optional
  "address":  "string"    // optional
}
```

**Success `201`:**
```json
{
  "ok": true,
  "user": { "id": "...", "username": "...", "role": "guest", "email": "...", "phone": "...", "address": "..." },
  "message": "Tạo tài khoản '...' thành công! Vui lòng đăng nhập."
}
```

**Errors:**
| Status | Condition |
|--------|-----------|
| `400` | Missing username/password, or password < 6 chars |
| `409` | Username already exists |
| `500` | Unexpected server error |

---

### `GET /api/me`

Returns the currently authenticated user's profile. Reads JWT from `auth_token` cookie.

**Success `200`:**
```json
{
  "user": {
    "id": "...",
    "username": "...",
    "role": "guest",
    "email": "...",
    "phone": "...",
    "address": "...",
    "doctor_id": null
  }
}
```

**Errors:** `401` (no token or expired), `404` (token valid but user deleted).

---

### `PUT /api/profile`

Updates the authenticated user's `email`, `phone`, and `address`. Protected by `@require_auth()` (any role).

**Request body (JSON):**
```json
{ "email": "...", "phone": "...", "address": "..." }
```

**Success `200`:**
```json
{ "ok": true, "message": "Cập nhật thông tin thành công" }
```

**Errors:** `401` (not authenticated).

---

### Admin & Doctor endpoints (protected)

| Endpoint | Auth mechanism | Required role |
|----------|----------------|---------------|
| `GET /api/admin/*` | `_check_admin()` in `admin_api.py` | `admin` |
| `POST /api/admin/cancel` | `_check_admin()` | `admin` |
| `GET /api/doctor/*` | `_get_current_doctor()` in `doctor_api.py` | `doctor` with `doctor_id` set |
| `GET /doctor-dashboard` | `@require_auth(allowed_roles=["doctor"])` | `doctor` |
| `GET /admin` | inline JWT check in route | `admin` |

---

## 8. Access-Control Patterns

Three distinct patterns are used in the codebase — understanding all three is necessary when adding new protected routes:

### Pattern A — `@require_auth()` decorator (recommended for new routes)

Defined in `app/main.py`. Reads `auth_token` cookie, verifies JWT, loads the live user from DB, and attaches it to `request.current_user`.

```python
# Any authenticated user:
@require_auth()
def my_endpoint():
    user = request.current_user   # full user dict

# Role-restricted:
@require_auth(allowed_roles=["admin"])
def admin_only():
    ...

@require_auth(allowed_roles=["doctor"])
def doctor_only():
    user = request.current_user   # includes user["doctor_id"]
```

HTTP responses on failure:
- `401` — no cookie, or JWT expired/invalid, or user not found in DB
- `403` — JWT valid but role not in `allowed_roles`
- `404` — JWT valid but user row was deleted

### Pattern B — `_check_admin()` helper (legacy, `admin_api.py`)

Returns a boolean; the route calls `abort(401)` itself. Does not expose `request.current_user`.

```python
def _check_admin():
    token = request.cookies.get("auth_token")
    if token:
        payload = auth.verify_jwt(token)
        user = storage.get_user_by_id(payload["sub"])
        if user and user["role"] == "admin":
            return True
    return False
```

### Pattern C — `_get_current_doctor()` helper (legacy, `doctor_api.py`)

Returns the user dict (or `None`). Also enforces that `doctor_id` is set — a `doctor` account without `doctor_id` is rejected.

```python
def _get_current_doctor():
    token = request.cookies.get("auth_token")
    payload = auth.verify_jwt(token)
    user = storage.get_user_by_id(payload["sub"])
    if not user or user.get("role") != "doctor" or not user.get("doctor_id"):
        return None
    return user
```

---

## 9. Token & Session Lifecycle

```
User submits login form
        │
        ▼
POST /api/login
  auth.login(username, password)
    ├── get_user_by_username()
    ├── verify_password()
    └── generate_jwt(user_id, username, role)
        │
        ▼
  Set-Cookie: auth_token=<JWT>; HttpOnly; SameSite=Lax; Max-Age=86400
        │
        ▼
Every subsequent request (browser sends cookie automatically)
  @require_auth / _check_admin / _get_current_doctor
    ├── read auth_token from request.cookies
    ├── auth.verify_jwt(token)  ← checks HS256 signature + exp
    └── storage.get_user_by_id(payload["sub"])  ← live DB lookup
        │
        ▼
POST /api/logout
  Set-Cookie: auth_token=; Max-Age=0
```

**Key properties:**
- Token expiry: **24 hours** from issue time.
- There is **no refresh mechanism** — after expiry the user must log in again.
- There is **no token blacklist / revocation** — invalidating a token before expiry requires changing `SECRET_KEY` (which invalidates all tokens).
- The JWT is **never read by JavaScript** (`HttpOnly`), preventing XSS token theft.
- Each request performs **one DB read** (`get_user_by_id`) to confirm the user still exists. This is intentional — it allows an admin to deactivate an account and have it take effect on the next request.

---

## 10. Rate Limiting

All `/api/*` endpoints are guarded by an in-process token-bucket limiter in `app/main.py`:

| Parameter | Value |
|-----------|-------|
| Window | 60 seconds |
| Max requests per IP | 30 |
| Max IPs tracked | 5 000 (LRU eviction) |
| Response on limit | `429 {"error": "Quá nhiều yêu cầu..."}` |

Static pages (`/`, `/admin`, `/login`, `/doctor-dashboard`) are **not** rate-limited.

---

## 11. Frontend Integration (`login.html`)

The login page (`/login`) is a single-page form that toggles between **Login** and **Register** views.

### Login flow
1. User fills `username` + `password`, submits.
2. `handleLogin()` POSTs to `/api/login` with `credentials: 'include'`.
3. On `200`: reads `data.user.role` and redirects:
   - `admin` → `/admin`
   - `doctor` → `/doctor-dashboard`
   - `guest` → `/`
4. On error: shows inline error message for 4 seconds.

### Register flow
1. User fills `username`, `password`, `email` (optional), `phone` (optional), `address` (optional).
2. `handleRegister()` POSTs to `/api/register`.
3. On `201`: shows success message and auto-switches back to login view after 1.5 s.
4. On `409`: shows "username already taken" error.

### Auto-redirect on load
On page load, `GET /api/me` is called. If it returns `200`, the user is already authenticated and is redirected by role automatically — they never see the login form.

### "Continue without login"
A link at the bottom of the login form sends the user to `/` without requiring authentication. The chatbot works for anonymous users.

### Demo user buttons
Pre-filled quick-login buttons for `admin` and demo doctor accounts (`bs_sr_01`, `bs_nc_01`) are shown on the login form for development convenience.

---

## 12. Seeding Users (`scripts/seed_users.py`)

Run once after `DATABASE_URL` is set to populate the database with initial accounts:

```bash
python -m scripts.seed_users
```

The script is **idempotent** — existing usernames are skipped.

### Seeded accounts

| Username | Role | Password | Notes |
|----------|------|----------|-------|
| `admin` | admin | `test123` | System administrator |
| `bs_tq_01` | doctor | `test123` | BS. Nguyễn Văn An — Khám tổng quát |
| `bs_tq_02` | doctor | `test123` | BS. Trần Thị Bình — Khám tổng quát |
| `bs_sr_01` | doctor | `test123` | BS. Lê Minh Châu — Sâu răng |
| `bs_nn_01` | doctor | `test123` | BS. Phạm Quốc Dũng — Nội nha |
| `bs_nc_01` | doctor | `test123` | BS. Hoàng Thị Em — Nha chu |
| `bs_nhr_01` | doctor | `test123` | BS. Vũ Đình Phúc — Nhổ răng |
| `bs_cn_01` | doctor | `test123` | BS. Đỗ Thị Giang — Chỉnh nha |
| `bs_cn_02` | doctor | `test123` | BS. Ngô Văn Hải — Chỉnh nha |
| `bs_ph_01` | doctor | `test123` | BS. Bùi Thị Inh — Phục hình |
| `bs_tm_01` | doctor | `test123` | BS. Dương Văn Khang — Thẩm mỹ |
| `bs_nhi_01` | doctor | `test123` | BS. Lý Thị Lan — Nha nhi |
| `nguyen_thi_mai` | guest | `test123` | 0901234567 · 123 Nguyễn Huệ, Q1, HCM |
| `tran_van_minh` | guest | `test123` | 0912345678 · 45 Lê Lợi, Đà Nẵng |
| `le_thi_hoa` | guest | `test123` | 0923456789 · 78 Hoàn Kiếm, Hà Nội |
| `pham_duc_long` | guest | `test123` | 0934567890 · 22 Trần Phú, Huế |
| `hoang_thi_thu` | guest | `test123` | 0945678901 · 56 Bùi Thị Xuân, Hà Nội |

---

## 13. Environment Variables & Configuration

| Variable | Default | Production requirement |
|----------|---------|------------------------|
| `SECRET_KEY` | `shi-nha-khoa-demo-key` | **Must change.** Any leak means all tokens can be forged. Use a random 32+ byte hex string. |
| `DATABASE_URL` | _(empty)_ | Required for auth to work. Format: PostgreSQL connection string (Supabase Transaction Pooler recommended). |
| `SECURE_COOKIE` | `false` | Set to `true` in HTTPS production — adds `Secure` flag to `auth_token` cookie so it is never sent over plain HTTP. |
| `FLASK_DEBUG_WARN_SUPPRESS` | _(unset)_ | Set to `1` to suppress the startup warning about running `debug=True` on `0.0.0.0`. |

---

## 14. Security Properties & Known Constraints

### Implemented mitigations

| Threat | Mitigation |
|--------|-----------|
| XSS token theft | `HttpOnly` cookie — JS cannot read `auth_token` |
| CSRF | `SameSite=Lax` cookie attribute |
| Password brute-force | Rate limiter (30 req/min per IP) + bcrypt cost 12 |
| Username enumeration on login | Same `InvalidCredentialsError` message for "not found" and "wrong password" |
| Username enumeration on register | `409` only; does not reveal whether the exact username exists in other contexts |
| Privilege escalation via register | `role` always forced to `"guest"` in `/api/register`; client-supplied role is ignored |
| Weak passwords | Minimum 6-character length validation |
| Stale session after account delete | Every request re-fetches user from DB; deleted users immediately get `404` |
| SQL injection | Parameterised queries (`%s`) throughout storage layer |

### Known constraints / not yet implemented

| Limitation | Notes |
|-----------|-------|
| No token revocation / blacklist | Changing `SECRET_KEY` invalidates all active sessions. No per-token revocation. |
| No token refresh | 24-hour hard expiry; users must re-login after expiry |
| No email verification | Accounts are active immediately after registration |
| No password reset flow | No "forgot password" endpoint exists |
| No account lockout | Repeated failed logins are only slowed by the IP-level rate limiter, not per-account lockout |
| No MFA | Single factor (password) only |
| In-process rate limiter | Resets on restart; does not work across multiple worker processes |
| JSON-file mode | Auth is completely non-functional without `DATABASE_URL` |

---

## 15. Error Reference

| Exception class | Module | HTTP response |
|----------------|--------|---------------|
| `AuthError` | `app/core/auth.py` | `401` |
| `InvalidCredentialsError` | `app/core/auth.py` | `401` |
| `UserAlreadyExistsError` | `app/core/auth.py` | `409` |
| `DuplicateUsernameError` | `app/core/storage.py` | Caught by `create_user_account`, re-raised as `UserAlreadyExistsError` |
| `jwt.ExpiredSignatureError` | PyJWT | Caught by `verify_jwt`, re-raised as `AuthError` |
| `jwt.InvalidTokenError` | PyJWT | Caught by `verify_jwt`, re-raised as `AuthError` |

---

## 16. Extension Guide

### Adding a new protected route

Use the `@require_auth()` decorator (Pattern A). Do not copy Patterns B or C into new code.

```python
# In app/main.py or a new Blueprint:
@app.route("/api/something", methods=["GET"])
@require_auth(allowed_roles=["guest", "admin"])   # or omit for any logged-in user
def something():
    user = request.current_user   # {"id", "username", "role", "email", "phone", "address", ...}
    return jsonify({"user_id": user["id"]})
```

### Adding a new role

1. Extend the `CHECK` constraint in `SCHEMA_SQL` in `storage.py`.
2. Add migration: `ALTER TABLE users DROP CONSTRAINT ...; ALTER TABLE users ADD CONSTRAINT ... CHECK (role IN ('admin', 'doctor', 'guest', 'NEW_ROLE'));` (Postgres syntax).
3. Update `api_register` if the new role should be self-registrable.
4. Add the role to `allowed_roles` lists on any relevant endpoints.

### Adding a new user profile field

1. Add the column to `SCHEMA_SQL` and add an `ALTER TABLE users ADD COLUMN IF NOT EXISTS ...` line below it.
2. Add the field to `create_user()`, `get_user_by_username()`, `get_user_by_id()` column lists and row mappings.
3. Add the field to `create_user_account()` signature and return dict.
4. Expose the field in `/api/register`, `/api/me`, and `update_user_profile()` as needed.
5. Update `seed_users.py` if it applies to seeded accounts.
