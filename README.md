# Blom — AI Growth Agent · Backend

> **An autonomous marketing intelligence platform** that scrapes and analyses your business website, surfaces evidence-based growth opportunities, proposes concrete marketing actions, and executes them across GitHub, Instagram, and the web — all with mandatory human approval at every step.

Blom operates in **two independent intelligence modes**:

| Mode | Engine | Input | Output |
|------|--------|-------|--------|
| **Text Analysis** (original) | `analyze_business_website` | Scraped HTML + Search Console data | Business profile → opportunities → actions |
| **Visual GTM OS** (PixelRAG) | `run_gtm_analysis` | Full-page screenshots of you *and your competitors* | 5-axis GTM score, blind spots, competitor teardown, 30-day dossier |

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Core Agent Pipeline](#core-agent-pipeline)
- [Visual GTM Pipeline (PixelRAG)](#visual-gtm-pipeline-pixelrag)
- [Feature Breakdown](#feature-breakdown)
  - [Authentication & Security](#authentication--security)
  - [Business Management](#business-management)
  - [Website Analysis](#website-analysis)
  - [Opportunity Generation](#opportunity-generation)
  - [Decision Engine & Action Planning](#decision-engine--action-planning)
  - [Action Approval & Execution](#action-approval--execution)
  - [Connector Layer](#connector-layer)
  - [Measurements & Learning Loop](#measurements--learning-loop)
  - [Social, SEO & Code Integrations](#social-seo--code-integrations)
- [Tech Stack](#tech-stack)
- [Frontend SPA](#frontend-spa)
- [Project Structure](#project-structure)
- [API Reference](#api-reference)
- [Setup & Running Locally](#setup--running-locally)
- [Environment Variables](#environment-variables)
- [Security Hardening](#security-hardening)
- [Background Task Queue](#background-task-queue)
- [Firestore Data Model](#firestore-data-model)
- [Testing](#testing)
- [Known Issues & Drift](#known-issues--drift)
- [Development Workflow](#development-workflow)

---

## Overview

Blom is a **Flask-based AI backend** that acts as an autonomous growth-marketing agent for small businesses. A user registers their business, connects it to their website, GitHub account, Instagram page, and/or Google Search Console, and the agent then:

1. **Observes** — scrapes the business website safely
2. **Enriches** — pulls real search performance data from Google Search Console (if connected)
3. **Analyses** — uses an LLM to build a structured business profile from the scraped content and search data
4. **Identifies opportunities** — generates ranked, evidence-grounded growth opportunities
5. **Plans actions** — converts each opportunity into a concrete, executable action plan
6. **Requests approval** — every action requires explicit user sign-off before it runs
7. **Executes** — writes files to GitHub, posts to Instagram, or updates web pages
8. **Learns** — records measurements after execution and generates learnings that feed back into future decisions

The **Visual GTM OS** runs a parallel track: it renders your site *and your competitors'* in a headless browser, slices them into labelled vertical tiles, and hands the pixels to a vision LLM for a side-by-side competitive teardown and an executive GTM dossier.

The entire pipeline is asynchronous, driven by [Celery](https://docs.celeryq.dev/) backed by Redis, with state persisted in Google Cloud Firestore.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Flask Application                           │
│  app.py — CORS · ProxyFix · session hardening · no-cache headers    │
│                                                                      │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌──────────┐ ┌──────────┐ ┌─────┐ │
│  │ auth.py│ │user.py │ │auth_api│ │business_ │ │github_con│ │gtm_ │ │
│  │ HTML + │ │business│ │  .py   │ │ api.py   │ │nections  │ │routes│ │
│  │  SPA   │ │+actions│ │ JSON   │ │ list/get │ │          │ │     │ │
│  └───┬────┘ └───┬────┘ └───┬────┘ └────┬─────┘ └────┬─────┘ └──┬──┘ │
│      │          │          │           │            │          │    │
│  ┌───▼──────────▼──────────▼───────────▼────────────▼──────────▼──┐  │
│  │  instagram_connections.py  ·  search_console_connections.py    │  │
│  └────────────────────────────┬───────────────────────────────────┘  │
│                               │                                      │
│                 ┌─────────────▼─────────────┐                        │
│                 │   Firebase Auth +         │                        │
│                 │   Cloud Firestore         │                        │
│                 └─────────────┬─────────────┘                        │
│                               │                                      │
│              ┌────────────────▼─────────────────┐                    │
│              │        Celery Worker           │                    │
│              │                                │                    │
│              │  PIPELINE A — TEXT              │                    │
│              │  analyze_business_website()     │                    │
│              │   → website_analyzer            │                    │
│              │   → agent/analyzer      (LLM)   │                    │
│              │   → GoogleSearchConsoleAPI(opt) │                    │
│              │   → opportunity_generator(LLM)  │                    │
│              │   → decision_engine      (LLM)  │                    │
│              │   → actions: pending_approval   │                    │
│              │                                │                    │
│              │  PIPELINE B — VISUAL GTM        │                    │
│              │  run_gtm_analysis()             │                    │
│              │   → pixelrag_service   (tiles)  │                    │
│              │   → gtm_discovery      (SERP)   │                    │
│              │   → gtm_engine       (VLM)      │                    │
│              │   → gtm_dossier_service (.md)   │                    │
│              │                                │                    │
│              │  EXECUTION                      │                    │
│              │  execute_approved_action()      │                    │
│              │   → Connector Layer             │                    │
│              │   → Measurement + Learning      │                    │
│              └────────────────────────────────┘                    │
│                               │                                      │
│               ┌───────────────▼───────────────┐                      │
│               │   Redis — broker · backend ·   │                      │
│               │   auth rate-limit store        │                      │
│               └───────────────────────────────┘                      │
└──────────────────────────────────────────────────────────────────────┘
```

### Request flow (text pipeline)

```
POST /api/business/<id>/analyze
   → routes/user.py::analyze_business()
   → Firestore: businesses/<id>/agent_runs/<run_id>  {status: "queued"}
   → task.analyze_business_website.delay(...)       → 202 {run_id, task_id}
                                                    │
              Celery worker picks up ────────────────┘
   → guard ownership → fetch → parse → save observation
   → LLM profile → [GSC enrich] → LLM opportunities → validate → dedupe
   → LLM actions per opportunity
   → single terminal update {status: "awaiting_approval", actions_created: N}
```

The SPA polls `GET /api/business/<id>/runs/latest` every 3 seconds until the status is terminal.

---

## Core Agent Pipeline

Triggered by a single call: `POST /api/business/<id>/analyze`.

| Step | Module | Description |
|------|--------|-------------|
| **1. Guard** | `routes/user.py` | Verifies business exists, `owner_id == session user`, `website_url` present |
| **2. Fetch** | `website_analyzer.fetch_website_html()` | SSRF-safe HTTP fetch with DNS pinning, per-hop redirect validation, 2 MB cap |
| **3. Parse** | `website_analyzer.analyze_html()` | Extracts title, meta description, headings (H1–H3), up to 100 links |
| **4. Observe** | Firestore | Persists `businesses/<id>/observations/<obs_id>` with source + final URL |
| **5. Profile** | `agent/analyzer.py` → LLM | Structured business profile (summary, audience, value prop, strengths/weaknesses) |
| **6. Enrich** | `connectors/google_search_console.py` | Optional 28-day search analytics (clicks, impressions, CTR, top 25 queries/pages). Wrapped in try/except — a GSC failure never breaks the run |
| **7. Opportunities** | `agent/opportunity_generator.py` → LLM | 0–5 ranked, evidence-grounded opportunities via strict `json_schema` response format |
| **8. Validate** | `agent/opportunity_validation.py` | Strict schema validation — raises on any violation, never silently normalises |
| **9. Dedupe** | `services/opportunity_service.py` | Skips an opportunity whose `problem_key` already exists for the business |
| **10. Decide** | `agent/decision_engine.py` → LLM | One concrete action per opportunity, informed by up to 20 historical learnings |
| **11. Await approval** | Firestore + REST | Actions stored as `pending_approval`; user must approve via `POST .../actions/<id>/approve` |
| **12. Execute** | `services/execution_engine.py` + Connectors | Runs the approved action through the routed connector |
| **13. Measure** | `services/measurement_service.py` | Records `execution_success: 1` against the execution |
| **14. Learn** | `services/learning_service.py` | Deterministic learning synthesis stored idempotently, feeding future decisions |

---

## Visual GTM Pipeline (PixelRAG)

Triggered by `POST /api/gtm/run`. This pipeline exists because text scraping discards roughly a third of a page's meaning — layout, visual hierarchy, above-the-fold composition, social proof placement, and pricing presentation are all invisible to HTML extraction. PixelRAG moves the analysis into **pixel space** and adds a **competitive** dimension the text pipeline never had.

```
POST /api/gtm/run
   → routes/gtm_routes.py::trigger_gtm_run()
   → Firestore: businesses/<id>/gtm_runs/<run_id>  {status: "queued"}
   → task.run_gtm_analysis.delay(...)              → 202 {run_id, task_id}
   │
   │  Celery worker
   ▼
 1. pixelrag_service.render_and_tile_page(website_url)
      · headless Chromium via Playwright
      · waits for networkidle (falls back to domcontentloaded)
      · dismisses cookie banners (10 selectors)
      · measures scrollHeight, scrolls, then screenshots per 800px slice
      · labels tiles: hero · value · social · pricing · features · details
                       testimonials · faq · footer · extra_1..3
      · writes manifest.json
      → static/tiles/<business_id>/<run_id>/user_site/
   │
 2. gtm_discovery_service.discover_competitors(max=2)
      · seed queries = GSC top queries → Firestore keywords/industry → fallback
      · DuckDuckGo HTML SERP scrape → a.result__url extraction
      · filters 24 aggregators/social platforms
   │
 3. pixelrag_service.render_and_tile_page(comp_url)  ×N
      → static/tiles/<business_id>/<run_id>/comp_N/
   │
 4. agent/gtm_engine.analyze_gtm_tiles(...)          ← Groq Vision
      · up to 3 user tiles + 2 tiles per competitor
      · base64 data-URL image parts in one multimodal request
      · every score clamped 0–100, confidence clamped [0.1, 1.0]
      · invalid enum values coerced to safe defaults
      · returns all-defaults on ANY LLM exception (never raises)
   │
 5. services/opportunity_service.create_opportunity() per opportunity
   │
 6. gtm_dossier_service.generate_gtm_dossier_markdown()
      → static/dossiers/<business_id>/<run_id>.md
   │
 7. Firestore terminal update {status: "completed", gtm_scores, blind_spots,
      competitors_analyzed, user_manifest, opportunities_created_count, dossier_path}
```

### GTM score dimensions

The vision engine scores the business on five axes, each 0–100:

| Score | What it measures |
|-------|------------------|
| `overall` | Composite GTM health |
| `above_the_fold` | Strength of the first-screen value proposition |
| `pricing_clarity` | How legibly pricing and value are communicated |
| `social_proof` | Presence and prominence of testimonials, logos, case studies |
| `cro_friction` | Conversion friction — CTA clarity, form friction, navigation traps |

### The dossier

`GET /api/gtm/runs/<run_id>/dossier` streams the generated Markdown, regenerating it inline if the file is missing. Four sections:

1. **Executive Summary & GTM Health Score** — overall score + per-axis table
2. **Competitive Landscape Benchmark** — side-by-side vs discovered competitors
3. **Critical Positioning Blind Spots** — gaps relative to the competitive set
4. **Prioritized 30-Day Tactical Roadmap** — numbered, impact-tagged actions

---

## Feature Breakdown

### Authentication & Security

Located in `routes/auth.py` and `routes/auth_api.py`:

- **Dual auth surface**: a JSON API (`/api/auth/register|login|logout|me`) used by the SPA, plus a legacy server-rendered flow (`/login`, `/register`) whose Jinja templates are currently empty (see [Known Issues](#known-issues--drift)).
- **Session-cookie auth, not bearer tokens** — a deliberate decision so that all ~20 pre-existing session-guarded routes required zero changes when the JSON API was added.
- **CSRF protection**: the login form embeds a one-time HMAC-compared token (`_login_csrf`); constant-time comparison prevents timing attacks.
- **IP-based brute-force protection**: Redis-first rate limiter with in-memory fallback. 5 failed login attempts → 15-minute IP lockout. Registration capped at 3 accounts per IP per hour. Every helper swallows `RedisError` and degrades safely — Redis being down never locks anyone out or blocks signups.
- **Device binding**: on login the user's `device_id` is stored in Firestore. Unexpected devices write an audit entry to `security_logs`.
- **Session token rotation**: a new cryptographic token on every login is stored in Firestore as `active_session_token`. Logging in elsewhere invalidates all previous sessions immediately.
- **Session hardening**: `HttpOnly`, `SameSite=Lax`, and `Secure` whenever `DEBUG` is false.
- **Password security**: hashed with Werkzeug; minimum 8-character policy.
- **Ownership checks**: every business-scoped endpoint verifies `owner_id == session["user_id"]` **before** any read, so unauthenticated requests get 401 rather than leaking existence via 404.

### Business Management

Routes in `routes/user.py` (writes) and `routes/business_api.py` (reads):

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/business` | GET | List businesses owned by the caller (JSON) |
| `/api/business` | POST | Create a business record |
| `/api/business/<id>` | GET | Fetch a single business |
| `/api/business/<id>` | PATCH | Update `name`, `website_url`, `industry`, `description` (allow-list only) |
| `/api/business/<id>` | DELETE | Delete a business |

Business documents carry `name`, `website_url`, `industry`, `description`, `owner_id`, and timestamps. Website URLs pass through `validations.py` before storage.

### Website Analysis

`website_analyzer.py` implements multi-layer SSRF defence:

- **Scheme whitelist** — only `http://` and `https://`.
- **Port whitelist** — 80 and 443 only (30 other ports explicitly blocked).
- **IP blocklist** — 21 CIDRs covering RFC-1918, loopback, link-local, documentation, multicast, and reserved ranges, plus alternative IPv4 notations (decimal, octal, hex, short-form) that bypass naive parsing.
- **DNS rebinding prevention** — the hostname is resolved once at validation time and the resolved IP is *pinned* on the thread via a custom `socket.getaddrinfo` dispatcher installed at import, closing the TOCTOU window between validation and connection.
- **Redirect validation** — up to 5 hops, each independently re-validated against the full policy.
- **Size cap** — 2 MB decompressed, streamed rather than buffered.
- **Control-character rejection** — guards the CVE-2023-24329 class of attack.
- **Bracket audit** — guards CVE-2025-0938-style authority confusion.
- **Credential / backslash rejection** — `user:password@` and backslash-authority URLs are refused.

Run status lives in `businesses/<id>/agent_runs/<run_id>`: `status`, `analysis_status`, `observation_id`, `opportunity_ids`, `actions_created`, `task_id`, timestamps.

### Opportunity Generation

`agent/opportunity_generator.py` calls the LLM with `OPPORTUNITY_GENERATION_SYSTEM_PROMPT` under a strict `response_format={"type": "json_schema", ...}` (`additionalProperties: false`, full `required` list). When Search Console data exists it is included in the analysis context, enabling search-grounded opportunities such as low CTR on high-impression queries.

```json
{
  "title": "string",
  "description": "string",
  "problem": "string",
  "problem_key": "social_proof | pricing_transparency | value_proposition | support_information | legal_information | seo_visibility | content_gap | conversion_friction | technical_issue | audience_targeting | other",
  "evidence": ["string"],
  "potential_impact": "low | medium | high",
  "confidence": 0.0,
  "type": "website | content | seo | conversion | social | other"
}
```

- Results are sorted by `potential_impact` then `confidence`, descending.
- `agent/opportunity_validation.py` enforces **strict** semantics: 8 required keys, max 5 items, confidence must be numeric (bool rejected) within `[0, 1]`, evidence must be a non-empty list of non-empty strings, ordering must be strictly descending. It **raises** on violation rather than coercing. Extra keys are tolerated.
- Deduplication happens in `services/opportunity_service.py` by `problem_key`.
- The prompt is explicitly grounded: the model must cite evidence from the analysis, and speculative items below ~0.3 confidence are excluded.

### Decision Engine & Action Planning

`agent/decision_engine.py` converts each validated opportunity into one concrete proposed action. The model receives:

1. The full business analysis (including Search Console data when present)
2. The opportunity details
3. Up to 20 recent `learning_type: "marketing"` learnings retrieved from Firestore

The output schema has 12 required fields including `action_type` (`website | github | content | seo | social | email | research | other`), `requires_approval: true` (hardcoded and validated), and `expected_outcome` (metrics to monitor, not a promised result). Optional execution fields: `content_type`, `page_url`, `content`, `target_path`. Extra keys returned by the model are stripped before validation.

**Historical learning discipline**: the system prompt forbids implying causation from past measurements; correlational language ("was associated with", "was observed alongside") is mandated.

### Action Approval & Execution

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/business/<id>/actions` | GET | List actions (optional `?status=`) |
| `/api/business/<id>/actions/<action_id>` | GET | Single action detail |
| `/api/business/<id>/actions/<action_id>/approve` | POST | Approve → queue execution |
| `/api/business/<id>/actions/<action_id>/reject` | POST | Reject |
| `/api/business/<id>/actions/dry-run` | POST | Create a dry-run test action |
| `/api/business/<id>/actions/test-approval` | POST | Create a pending-approval test action |
| `/api/business/<id>/executions/<exec_id>` | GET | Poll execution status |
| `/api/business/<id>/executions/test` | POST | Manually queue an approved action |

The **approve endpoint** runs inside a Firestore transaction: it marks the action approved, creates the `executions/<exec_id>` document (`status: queued`), and enqueues exactly one Celery job — all-or-nothing. Re-approving returns the existing `execution_id` with `already_approved` rather than duplicating work. Only `pending_approval` actions can be approved; only `approved` actions can execute.

The **execution engine** (`services/execution_engine.py`):

1. Returns early if the execution is already `completed` (idempotent).
2. Validates the execution status is `queued` or `running`.
3. **Requires `action.status == "approved"`** — an unapproved action can never execute.
4. Routes through `connectors.get_connector(action)` and calls `execute()`.
5. On success: writes the result, then `record_measurement(execution_success=1)` and `create_learning_from_measurement`.
6. On failure: writes `failed` plus the error string, then re-raises.

### Connector Layer

All connectors implement `BaseConnector.execute()` and are reached through the `get_connector(action)` factory.

| Connector | Routed Action Type | Behaviour |
|-----------|--------------------|-----------|
| **GitHubConnector** | `github` | Creates branch `agent/<title-slug>-<exec_id[:12]>`, writes/updates one file |
| **InstagramConnector** | `social` | Creates a media container → polls status → publishes |
| **WebsiteConnector** | `website` | Validates website actions; performs no real writes |
| **DryRunConnector** | `dry_run` | No-op simulation for pipeline testing |

**GitHub safety guards**:

- `target_path` must be relative — no leading `/`, no `..` traversal.
- Destructive-replacement check: if the existing file has ≥ 20 lines, the new content must retain ≥ 25 % of the original length **and** stay within a 50 % line-deletion ratio. `difflib` performs the comparison.
- Branch naming is deterministic per execution, so retries reuse the same branch.

### Measurements & Learning Loop

After every successful execution:

1. `measurement_service.record_measurement()` writes `businesses/<id>/measurements/` with `metric: "execution_success"`, `value: 1`, `source: "execution_engine"`, and a stamped `action_id`.
2. `learning_service.create_learning_from_measurement()` synthesises a structured learning — **deterministically, without an LLM call**:
   ```json
   {
     "observation": "string",
     "outcome": "string",
     "learning": "string",
     "learning_type": "marketing",
     "confidence": 0.0,
     "metric": "string",
     "direction": "positive | negative | neutral"
   }
   ```
   Three branches: `execution_success` (operational, confidence 1.0), before/after marketing comparison (confidence 0.7), and generic (confidence 0.5).
3. The `measurement_id` is used as the learning's **document ID** inside a `@firestore.transactional` block, making the write idempotent — retries never create duplicates.
4. Future decision-engine calls retrieve up to 20 recent learnings, closing the loop.

### Social, SEO & Code Integrations

#### GitHub OAuth — `routes/github_connections.py`

| Endpoint | Description |
|----------|-------------|
| `GET /api/connections/github/connect` | Returns a signed `authorization_url` |
| `GET /api/connections/github/callback` | Exchanges the code, fetches account info, stores the connection, redirects to `{FRONTEND_URL}/connections` |
| `GET /api/connections/github/repositories` | Lists repos accessible to the connected account |
| `PATCH /api/connections/github/repository` | Selects `owner/repo`, validates format and ownership, captures `default_branch` |

OAuth state is **cryptographically signed** with `URLSafeTimedSerializer(SECRET_KEY, salt="github-oauth-state")` and `max_age=600` — not merely compared for equality.

#### Instagram OAuth — `routes/instagram_connections.py`

| Endpoint | Description |
|----------|-------------|
| `GET /api/connections/instagram` | Redirects to Meta OAuth with `state` + `business_id` in session |
| `GET /api/connections/instagram/callback` | Exchanges the code, stores the connection |
| `GET /api/connections/instagram/status` | Returns connection status |

Required scopes: `instagram_business_basic`, `instagram_business_content_publish`. Config is read in `config/instagram.py`, which raises a `RuntimeError` listing every missing key.

#### Google Search Console OAuth — `routes/search_console_connections.py`

| Endpoint | Description |
|----------|-------------|
| `GET /api/connections/search-console/connect` | Returns `{authorization_url, code_verifier}`; verifier + state stored in session |
| `GET /api/connections/search-console/callback` | PKCE exchange; **reuses an existing refresh token** when Google omits one; verifies access via `list_sites()` before saving |
| `GET /api/connections/search-console/properties` | Lists `siteUrl` + `permissionLevel` |
| `POST /api/connections/search-console/add-property` | Accepts `sc-domain:` or HTTP(S) URL-prefix; returns 403 `reconnect_required` on Google 403 |
| `POST /api/connections/search-console/select-property` | Only allows properties present in `list_sites()` |
| `GET /api/connections/search-console/analytics` | Window `[today-30d, today-3d]`; totals + top 25 queries + top 25 pages |

Scope: `https://www.googleapis.com/auth/webmasters.readonly`. The 3-day lag at the tail of the window avoids the partial-data artefacts Search Console reports for recent dates. `OAUTHLIB_RELAX_TOKEN_SCOPE=1` is set at exchange time to tolerate Google's incremental scope grants.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Web Framework** | Flask 3.1.3 |
| **Database** | Google Cloud Firestore (document store) |
| **Auth Provider** | Firebase Admin SDK 7.5 |
| **Task Queue** | Celery 5.6 |
| **Broker / Backend / Rate limits** | Redis 8 |
| **LLM Provider** | Groq SDK 1.7 (OpenAI-compatible `chat.completions`) |
| **Text model** | `GROQ_MODEL` — default `llama-3.3-70b-versatile` |
| **Vision model** | `GROQ_VISION_MODEL` — default `llama-3.2-11b-vision-preview` |
| **Headless Browser** | Playwright 1.49 (Chromium) |
| **HTML / SERP Parsing** | BeautifulSoup4 4.15 |
| **Search Console** | Google Search Console API v1 (`google-api-python-client`) |
| **Token Encryption** | `cryptography` Fernet |
| **Password Hashing** | Werkzeug (`pbkdf2:sha256`) |
| **HTTP Client** | `requests` 2.34 |
| **CORS** | `flask-cors` 6.0 |
| **Proxy Support** | `werkzeug.middleware.proxy_fix.ProxyFix` |
| **Frontend** | Vanilla JS SPA + Tailwind CDN — no build step |
| **Config** | `python-dotenv` |

> **Note on unused dependencies.** `Flask-SQLAlchemy`, `Flask-Migrate`, `alembic`, and `psycopg2-binary` are pinned in `requirements.txt` but **nothing in the codebase uses them**. There are no SQL models, no migrations, and no relational database. Firestore is the only datastore. These pins can be removed.

---

## Frontend SPA

`static/` contains a dependency-free single-page application served by Flask itself — `auth_bp.home()` returns `send_static_file("index.html")` at `/`.

| File | Size | Purpose |
|------|------|---------|
| `static/index.html` | ~14 KB | Shell with four `data-view` sections: `login`, `register`, `dashboard`, `business`; create/edit and delete-confirm modals; toast container |
| `static/js/api.js` | ~0.9 KB | `apiFetch()` wrapper — `credentials: "same-origin"`, JSON encode, throws `{message, status}` |
| `static/js/app.js` | ~20 KB | View router and all handlers, ~15 `apiFetch` call sites, light/dark theme persisted to `localStorage["blom-theme"]` |

Design decisions worth knowing:

- **Same-origin, not a separate dev server.** The SPA is served by Flask, so the `HttpOnly` `SameSite=Lax` session cookie just works with no CORS preflight and no token plumbing. The `flask_cors` registration in `app.py` is a vestige of the earlier cross-origin phase.
- **No build step.** Tailwind via CDN, vanilla ES modules, `node --check` used for JS syntax verification in CI-equivalent checks.
- **401 dispatch.** `apiFetch` fires a `session-expired` `CustomEvent` on 401 for non-auth routes, which the app shell handles centrally.
- **The SPA polls** `GET /api/business/<id>/runs/latest` every 3 s until a run reaches a terminal status.

---

## Project Structure

```
backend/
├── app.py                        # Flask app object, CORS, ProxyFix, session hardening,
│                                 # blueprint registration, no-cache headers, 404/500 handlers
├── task.py                       # Celery app + all 4 background jobs
├── firebase.py                   # Firebase Admin init, exports the Firestore `db` client
├── redis_helpers.py              # 5 Redis-backed auth-rate-limit helpers (fail-safe)
├── validations.py                # SSRF-hardened URL validation & resolution
├── website_analyzer.py           # SSRF-safe HTTP fetcher (DNS pinning) + HTML parser
├── decorators.py                 # login_required session guard (currently unreferenced)
├── extensions.py                 # Empty placeholder — no Flask extensions in use
│
├── agent/                        # LLM reasoning layer (Groq)
│   ├── analyzer.py               # Website observation → business profile (LLM)
│   ├── opportunity_generator.py  # Business profile → growth opportunities (LLM, json_schema)
│   ├── opportunity_validation.py # Strict validators — raise, never normalise
│   ├── decision_engine.py        # Opportunity → concrete action plan (LLM)
│   ├── gtm_engine.py             # Vision-LLM GTM engine (PixelRAG tiles → scores + insights)
│   ├── learning_generator.py     # Measurement → structured learning (deterministic, no LLM)
│   └── prompts.py                # All text-pipeline system + user prompts
│
├── routes/                       # Flask blueprints (8 registered, home.py is an empty orphan)
│   ├── auth.py                   # Serves the SPA + legacy HTML login/register/logout
│   ├── auth_api.py               # JSON auth (/api/auth/*)
│   ├── user.py                   # Business CRUD, agent runs, actions, approval, measurements
│   ├── business_api.py           # Business list/get JSON reads
│   ├── github_connections.py     # GitHub OAuth + repository selection
│   ├── instagram_connections.py  # Instagram OAuth + status
│   ├── search_console_connections.py  # GSC OAuth (PKCE) + properties + analytics
│   ├── gtm_routes.py             # Visual GTM OS endpoints (/api/gtm/*)
│   └── home.py                   # Empty, unregistered
│
├── services/                     # Business logic + persistence layer
│   ├── execution_engine.py       # Action execution orchestrator
│   ├── opportunity_service.py    # Validate + dedupe + persist opportunities
│   ├── opportunity_action_service.py  # Batch action generation with created/existing counters
│   ├── action_service.py         # Create actions with dedupe on live statuses
│   ├── action_generation_service.py  # Single action generation helper (currently unreferenced)
│   ├── measurement_service.py    # Record execution measurements
│   ├── learning_service.py       # Transactional, idempotent learning creation
│   ├── connection_service.py     # Provider connection CRUD + Fernet decrypt-on-read
│   ├── token_encryption.py       # Fernet encrypt/decrypt for stored OAuth tokens
│   ├── instagram_service.py      # Instagram account helper (see Known Issues)
│   ├── pixelrag_service.py       # Playwright page render → labelled vertical tiles + manifest
│   ├── gtm_discovery_service.py  # Competitor discovery (GSC seeds + DuckDuckGo SERP)
│   └── gtm_dossier_service.py    # Executive GTM dossier Markdown generation + persistence
│
├── connectors/                   # Action execution + third-party API clients
│   ├── __init__.py               # get_connector() factory
│   ├── base.py                   # BaseConnector abstract class
│   ├── dry_run.py                # No-op connector
│   ├── website.py                # Website action validation connector
│   ├── website_api.py            # Website page draft/publish client (no connector wired to it)
│   ├── github.py                 # Branch + file update with anti-destruction guards
│   ├── github_api.py             # Raw GitHub REST wrapper
│   ├── instagram.py              # Container → poll → publish connector
│   ├── instagram_api.py          # Raw Instagram Graph API wrapper
│   ├── google_search_console.py  # GSC OAuth (PKCE) + Search Console v1 API
│   └── test_actions.py           # Test action fixture builders
│
├── config/
│   └── instagram.py              # 7 INSTAGRAM_* vars + validate_instagram_config()
│
├── static/                       # The SPA + generated artifacts
│   ├── index.html, js/app.js, js/api.js
│   ├── tiles/<business_id>/<run_id>/     # PixelRAG tile output
│   └── dossiers/<business_id>/<run_id>.md  # Generated GTM dossiers
│
├── templates/                    # Jinja templates — currently all 0 bytes
├── tests/                        # pytest suite (23 test files)
│   ├── conftest.py               # sys.path bootstrap
│   ├── gtm/                      # 6 files — PixelRAG / discovery / engine / dossier / routes
│   └── search_console/           # 5 files + conftest (shared fixtures) + RUNBOOK.md
├── scripts/                      # Live E2E utilities
│   ├── e2e_analyze_flow.py       # Register → login → business → analyze → poll → assert
│   └── live_opportunity_flow.py  # One-shot live chain against a deployed instance
├── docs/superpowers/             # 8 design specs + 8 implementation plans
├── venv/                         # Local virtualenv
├── requirements.txt
└── .env                          # Environment configuration (never commit)
```

---

## API Reference

All routes are session-cookie authenticated unless marked `—`. No blueprint uses `url_prefix`; every path is declared in full.

### Authentication

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/` | — | Serve the SPA shell |
| `POST` | `/api/auth/register` | — | Register → 201, 400, 409 (duplicate), 429 (throttled), 500 |
| `POST` | `/api/auth/login` | — | → 200, 400, 401 (bad creds), 403 (disabled), 423 (locked) |
| `POST` | `/api/auth/logout` | session | Nulls `active_session_token`, clears session |
| `GET` | `/api/auth/me` | session | Current user profile |
| `GET/POST` | `/login`, `/register`, `/logout` | — | Legacy server-rendered flow (templates empty) |

### Businesses

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/business` | session | List owned businesses |
| `POST` | `/api/business` | session | Create business → 201 |
| `GET` | `/api/business/<id>` | session | 200 / 401 / 403 / 404 |
| `PATCH` | `/api/business/<id>` | session | Update allow-listed fields |
| `DELETE` | `/api/business/<id>` | session | Delete business |

### Agent Runs & Analysis

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/business/<id>/analyze` | session | Queue text pipeline → 202 `{run_id, task_id}`; 503 if broker unreachable |
| `GET` | `/api/business/<id>/runs/latest` | session | Latest run by `created_at` |

### Opportunities

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/business/<id>/opportunities` | session | List all |
| `GET` | `/api/business/<id>/opportunities/<opp_id>` | session | Single opportunity |

### Actions & Executions

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/business/<id>/actions` | session | List actions (`?status=`) |
| `GET` | `/api/business/<id>/actions/<action_id>` | session | Single action |
| `POST` | `/api/business/<id>/actions/<action_id>/approve` | session | Approve → 202, queues exactly one execution (idempotent) |
| `POST` | `/api/business/<id>/actions/<action_id>/reject` | session | Reject |
| `POST` | `/api/business/<id>/actions/dry-run` | session | Create dry-run action → 201 |
| `POST` | `/api/business/<id>/actions/test-approval` | session | Create pending-approval action → 201 |
| `GET` | `/api/business/<id>/executions/<exec_id>` | session | Execution status |
| `POST` | `/api/business/<id>/executions/test` | session | Manually queue → 202 |

### Measurements & Learnings

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/business/<id>/measurements` | session | Filters `?execution_id=`, `?metric=` |
| `GET` | `/api/business/<id>/learnings` | session | Filters `?execution_id=`, `?outcome=` |

### Visual GTM OS

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/gtm/run` | session | Queue PixelRAG pipeline → 202 `{run_id, task_id}` |
| `GET` | `/api/gtm/runs` | session | List runs (`?business_id=`), `created_at` DESC |
| `GET` | `/api/gtm/runs/<run_id>` | session | Run detail — scores, blind spots, competitors |
| `GET` | `/api/gtm/runs/<run_id>/dossier` | session | Stream the Markdown dossier; regenerates inline if absent |

### Integrations

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/connections/github/connect` | session | Signed authorization URL |
| `GET` | `/api/connections/github/callback` | session | OAuth callback |
| `GET` | `/api/connections/github/repositories` | session | List accessible repos |
| `PATCH` | `/api/connections/github/repository` | session | Select active repo |
| `GET` | `/api/connections/instagram` | session | Start Instagram OAuth |
| `GET` | `/api/connections/instagram/callback` | session | Instagram OAuth callback |
| `GET` | `/api/connections/instagram/status` | session | Connection status |
| `GET` | `/api/connections/search-console/connect` | session | Start GSC OAuth (PKCE) |
| `GET` | `/api/connections/search-console/callback` | session | GSC OAuth callback |
| `GET` | `/api/connections/search-console/properties` | session | List accessible properties |
| `POST` | `/api/connections/search-console/add-property` | session | Add a `sc-domain:` or URL-prefix property |
| `POST` | `/api/connections/search-console/select-property` | session | Set the active property |
| `GET` | `/api/connections/search-console/analytics` | session | 28-day analytics |

---

## Setup & Running Locally

### Prerequisites

- **Python 3.11+** (the project's venv runs 3.13)
- **Redis** on `localhost:6379`
- **Firebase** project with Firestore enabled + a service-account key
- **Groq API key**
- **Playwright browsers** — only required for the Visual GTM pipeline:
  ```bash
  playwright install chromium
  ```
- **Optional:** GitHub OAuth App, Instagram App, Google OAuth 2.0 client with the Search Console API enabled

### Installation

```bash
# 1. Clone and enter the repo
git clone <repo-url>
cd backend

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 3b. Test-only dependencies (deliberately NOT in requirements.txt)
pip install pytest responses google-auth-oauthlib google-api-python-client

# 4. Configure environment variables
#    NOTE: there is no .env.example in the repo — create .env from scratch
#    using the Environment Variables table below.
touch .env

# 5. Generate a Fernet key for TOKEN_ENCRYPTION_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 6. Start Redis
redis-server &

# 7. Start the Celery worker (separate terminal)
./venv/bin/celery -A task worker --loglevel=info

# 8. Start Flask (separate terminal)
python app.py
```

The API and SPA are available at `http://localhost:5000`.

> **Two flags you will need for local E2E runs.** `app.py` sets `SESSION_COOKIE_SECURE = not DEBUG`, so with `DEBUG=false` the browser drops the session cookie over plain HTTP and every request 401s. For local E2E work set `DEBUG=true`. Separately, `celery -A task worker` is not optional — without a worker running, `POST /api/business/<id>/analyze` returns 503.

### Production

```bash
gunicorn -w 4 -b 0.0.0.0:8000 "app:app"
```

Set `DEBUG=false`. Behind a proxy, `ProxyFix` is already mounted with `x_proto=1, x_host=1`, so `X-Forwarded-Proto` and `X-Forwarded-Host` are honoured for one hop.

**The Celery broker is currently hardcoded** to `redis://localhost:6379/0` in `task.py` and does **not** read `REDIS_URL`. A deployed instance needs `localhost:6379` to actually be Redis, or `task.py` must be changed to read the env var.

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SECRET_KEY` | ✅ | — | Flask session secret. **App fails to import if unset.** Also the salt for the GitHub OAuth state serializer |
| `FIREBASE_CREDENTIALS` | ✅ | — | Service-account JSON **inline** or a **file path**. **Import fails if unset or unresolvable** |
| `GROQ_API_KEY` | ✅ | — | Groq auth. `Groq()` raises at construction without it |
| `TOKEN_ENCRYPTION_KEY` | ✅ for connections | — | Fernet key for at-rest OAuth token encryption. Generate with the command above |
| `DEBUG` | — | `False` | `true`/`false`; drives debug mode and `SESSION_COOKIE_SECURE` |
| `PORT` | — | `5000` | Dev server port |
| `REDIS_URL` | — | `redis://localhost:6379/0` | Rate-limit store only. **Celery does not read this** |
| `GROQ_MODEL` | — | `llama-3.3-70b-versatile` | Any OpenAI-compatible model string |
| `GROQ_VISION_MODEL` | — | `llama-3.2-11b-vision-preview` | Vision model for the GTM engine |
| `FRONTEND_URL` | — | `http://localhost:3000` | GitHub OAuth post-callback redirect target |
| `GTM_DOSSIER_DIR` | — | `static/dossiers` | Dossier output directory |
| `GITHUB_CLIENT_ID` | — | — | GitHub OAuth App client ID |
| `GITHUB_CLIENT_SECRET` | — | — | GitHub OAuth App secret |
| `GITHUB_REDIRECT_URI` | — | — | GitHub OAuth callback |
| `INSTAGRAM_CLIENT_ID` | — | — | Meta app ID |
| `INSTAGRAM_CLIENT_SECRET` | — | — | Meta app secret |
| `INSTAGRAM_REDIRECT_URI` | — | — | Instagram OAuth callback |
| `INSTAGRAM_OAUTH_AUTHORIZE_URL` | — | — | Meta authorize endpoint |
| `INSTAGRAM_OAUTH_TOKEN_URL` | — | — | Meta token endpoint |
| `INSTAGRAM_API_BASE_URL` | — | — | Graph API base |
| `INSTAGRAM_OAUTH_SCOPES` | — | `instagram_business_basic instagram_business_content_publish` | Required scopes |
| `GOOGLE_SEARCH_CONSOLE_CLIENT_ID` | — | — | Google OAuth 2.0 client ID (Web application type) |
| `GOOGLE_SEARCH_CONSOLE_CLIENT_SECRET` | — | — | Google OAuth 2.0 client secret |
| `GOOGLE_SEARCH_CONSOLE_REDIRECT_URI` | — | — | Google OAuth callback |
| `OAUTHLIB_RELAX_TOKEN_SCOPE` | — | set to `1` in code | Tolerates Google's incremental scope grants at token exchange |
| `E2E_BASE` | — | `http://127.0.0.1:5000` | Base URL for `scripts/e2e_analyze_flow.py` |
| `WEBSITE_API_BASE_URL` | — | — | Website publishing API (client exists, no connector wired) |

> ⚠️ **Never commit `.env`, the Firebase service-account JSON, or the Google OAuth client secret.** `.gitignore` already excludes `.env`, `ai-agent-*-firebase-adminsdk-*.json`, and `client_secret_*.json`. Verify they are untracked before your first commit.

---

## Security Hardening

| Concern | Mitigation |
|---------|-----------|
| **SSRF** | Per-hop URL validation, 21-CIDR IP blocklist (private/loopback/link-local/reserved), alternative-IPv4-notation rejection, DNS rebinding prevention via thread-local IP pinning, port whitelist {80, 443}, 2 MB streaming cap |
| **URL parsing exploits** | CVE-2023-24329-class control-character rejection; CVE-2025-0938-class bracket audit; IDNA normalisation; credentials-in-URL and backslash-authority rejection; fragments dropped |
| **Prompt injection** | System prompts explicitly instruct the LLM to treat scraped content as *data, never as instructions*; untrusted content is XML-tagged to separate it from the instruction channel |
| **Prompt injection (GTM)** | The vision engine's system prompt carries its own grounding rules; **any** LLM exception returns a fully-defaulted structured result rather than propagating attacker-influenced text |
| **Brute force** | Redis-backed IP lockout (5 attempts → 15 min), registration throttle (3/hour/IP), in-memory fallback, all helpers fail-safe when Redis is down |
| **CSRF** | One-time HMAC token on the login form with constant-time comparison |
| **Session hijacking** | Session token mirrored in Firestore; rotated on every login, invalidating all prior sessions; `HttpOnly` + `SameSite=Lax` + `Secure` in production |
| **OAuth state forgery** | GitHub uses a signed, time-limited `URLSafeTimedSerializer` state (`max_age=600`); Instagram and Google store state in the signed session cookie |
| **PKCE** | Google Search Console uses a code verifier to prevent authorisation-code interception |
| **Destructive GitHub writes** | Line-count and deletion-ratio checks via `difflib` before any file update |
| **Path traversal** | GitHub `target_path` validated: no leading `/`, no `..` components |
| **Token exposure** | OAuth access and refresh tokens encrypted at rest with Fernet; decrypted only on read inside `connection_service` |
| **Account takeover** | Device-ID binding with audit logging on mismatch |
| **IDOR** | Every business-scoped endpoint checks `owner_id == session["user_id"]` before any read or write, so 401 precedes 404 and existence never leaks |
| **Cache leakage** | `Cache-Control: no-cache, no-store, must-revalidate, private` on every response |
| **Proxy spoofing** | `ProxyFix` scoped to exactly one hop for `X-Forwarded-Proto` / `X-Forwarded-Host` |

---

## Background Task Queue

`task.py` defines the Celery app and four jobs. All agent and service imports happen **inside** the task bodies so that constructing the module never builds a `Groq()` client — this keeps worker startup and route imports independent of LLM credentials.

| Task | Name | Trigger | Does |
|------|------|---------|------|
| `analyze_business_website` | `tasks.analyze_business_website` | `POST /api/business/<id>/analyze` | The 14-stage text pipeline |
| `run_gtm_analysis` | `tasks.run_gtm_analysis` | `POST /api/gtm/run` | The PixelRAG visual GTM pipeline |
| `execute_approved_action` | `tasks.execute_approved_action` | `POST .../actions/<id>/approve` | Delegates to `services.execution_engine.execute_action` |
| `run_agent_cycle` | `tasks.run_agent_cycle` | Internal | Thin wrapper that `.delay()`s the analyze task |

Broker and result backend both point at Redis. Monitoring:

```bash
./venv/bin/celery -A task worker --loglevel=info
./venv/bin/celery -A task flower    # web UI at localhost:5555
```

**Failure semantics differ between the two pipelines, deliberately:**

- The text pipeline performs a *single terminal* Firestore update at the end. Partial results (the observation, any created opportunities) survive a late failure, and the run is marked `failed` with the error string.
- `POST /api/gtm/run` logs a Celery dispatch failure as a warning and **still returns 202**, so a broker outage does not surface as a hard error to the caller — check the run document rather than the HTTP status.

---

## Firestore Data Model

```
users/{uid}
  ├── email, username, role, status
  ├── password_hash
  ├── active_session_token, bound_device_id, last_ip
  └── subscription_status, subscription_expiry, created_at, last_login

businesses/{business_id}
  ├── owner_id, name, website_url, industry, description, created_at, updated_at
  │
  ├── agent_runs/{run_id}
  │   └── status (queued|running|awaiting_approval|completed|failed), analysis_status,
  │       observation_id, opportunity_ids[], actions_created, task_id, timestamps
  │
  ├── observations/{obs_id}
  │   └── source_url, final_url,
  │       analysis { title, description, meta_description, headings[], links[], search_console{} },
  │       created_at
  │
  ├── opportunities/{opp_id}
  │   └── title, description, problem_key, evidence[], potential_impact,
  │       confidence, type, status ("identified"), created_at
  │
  ├── actions/{action_id}
  │   └── action_type, status (pending_approval → approved → running → completed|failed),
  │       requires_approval, content, content_type, page_url, target_path,
  │       opportunity_id, expected_outcome
  │
  ├── executions/{exec_id}
  │   └── action_id, status (queued → running → completed|failed), result, error,
  │       task_id, timestamps
  │
  ├── measurements/{measurement_id}
  │   └── metric, value, action_id, execution_id, source, created_at
  │
  ├── learnings/{measurement_id}        ← ID is the measurement_id: idempotent by construction
  │   └── observation, outcome, learning, learning_type, confidence,
  │       direction, metric, execution_id
  │
  ├── connections/{connection_id}
  │   └── provider (github | instagram | google_search_console)
  │       access_token    (Fernet-encrypted)
  │       refresh_token   (Fernet-encrypted)
  │       token_expires_at, account_id
  │       repository + default_branch   (github)
  │       site_id                        (google_search_console)
  │       status, created_at
  │
  └── gtm_runs/{run_id}
      └── status (queued|running|completed|failed),
          gtm_scores { overall, above_the_fold, pricing_clarity, social_proof, cro_friction },
          blind_spots[], competitors_analyzed[], user_manifest{},
          opportunities_created_count, dossier_path,
          started_at, completed_at, error

security_logs/{log_id}
  └── type (device_mismatch), device_id, user_id, ip, timestamp
```

---

## Testing

**Framework:** pytest with `unittest.mock`. There is **no** `pytest.ini`, `pyproject.toml`, `setup.cfg`, or `tox.ini` — zero pytest configuration, so tests must be run from the repository root. Test dependencies are intentionally kept out of `requirements.txt` and installed separately (see [Setup](#setup--running-locally)).

```bash
./venv/bin/python -m pytest tests/ -q
```

### Current status — not green

**233 tests are collected. Roughly 60–66 fail per run, and that total is non-deterministic** — three consecutive identical runs produced 66, 60, and 65 failures. The *set* of failing files is completely stable; only the count inside `test_opportunity_validation.py` wobbles (39–40), because those heavily-parametrized cases depend on ordering that the suite does not control. **Trust the per-file breakdown, not the total.**

| File | Failures | Cause |
|------|----------|-------|
| `tests/test_opportunity_validation.py` | 39–40 | Parametrized against an older validator; expects 8-key opportunities and different strictness semantics |
| `tests/test_connectors.py` | 11 | Expects `get_connector` to `raise ValueError` for unknown types; it now returns `None`. Also expects `InstagramConnector` to return `status: "not_implemented"` |
| `tests/test_opportunity_generator.py` | 6 | Expects an earlier payload shape (`description` vs `meta_description` mismatch) |
| `tests/test_task_pipeline.py` | 5 | Asserts a `position` field on opportunity docs that `opportunity_service.create_opportunity` does not write |
| `tests/test_execution_engine.py` | 2 | Same stale `get_connector` contract |

These are recorded as **accepted drift** in the SDD ledger at `.superpowers/sdd/2026-09-17-frontend-spa/progress.md` — the baseline was deliberately frozen at "107 passed + 3 failed" so the SPA work would not be blocked by connector refactors. The count grew afterwards because the validation suite was heavily parametrized after that baseline was set.

### Green suites

Everything else passes, including all work added for the two most recent features:

| Suite | Result | Coverage |
|-------|--------|----------|
| `tests/gtm/` | **49 passed**, 0 failed | PixelRAG tiling (happy path, height cap, cookie banners, navigation failures, timeouts), competitor discovery (domain extraction, aggregator filtering, GSC seeds, DuckDuckGo parsing, network errors), vision engine (base64 encoding, output normalisation, multimodal prompt assembly, LLM-exception path), dossier generation and persistence, all four GTM routes, scaffolding |
| `tests/search_console/` | **62 passed**, 0 failed | OAuth flow config, PKCE exchange, refresh-token construction/refresh/skip, `list_sites`, `add_site`, `get_search_analytics`, and all six GSC routes |
| Remaining 7 root files | **48 passed**, 0 failed | Auth API, auth/Redis wiring, business API guard ordering, frontend static serving, Redis helper degradation, user routes, `analyze_html` fields |

### Testing conventions

- `tests/search_console/conftest.py` is the **de-facto shared fixture module**. It sets five env defaults before any import (GSC client id/secret/redirect, a freshly generated Fernet key, `SECRET_KEY`) and exports `flask_app`, `client`, `auth_client`, `callback_client`, `mock_business_doc`, `mock_missing_doc`, `mock_wrong_owner_doc`, `mock_connection`. `tests/gtm/conftest.py` re-exports these and adds `mock_gtm_business_doc`, `mock_playwright_page`, and `mock_vision_response`.
- **Patch at the module boundary.** Route tests patch `routes.search_console_connections.*`; connector tests patch `routes.google_search_console.*` at the Google library boundary.
- **Firestores are faked, not mocked.** Older suites hand-roll small in-file fakes (`FakeTaskDb`/`_Ref`/`_Collection` in `test_task_pipeline.py` and `test_execution_engine.py`, `BizDb` in `test_business_api.py`, `FakeQuery`/`FakeRef` in `test_user_routes.py`). This was a deliberate choice — do not refactor them into a shared module.
- **Verify state, not queries** — assertions check persisted Firestore documents rather than call counts.
- `tests/search_console/RUNBOOK.md` is a 170-line manual E2E runbook with curl commands, a 7-step happy path, three failure scenarios, and a completed sign-off table.

---

## Known Issues & Drift

Honest inventory of what is currently broken, dead, or misleading. Nothing here is fixed; it is documented so the next contributor does not have to rediscover it.

### Blocked / broken code paths

| Issue | Location | Impact |
|-------|----------|--------|
| `NameError` — references undefined local `account` | `routes/instagram_connections.py:215` | **The Instagram OAuth callback cannot succeed.** `get_instagram_account` is imported but never called |
| `INSTAGRAM_API_BASE_URL` used but never imported | `connectors/instagram_api.py:19,25` | `NameError` on any `InstagramAPI` construction |
| `create_media_container` / `get_media_container_status` / `publish_media` defined at module level with a `self` first parameter | `connectors/instagram_api.py` | Not actually methods of `InstagramAPI`, so `InstagramConnector` gets `AttributeError` |
| `InstagramAPI(base_url=..., access_token=...)` but `__init__` accepts only `access_token` | `services/instagram_service.py:12` | Constructor mismatch |
| `get_connector` has no fallback and no `raise` | `connectors/__init__.py` | Unknown action types return `None`, so `execution_engine` fails with `AttributeError` instead of a clean `ValueError` |

Net effect: **the Instagram execution path is non-functional end to end.** The GitHub and dry-run paths work.

### Missing files / empty files

| Issue | Detail |
|-------|--------|
| `templates/*.html` are all **0 bytes** | `app.py`'s 404/500 handlers and `routes/auth.py`'s `/login` and `/register` render them, so error pages return an **empty body** and the legacy HTML auth flow renders nothing. The SPA is unaffected |
| `templates/business.html` **does not exist** | `routes/user.py:44` renders it. The route is shadowed by `auth_bp`'s `/` so it is unreachable in practice |
| `routes/home.py` is **0 bytes** | Not imported anywhere |
| `extensions.py` is **0 bytes** | Not imported anywhere. No Flask extension instances exist in the project |
| No `.env.example` | Setup requires creating `.env` from scratch |

### Dead code

`decorators.py::login_required` (imported nowhere — `routes/auth.py` carries a commented-out duplicate), `services/action_generation_service.py`, `connectors/website_api.py` (no connector is wired to it), `task.run_agent_cycle` (a thin `.delay()` wrapper), `connectors/test_actions.py`, `routes/auth.py::_subscription_is_active`, and the payment-blueprint hooks (`from routes.payment import payment_bp` is commented out in `app.py`).

### Configuration debt

- **Celery broker/backend are hardcoded** to `redis://localhost:6379/0` in `task.py` and ignore `REDIS_URL`. A deployed environment needs to change this.
- **`requirements.txt` omits three imported packages**: `pytest` (used throughout `tests/`), `google-auth-oauthlib` (the `Flow` object in `connectors/google_search_console.py`), and `google-api-python-client` (`googleapiclient.discovery.build`). Note `google-auth` *is* pinned, but it is `google-auth-oauthlib` that is actually needed.
- **`requirements.txt` pins four unused packages**: `Flask-SQLAlchemy`, `Flask-Migrate`, `alembic`, `psycopg2-binary`.
- The blocked-CIDR table in `website_analyzer.py` is a **deliberate duplication** of the one in `validations.py`. It is intentional, not an oversight — keep them in sync when editing either.
- `flask_cors` is registered with a single hardcoded origin `http://localhost:3000`, but the SPA is now same-origin, so CORS is effectively unused.

### Untracked local artifacts

These are gitignored but present in the working tree. Do not commit them:

- `.coverage`, `summary.txt` (a stale captured pytest failure report), `dump.rdb` (Redis snapshot), `hello.txt`
- `ai-agent-86543-firebase-adminsdk-*.json` — **live Firebase service-account private key**
- `client_secret_*.googleusercontent.com.json` — **live Google OAuth client secret**
- `pixelrag_test_tiles/` — PixelRAG output artifacts from manual testing

---

## Development Workflow

The project uses **spec-driven development (SDD)** under `docs/superpowers/`. Every feature has a design spec, a task-by-task implementation plan, and an execution ledger.

```
docs/superpowers/
├── specs/     # 8 design documents — requirements, decisions, rejected alternatives
└── plans/     # 8 implementation plans — numbered TDD tasks with verification steps
.superpowers/sdd/<plan-name>/     # execution ledger (gitignored)
├── progress.md                    # commit ranges, test baselines, USER DECISION points
├── task-N-brief.md / task-N-report.md
└── review-<sha>..<sha>.diff
```

| Document | Feature |
|----------|---------|
| `specs/2026-09-15-background-analysis-e2e-test-design.md` | Repairing the Redis → Celery → analyze → agent_runs flow |
| `specs/2026-09-15-opportunity-generator-testing-design.md` | Testable opportunity generation + reusable strict validators |
| `specs/2026-09-16-connector-routing-tests-design.md` | Pinning existing connector behaviour with zero production changes |
| `specs/2026-09-16-opportunity-pipeline-wiring-design.md` | Wiring agent modules into the Celery task; Approach A (sequential stages) chosen over `chain()` |
| `specs/2026-09-17-api-auth-design.md` | JSON auth — session-cookie over bearer tokens so existing routes needed no changes |
| `specs/2026-09-17-frontend-spa-design.md` | The SPA — same-origin static app, Tailwind CDN, no build step |
| `specs/2026-10-16-google-search-console-testing-design.md` | The 40-test GSC suite + manual runbook; documents one known semantic bug rather than fixing it |
| `specs/2026-10-16-pixelrag-gtm-system-design.md` | The Visual GTM OS — PixelRAG, competitor discovery, VLM teardown, executive dossier |

Plans commonly pin exact error strings that must stay byte-for-byte unchanged, call out that pytest is dev-only and must not enter `requirements.txt`, and set explicit coverage targets (the PixelRAG plan requires **≥ 90 % line coverage** on new GTM modules).

### Live utility scripts

```bash
# Full E2E: register → login → create business → analyze → poll Firestore → assert → cleanup
./venv/bin/python scripts/e2e_analyze_flow.py

# One-shot live chain against a deployed instance
./venv/bin/python scripts/live_opportunity_flow.py
```

`e2e_analyze_flow.py` decodes the Flask session cookie to extract the `_login_csrf` token. It requires `DEBUG=true` locally — with the Secure cookie flag on, the session cookie is dropped over plain HTTP.

---

*Flask · Celery · Firestore · Redis · Groq (text + vision) · Playwright · Google Search Console API*