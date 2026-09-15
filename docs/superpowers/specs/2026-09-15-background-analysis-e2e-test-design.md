# Design: Background-Analysis Flow — Fix & End-to-End Test

Date: 2026-09-15
Status: Approved

## Goal

Make the background website-analysis flow run correctly and prove it end-to-end:
**Redis → Celery worker → `POST /api/business/<id>/analyze` → `agent_runs` → website fetch → `observations`.**

The flow exists in code but cannot run today because of import bugs, missing
Infrastructure (Redis not running, no Celery worker), a stale running app, and
missing `redis_*` auth helpers.

## 1. Architecture & components

```
Browser/curl ──HTTP──▶ Flask (app.py)
                          ├─ routes/auth.py   ──▶ Redis ─▶ Firestore (users)
                          ├─ routes/user.py   ──▶ Firestore (businesses, agent_runs)
                          │      └─ analyze endpoint ──▶ .delay() ─▶ Redis broker
                          └─ task.py (worker) ◀── consumes ──▶ website_analyzer.py ─▶ Firestore (observations)
```

- **Flask** (`app.py`) — HTTP front door; registers `auth_bp`, `user_bp`; session-cookie auth.
- **`routes/auth.py`** — register/login/logout; uses the new `redis_*` helpers for
  rate limiting with an in-memory fallback.
- **`routes/user.py`** — business CRUD + `POST /api/business/<id>/analyze` which
  creates an `agent_runs` doc and enqueues Celery work.
- **`redis_helpers.py`** (new) — 5 functions wrapping the Redis client.
- **Redis** — Celery broker/backend + auth rate-limit store.
- **Celery worker** (`task.py`) — `analyze_business_website` task.
- **`website_analyzer.py`** — SSRF-hardened fetch + HTML analysis.
- **Firestore** — `businesses`, `businesses/{id}/agent_runs`, `businesses/{id}/observations`.

## 2. Code fixes

### `routes/user.py`
1. `from tasks import analyze_business_website` → `from task import analyze_business_website`.
2. Add `jsonify` to the Flask import.
3. Add `from validations import validate_website_url`.

### New `redis_helpers.py`
Implement exactly these 5 functions, all Redis-first with a fallback sentinel that
`auth.py` already handles when Redis is unreachable:

- `redis_increment_login_attempts(ip, max_attempts, lockout_seconds) -> (count, is_locked, ttl)`
  — INCR a per-IP counter (with lockout expiry); set a lock key when `count >= max_attempts`.
  On Redis error return `(0, False, 0)`.
- `redis_reset_login_attempts(ip)` — delete the attempt + lock keys. No-op on Redis error.
- `redis_check_registration_limit(ip, max_per_hour) -> bool | None` — `None` signals
  Redis unavailable (caller falls back to in-memory).
- `redis_log_registration(ip)` — INCR an hourly key with 3600s expiry. No-op on Redis error.
- `redis_is_locked(ip) -> (bool, remaining_seconds)` — TTL-based lock check.
  On Redis error return `(False, 0)`.

Client URL from env `REDIS_URL` (default `redis://localhost:6379/0`).

### `routes/auth.py`
Add `from redis_helpers import redis_increment_login_attempts, redis_reset_login_attempts, redis_check_registration_limit, redis_log_registration, redis_is_locked` — removes the NameErrors.

### `routes/user.py` analyze endpoint
Wrap `analyze_business_website.delay(...)` in try/except: on broker failure, mark the
run `failed` and return 503 instead of an unhandled 500.

### New stub routes in `routes/user.py`
`auth.py:login` redirects via `url_for("user.dashboard")`,
`url_for("user.create_profile")`, and `url_for("user.generate_logbook")` — none of
these routes exist, so a real login would `BuildError`. Add all three as minimal
200 JSON stubs so the login redirect chain resolves.

### Test-environment note
`SESSION_COOKIE_SECURE` is derived from `DEBUG`; with `DEBUG=False` (default) the
session cookie is `Secure` and a plain-HTTP test client would drop it. Run the app
for the E2E with `DEBUG=True` so cookies are accepted over `http://127.0.0.1:5000`.

### `task.py`
No change to the task name (`tasks.analyze_business_website`) or the Celery config.
Worker is started with `celery -A task worker`.

## 3. End-to-end run (happy path)

1. Start `redis-server` (daemonized).
2. Start worker: `celery -A task worker --loglevel=info` (background).
3. Kill stale Flask PID 12862; start fresh `app.py` on :5000.
4. `GET /login` → capture CSRF `login_token`.
5. `POST /register` → real Firebase Auth user + Firestore `users/{uid}`.
6. `POST /login` (email/password/device_id/token) → session cookie.
7. `POST /api/business` (name + `https://example.com` as the website URL) → business id (201).
8. `POST /api/business/<id>/analyze` → 202; `agent_runs` created `queued`; task id stored.
9. Worker consumes → run `running` → `fetch_website_html()` (DNS pin) →
   `analyze_html()` → observation saved → run `completed` with `observation_id`.
10. Verify Firestore: run status + timestamps; observation analysis
    (title / description / headings / links).

## 4. Error handling

- Redis down → helpers return sentinels; auth uses existing in-memory lockout. Celery
  worker shows broker errors and retries/raises in task `except`.
- Website fetch failures (SSRF rejection, non-200, non-HTML, timeout, >2 MB) → task
  catches, marks run `failed` with error string, re-raises.
- Missing business / wrong owner / no website URL → run `failed` with explicit message
  (already implemented in `task.py`).
- Broker down at enqueue time → 503 + run marked `failed` (new guard in analyze endpoint).

## 5. Testing & cleanup

- Drive with `curl` using a cookie jar; poll the run doc through
  `queued → running → completed`.
- Exercise the failure path once: create a second business with a syntactically
  valid but unresolvable hostname (`https://does-not-exist-<rand>.invalid`, a
  guaranteed non-resolving TLD). `validate_website_url` accepts it at save time;
  the fetch fails at DNS time in the worker → confirm `status=failed` + error
  message. (Note: `https://127.0.0.1` was ruled out — the create-business
  validator already rejects loopback IPs, so it could never be stored.)
- After the test, delete the test business (including its `agent_runs` and
  `observations` subcollections) and the test user (Firestore doc + Firebase Auth uid).
- Code fixes stay in place; only test artifacts are removed.

## Out of scope

- Payments blueprint (commented out in `app.py`).
- `routes/home.py` (empty).
- Any refactor of `validations.py` / `website_analyzer.py` beyond what is required.
- Initializing a git repository (this project is not under version control).