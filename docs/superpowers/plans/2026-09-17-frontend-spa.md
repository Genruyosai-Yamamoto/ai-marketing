# Frontend SPA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the product's first usable UI as a same-origin static SPA (HTML + Tailwind CSS CDN + vanilla JS) served by the existing Flask app, covering auth (login/register), a business dashboard (list/create/edit/delete), and business detail (analyze → poll run, opportunities, actions approve/reject).

**Architecture:** One `static/` folder served by Flask (same origin → the HttpOnly `SameSite=Lax` session cookie just works, no CORS). `index.html` is a shell with view containers; `js/api.js` is a thin fetch wrapper; `js/app.js` is the view router + handlers. Two new backend JSON reads (`GET /api/business`, `GET /api/business/<id>`) land in a new `routes/business_api.py` blueprint so nothing in the user's WIP files is touched.

**Tech Stack:** Flask (backend), Tailwind CSS via CDN (`cdn.tailwindcss.com`) + Inter font, vanilla JS (ES2017+, no framework, no build step), pytest (backend tests), `node --check` (JS syntax verification).

## Global Constraints

- **Session-cookie auth only.** No tokens in `localStorage`/`sessionStorage`. The HttpOnly cookie governs login. Same-origin only; do not add CORS.
- **Backend envelope contract (verbatim):** success `{"success": true, ...}`, error `{"success": false, "error": "<message>"}`. The UI must display the server's `error` string verbatim and must never invent its own copy.
- **Endpoint semantics (verbatim):** handle these by HTTP status from the existing routes — register `201`/`400`/`409`/`429`/`500`, login `200`/`400`/`401`/`403`/`423`/`500`, logout `200`, me `200`/`401`, business create `201`/`400`/`401`, business update `200`/`400`/`401`/`403`/`404`, business delete `200`/`401`/`403`/`404`, analyze `202`/`400`/`401`/`403`/`404`/`503`, runs/latest `200`/`401`/`403`/`404`, opportunities `200`/`401`/`403`/`404`, actions `200`/`401`/`403`/`404`, approve `202`/`400`/`401`/`403`/`404`, reject `200`/`400`/`401`/`403`/`404`.
- **Analyze/run polling:** poll `GET /api/business/<id>/runs/latest` every 3 s until `status` is terminal (`completed` or `failed`); then stop. Show the run's `error` string on failure.
- **Never stage, modify, or remove the user's dirty/untracked files:** `agent/prompts.py`, `routes/user.py`, `scripts/live_opportunity_flow.py`, `task.py`, `tests/test_user_routes.py`, `agent/decision_engine.py`, `config/`, `connectors/`, `services/`, `routes/instagram_connections.py`, `tests/test_task_pipeline.py`, `hello.txt`, and any other `docs/superpowers/plans/` / `docs/superpowers/specs/` files (except this workstream's own spec via `git add docs/superpowers/specs/2026-09-17-frontend-spa-design.md`).
- **`app.py` selective staging (only for Task 1):** the working-tree `app.py` already contains the user's uncommitted lines (`from routes.instagram_connections import ...`, `app.register_blueprint(instagram_connections_bp)`, `PORT 8000`). Staged content for the commit must be `git show HEAD:app.py` + ONLY this feature's two `business_api` lines. Procedure: edit the working tree, `cp app.py /tmp/opencode/app.py.staged`, strip the user's three lines from the staged copy, `cp /tmp/opencode/app.py.staged app.py && git add app.py`, then restore the working-tree file from the pre-edit copy. Never `git add -A`.
- **Test commands:** backend `./venv/bin/python -m pytest <file> -v`; JS syntax `node --check static/js/api.js && node --check static/js/app.js`.
- **Accept-the-drift baseline:** the full suite currently sits at **107 passed + 3 failed** (the 3 are the user's uncommitted `InstagramConnector.execute(action, business_id, user_id)` refactor vs the committed connector/execution-engine tests — accepted drift, do NOT fix). This plan's work must not introduce regressions; new tests add to the passing count.
- **Demo/dummy data must never reach Firestore or local storage.** The SPA renders whatever the backend returns; no seeded fixtures in frontend code.

---

### Task 0: Commit the design spec

**Files:**
- Modify: `docs/superpowers/specs/2026-09-17-frontend-spa-design.md` (already written; commit only)

**Interfaces:**
- Consumes: nothing.
- Produces: a committed design reference for all later tasks.

- [ ] **Step 1: Commit the spec**

```bash
git add docs/superpowers/specs/2026-09-17-frontend-spa-design.md
git commit -m "docs: frontend spa design spec"
```

- [ ] **Step 2: Verify only the spec is staged**

```bash
git status --short
```
Expected: staged entry for the spec only; all user dirty/untracked files remain unstaged/untouched.

---

### Task 1: Backend business read API (`GET /api/business` + `GET /api/business/<id>`)

**Files:**
- Create: `routes/business_api.py`
- Test: `tests/test_business_api.py`
- Modify: `app.py` (register `business_api_bp`; selective staging only)

**Interfaces:**
- Consumes: `firebase.db` (real Firestore `db` object the way `routes/user.py` uses it), Flask `session` for `session["user_id"]`.
- Produces:
  - `business_api_bp` — `Blueprint("business_api", __name__)`
  - `GET /api/business` → `200 {"success": true, "businesses": [{"id": str, **stored_business_data}]}`; `401 {"success": false, "error": "Authentication required"}` when no `session["user_id"]`.
  - `GET /api/business/<business_id>` → `200 {"success": true, "business": {"id": str, **stored_business_data}}`; `401` (no session), `404 {"success": false, "error": "Business not found"}`, `403 {"success": false, "error": "You do not have permission to view this business"}`. Guard order: session → existence → ownership (matches `routes/user.py`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_business_api.py`:

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


class BizSnapshot:
    def __init__(self, data, doc_id):
        self.exists = data is not None
        self._data = dict(data) if data else {}
        self.id = doc_id

    def to_dict(self):
        return dict(self._data)


class BizQuery:
    def __init__(self, snapshots):
        self._snapshots = list(snapshots)

    def stream(self):
        return iter(self._snapshots)


class BizRef:
    def __init__(self, db, path):
        self._db = db
        self.path = tuple(path)
        self.id = self.path[-1]

    def get(self):
        return BizSnapshot(self._db._store.get(self.path), self.id)

    def set(self, data):
        self._db._store[self.path] = dict(data)


class BizCollection:
    def __init__(self, db, path):
        self._db = db
        self.path = tuple(path)

    def document(self, doc_id):
        return BizRef(self._db, self.path + (doc_id,))

    def where(self, *args, **kwargs):
        if kwargs.get("filter") is not None:
            field, op, value = (
                kwargs["filter"].field_path,
                kwargs["filter"].op_string,
                kwargs["filter"].value,
            )
        else:
            field, op, value = args[:3]
        found = []
        for path, data in self._db._store.items():
            if len(path) == len(self.path) + 1 and path[: len(self.path)] == self.path:
                if op == "==" and data.get(field) == value:
                    found.append(BizSnapshot(data, path[-1]))
        return BizQuery(found)


class BizDb:
    def __init__(self):
        self._store = {}

    def collection(self, name):
        return BizCollection(self, (name,))


@pytest.fixture
def fake_db(monkeypatch):
    import routes.business_api as business_api

    db = BizDb()
    monkeypatch.setattr(business_api, "db", db)
    return db


def seed(db, biz_id, data):
    db.collection("businesses").document(biz_id).set(data)


def test_business_api_blueprint_registered(flask_app):
    rules = {r.rule for r in flask_app.url_map.iter_rules()}
    assert "/api/business" in rules
    assert "/api/business/<business_id>" in rules


def test_list_unauthenticated_401(client):
    resp = client.get("/api/business")
    assert resp.status_code == 401
    assert resp.get_json() == {"success": False, "error": "Authentication required"}


def test_list_returns_only_callers_businesses(fake_db, client):
    seed(fake_db, "b1", {"owner_id": "u1", "name": "One", "created_at": "t1"})
    seed(fake_db, "b2", {"owner_id": "u2", "name": "Two", "created_at": "t2"})
    with client.session_transaction() as sess:
        sess["user_id"] = "u1"

    resp = client.get("/api/business")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["businesses"] == [
        {"id": "b1", "owner_id": "u1", "name": "One", "created_at": "t1"}
    ]


def test_list_empty(fake_db, client):
    with client.session_transaction() as sess:
        sess["user_id"] = "u1"

    resp = client.get("/api/business")
    assert resp.status_code == 200
    assert resp.get_json() == {"success": True, "businesses": []}


def test_get_unauthenticated_401(client):
    resp = client.get("/api/business/b1")
    assert resp.status_code == 401
    assert resp.get_json() == {"success": False, "error": "Authentication required"}


def test_get_not_found_404(fake_db, client):
    with client.session_transaction() as sess:
        sess["user_id"] = "u1"

    resp = client.get("/api/business/missing")
    assert resp.status_code == 404
    assert resp.get_json() == {"success": False, "error": "Business not found"}


def test_get_non_owner_403(fake_db, client):
    seed(fake_db, "b1", {"owner_id": "u2", "name": "Two"})
    with client.session_transaction() as sess:
        sess["user_id"] = "u1"

    resp = client.get("/api/business/b1")
    assert resp.status_code == 403
    assert resp.get_json() == {
        "success": False,
        "error": "You do not have permission to view this business",
    }


def test_get_owner_200(fake_db, client):
    data = {
        "owner_id": "u1",
        "name": "One",
        "website_url": "https://example.com",
        "industry": "retail",
        "description": "desc",
        "created_at": "t1",
        "updated_at": "t1",
    }
    seed(fake_db, "b1", data)
    with client.session_transaction() as sess:
        sess["user_id"] = "u1"

    resp = client.get("/api/business/b1")
    assert resp.status_code == 200
    assert resp.get_json() == {"success": True, "business": {"id": "b1", **data}}


def test_guard_order_unauthenticated_beats_404(fake_db, client):
    seed(fake_db, "b1", {"owner_id": "u1", "name": "One"})

    resp = client.get("/api/business/b1")
    assert resp.status_code == 401  # no session → 401, NOT 404 or 403
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
./venv/bin/python -m pytest tests/test_business_api.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'routes.business_api'` (the blueprint import in `app.py` also fails until the module and registration exist). At minimum, `test_business_api_blueprint_registered` must fail.

- [ ] **Step 3: Write the module**

Create `routes/business_api.py`:

```python
from flask import Blueprint, jsonify, session

from firebase import db

business_api_bp = Blueprint("business_api", __name__)


@business_api_bp.route("/api/business", methods=["GET"])
def list_businesses():
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({
            "success": False,
            "error": "Authentication required",
        }), 401

    businesses = (
        db.collection("businesses")
        .where("owner_id", "==", user_id)
        .stream()
    )

    business_list = [
        {"id": doc.id, **doc.to_dict()}
        for doc in businesses
    ]

    return jsonify({
        "success": True,
        "businesses": business_list,
    }), 200


@business_api_bp.route("/api/business/<business_id>", methods=["GET"])
def get_business(business_id):
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({
            "success": False,
            "error": "Authentication required",
        }), 401

    business_ref = db.collection("businesses").document(business_id)
    business_doc = business_ref.get()

    if not business_doc.exists:
        return jsonify({
            "success": False,
            "error": "Business not found",
        }), 404

    business = business_doc.to_dict()

    if business.get("owner_id") != user_id:
        return jsonify({
            "success": False,
            "error": "You do not have permission to view this business",
        }), 403

    return jsonify({
        "success": True,
        "business": {
            "id": business_doc.id,
            **business,
        },
    }), 200
```

- [ ] **Step 4: Register the blueprint in `app.py` (selective staging)**

Edit the working-tree `app.py` with two exact edits:

Edit 1 — after the line `from routes.auth_api import api_auth_bp`, add:

```python
from routes.business_api import business_api_bp
```

Edit 2 — after the line `app.register_blueprint(api_auth_bp)`, add:

```python
app.register_blueprint(business_api_bp)
```

Then stage **only** this feature's lines (never the user's `instagram_connections`/`PORT` changes):

```bash
cp app.py /tmp/opencode/app.py.worktree.pre
cp app.py /tmp/opencode/app.py.staged
# Remove the user's uncommitted lines from the staged copy:
sed -i '/from routes.instagram_connections import instagram_connections_bp/d' /tmp/opencode/app.py.staged
sed -i '/app.register_blueprint(instagram_connections_bp)/d' /tmp/opencode/app.py.staged
sed -i 's/int(os.environ.get("PORT", 8000))/int(os.environ.get("PORT", 5000))/' /tmp/opencode/app.py.staged
cp /tmp/opencode/app.py.staged app.py
git add app.py
cp /tmp/opencode/app.py.worktree.pre app.py
```

Verify the staged diff touches only this feature:

```bash
git diff --cached app.py
```
Expected: only the `from routes.business_api import business_api_bp` import and `app.register_blueprint(business_api_bp)` registration (the `api_auth` lines are already in HEAD from the earlier auth workstream).

- [ ] **Step 5: Run tests to verify they pass**

```bash
./venv/bin/python -m pytest tests/test_business_api.py -v
```
Expected: all 9 tests PASS.

- [ ] **Step 6: Run the full suite for regressions**

```bash
./venv/bin/python -m pytest -q
```
Expected: 116 passed, 3 failed — the 3 failures must be exactly the accepted drift (`test_instagram_connector_accepts_social_action`, `test_instagram_connector_rejects_non_social_action`, `test_execute_action_completed_social`). No new failures. (Baseline 107 + this task's 9 tests = 116; the plan-wide target of 118 lands after Task 2 adds `test_frontend_static.py`'s 2 tests.)

- [ ] **Step 7: Commit**

```bash
git add routes/business_api.py tests/test_business_api.py
git commit -m "feat: add business read API endpoints"
```

- [ ] **Step 8: Verify working tree still has the user's lines**

```bash
git diff app.py | grep -E "instagram_connections|PORT" | head
```
Expected: the user's `instagram_connections` import/registration and `PORT`, 8000 remain as unstaged working-tree changes.

---

### Task 2: SPA shell (`index.html` + `js/api.js`) and serve it from `/`

**Files:**
- Create: `static/index.html`
- Create: `static/js/api.js`
- Modify: `routes/auth.py` (`home()` body only, one line)
- Test: `tests/test_frontend_static.py`

**Interfaces:**
- Consumes: nothing from Task 1 (backend reads land in Tasks 5's detail flow; this task only builds the shell + fetch wrapper).
- Produces:
  - `static/index.html` — Tailwind CDN + Inter, `<div id="toast-container">`, navbar (`#nav-brand`, `#nav-auth`, `#theme-toggle`), view containers `#view-login`, `#view-register`, `#view-dashboard`, `#view-business`, business form modal `#business-modal`, delete modal `#delete-modal`, all with the exact element ids listed below in `app.js` (Task 3/4 consume them).
  - `static/js/api.js` — exports global `apiFetch(path, options)`.
  - `routes/auth.py:home()` returns `current_app.send_static_file("index.html")`.
  - `GET /` → 200, HTML containing `js/api.js` and `js/app.js`; `GET /static/js/api.js` → 200; `GET /static/js/app.js` → 200.

- [ ] **Step 1: Write the failing static-serving test**

Create `tests/test_frontend_static.py`:

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


def test_home_serves_spa(client):
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "js/api.js" in html
    assert "js/app.js" in html


def test_static_js_served(client):
    for asset in ("/static/js/api.js", "/static/js/app.js"):
        resp = client.get(asset)
        assert resp.status_code == 200
        assert len(resp.data) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
./venv/bin/python -m pytest tests/test_frontend_static.py -v
```
Expected: FAIL — `home.html` renders blank (or the file missing), assets 404 (no `static/` yet).

- [ ] **Step 3: Write `static/js/api.js`**

Create `static/js/api.js`:

```javascript
const AUTH_ROUTES = ["/api/auth/login", "/api/auth/register", "/api/auth/logout"];

async function apiFetch(path, options = {}) {
  const opts = {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    ...options,
  };
  if (opts.body && typeof opts.body !== "string") {
    opts.body = JSON.stringify(opts.body);
  }

  let resp;
  try {
    resp = await fetch(path, opts);
  } catch (err) {
    throw { message: "Network error. Please try again.", status: 0 };
  }

  let body = null;
  try {
    body = await resp.json();
  } catch (err) {
    body = null;
  }

  if (!resp.ok) {
    if (resp.status === 401 && !AUTH_ROUTES.includes(path)) {
      document.dispatchEvent(new CustomEvent("session-expired"));
    }
    const message = (body && body.error) || "Request failed.";
    throw { message, status: resp.status };
  }
  return body;
}
```

- [ ] **Step 4: Write `static/index.html`**

Create `static/index.html`. It must include (exact ids are consumed by `app.js` in Tasks 3–4; do not rename):

```html
<!DOCTYPE html>
<html lang="en" class="h-full">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>blom</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      darkMode: "class",
      theme: {
        extend: {
          fontFamily: { sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"] },
        },
      },
    };
  </script>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" />
  <script src="/static/js/api.js" defer></script>
  <script src="/static/js/app.js" defer></script>
</head>
<body class="h-full bg-gray-50 text-gray-900 dark:bg-gray-950 dark:text-gray-100 font-sans antialiased">
  <div id="toast-container" class="fixed top-4 right-4 z-[60] space-y-2 w-80 max-w-[90vw]"></div>

  <nav class="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 sticky top-0 z-40">
    <div class="max-w-6xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
      <div id="nav-brand" class="text-lg font-bold tracking-tight text-indigo-600 dark:text-indigo-400">
        blom
      </div>
      <div id="nav-auth" class="hidden items-center gap-3">
        <button id="theme-toggle" class="text-sm text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white" type="button">
          Toggle theme
        </button>
        <button id="logout-btn" class="text-sm text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white" type="button">
          Log out
        </button>
      </div>
    </div>
  </nav>

  <!-- ── LOGIN ───────────────────────────────────────────── -->
  <section id="view-login" data-view="login" class="hidden max-w-md mx-auto px-4 py-16">
    <div class="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 p-8">
      <h1 class="text-2xl font-bold mb-6">Sign in</h1>
      <div id="login-error" class="hidden mb-4 text-sm text-red-700 dark:text-red-400"></div>
      <form id="login-form" class="space-y-4">
        <div>
          <label for="login-email" class="block text-sm font-medium mb-1">Email</label>
          <input id="login-email" type="email" required
                 class="w-full rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
        </div>
        <div>
          <label for="login-password" class="block text-sm font-medium mb-1">Password</label>
          <input id="login-password" type="password" required
                 class="w-full rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
        </div>
        <button id="login-submit" type="submit"
                class="w-full rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold py-2.5 disabled:opacity-60">
          Sign in
        </button>
      </form>
      <p class="mt-6 text-sm text-gray-600 dark:text-gray-400">
        No account?
        <button id="login-btn-register" type="button" class="text-indigo-600 dark:text-indigo-400 font-medium">Create one</button>
      </p>
    </div>
  </section>

  <!-- ── REGISTER ────────────────────────────────────────── -->
  <section id="view-register" data-view="register" class="hidden max-w-md mx-auto px-4 py-16">
    <div class="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 p-8">
      <h1 class="text-2xl font-bold mb-6">Create your account</h1>
      <div id="register-error" class="hidden mb-4 text-sm text-red-700 dark:text-red-400"></div>
      <form id="register-form" class="space-y-4">
        <div>
          <label for="register-username" class="block text-sm font-medium mb-1">Username</label>
          <input id="register-username" type="text" required autocomplete="username"
                 class="w-full rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
        </div>
        <div>
          <label for="register-email" class="block text-sm font-medium mb-1">Email</label>
          <input id="register-email" type="email" required autocomplete="email"
                 class="w-full rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
        </div>
        <div>
          <label for="register-password" class="block text-sm font-medium mb-1">Password</label>
          <input id="register-password" type="password" required autocomplete="new-password"
                 class="w-full rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
        </div>
        <div>
          <label for="register-confirm" class="block text-sm font-medium mb-1">Confirm password</label>
          <input id="register-confirm" type="password" required autocomplete="new-password"
                 class="w-full rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
        </div>
        <button id="register-submit" type="submit"
                class="w-full rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold py-2.5 disabled:opacity-60">
          Create account
        </button>
      </form>
      <p class="mt-6 text-sm text-gray-600 dark:text-gray-400">
        Already have an account?
        <button id="register-btn-login" type="button" class="text-indigo-600 dark:text-indigo-400 font-medium">Sign in</button>
      </p>
    </div>
  </section>

  <!-- ── DASHBOARD ───────────────────────────────────────── -->
  <section id="view-dashboard" data-view="dashboard" class="hidden max-w-6xl mx-auto px-4 sm:px-6 py-8">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold">Your businesses</h1>
      <button id="create-business-btn"
              class="rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold px-4 py-2.5">
        New business
      </button>
    </div>
    <div id="business-grid" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"></div>
    <div id="dashboard-empty" class="hidden text-center py-24 text-gray-500 dark:text-gray-400">
      <p class="text-lg font-medium">No businesses yet</p>
      <p class="mt-1 text-sm">Create your first business to get started.</p>
    </div>
  </section>

  <!-- ── BUSINESS DETAIL ─────────────────────────────────── -->
  <section id="view-business" data-view="business" class="hidden max-w-4xl mx-auto px-4 sm:px-6 py-8">
    <button id="back-to-dashboard" class="text-sm text-indigo-600 dark:text-indigo-400 mb-4">← Back to dashboard</button>

    <div class="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 p-6 mb-6">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 id="biz-name" class="text-2xl font-bold"></h1>
          <p id="biz-industry" class="text-sm text-gray-500 dark:text-gray-400 mt-1"></p>
          <a id="biz-website" target="_blank" rel="noopener noreferrer"
             class="text-sm text-indigo-600 dark:text-indigo-400 mt-1 inline-block"></a>
          <p id="biz-description" class="text-sm text-gray-600 dark:text-gray-300 mt-2"></p>
        </div>
        <div class="flex gap-2">
          <button id="biz-edit-btn" type="button"
                  class="rounded-lg border border-gray-300 dark:border-gray-700 text-sm px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-800">Edit</button>
          <button id="biz-delete-btn" type="button"
                  class="rounded-lg border border-red-300 dark:border-red-800 text-sm px-3 py-2 text-red-700 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950">Delete</button>
        </div>
      </div>

      <div class="mt-6 pt-6 border-t border-gray-200 dark:border-gray-800">
        <button id="analyze-btn"
                class="rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold px-4 py-2.5 disabled:opacity-60">
          Analyze website
        </button>
        <div id="run-status" class="mt-3"></div>
      </div>
    </div>

    <div class="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 p-6 mb-6">
      <h2 class="text-lg font-semibold mb-4">Opportunities</h2>
      <div id="opportunities-list" class="space-y-3"></div>
      <div id="opportunities-empty" class="hidden text-sm text-gray-500 dark:text-gray-400">
        Run an analysis to find opportunities.
      </div>
    </div>

    <div class="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 p-6">
      <h2 class="text-lg font-semibold mb-4">Actions</h2>
      <div id="actions-list" class="space-y-3"></div>
      <div id="actions-empty" class="hidden text-sm text-gray-500 dark:text-gray-400">No actions yet.</div>
    </div>
  </section>

  <!-- ── BUSINESS FORM MODAL ─────────────────────────────── -->
  <div id="business-modal" class="hidden fixed inset-0 z-50 flex items-center justify-center">
    <div class="absolute inset-0 bg-black/40" data-close="business-modal"></div>
    <div class="relative bg-white dark:bg-gray-900 rounded-xl shadow-lg p-6 w-full max-w-lg mx-4">
      <h2 id="business-modal-title" class="text-lg font-semibold mb-4">New business</h2>
      <div id="business-form-error" class="hidden mb-3 text-sm text-red-700 dark:text-red-400"></div>
      <form id="business-form" class="space-y-4">
        <input id="business-id" type="hidden" />
        <div>
          <label for="business-field-name" class="block text-sm font-medium mb-1">Name</label>
          <input id="business-field-name" type="text" required
                 class="w-full rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
        </div>
        <div>
          <label for="business-field-website" class="block text-sm font-medium mb-1">Website URL</label>
          <input id="business-field-website" type="url"
                 class="w-full rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
        </div>
        <div>
          <label for="business-field-industry" class="block text-sm font-medium mb-1">Industry</label>
          <input id="business-field-industry" type="text"
                 class="w-full rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
        </div>
        <div>
          <label for="business-field-description" class="block text-sm font-medium mb-1">Description</label>
          <textarea id="business-field-description" rows="3"
                    class="w-full rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"></textarea>
        </div>
        <div class="flex justify-end gap-2">
          <button type="button" data-close="business-modal"
                  class="rounded-lg border border-gray-300 dark:border-gray-700 text-sm px-4 py-2 hover:bg-gray-50 dark:hover:bg-gray-800">Cancel</button>
          <button id="business-submit" type="submit"
                  class="rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold px-4 py-2 disabled:opacity-60">Save</button>
        </div>
      </form>
    </div>
  </div>

  <!-- ── DELETE CONFIRM MODAL ────────────────────────────── -->
  <div id="delete-modal" class="hidden fixed inset-0 z-50 flex items-center justify-center">
    <div class="absolute inset-0 bg-black/40" data-close="delete-modal"></div>
    <div class="relative bg-white dark:bg-gray-900 rounded-xl shadow-lg p-6 w-full max-w-md mx-4">
      <h2 class="text-lg font-semibold mb-2">Delete business?</h2>
      <p class="text-sm text-gray-600 dark:text-gray-300 mb-5">
        <span id="delete-biz-name"></span> and all of its data will be permanently removed.
      </p>
      <div class="flex justify-end gap-2">
        <button type="button" data-close="delete-modal"
                class="rounded-lg border border-gray-300 dark:border-gray-700 text-sm px-4 py-2 hover:bg-gray-50 dark:hover:bg-gray-800">Cancel</button>
        <button id="delete-confirm"
                class="rounded-lg bg-red-600 hover:bg-red-700 text-white text-sm font-semibold px-4 py-2 disabled:opacity-60">Delete</button>
      </div>
    </div>
  </div>
</body>
</html>
```

- [ ] **Step 5: Create a placeholder `static/js/app.js`**

Create `static/js/app.js` with a single line so `/static/js/app.js` resolves during Task 2 (full logic lands in Tasks 3–4):

```javascript
console.log("blom app shell loaded");
```

- [ ] **Step 6: Point `auth_bp.home()` at the SPA**

In `routes/auth.py`, replace:

```python
@auth_bp.route("/")
def home():
    return render_template("home.html")
```

with:

```python
@auth_bp.route("/")
def home():
    return current_app.send_static_file("index.html")
```

`current_app` is already imported at the top of `routes/auth.py`.

- [ ] **Step 7: Run tests to verify they pass**

```bash
./venv/bin/python -m pytest tests/test_frontend_static.py -v
```
Expected: both tests PASS (home serves the SPA, both JS assets 200).

- [ ] **Step 8: Verify JS assets are syntax-valid**

```bash
node --check static/js/api.js && node --check static/js/app.js
```
Expected: both exit 0 with no output.

- [ ] **Step 9: Commit**

```bash
git add static/index.html static/js/api.js static/js/app.js routes/auth.py tests/test_frontend_static.py
git commit -m "feat: add frontend SPA shell"
```

---

### Task 3: `app.js` auth flow

**Files:**
- Modify: `static/js/app.js` (replace the placeholder entire file)

**Interfaces:**
- Consumes: `apiFetch` from `static/js/api.js`; element ids from `static/index.html` (Task 2).
- Produces:
  - `let wasAuthed` (module flag), `const state = { user: null }` future extension point.
  - `showView(name)`, `showToast(message, type)`, `setNavForAuth(authed)`.
  - `bootstrap()` → `GET /api/auth/me`; 200 → dashboard view + `#nav-auth` visible; 401 → login view.
  - `handleLogin(event)`, `handleRegister(event)`, `handleLogout()`.
  - `goToLogin(prefillEmail)`, `goToRegister()`.
  - `session-expired` listener: if `wasAuthed`, toast "Your session has expired. Please log in again." then go to login view.

- [ ] **Step 1: Write the full auth-flow `app.js`**

Replace the entire content of `static/js/app.js` with:

```javascript
const state = { user: null };
let wasAuthed = false;

function $(id) {
  return document.getElementById(id);
}

function showView(name) {
  for (const view of document.querySelectorAll("section[data-view]")) {
    view.classList.add("hidden");
  }
  $("view-" + name).classList.remove("hidden");
}

function setNavForAuth(authed) {
  const nav = $("nav-auth");
  if (authed) {
    nav.classList.remove("hidden");
    nav.classList.add("flex");
  } else {
    nav.classList.add("hidden");
    nav.classList.remove("flex");
  }
}

function showToast(message, type = "error") {
  const colors = type === "success"
    ? "bg-emerald-600 text-white"
    : "bg-red-600 text-white";
  const el = document.createElement("div");
  el.className = "rounded-lg px-4 py-3 text-sm shadow-lg " + colors;
  el.textContent = message;
  $("toast-container").appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

function showInline(el, message) {
  el.textContent = message;
  el.classList.remove("hidden");
}

function hideInline(el) {
  el.classList.add("hidden");
  el.textContent = "";
}

async function bootstrap() {
  try {
    const body = await apiFetch("/api/auth/me");
    state.user = body.user;
    wasAuthed = true;
    setNavForAuth(true);
    location.hash = "#dashboard";
    showView("dashboard");
  } catch (err) {
    setNavForAuth(false);
    location.hash = "#login";
    showView("login");
  }
}

async function handleLogin(event) {
  event.preventDefault();
  const submit = $("login-submit");
  const email = $("login-email").value.trim().toLowerCase();
  const password = $("login-password").value;
  hideInline($("login-error"));
  submit.disabled = true;
  submit.textContent = "Signing in…";

  try {
    const body = await apiFetch("/api/auth/login", {
      method: "POST",
      body: { email, password },
    });
    state.user = { id: body.user_id, email: body.email, role: body.role };
    wasAuthed = true;
    setNavForAuth(true);
    $("login-password").value = "";
    location.hash = "#dashboard";
    showView("dashboard");
  } catch (err) {
    // 401 on login is a plain credential error (AUTH_ROUTES suppress session-expired).
    showInline($("login-error"), err.message || "Unable to sign in.");
  } finally {
    submit.disabled = false;
    submit.textContent = "Sign in";
  }
}

async function handleRegister(event) {
  event.preventDefault();
  const submit = $("register-submit");
  const username = $("register-username").value.trim();
  const email = $("register-email").value.trim().toLowerCase();
  const password = $("register-password").value;
  const confirm = $("register-confirm").value;
  hideInline($("register-error"));

  if (password.length < 8) {
    showInline($("register-error"), "Password must be at least 8 characters.");
    return;
  }
  if (password !== confirm) {
    showInline($("register-error"), "Passwords do not match.");
    return;
  }
  submit.disabled = true;
  submit.textContent = "Creating account…";

  try {
    await apiFetch("/api/auth/register", {
      method: "POST",
      body: { username, email, password },
    });
    showToast("Account created. Please sign in.", "success");
    goToLogin(email);
  } catch (err) {
    showInline($("register-error"), err.message || "Unable to create account.");
  } finally {
    submit.disabled = false;
    submit.textContent = "Create account";
  }
}

async function handleLogout() {
  try {
    await apiFetch("/api/auth/logout", { method: "POST" });
  } catch (err) {
    // Even if the request fails, clear the client state and return to login.
  }
  state.user = null;
  wasAuthed = false;
  setNavForAuth(false);
  location.hash = "#login";
  showView("login");
}

function goToLogin(prefillEmail) {
  if (prefillEmail) {
    $("login-email").value = prefillEmail;
  }
  hideInline($("login-error"));
  location.hash = "#login";
  showView("login");
}

function goToRegister() {
  hideInline($("register-error"));
  location.hash = "#register";
  showView("register");
}

$("login-form").addEventListener("submit", handleLogin);
$("login-btn-register").addEventListener("click", goToRegister);
$("register-form").addEventListener("submit", handleRegister);
$("register-btn-login").addEventListener("click", () => goToLogin(null));
$("logout-btn").addEventListener("click", handleLogout);

document.addEventListener("session-expired", () => {
  if (wasAuthed) {
    showToast("Your session has expired. Please log in again.");
  }
  state.user = null;
  wasAuthed = false;
  setNavForAuth(false);
  location.hash = "#login";
  showView("login");
});

// ── Theme toggle ─────────────────────────────────────────────
const themeKey = "blom-theme";

function initTheme() {
  const saved = localStorage.getItem(themeKey);
  const prefersDark =
    window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  const dark = saved ? saved === "dark" : prefersDark;
  document.documentElement.classList.toggle("dark", dark);
}

function toggleTheme() {
  const dark = document.documentElement.classList.toggle("dark");
  localStorage.setItem(themeKey, dark ? "dark" : "light");
}

initTheme();
$("theme-toggle").addEventListener("click", toggleTheme);

bootstrap();
```

`showView`, `showToast`, `setNavForAuth`, `$` are added now to be consumed by Task 4.

- [ ] **Step 2: Verify JS syntax**

```bash
node --check static/js/app.js && node --check static/js/api.js
```
Expected: both exit 0.

- [ ] **Step 3: Run the static tests (no regressions)**

```bash
./venv/bin/python -m pytest tests/test_frontend_static.py tests/test_business_api.py -q
```
Expected: all pass.

- [ ] **Step 4: Browser smoke — auth flow**

Run the app locally (uses `.env` SECRET_KEY + real Firestore creds file present in `config/`):

```bash
DEBUG=False PORT=8099 ./venv/bin/python app.py
```

Then, in a browser at `http://127.0.0.1:8099/`:
1. Login view renders (no console errors).
2. "Create one" switches to register.
3. Register with email/password (≥8 chars) → success toast → auto-switch to sign in; mismatched confirm shows inline error; short password shows inline error.
4. Sign in → dashboard view + nav shows brand, theme toggle, logout.
5. Log out → returns to login view.

(Kill the server when done: `kill <pid>`.)

- [ ] **Step 5: Commit**

```bash
git add static/js/app.js
git commit -m "feat: add frontend auth flow"
```

---

### Task 4: `app.js` dashboard (list / create / edit / delete)

**Files:**
- Modify: `static/js/app.js` (append/replace with the dashboard logic; keep every Task 3 function intact)

**Interfaces:**
- Consumes: `apiFetch`, `$`, `showView`, `showToast`, `showInline`, `hideInline`, `state` from Tasks 2–3.
- Produces:
  - `loadBusinesses()` → `GET /api/business` → `renderBusinessCards(list)` or empty state.
  - `openBusinessModal(business=null)` — create (title "New business", empty fields) vs edit (title "Edit business", pre-filled).
  - `handleBusinessSubmit(event)` → `POST /api/business` (create) or `PATCH /api/business/<id>` (edit) → reload list → close modal.
  - `openDeleteModal(businessId, name)`, `handleDeleteConfirm(event)` → `DELETE /api/business/<id>` → reload list.
  - Modal open/close helpers incl. `data-close` backdrop overlay behavior; `business-modal`/`delete-modal` toggle.

- [ ] **Step 1: Add the dashboard logic to `static/js/app.js`**

Append the following to the end of `static/js/app.js` (after the existing `bootstrap()` call):

```javascript
// ── Dashboard ──────────────────────────────────────────────

let editingBusinessId = null;
let deletingBusinessId = null;

function openModal(id) {
  $(id).classList.remove("hidden");
}

function closeModal(id) {
  $(id).classList.add("hidden");
}

function renderBusinessCards(businesses) {
  const grid = $("business-grid");
  const empty = $("dashboard-empty");
  grid.innerHTML = "";

  if (!businesses.length) {
    empty.classList.remove("hidden");
    return;
  }
  empty.classList.add("hidden");

  for (const biz of businesses) {
    const card = document.createElement("div");
    card.className = "bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 p-5 cursor-pointer hover:border-indigo-400 dark:hover:border-indigo-500 transition-colors";
    card.addEventListener("click", () => {
      // openBusinessDetail is defined in Task 5; guard so this commit is safe standalone.
      if (typeof openBusinessDetail === "function") {
        openBusinessDetail(biz.id);
      }
    });

    const title = document.createElement("div");
    title.className = "flex items-start justify-between gap-2";

    const name = document.createElement("h3");
    name.className = "text-lg font-semibold";
    name.textContent = biz.name || "Untitled business";

    const industry = document.createElement("span");
    if (biz.industry) {
      industry.className = "text-xs font-medium rounded-full bg-indigo-50 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-300 px-2 py-0.5";
      industry.textContent = biz.industry;
    } else {
      industry.hidden = true;
    }
    title.appendChild(name);
    title.appendChild(industry);

    const website = document.createElement("p");
    if (biz.website_url) {
      website.className = "text-sm text-indigo-600 dark:text-indigo-400 mt-1";
      website.textContent = biz.website_url;
    }

    const desc = document.createElement("p");
    if (biz.description) {
      desc.className = "text-sm text-gray-600 dark:text-gray-300 mt-2 line-clamp-2";
      desc.textContent = biz.description;
    }

    card.appendChild(title);
    if (biz.website_url) card.appendChild(website);
    if (biz.description) card.appendChild(desc);
    grid.appendChild(card);
  }
}

async function loadBusinesses() {
  const body = await apiFetch("/api/business");
  renderBusinessCards(body.businesses || []);
}

function openBusinessModal(business = null) {
  editingBusinessId = business ? business.id : null;
  $("business-modal-title").textContent = business ? "Edit business" : "New business";
  $("business-id").value = business ? business.id : "";
  $("business-field-name").value = business ? business.name || "" : "";
  $("business-field-website").value = business ? business.website_url || "" : "";
  $("business-field-industry").value = business ? business.industry || "" : "";
  $("business-field-description").value = business ? business.description || "" : "";
  hideInline($("business-form-error"));
  openModal("business-modal");
  $("business-field-name").focus();
}

async function handleBusinessSubmit(event) {
  event.preventDefault();
  const submit = $("business-submit");
  hideInline($("business-form-error"));

  const payload = {
    name: $("business-field-name").value.trim(),
    website_url: $("business-field-website").value.trim(),
    industry: $("business-field-industry").value.trim(),
    description: $("business-field-description").value.trim(),
  };

  if (!payload.name) {
    showInline($("business-form-error"), "Business name is required.");
    return;
  }

  submit.disabled = true;
  submit.textContent = "Saving…";

  try {
    if (editingBusinessId) {
      await apiFetch("/api/business/" + editingBusinessId, {
        method: "PATCH",
        body: payload,
      });
      showToast("Business updated.", "success");
    } else {
      await apiFetch("/api/business", {
        method: "POST",
        body: payload,
      });
      showToast("Business created.", "success");
    }
    closeModal("business-modal");
    await loadBusinesses();
  } catch (err) {
    showInline($("business-form-error"), err.message || "Unable to save business.");
  } finally {
    submit.disabled = false;
    submit.textContent = "Save";
  }
}

function openDeleteModal(businessId, name) {
  deletingBusinessId = businessId;
  $("delete-biz-name").textContent = name || "This business";
  openModal("delete-modal");
}

async function handleDeleteConfirm() {
  const confirm = $("delete-confirm");
  confirm.disabled = true;
  confirm.textContent = "Deleting…";

  try {
    await apiFetch("/api/business/" + deletingBusinessId, {
      method: "DELETE",
    });
    showToast("Business deleted.", "success");
    closeModal("delete-modal");
    await loadBusinesses();
  } catch (err) {
    showToast(err.message || "Unable to delete business.");
    closeModal("delete-modal");
  } finally {
    confirm.disabled = false;
    confirm.textContent = "Delete";
    deletingBusinessId = null;
  }
}

$("create-business-btn").addEventListener("click", () => openBusinessModal(null));
$("business-form").addEventListener("submit", handleBusinessSubmit);
$("delete-confirm").addEventListener("click", handleDeleteConfirm);

for (const el of document.querySelectorAll("[data-close]")) {
  el.addEventListener("click", () => closeModal(el.dataset.close));
}

// Dashboard load on page refresh while already signed in:
window.addEventListener("load", () => {
  if ($("view-dashboard").classList.contains("hidden") === false) {
    loadBusinesses();
  }
});
```

Then edit the success block of the Task 3 `handleLogin` function so a fresh login also loads the dashboard (`loadBusinesses` is hoisted, so it is callable even though it is defined later in the file). Replace:

```js
    $("login-password").value = "";
    location.hash = "#dashboard";
    showView("dashboard");
```

with:

```js
    $("login-password").value = "";
    location.hash = "#dashboard";
    showView("dashboard");
    try {
      await loadBusinesses();
    } catch (loadErr) {
      showToast(loadErr.message || "Unable to load businesses.");
    }
```

**Note on Task 4 self-contained behavior:** `handleLogin` now loads the dashboard directly (the earlier `const _origLogin` re-wrap idea was dead code — the form listener captured the original function reference, so do NOT reintroduce it). The `window.addEventListener("load", ...)` block covers the page-refresh-already-authed path. Task 5 replaces this `load` listener with a cleaner `bootstrap` re-wrap; every step here is independently correct.

- [ ] **Step 2: Verify JS syntax**

```bash
node --check static/js/app.js
```
Expected: exit 0.

- [ ] **Step 3: Run the static tests**

```bash
./venv/bin/python -m pytest tests/test_frontend_static.py tests/test_business_api.py -q
```
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add static/js/app.js
git commit -m "feat: add frontend business dashboard"
```

---

### Task 5: `app.js` business detail (analyze/poll, opportunities, actions)

**Files:**
- Modify: `static/js/app.js` (append detail logic; keep all Task 3–4 functions)

**Interfaces:**
- Consumes: `apiFetch`, `$`, `showView`, `showToast`, `showInline`, `hideInline`, `openModal`, `closeModal`, `openBusinessModal`, `openDeleteModal`, `loadBusinesses`, `state` from Tasks 2–4.
- Produces:
  - `openBusinessDetail(businessId)` — sets `state.businessId`, shows `view-business`, loads header + opportunities + actions, starts run-status check.
  - `startAnalysis()` — `POST /api/business/<id>/analyze` → toast → `pollRunStatus()`.
  - `pollRunStatus()` — `GET /api/business/<id>/runs/latest`; render status pill; terminal (`completed`/`failed`) stops the interval and reloads opportunities+actions; `queued`/`running` continues.
  - `loadOpportunities()`, `loadActions()`, `renderActions(list)`.
  - `approveAction(actionId)` → `POST .../actions/<actionId>/approve`; `rejectAction(actionId)` → `POST .../actions/<actionId>/reject`; both reload actions.

- [ ] **Step 1: Add the business-detail logic to `static/js/app.js`**

Append the following to the end of `static/js/app.js`:

```javascript
// ── Business detail ─────────────────────────────────────────

let runPollTimer = null;
let currentBusiness = null;

function renderRunStatus(status, error) {
  const el = $("run-status");
  el.innerHTML = "";
  const pill = document.createElement("span");
  const label = status || "queued";
  const map = {
    "queued": "bg-amber-100 dark:bg-amber-950 text-amber-800 dark:text-amber-300",
    "running": "bg-blue-100 dark:bg-blue-950 text-blue-800 dark:text-blue-300",
    "completed": "bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300",
    "failed": "bg-red-100 dark:bg-red-950 text-red-800 dark:text-red-300",
  };
  pill.className = "inline-block text-sm font-medium rounded-full px-3 py-1 " + (map[label] || map.queued);
  pill.textContent = label;
  el.appendChild(pill);
  if (error) {
    const msg = document.createElement("p");
    msg.className = "mt-2 text-sm text-red-700 dark:text-red-400";
    msg.textContent = error;
    el.appendChild(msg);
  }
}

function renderOpportunities(list) {
  const container = $("opportunities-list");
  const empty = $("opportunities-empty");
  container.innerHTML = "";
  if (!list.length) {
    empty.classList.remove("hidden");
    return;
  }
  empty.classList.add("hidden");
  for (const opp of list) {
    const box = document.createElement("div");
    box.className = "rounded-lg border border-gray-200 dark:border-gray-800 p-4";
    const title = document.createElement("h3");
    title.className = "font-semibold";
    title.textContent = opp.title || opp.headline || "Opportunity";
    const summary = document.createElement("p");
    summary.className = "text-sm text-gray-600 dark:text-gray-300 mt-1";
    summary.textContent = opp.summary || opp.description || "";
    box.appendChild(title);
    if (summary.textContent) box.appendChild(summary);
    container.appendChild(box);
  }
}

async function loadOpportunities() {
  const body = await apiFetch("/api/business/" + state.businessId + "/opportunities");
  renderOpportunities(body.opportunities || []);
}

function renderActions(list) {
  const container = $("actions-list");
  const empty = $("actions-empty");
  container.innerHTML = "";
  if (!list.length) {
    empty.classList.remove("hidden");
    return;
  }
  empty.classList.add("hidden");
  for (const action of list) {
    const row = document.createElement("div");
    row.className = "rounded-lg border border-gray-200 dark:border-gray-800 p-4";

    const head = document.createElement("div");
    head.className = "flex flex-wrap items-center justify-between gap-2";

    const title = document.createElement("h3");
    title.className = "font-semibold";
    title.textContent = action.title || "Action";

    const pill = document.createElement("span");
    const statusMap = {
      "pending_approval": "bg-amber-100 dark:bg-amber-950 text-amber-800 dark:text-amber-300",
      "approved": "bg-blue-100 dark:bg-blue-950 text-blue-800 dark:text-blue-300",
      "rejected": "bg-gray-200 dark:bg-gray-800 text-gray-700 dark:text-gray-300",
      "executed": "bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300",
    };
    pill.className = "text-xs font-medium rounded-full px-2 py-0.5 " + (statusMap[action.status] || "bg-gray-200 dark:bg-gray-800 text-gray-700 dark:text-gray-300");
    pill.textContent = action.status || "unknown";

    head.appendChild(title);
    head.appendChild(pill);

    const desc = document.createElement("p");
    if (action.description) {
      desc.className = "text-sm text-gray-600 dark:text-gray-300 mt-1";
      desc.textContent = action.description;
    }

    const buttons = document.createElement("div");
    buttons.className = "flex gap-2 mt-3";
    if (action.status === "pending_approval") {
      const approve = document.createElement("button");
      approve.type = "button";
      approve.className = "rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold px-3 py-1.5 disabled:opacity-60";
      approve.textContent = "Approve";
      approve.addEventListener("click", () => approveAction(action.id));

      const reject = document.createElement("button");
      reject.type = "button";
      reject.className = "rounded-lg border border-gray-300 dark:border-gray-700 text-xs px-3 py-1.5 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-60";
      reject.textContent = "Reject";
      reject.addEventListener("click", () => rejectAction(action.id));

      buttons.appendChild(approve);
      buttons.appendChild(reject);
    }

    row.appendChild(head);
    if (action.description) row.appendChild(desc);
    if (buttons.children.length) row.appendChild(buttons);
    container.appendChild(row);
  }
}

async function loadActions() {
  const body = await apiFetch("/api/business/" + state.businessId + "/actions");
  renderActions(body.actions || []);
}

async function approveAction(actionId) {
  await apiFetch("/api/business/" + state.businessId + "/actions/" + actionId + "/approve", {
    method: "POST",
  });
  showToast("Action approved.", "success");
  await loadActions();
}

async function rejectAction(actionId) {
  await apiFetch("/api/business/" + state.businessId + "/actions/" + actionId + "/reject", {
    method: "POST",
  });
  showToast("Action rejected.", "success");
  await loadActions();
}

async function startAnalysis() {
  const btn = $("analyze-btn");
  btn.disabled = true;
  btn.textContent = "Analyzing…";
  try {
    await apiFetch("/api/business/" + state.businessId + "/analyze", {
      method: "POST",
    });
    showToast("Analysis started.", "success");
    pollRunStatus(true);
  } catch (err) {
    showToast(err.message || "Unable to start analysis.");
    btn.disabled = false;
    btn.textContent = "Analyze website";
  }
}

async function pollRunStatus(immediate) {
  if (!state.businessId) return;
  const run = async () => {
    try {
      const body = await apiFetch("/api/business/" + state.businessId + "/runs/latest");
      const run = body.run;
      if (!run) {
        renderRunStatus("queued", null);
        return;
      }
      const status = run.status;
      renderRunStatus(status, run.error);
      if (status === "completed" || status === "failed") {
        stopPolling();
        $("analyze-btn").disabled = false;
        $("analyze-btn").textContent = "Analyze website";
        if (status === "completed") {
          try {
            await loadOpportunities();
            await loadActions();
          } catch (err) {
            showToast(err.message || "Could not refresh results.");
          }
        }
        return;
      }
    } catch (err) {
      renderRunStatus("running", null);
    }
  };
  if (immediate) {
    await run();
  }
  if (runPollTimer) clearInterval(runPollTimer);
  runPollTimer = setInterval(run, 3000);
}

function stopPolling() {
  if (runPollTimer) {
    clearInterval(runPollTimer);
    runPollTimer = null;
  }
}

async function openBusinessDetail(businessId) {
  stopPolling();
  state.businessId = businessId;
  try {
    const body = await apiFetch("/api/business/" + businessId);
    currentBusiness = body.business;
    $("biz-name").textContent = currentBusiness.name || "Untitled business";
    $("biz-industry").textContent = currentBusiness.industry || "";
    const link = $("biz-website");
    if (currentBusiness.website_url) {
      link.href = currentBusiness.website_url;
      link.textContent = currentBusiness.website_url;
    } else {
      link.removeAttribute("href");
      link.textContent = "";
    }
    $("biz-description").textContent = currentBusiness.description || "";
    $("analyze-btn").disabled = false;
    $("analyze-btn").textContent = "Analyze website";
    showView("business");
    renderRunStatus("queued", null);
    await loadOpportunities();
    await loadActions();
    pollRunStatus(true);
  } catch (err) {
    showToast(err.message || "Unable to load business.");
    if (err.status === 404 || err.status === 403) {
      showView("dashboard");
      try {
        await loadBusinesses();
      } catch (loadErr) {
        showToast(loadErr.message || "Unable to load businesses.");
      }
    }
  }
}

$("back-to-dashboard").addEventListener("click", () => {
  stopPolling();
  state.businessId = null;
  showView("dashboard");
  loadBusinesses().catch((err) => showToast(err.message || "Unable to load businesses."));
});

$("analyze-btn").addEventListener("click", startAnalysis);
$("biz-edit-btn").addEventListener("click", () => openBusinessModal(currentBusiness));
$("biz-delete-btn").addEventListener("click", () => {
  openDeleteModal(currentBusiness.id, currentBusiness.name);
});

// Dashboard cards → detail (also used by Task 4's renderBusinessCards).
// Successfully restructured login wiring for clean dashboard load:
const _origBootstrap = bootstrap;
bootstrap = async function () {
  await _origBootstrap();
  if (state.user) {
    try {
      await loadBusinesses();
    } catch (err) {
      showToast(err.message || "Unable to load businesses.");
    }
  }
};
bootstrap();
```

**Important:** because `app.js` has `defer` and `api.js`/`index.html` load it once, there must be exactly one dashboard-load path and one `bootstrap()` call. Task 4 wired dashboard load per-case (a `load`-listener for the refresh path + a direct `await loadBusinesses()` inside `handleLogin`). Task 5 replaces that with a single clean `bootstrap` re-wrap (covers both login and refresh). Task 5 Step 2 consolidation: delete the Task 4 `window.addEventListener("load", ...)` block, delete the Task 3 trailing `bootstrap();` call (the line just above the `// ── Dashboard ──` comment), and keep Task 5's `bootstrap();` at the end of the file. **The final `app.js` must not contain Task 4's `window.addEventListener("load", ...)` block and must contain exactly one `bootstrap();` call.** `handleLogin` keeps its inline `await loadBusinesses()` (harmless — `loadBusinesses` re-renders the already-visible dashboard).

- [ ] **Step 2: Consolidate the final `app.js` (single dashboard-load path)**

Because Tasks 4 and 5 both touch login/bootstrap wiring, the committed file must be the consolidated version. After appending Task 5's block, edit `static/js/app.js` to:

1. Delete the Task 4 `window.addEventListener("load", ...)` dashboard-load block.
2. Delete the Task 3 trailing `bootstrap();` call (the line directly above the `// ── Dashboard ──` comment) so the file has exactly one `bootstrap()` invocation (Task 5's at the end).
3. Leave the Task 4 edit inside `handleLogin` (`await loadBusinesses()` after `showView("dashboard")`) in place — it re-renders the already-visible dashboard and is harmless.

Verify with `grep -c "bootstrap();" static/js/app.js` → expect `1`; `grep -c "_origLogin" static/js/app.js` → expect `0`; `node --check static/js/app.js` → exit 0.

- [ ] **Step 3: Verify JS syntax**

```bash
node --check static/js/app.js
```
Expected: exit 0.

- [ ] **Step 4: Run the static tests**

```bash
./venv/bin/python -m pytest tests/test_frontend_static.py tests/test_business_api.py -q
```
Expected: all pass.

- [ ] **Step 5: Browser smoke — full flow**

Run the app (real Firestore creds present under `config/`):

```bash
DEBUG=False PORT=8099 ./venv/bin/python app.py
```

In a browser at `http://127.0.0.1:8099/` (register/login first if needed):
1. Sign in → dashboard renders cards for existing businesses; empty state if none.
2. "New business" → modal validates (blank name → inline error) → create → card appears.
3. Open a business → detail view shows header, "Analyze website" button, run-status, opportunities, actions.
4. Click Analyze → status pill transitions through `queued`/`running` to `completed` (or `failed` with the error text) via polling.
5. If actions exist with `pending_approval`, approve → pill flips to `approved`; reject → `rejected`.
6. Edit (from header or dashboard) then Delete → confirm modal → card removed.

(Kill the server when done.)

- [ ] **Step 6: Commit**

```bash
git add static/js/app.js
git commit -m "feat: add frontend business detail and actions"
```

---

### Task 6: Final verification, full suite, git audit

**Files:**
- None (read-only checks)

**Interfaces:**
- Consumes: the completed Tasks 0–5.

- [ ] **Step 1: Full backend suite**

```bash
./venv/bin/python -m pytest -q
```
Expected: 118 passed, 3 failed — the 3 failures are exactly the accepted connector drift. Optional confirmation: `./venv/bin/python -m pytest tests/test_business_api.py tests/test_frontend_static.py -q` → all 11 pass.

- [ ] **Step 2: JS syntax final check**

```bash
node --check static/js/api.js && node --check static/js/app.js
```
Expected: both exit 0.

- [ ] **Step 3: Confirm single bootstrap and no stale re-wraps**

```bash
grep -c "bootstrap();" static/js/app.js
grep -c "_origLogin" static/js/app.js
grep -c 'window.addEventListener("load",' static/js/app.js
```
Expected: `1`, `0`, `0`.

- [ ] **Step 4: Git hygiene audit**

```bash
git status --short
git log --oneline -12
```
Expected: working tree shows only the user's pre-existing dirty/untracked files (never stripped or staged); commit list shows the six feature commits from Tasks 0–5 on top of the pre-existing branch history — `docs: frontend spa design spec`, `feat: add business read API endpoints`, `feat: add frontend SPA shell`, `feat: add frontend auth flow`, `feat: add frontend business dashboard`, `feat: add frontend business detail and actions`. No `git add -A`, no staging of user files anywhere in history.

- [ ] **Step 5: Updated spec Verification pass**

Confirm the spec's Verification section claims against this run: backend tests pass, `/` serves the SPA via the test client in `test_frontend_static.py`, `node --check` passes, browser flow smoke-tested in Tasks 3 and 5.

## Execution Log

Executed Sep 18 2026 via subagent-driven development on branch `fix/e2e-background-analysis`.

Commits (base `b269234`):
- `bbdea70` docs: frontend spa design spec (Task 0)
- `108175e` feat: add business read API endpoints (Task 1)
- `c5cc969` feat: add frontend SPA shell (Task 2; includes the one-line `routes/auth.py` `home()` change folded in after a blocked first attempt left it uncommitted)
- `629131b` feat: add frontend auth flow (Task 3)
- `ffc7374` feat: add frontend business dashboard (Task 4)
- `4d15029` feat: add frontend business detail and actions (Task 5)
- `3c538f4` fix: stop status poll on logout/expiry; whitelist website scheme (post-plan condition fixes, approved by focused review)

Verification (Task 6, all green): full suite `118 passed, 3 failed` where the 3 failures are exactly the accepted pre-existing connector drift; new tests `11 passed` (`tests/test_business_api.py` 9, `tests/test_frontend_static.py` 2); `node --check` exit 0 on both JS files; `bootstrap();` count 1, `_origLogin` 0, `window.addEventListener("load",` 0; git audit confirms only the six feature commits touched only workstream files (committed `app.py` delta is exactly the two `business_api` lines; the user's `instagram_connections`/`PORT 8000` lines and all other user WIP files remain unstaged and untouched, no `git add -A`).

Deviations resolved during execution:
1. User decision (option B): asset URLs are `/static/js/...` (not `/js/...`); `app.py` untouched in Task 2. Plan text updated to match throughout.
2. Task 1 Step 6 expected count corrected: after Task 1 the suite is `116 passed` (107 + 9); the plan-wide `118` lands after Task 2. Plan text updated.
3. Browser smoke steps (Task 3 Step 4, Task 5 Step 5) deferred to the human — automated equivalents (pytest + `node --check` + curl of `/` and `/static/js/app.js` returning 200 from a `PORT=8099` server) passed in their place. The full interactive browser pass remains for the user.
4. `routes/auth.py` `home()` already served `index.html` via a stale working-tree edit from the blocked Task 2 attempt; controller folded it into `c5cc969` (it is a Task 2 requirement of the plan's Step 6).

Deferred minors (task reviews approved; batched for a future housekeeping pass if desired): EOF trailing newlines on committed JS/Python files; `test_business_api_blueprint_registered` weak RED signal; api.js `Content-Type` on GET + `session-expired` 401-only (both brief-mandated); `approveAction`/`rejectAction` no try/catch; redundant post-terminal poll; poll error masked as "running"; detail view aggregates ops+actions into one try; delete-failure toast missing "error" type; post-save reload rejection lands in closed-modal catch.