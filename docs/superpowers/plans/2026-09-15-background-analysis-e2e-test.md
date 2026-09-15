# Background-Analysis Flow — Fix & End-to-End Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the background website-analysis flow (`Redis → Celery worker → POST /api/business/<id>/analyze → agent_runs → website fetch → observations`) run and prove it end-to-end against the live stack.

**Architecture:** Fix the import/module breakages (missing `jsonify`, `validate_website_url`, wrong `tasks` import), add a new `redis_helpers.py` module whose 5 functions back auth rate-limiting on Redis with the exact fallback sentinels `auth.py` already handles, add three stub auth-redirect routes, then bring up Redis/Celery/Flask and drive a real register→login→create→analyze flow with a Python `requests` script that asserts each stage and cleans up test data.

**Tech Stack:** Flask 3.1, Celery 5.6, Redis (broker + rate-limits), Firebase Admin (Firestore + Auth), `website_analyzer.py` (requests/BeautifulSoup), pytest (new, dev-only).

## Global Constraints

- Python interpreter: `/home/parrot/blom/backend/venv/bin/python` (3.13).
- Run all `pytest` from `/home/parrot/blom/backend` (so `.env` is picked up by `firebase.py`).
- `.env` holds `FIREBASE_CREDENTIALS` (path to the service-account JSON) and `SECRET_KEY`; required to import any module that pulls in `firebase.py`.
- Redis URL: `redis://localhost:6379/0` (Celery broker/backend default in `task.py`, and default in `redis_helpers.py`).
- Celery entry point: `task.py` (module `task`); task name `tasks.analyze_business_website` (unchanged). Worker: `./venv/bin/celery -A task worker --loglevel=info`.
- Flask runs on `:5000` via `python app.py`. For the E2E it MUST be started with `DEBUG=True` (`DEBUG` is unset in `.env` by default, which would mark the session cookie `Secure` and cause a plain-HTTP test client to drop it).
- `routes/user.py` must keep exactly one import of the Celery task: `from task import analyze_business_website`.
- SECURITY: the service-account file `ai-agent-86543-firebase-adminsdk-fbsvc-68c677eed5.json` must be added to `.gitignore` BEFORE the first commit. Never stage `.env` or venv.
- Project has no git repo yet; Task 1 initializes it. Every task ends with a commit.
- pytest is a dev-only dependency; do NOT add it to `requirements.txt`.

---

### Task 1: Initialize git repo, add secret guard, install pytest

**Files:**
- Create: `tests/conftest.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: a git repo, a `.gitignore` that protects the service-account key, an importable `tests/` package, and pytest available in the venv.

- [ ] **Step 1: Initialize the repository**

```bash
cd /home/parrot/blom/backend
git init
```

- [ ] **Step 2: Add the service-account key to `.gitignore` so it can never be committed**

Append to `.gitignore` (it currently only ignores the `church-54be3-*.json` credential):

```gitignore
# Firebase service-account keys — never commit
ai-agent-*-firebase-adminsdk-*.json
```

- [ ] **Step 3: Install pytest into the venv**

```bash
/home/parrot/blom/backend/venv/bin/python -m pip install pytest
```

- [ ] **Step 4: Create `tests/conftest.py` so imports resolve and `.env` is loadable from pytest**

```python
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
```

- [ ] **Step 5: Verify pytest runs**

Run: `/home/parrot/blom/backend/venv/bin/python -m pytest -q`
Expected: `no tests ran` with exit code 5 (or `0 tests collected`). No import errors.

- [ ] **Step 6: Commit**

```bash
git add .gitignore tests/conftest.py
git commit -m "chore: init repo, protect service-account key, add pytest"
```

---

### Task 2: Create `redis_helpers.py` (TDD)

**Files:**
- Create: `redis_helpers.py`
- Test: `tests/test_redis_helpers.py`

**Interfaces:**
- Produces (consumed by Task 3 and `routes/auth.py`):
  - `redis_increment_login_attempts(ip: str, max_attempts: int, lockout_seconds: int) -> tuple[int, bool, int]` — `(count, is_locked, ttl)`; Redis-down → `(0, False, 0)`.
  - `redis_reset_login_attempts(ip: str) -> None` — no-op when Redis is down.
  - `redis_check_registration_limit(ip: str, max_per_hour: int) -> bool | None` — `None` when Redis is down.
  - `redis_log_registration(ip: str) -> None` — no-op when Redis is down.
  - `redis_is_locked(ip: str) -> tuple[bool, int]` — `(bool, remaining_seconds)`; Redis-down → `(False, 0)`.
  - `_get_redis() -> redis.Redis` — lazily creates a client from env `REDIS_URL` (default `redis://localhost:6379/0`) with 2s connect/socket timeouts.

- [ ] **Step 1: Write the failing test**

`tests/test_redis_helpers.py`:

```python
import pytest

import redis_helpers


DEAD_URL = "redis://127.0.0.1:6399/15"


@pytest.fixture
def redis_down(monkeypatch):
    monkeypatch.setenv("REDIS_URL", DEAD_URL)
    return DEAD_URL


def test_increment_returns_fallback_when_redis_down(redis_down):
    result = redis_helpers.redis_increment_login_attempts("1.2.3.4", 5, 900)
    assert result == (0, False, 0)


def test_is_locked_returns_false_when_redis_down(redis_down):
    assert redis_helpers.redis_is_locked("1.2.3.4") == (False, 0)


def test_check_registration_limit_returns_none_when_redis_down(redis_down):
    assert redis_helpers.redis_check_registration_limit("1.2.3.4", 3) is None


def test_log_and_reset_are_noops_when_redis_down(redis_down):
    redis_helpers.redis_log_registration("1.2.3.4")
    redis_helpers.redis_reset_login_attempts("1.2.3.4")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/parrot/blom/backend/venv/bin/python -m pytest tests/test_redis_helpers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'redis_helpers'`.

- [ ] **Step 3: Write the implementation**

`redis_helpers.py`:

```python
import os

import redis


DEFAULT_REDIS_URL = "redis://localhost:6379/0"


def _get_redis():
    return redis.Redis.from_url(
        os.environ.get("REDIS_URL", DEFAULT_REDIS_URL),
        socket_connect_timeout=2,
        socket_timeout=2,
    )


def redis_increment_login_attempts(ip, max_attempts, lockout_seconds):
    try:
        r = _get_redis()
        key = f"login_attempts:{ip}"
        lock_key = f"login_lock:{ip}"
        count = r.incr(key)
        r.expire(key, lockout_seconds)
        is_locked = count >= max_attempts
        if is_locked:
            r.set(lock_key, "1", ex=lockout_seconds)
        ttl = r.ttl(lock_key)
        return count, is_locked, ttl
    except redis.RedisError:
        return 0, False, 0


def redis_reset_login_attempts(ip):
    try:
        r = _get_redis()
        r.delete(f"login_attempts:{ip}", f"login_lock:{ip}")
    except redis.RedisError:
        pass


def redis_check_registration_limit(ip, max_per_hour):
    try:
        r = _get_redis()
        key = f"reg_count:{ip}"
        raw = r.get(key)
        current = int(raw) if raw is not None else 0
        return current < max_per_hour
    except redis.RedisError:
        return None


def redis_log_registration(ip):
    try:
        r = _get_redis()
        key = f"reg_count:{ip}"
        r.incr(key)
        r.expire(key, 3600)
    except redis.RedisError:
        pass


def redis_is_locked(ip):
    try:
        r = _get_redis()
        ttl = r.ttl(f"login_lock:{ip}")
        if ttl and ttl > 0:
            return True, ttl
        return False, 0
    except redis.RedisError:
        return False, 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/parrot/blom/backend/venv/bin/python -m pytest tests/test_redis_helpers.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add redis_helpers.py tests/test_redis_helpers.py
git commit -m "feat: add Redis rate-limit helpers with in-memory fallback
```

---

### Task 3: Wire `redis_helpers` into `routes/auth.py`

**Files:**
- Modify: `routes/auth.py` (add import)
- Test: `tests/test_auth_redis_wiring.py`

**Interfaces:**
- Consumes: all 5 functions from Task 2.
- Produces: `routes.auth` importable without `NameError`; calls `redis_*` succeed (fallback path) and the in-memory dicts (`login_attempts`, `locked_ips`, `registration_log`) are the safety net when Redis is down.

- [ ] **Step 1: Write the failing test**

`tests/test_auth_redis_wiring.py`:

```python
import pytest


@pytest.fixture
def redis_down(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6399/15")


def test_auth_module_imports_redis_helpers(redis_down):
    import routes.auth as auth
    assert callable(auth.redis_increment_login_attempts)


def test_increment_attempts_falls_back_to_memory(redis_down):
    import routes.auth as auth
    auth.login_attempts.clear()
    auth.locked_ips.clear()
    auth._increment_attempts("9.9.9.9")
    assert auth.login_attempts.get("9.9.9.9") == 1
    assert not auth.locked_ips.get("9.9.9.9")


def test_reset_attempts_clears_memory(redis_down):
    import routes.auth as auth
    auth.login_attempts.clear()
    auth.locked_ips.clear()
    auth._increment_attempts("9.9.9.9")
    auth._reset_attempts("9.9.9.9")
    assert "9.9.9.9" not in auth.login_attempts
    assert "9.9.9.9" not in auth.locked_ips


def test_check_registration_limit_falls_back_to_memory(redis_down):
    import routes.auth as auth
    auth.registration_log.clear()
    ip = "9.9.9.9"
    assert auth.check_registration_limit(ip) is True
    auth.log_registration(ip)
    auth.log_registration(ip)
    auth.log_registration(ip)
    assert auth.check_registration_limit(ip) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/parrot/blom/backend/venv/bin/python -m pytest tests/test_auth_redis_wiring.py -v`
Expected: FAIL — `NameError: name 'redis_increment_login_attempts' is not defined`.

- [ ] **Step 3: Add the import to `routes/auth.py`**

Right after the existing imports block (after line 9, `from functools import wraps`):

```python
from redis_helpers import (
    redis_check_registration_limit,
    redis_increment_login_attempts,
    redis_is_locked,
    redis_log_registration,
    redis_reset_login_attempts,
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/parrot/blom/backend/venv/bin/python -m pytest tests/test_auth_redis_wiring.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add routes/auth.py tests/test_auth_redis_wiring.py
git commit -m "fix: wire redis_helpers into auth rate limiting"
```

---

### Task 4: Fix `routes/user.py` imports, add auth-redirect stubs, guard the broker call

**Files:**
- Modify: `routes/user.py`
- Test: `tests/test_user_routes.py`

**Interfaces:**
- Consumes: `validate_website_url` (from `validations.py`), `analyze_business_website` (from `task.py`).
- Produces: `import app` works (blueprints register); `POST /api/business/<id>/analyze` returns 503 and marks the run `failed` when the broker is unreachable; url_for endpoints `user.dashboard`, `user.create_profile`, `user.generate_logbook` resolve.

- [ ] **Step 1: Write the failing tests**

`tests/test_user_routes.py`:

```python
import pytest


@pytest.fixture
def flask_app():
    import app as app_module
    app_module.app.config["TESTING"] = True
    return app_module.app


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()


class FakeQuery:
    def __init__(self, exists, data=None):
        self._exists = exists
        self._data = data or {}

    @property
    def exists(self):
        return self._exists

    def to_dict(self):
        return dict(self._data)


class FakeRef:
    def __init__(self, doc_id):
        self.id = doc_id
        self.updates = []

    def get(self):
        if self.id == "b1":
            return FakeQuery(
                True,
                {"owner_id": "u1", "name": "Test Biz", "website_url": "https://example.com"},
            )
        return FakeQuery(False)

    def collection(self, sub):
        return FakeCollection(sub, parent=self)

    def set(self, data):
        self._set = data

    def update(self, data):
        self.updates.append(data)


class FakeCollection:
    def __init__(self, name, parent=None):
        self.name = name
        self.parent = parent

    def document(self, doc_id=None):
        return FakeRef(doc_id or "auto_run_id")


class FakeDb:
    def collection(self, name):
        return FakeCollection(name)


def test_app_boots_and_blueprints_register(flask_app):
    rules = {r.rule for r in flask_app.url_map.iter_rules()}
    assert "/api/business/<business_id>/analyze" in rules
    assert "/dashboard" in rules
    assert "/create-profile" in rules
    assert "/generate-logbook" in rules


def test_analyze_returns_503_and_fails_run_when_broker_down(monkeypatch, flask_app, client):
    import routes.user as routes_user

    def raise_broker(*args, **kwargs):
        raise RuntimeError("broker unreachable")

    monkeypatch.setattr(routes_user.analyze_business_website, "delay", raise_broker)
    monkeypatch.setattr(routes_user, "db", FakeDb())

    with client.session_transaction() as sess:
        sess["user_id"] = "u1"

    resp = client.post("/api/business/b1/analyze", json={})
    assert resp.status_code == 503
    assert resp.get_json()["success"] is False

    biz_ref = routes_user.db.collection("businesses").document("b1")
    run_ref = biz_ref.collection("agent_runs").document("auto_run_id")
    assert run_ref.updates, "run doc should have been updated"
    assert run_ref.updates[-1]["status"] == "failed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/parrot/blom/backend/venv/bin/python -m pytest tests/test_user_routes.py -v`
Expected: FAIL — either `ModuleNotFoundError: No module named 'tasks'` at import, `NameError: name 'jsonify' is not defined`, or the route assertions fail.

- [ ] **Step 3: Apply the `routes/user.py` fixes**

3a. Fix the Celery task import (there are two identical lines — lines 5 and 10). Replace both with a single import:

```python
from task import analyze_business_website
```

3b. Add `jsonify` to the Flask import (line 1):

```python
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, jsonify
```

3c. Add the URL validator import after the `import uuid`/firestore imports:

```python
from validations import validate_website_url
```

3d. Add three stub routes at the end of `routes/user.py` (so `auth.py:login` redirects resolve):

```python
@business_bp.route("/dashboard", methods=["GET"])
def dashboard():
    return jsonify({"success": True, "message": "Dashboard placeholder"}), 200


@business_bp.route("/create-profile", methods=["GET", "POST"])
def create_profile():
    return jsonify({"success": True, "message": "Profile placeholder"}), 200


@business_bp.route("/generate-logbook", methods=["GET"])
def generate_logbook():
    return jsonify({"success": True, "message": "Logbook placeholder"}), 200
```

3e. Guard the analyzer's broker call (replace the current bare `.delay(...)` block):

```python
    # Send background job to Celery
    try:
        task = analyze_business_website.delay(
            business_id,
            user_id,
            run_id,
        )
    except Exception as exc:
        run_ref.update({
            "status": "failed",
            "error": str(exc),
            "failed_at": datetime.utcnow().isoformat(),
        })
        return jsonify({
            "success": False,
            "error": "Analysis job could not be queued",
            "detail": str(exc),
        }), 503

    # Store Celery task ID
    run_ref.update({
        "task_id": task.id,
    })
```

- [ ] **Step 4: Run all tests**

Run: `/home/parrot/blom/backend/venv/bin/python -m pytest -q`
Expected: 4 auth tests + 2 user tests pass. Note: `redis_helpers` tests also run (4).

- [ ] **Step 5: Commit**

```bash
git add routes/user.py tests/test_user_routes.py
git commit -m "fix: repair user route imports, add redirect stubs, guard broker enqueue"
```

---

### Task 5: Bring up the infrastructure and verify it

**Files:** none (no code changes).

**Interfaces:**
- Produces: Redis running on `localhost:6379`; Celery worker for `task` module registered and ready; fresh Flask on `:5000` with `DEBUG=True`.

- [ ] **Step 1: Start Redis**

```bash
redis-server --daemonize yes
redis-cli ping
```
Expected: `PONG`.

- [ ] **Step 2: Start the Celery worker (background)**

```bash
nohup /home/parrot/blom/backend/venv/bin/celery -A task worker --loglevel=info > /tmp/celery_worker.log 2>&1 &
sleep 4
grep -E "ready\.|mingle|celery@" /tmp/celery_worker.log | head -5
```
Expected: log lines showing the worker started and `tasks.analyze_business_website` registered.

- [ ] **Step 3: Restart Flask with `DEBUG=True`**

```bash
pkill -f "python app.py" || true
sleep 1
cd /home/parrot/blom/backend
nohup env DEBUG=True ./venv/bin/python app.py > /tmp/flask.log 2>&1 &
sleep 3
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5000/login
```
Expected: `200`.

- [ ] **Step 4: Verify the broker is reachable (smoke)**

```bash
cd /home/parrot/blom/backend
./venv/bin/python - <<'PY'
from task import celery
conn = celery.connection()
conn.ensure_connection(timeout=5)
print("broker OK:", conn.as_uri())
conn.release()
PY
```
Expected: prints `broker OK: redis://localhost:6379/0` without raising. (This checks broker connectivity only — no task is enqueued, so the worker and Firestore are untouched.)

- [ ] **Step 5: Commit (none — no code changes in this task)**

No commit. Proceed to Task 6.

---

### Task 6: E2E happy path — write and run `scripts/e2e_analyze_flow.py`

**Files:**
- Create: `scripts/e2e_analyze_flow.py`

**Interfaces:**
- Consumes: running stack from Task 5; Flask session cookie (CSRF token decoding via `SecureCookieSessionInterface`); Firestore + Firebase Auth for verification and cleanup.
- Produces: a repeatable E2E driver with `main()` running the happy path and `--fail-case` running the failure path; prints a PASS/FAIL summary.

- [ ] **Step 1: Write the script**

`scripts/e2e_analyze_flow.py`:

```python
import os
import secrets
import sys
import time

import requests
from flask.sessions import SecureCookieSessionInterface

BASE = os.environ.get("E2E_BASE", "http://127.0.0.1:5000")


def _csrf(session_cookie):
    from app import app as flask_app
    serializer = SecureCookieSessionInterface().get_signing_serializer(flask_app)
    data = serializer.loads(session_cookie)
    return data.get("_login_csrf")


def _new_session():
    return requests.Session(), requests.Session(), requests.Session()


def register_and_login(rand):
    s = requests.Session()
    email = f"e2e-{rand}@blom.test"
    pw = secrets.token_urlsafe(12)

    r = s.get(f"{BASE}/login")
    assert r.status_code == 200
    csrf = _csrf(s.cookies.get("session"))

    r = s.post(
        f"{BASE}/register",
        data={"username": f"e2euser-{rand}", "email": email, "password": pw, "confirm_password": pw},
        allow_redirects=False,
    )
    assert r.status_code == 302, r.text

    r = s.post(
        f"{BASE}/login",
        data={"email": email, "password": pw, "device_id": "e2e-device", "login_token": csrf},
        allow_redirects=False,
    )
    assert r.status_code == 302, r.text
    return s, email


def create_business(s, name, url):
    r = s.post(f"{BASE}/api/business", json={"name": name, "website_url": url})
    assert r.status_code == 201, r.text
    return r.json()["business"]["id"]


def trigger_analyze(s, biz_id):
    r = s.post(f"{BASE}/api/business/{biz_id}/analyze", json={})
    assert r.status_code == 202, r.text
    return r.json()["run_id"], r.json()["task_id"]


def poll_run(biz_id, run_id, timeout=90):
    from firebase import db
    run_ref = db.collection("businesses").document(biz_id).collection("agent_runs").document(run_id)
    deadline = time.time() + timeout
    doc = None
    while time.time() < deadline:
        doc = run_ref.get()
        if not doc.exists:
            time.sleep(1)
            continue
        data = doc.to_dict()
        if data.get("status") in ("completed", "failed"):
            return data
        time.sleep(1)
    return doc.to_dict() if doc else {}


def run_happy(rand):
    s, email = register_and_login(rand)
    biz_id = create_business(s, "E2E Happy Business", "https://example.com")
    run_id, task_id = trigger_analyze(s, biz_id)
    print(f"[happy] biz={biz_id} run={run_id} task={task_id}")
    data = poll_run(biz_id, run_id)
    assert data.get("status") == "completed", f"expected completed, got {data}"
    obs_id = data.get("observation_id")
    assert obs_id, "run missing observation_id"
    from firebase import db
    obs = db.collection("businesses").document(biz_id).collection("observations").document(obs_id).get()
    assert obs.exists, "observation doc missing"
    analysis = obs.to_dict().get("analysis") or {}
    assert analysis.get("title") or analysis.get("headings"), "analysis empty"
    print(f"[happy] PASS observation={obs_id} status=completed")
    return email, [biz_id]


def run_failure(rand):
    s, email = register_and_login(rand)
    from firebase import db
    biz_id = create_business(s, "E2E Failure Business", f"https://does-not-exist-{rand}.invalid")
    run_id, task_id = trigger_analyze(s, biz_id)
    print(f"[fail] biz={biz_id} run={run_id} task={task_id}")
    data = poll_run(biz_id, run_id)
    assert data.get("status") == "failed", f"expected failed, got {data}"
    assert data.get("error"), "failed run missing error field"
    print(f"[fail] PASS run failed with error={data.get('error')!r}")
    return email, [biz_id]


def cleanup(emails, biz_ids):
    from firebase import db
    from firebase_admin import auth as admin_auth
    for biz_id in biz_ids:
        ref = db.collection("businesses").document(biz_id)
        for sub in ("observations", "agent_runs"):
            for doc in ref.collection(sub).stream():
                doc.reference.delete()
        ref.delete()
        print(f"[cleanup] deleted business {biz_id}")
    for email in emails:
        q = db.collection("users").where("email", "==", email).limit(1).get()
        if q:
            uid = q[0].id
            db.collection("users").document(uid).delete()
            try:
                admin_auth.delete_user(uid)
            except Exception as exc:
                print(f"[cleanup] auth delete failed for {uid}: {exc}")
            print(f"[cleanup] deleted user {uid}")


def main():
    emails, biz_ids = [], []
    for fn in ("run_happy", "run_failure"):
        if fn == "run_happy" or "--fail-case" in sys.argv:
            try:
                email, ids = getattr(sys.modules[__name__], fn)(secrets.token_hex(4))
                emails.append(email)
                biz_ids.extend(ids)
            except AssertionError as exc:
                print(f"[FAIL] {fn}: {exc}")
                cleanup(emails, biz_ids)
                sys.exit(1)
    cleanup(emails, biz_ids)
    print("E2E PASS")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the happy path**

Run (from `/home/parrot/blom/backend`):
```bash
./venv/bin/python scripts/e2e_analyze_flow.py
```
Expected stdout:
```
[happy] biz=... run=... task=...
[happy] PASS observation=... status=completed
```
(Without `--fail-case`, the failure phase is skipped in this loop implementation — Step 1 run validates the happy path and cleanup.)

- [ ] **Step 3: Verify cleanup ran**

Run:
```bash
./venv/bin/python - <<'PY'
from firebase import db
n = len(list(db.collection("businesses").where("name", "==", "E2E Happy Business").stream()))
print("remaining happy-test businesses:", n)
PY
```
Expected: `remaining happy-test businesses: 0`.

- [ ] **Step 4: Commit**

```bash
git add scripts/e2e_analyze_flow.py
git commit -m "test: add E2E driver for background analysis flow"
```

---

### Task 7: E2E failure path + final device verification

**Files:**
- Modify: `scripts/e2e_analyze_flow.py` (main() drives both phases by default)

**Interfaces:**
- Consumes: Task 6's `run_happy`, `run_failure`, `cleanup`.
- Produces: a single-command E2E that exercises happy + failure + cleanup, and a documented pass/fail.

- [ ] **Step 1: Make `main()` always run both phases**

Replace the `main()` body in `scripts/e2e_analyze_flow.py`:

```python
def main():
    emails, biz_ids = [], []
    for fn in ("run_happy", "run_failure"):
        try:
            email, ids = getattr(sys.modules[__name__], fn)(secrets.token_hex(4))
            emails.append(email)
            biz_ids.extend(ids)
        except AssertionError as exc:
            print(f"[FAIL] {fn}: {exc}")
            cleanup(emails, biz_ids)
            sys.exit(1)
    cleanup(emails, biz_ids)
    print("E2E PASS")
```

- [ ] **Step 2: Run the full E2E**

Run (from `/home/parrot/blom/backend`):
```bash
./venv/bin/python scripts/e2e_analyze_flow.py
```
Expected stdout, in order:
```
[happy] biz=... run=... task=...
[happy] PASS observation=... status=completed
[fail]  biz=... run=... task=...
[fail]  PASS run failed with error=...
[cleanup] deleted business ...
[cleanup] deleted user ...
E2E PASS
```

- [ ] **Step 3: Confirm the failure run carried a real error (not a raised/ignored one)**

The `[fail] PASS` line proves `status=failed` AND `error` was set by the worker's
`except` block in `task.py`. If the line shows `run failed with error='...'`, record
the exact message in your final report (expected values: a DNS-resolution `ValueError`
from `website_analyzer.validate_and_pin`).

- [ ] **Step 4: Confirm test artifacts are gone from Firestore and Auth**

Run:
```bash
./venv/bin/python - <<'PY'
from firebase import db
for name in ("E2E Happy Business", "E2E Failure Business"):
    leftover = list(db.collection("businesses").where("name", "==", name).stream())
    print(name, "leftover docs:", len(leftover))
users = [u for u in db.collection("users").where("email", ">=", "e2e-").where("email", "<", "e2e/").stream()]
print("e2e user docs remaining:", len(users))
PY
```
Expected: all zeros.

- [ ] **Step 5: Commit**

```bash
git add scripts/e2e_analyze_flow.py
git commit -m "test: run full E2E happy + failure + cleanup"
```

---

### Task 8: Final verification & handoff

**Files:** none.

- [ ] **Step 1: Run the full unit suite once more**

Run: `/home/parrot/blom/backend/venv/bin/python -m pytest -q`
Expected: all tests pass (redis_helpers ×4, auth wiring ×4, user routes ×2).

- [ ] **Step 2: Show the shipped diff summary**

Run: `git -C /home/parrot/blom/backend log --oneline` and `git -C /home/parrot/blom/backend status`
Expected: clean working tree; commits `chore: init repo…`, `feat: add Redis rate-limit helpers…`, `fix: wire redis_helpers into auth…`, `fix: repair user route imports…`, `test: add E2E driver…`, `test: run full E2E…`.

- [ ] **Step 3: Report**

Summarize for the user:
1. Files changed and why.
2. Full E2E chain result (Redis → Celery worker → analyze endpoint → agent_runs → fetch → observations), happy + failure.
3. Remaining infrastructure still running (Redis, Celery worker, Flask with `DEBUG=True`) and how to stop/restart in production mode (`DEBUG` unset).