# Frontend SPA — Design

Date: 2026-09-17
Status: Draft (pending user review)
Scope: Build the product's first usable UI as a static single-page application (plain HTML + Tailwind CSS via CDN + vanilla JavaScript) served same-origin by the existing Flask app. Views: login, register, business dashboard (list/create/edit/delete), and business detail (analyze → poll run, opportunities, actions approve/reject). Auth uses the existing session cookie via the JSON API (`/api/auth/*`). The server-rendered template flow (`routes/auth.py` form routes, `decorators.py`) is untouched except one line in `home()`. Instagram connections and executions/dry-run views are out of scope.

## Goal

The backend has a complete JSON API surface — JSON auth (`/api/auth/register|login|logout|me`), business CRUD (`POST/PATCH/DELETE /api/business...`), analyze (`POST /api/business/<id>/analyze`), runs (`GET .../runs/latest`), opportunities (list/detail), actions (list/detail/approve/reject) — but **no frontend**. All Flask templates (`home.html`, `login.html`, `registration.html`, `error.html`) are empty, and there is no `static/` folder.

This effort ships a same-origin static SPA so the product is usable end-to-end from a browser:

1. Login / register against the JSON auth API (session cookie).
2. Dashboard listing the caller's businesses, with create/edit/delete.
3. Business detail with website analysis, run-status polling, opportunities, and action approval/rejection.

Constraints that shaped the design:

- Auth is **session-cookie based** (`HttpOnly`, `SameSite=Lax`, no CORS) → the frontend must be served by the Flask app on the same origin for cookies to work. Hence "static SPA served by Flask", not a separate dev server.
- User asked for plain **HTML + TailwindCSS + JavaScript** — no framework, no build step, no Node toolchain. Tailwind via CDN.
- My earlier auth workstream's global constraints still apply: never stage/modify the user's dirty/untracked files (`routes/user.py`, `connectors/`, `services/`, `agent/`, `task.py`, `scripts/`, `tests/test_user_routes.py`, `config/`, `routes/instagram_connections.py`, `docs/` plans+specs, `hello.txt`). `app.py` is now a partially-dirty tracked file (user's uncommitted lines inside); any `app.py` edit must use the established selective-staging method.

## Design Decisions (from brainstorming)

- **Static SPA served by Flask** — same origin → session cookie auth works with zero CORS/changes to the ~15 guarded JSON routes.
- **Tailwind via CDN, vanilla JS, no build step** — matches the user's explicit stack choice; `cdn.tailwindcss.com` + Inter font.
- **View-switching SPA** — a single `index.html` shell with show/hide view containers driven by `app.js`; no routing library, no framework.
- **New `routes/business_api.py` blueprint** for the two missing read endpoints (`GET /api/business`, `GET /api/business/<id>`) — the existing `routes/user.py` (user-dirty) has create/update/delete/analyze/opportunities/actions but no JSON list/detail reads. New file keeps everything out of the user's WIP files.
- **`home()` serves the SPA** — `auth_bp.home()` changes from `render_template("home.html")` (which is empty) to serving `static/index.html`. One line in a clean, committed file.
- **Error handling via envelopes** — the backend's uniform `{"success":false,"error":...}` becomes a toast/banner + throw-through in `api.js`.
- **Scope cut** — Instagram connect/status and executions/dry-run views are explicitly out of scope for this iteration (user picked auth + dashboard + detail/actions only).

## API Surface the SPA Consumes

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/auth/register` | POST | create account (username/email/password) |
| `/api/auth/login` | POST | set session cookie |
| `/api/auth/logout` | POST | clear session |
| `/api/auth/me` | GET | session bootstrap / auth truth |
| `/api/business` | GET *(new)* | list caller's businesses |
| `/api/business/<id>` | GET *(new)* | single business detail |
| `/api/business` | POST | create business |
| `/api/business/<id>` | PATCH | update business |
| `/api/business/<id>` | DELETE | delete business |
| `/api/business/<id>/analyze` | POST | queue website analysis (202) |
| `/api/business/<id>/runs/latest` | GET | poll run status |
| `/api/business/<id>/opportunities` | GET | list opportunities |
| `/api/business/<id>/actions` | GET | list actions (all statuses) |
| `/api/business/<id>/actions/<aid>` | POST approve | approve pending action (202) |
| `/api/business/<id>/actions/<aid>` | POST reject | reject pending action |

## Component / Files

**Backend (new/changed):**

- `routes/business_api.py` (new) — `Blueprint("business_api", __name__)`:
  - `GET /api/business` → guard `session["user_id"]` (else 401); query `businesses` where `owner_id == user_id`; return `200 {"success": true, "businesses": [{id, **data}]}`.
  - `GET /api/business/<business_id>` → guard 401; fetch doc (404 if missing); 403 if `owner_id != user_id`; `200 {"success": true, "business": {id, **data}}`.
  - Guard order matches `routes/user.py`: auth check first, then existence, then ownership. Same JSON envelope style, `datetime`-free passthrough of stored fields.
  - Register in `app.py` (selective-staging method — user's `instagram_connections`/`PORT` lines stay unstaged).
- `routes/auth.py` — `home()` body becomes serving `static/index.html` (one line). Clean, committed file; normal commit.

**Frontend (new, all under `static/` served by Flask):**

- `static/index.html` — Tailwind CDN `<script>`, Inter font, navbar (brand + logout when authed), view containers: `#view-login`, `#view-register`, `#view-dashboard`, `#view-business`. Modals: business form (create/edit), confirm-delete.
- `static/js/api.js` — thin fetch wrapper: same-origin credentials, JSON parse, envelope normalization, throws `{message, status}` on errors, dispatches a `session-expired` event for 401s.
- `static/js/app.js` — view router (`showView(name)`), auth helpers (`bootstrap()`, `handleLogin`, `handleRegister`, `handleLogout`), dashboard render (`loadBusinesses`, create/edit/delete), business detail (`loadBusiness`, `startAnalysis` + polling, `loadOpportunities`, `loadActions`, approve/reject), toast/banner helpers, loading/empty states.

## Views & Data Flow

### Login
- Form (email, password) → `POST /api/auth/login`. 200 → dashboard view. Errors inline (400/401/423/429 messages shown verbatim).
- Link to register view. On app load, `bootstrap()` calls `/api/auth/me`; 401 → login view; 200 → dashboard.

### Register
- Form (username, email, password, confirm password). Client checks password ≥ 8 and confirm-match; server re-validates. 201 → success banner, auto-switch to login (email pre-filled). 409/429 shown verbatim.

### Dashboard
- `GET /api/business` on view entry → card grid (name, industry badge, website link, created date). Empty state CTA; loading skeleton.
- Create modal → `POST /api/business` (validates name + URL client-side, server re-validates) → prepend card.
- Edit modal (pre-filled) → `PATCH /api/business/<id>` → replace card.
- Delete confirm dialog → `DELETE /api/business/<id>` → remove card.
- Card click → business detail (`state.businessId`).

### Business detail
- Header card: back link, name/industry/website/description, Edit/Delete (reuse modals).
- **Analyze:** button → `POST /api/business/<id>/analyze`; on 202 start polling `GET /api/business/<id>/runs/latest` every 3 s. Status banner: queued → running → completed (green) / failed (red + error). Stop on terminal state. Button disabled while active.
- **Opportunities:** `GET /api/business/<id>/opportunities` → cards (title, summary, show-more). Empty state: "Run an analysis to find opportunities."
- **Actions:** `GET /api/business/<id>/actions` → rows with title, description, status pill. `pending_approval` rows show **Approve** / **Reject** buttons → `POST .../actions/<id>/approve|reject` → refresh. Actions list also refreshed after a run completes so newly generated actions appear.

### Logout
- Navbar button → `POST /api/auth/logout` → login view.

## Error Handling

- `api.js`: non-2xx with `{error}` → `throw {message: error, status}`; network/parse error → `{message: "Network error. Please try again."}`. Views show via `showToast(msg, type)` (inline banner for forms, transient toast for page actions).
- Any 401 on a protected endpoint (or `/api/auth/me`) → switch to login view with "Your session has expired. Please log in again."
- Loading states: per-view skeleton, buttons disabled + spinner while in flight.
- Form validation mirrors backend (defense in depth); server message wins.

## Security Notes

- No tokens in `localStorage`/`sessionStorage` — the HttpOnly session cookie alone governs auth (consistent with the backend anti-sharing design).
- No inline secrets; Tailwind CDN pinned to a specific version URL.
- Same-origin SPA inherits the existing cookie config (`HttpOnly`, `SameSite=Lax`, `SECURE` in prod, 30-min lifetime).
- The SPA never calls from another origin, so no CORS is added.

## Testing

### New backend tests — `tests/test_business_api.py`
Following the repo's file-local fake-Firestore pattern (as used in `tests/test_auth_api.py`): a `TESTING` Flask app with `secret_key` set and `business_api_bp` registered; `auth`-style session set directly via test client session. Cases:

1. `GET /api/business` unauthenticated → 401.
2. `GET /api/business` returns only the caller's businesses (two users, one each; assert caller sees exactly theirs).
3. `GET /api/business` with zero businesses → 200 empty list.
4. `GET /api/business/<id>` unauthenticated → 401.
5. `GET /api/business/<id>` nonexistent doc → 404.
6. `GET /api/business/<id>` non-owner → 403.
7. `GET /api/business/<id>` owner → 200 full fields (id + all stored data).
8. Guard order: unauthenticated (no session) beats 404/403 (session missing → 401 even with bad id).

### Frontend verification (no JS test framework in repo)
- Boot Flask against test fakes; `curl /` → serves `index.html`; `curl` each `static/js/*.js` → 200; Tailwind CDN tag present in served HTML.
- Headless browser pass against the running app: login view renders → register→login flow → dashboard lists businesses → open detail → analyze triggers polling → actions approve/reject update status.
- Full suite check: `./venv/bin/python -m pytest -q` must stay 107 passed + 3 accepted drift failures (connector refactor in user's WIP; no new regressions). New `test_business_api.py` cases add to the passing count.

## Out of Scope / Deferred

- Instagram connect/status and executions/dry-run UI (endpoints exist; views deferred per user's scope choice).
- Password reset UI (no backend API exists).
- Cross-origin deployment / CORS.
- Build pipeline / bundler / frameworks (explicitly excluded by the chosen stack).

## Verification

1. `./venv/bin/python -m pytest tests/test_business_api.py -v` → all pass.
2. `./venv/bin/python -m pytest -q` → 107 passed + 3 known drift failures (unchanged); no regressions.
3. Run app with test fakes; `curl -i /` → 200 HTML containing `js/app.js`; `curl -i /js/app.js` → 200.
4. Headless-browser smoke: register → login → create business → analyze → approve/reject an action.
5. `git status` audit: only own files staged (`routes/business_api.py`, `routes/auth.py` one-liner, `app.py` selective line, `static/*`, `tests/test_business_api.py`); user's dirty/untracked files untouched.