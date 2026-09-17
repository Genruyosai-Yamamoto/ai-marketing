# JSON API Auth — Design

Date: 2026-09-17
Status: Draft (pending user review)
Scope: Add JSON API auth endpoints (`register` / `login` / `logout` / `me`) to the existing Flask backend, wired to the existing session mechanism so all session-guarded routes work unchanged. Server-rendered `/login` + `/register` and `decorators.py` are untouched.

## Goal

The backend already has a full server-rendered auth flow in `routes/auth.py` (`/login`, `/register`, sessions, Firebase Auth, werkzeug password hashing, IP lockout, per-IP registration rate limiting) and every JSON route in `routes/user.py` / `routes/instagram_connections.py` guards on `session["user_id"]`. There is no JSON API for a separate frontend to authenticate with.

This effort adds a minimal, JSON-only auth API:

1. `POST /api/auth/register` — create a Firebase Auth user + Firestore record (same dual write as existing `/register`), rate-limited per IP.
2. `POST /api/auth/login` — verify credentials, issue a session cookie + session token (anti-sharing), with IP lockout.
3. `POST /api/auth/logout` — invalidate the session token and clear the session.
4. `GET /api/auth/me` — return the current user for session validation.

The API sets a **session cookie** (drop-in for the ~15 existing guarded routes) — no bearer tokens, no changes to protected routes.

## Design Decisions (from brainstorming)

- **JSON API auth endpoints** — the user already has server-rendered auth; the new surface is for a separate frontend.
- **Session-cookie mechanism** — `session["user_id"]` is how every protected route authenticates today. A cookie-based API needs zero changes to them; bearer tokens would touch all of them.
- **Firestore + Firebase Auth** — matches existing `/register` (`create_firebase_user_and_firestore`): create the Firebase Auth account *and* the `users/{uid}` Firestore record. Login verifies against the Firestore `password_hash` (`check_password_hash`), exactly like existing `/login` does today.
- **Reuse existing protections** — IP lockout, per-IP registration cap, and session-token anti-sharing logic already live (and are tested via `test_auth_redis_wiring.py`) in `routes/auth.py`. The API imports and reuses those helpers rather than duplicating them.

## Existing Helpers Being Reused (from `routes/auth.py`)

| Helper | Purpose |
|---|---|
| `_get_ip(request)` | Resolve client IP (X-Forwarded-For aware) |
| `redis_is_locked(ip)` / `locked_ips` | Login lockout gate (Redis-first, in-memory fallback) |
| `_increment_attempts(ip)`, `_reset_attempts(ip)` | Failed-login counters and lockout expiry |
| `check_registration_limit(ip)`, `log_registration(ip)` | Per-IP registration cap (3/hour) |
| `create_firebase_user_and_firestore(email, password, user_data)` | Firebase Auth create + `users/{uid}` Firestore set; returns `(uid, None)` or `(None, error)` |

## API Contract

All requests/responses are JSON. Success envelope: `{"success": true, ...}`. Error envelope: `{"success": false, "error": "<message>"}`. Unexpected exceptions are caught and returned as `500 {"success": false, "error": ...}`.

### `POST /api/auth/register`

Body: `{"username": str, "email": str, "password": str}`

- `email` lowercased and trimmed; `username` trimmed.
- Validation → `400`: missing `username`/`email`/`password`; `password` shorter than 8 chars.
- Registration cap → `429` (`"Too many registrations from this IP. Try again later."`).
- Existing email → `409` (`"Email already registered. Please login or use another email."`). Detected via a Firestore pre-check (query `users` by email); `create_firebase_user_and_firestore` returns this exact message if Firebase Auth also reports a duplicate. Any other error returned by the helper → `500` with `"Registration failed. Try again later."`.
- On success: build user record (`role: "user"`, `password_hash` via `generate_password_hash`, `status: "Active"`, `subscription_status: False`, `active_session_token: None`, timestamps via `datetime.utcnow().isoformat()`), call `create_firebase_user_and_firestore`, `log_registration(ip)`.
- Returns `201 {"success": true, "user_id": <uid>}`. Client then calls `/login` (no auto-session, matching existing `/register` behavior).

### `POST /api/auth/login`

Body: `{"email": str, "password": str}`

- Locked out (Redis or in-memory) → `423` with `"Try again in N minute(s)."`.
- Missing fields → `400`.
- Unknown email or wrong password → `401` `"Invalid credentials."`, attempts incremented.
- `status == "Disabled"` → `403` `"Account disabled. Contact support."`.
- Success: generate `secrets.token_hex(64)` session token, persist `active_session_token` + `last_login` + `last_ip`, `_reset_attempts(ip)`; `session.clear()` (fixation), `session.permanent = True` (30-min lifetime), set `session["user_id"]`, `session["email"]`, `session["role"]`, `session["session_token"]`.
- Returns `200 {"success": true, "user_id": ..., "email": ..., "role": ...}`.

### `POST /api/auth/logout`

- Reads `session["user_id"]`; if present, wipes `active_session_token` in Firestore (instantly invalidating all sessions, matching existing `/logout`). Then `session.clear()`.
- Returns `200 {"success": true, "message": "Logged out."}`.

### `GET /api/auth/me`

- No `session["user_id"]` → `401` `"Authentication required"`.
- Fetches `users/{user_id}`; missing → `401` and `session.clear()`.
- Returns `200 {"success": true, "user": {"id", "username", "email", "role", "status"}}`.

## Component / Files

- **`routes/auth_api.py`** (new): `Blueprint("api_auth", __name__)`, four routes above. Imports helpers from `routes.auth`, `from firebase import db`, `from werkzeug.security import check_password_hash, generate_password_hash`, `secrets`, `datetime`, `timedelta`, `FieldFilter`. Uses `current_app.logger` for exception logging.
- **`app.py`**: one added line — `app.register_blueprint(api_auth_bp)`.
- **No changes** to `routes/auth.py`, `routes/user.py`, `routes/instagram_connections.py`, `decorators.py`, `task.py`, or any connector/agent module. Session cookie settings (`HttpOnly`, `SameSite=Lax`) already configured in `app.py`.

## Data Flow

- register: JSON → validate → rate limit → dual create (Firebase + Firestore) → log → `201`
- login: JSON → lockout gate → lookup by email → hash verify → status check → issue session token (persist + cookie) → `200`
- logout: wipe stored token → clear session → `200`
- me: session `user_id` → fetch `users/{user_id}` → `200` / `401`

## Error Handling

- Every route returns the JSON envelope with the codes above.
- Firestore/Firebase exceptions during create/lookup are surfaced as `400`/`500` with a stable message; unexpected exceptions log via `current_app.logger.error` and return `500`.

## Security Notes

- Cookies inherit the existing `app.py` config: `SESSION_COOKIE_HTTPONLY`, `SESSION_COOKIE_SAMESITE=Lax`, production `SECURE`, 30-min `permanent_session_lifetime`.
- `login_token` form-CSRF is not part of the API (browser-form concern); SameSite=Lax + HttpOnly is the API's CSRF posture.
- Anti-sharing: every new login rotates `active_session_token`; `/me` and all existing guarded routes trust the cookie+token, so a concurrent login by another device invalidates prior sessions (the `login_required` in `decorators.py` enforces it; API routes that only check `user_id` follow the existing convention).
- Assumption (out of scope): a frontend on a **different origin** would additionally need CORS + `SameSite=None` configuration. Same-origin deployment needs nothing.

## Testing

New `tests/test_auth_api.py` following the repo's file-local fake-Firestore pattern (`_Snapshot` / `_Ref` / `_Collection`), with a `TESTING` Flask app (`secret_key` set, `api_auth_bp` + `auth_bp` registered, `redis_down`-style env for Redis fallback like `test_auth_redis_wiring.py`). `admin_auth.create_user` monkeypatched. Cases (13):

1. register success → `201`, user record written with hashed password (not plaintext), Firebase create called.
2. register missing fields → `400`.
3. register short password → `400`.
4. register duplicate email → `409`.
5. register rate cap → `429` after 3 registrations in the hour window (in-memory fallback).
6. login success → `200`, session populated, `active_session_token` persisted.
7. login wrong password → `401`, attempts incremented.
8. login unknown email → `401`.
9. login disabled user → `403`.
10. login locked out (5 attempts) → `423`.
11. logout → session cleared, Firestore token wiped.
12. me with session → `200` user payload.
13. me without session → `401`.

## Out of Scope / Deferred

- Password reset / forgot-password API (commented-out server-rendered flow stays as-is).
- Bearer-token / stateless auth (would require touching every protected route).
- CORS + cross-origin cookie setup.
- Token refresh / revocation endpoint (session invalidation via `active_session_token` rotation covers it).
- Subscription gating (gate stays commented out in existing `/login`).

## Verification

1. `./venv/bin/python -m pytest tests/test_auth_api.py -v` → all pass.
2. `./venv/bin/python -m pytest -q` → full suite stays green (93 current tests pass; this effort adds ~13).
3. `./venv/bin/python -m pytest tests/test_auth_redis_wiring.py -q` → existing Redis-wiring tests still green (helpers shared).