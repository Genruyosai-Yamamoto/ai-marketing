# Blom — AI Growth Agent · Backend

> **An autonomous marketing intelligence platform** that scrapes and analyses your business website, surfaces evidence-based growth opportunities, proposes concrete marketing actions, and executes them across GitHub, Instagram, and the web — all with mandatory human approval at every step.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Core Agent Pipeline](#core-agent-pipeline)
- [Feature Breakdown](#feature-breakdown)
  - [Authentication & Security](#authentication--security)
  - [Business Management](#business-management)
  - [Website Analysis](#website-analysis)
  - [Opportunity Generation](#opportunity-generation)
  - [Decision Engine & Action Planning](#decision-engine--action-planning)
  - [Action Approval & Execution](#action-approval--execution)
  - [Connector Layer](#connector-layer)
  - [Measurements & Learning Loop](#measurements--learning-loop)
  - [Social & Code Integrations](#social--code-integrations)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [API Reference](#api-reference)
- [Setup & Running Locally](#setup--running-locally)
- [Environment Variables](#environment-variables)
- [Security Hardening](#security-hardening)
- [Background Task Queue](#background-task-queue)
- [Firestore Data Model](#firestore-data-model)

---

## Overview

Blom is a **Flask-based AI backend** that acts as an autonomous growth-marketing agent for small businesses. A user registers their business, connects it to their website, GitHub account, and/or Instagram page, and the agent then:

1. **Observes** — scrapes the business website safely
2. **Analyses** — uses an LLM to build a structured business profile from the scraped content
3. **Identifies opportunities** — generates ranked, evidence-grounded growth opportunities
4. **Plans actions** — converts each opportunity into a concrete, executable action plan
5. **Requests approval** — every action requires explicit user sign-off before it runs
6. **Executes** — writes files to GitHub, posts to Instagram, or updates web pages
7. **Learns** — records measurements after execution and generates learnings that feed back into future decisions

The entire pipeline is asynchronous, driven by [Celery](https://docs.celeryq.dev/) backed by Redis, with state persisted in Google Cloud Firestore.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Flask Application                         │
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │  auth.py │  │  user.py │  │ github_con. │  │ instagram_  │  │
│  │ (web UI) │  │ (API)    │  │ (OAuth)     │  │ connections │  │
│  └────┬─────┘  └────┬─────┘  └──────┬──────┘  └──────┬──────┘  │
│       └─────────────┴───────────────┴─────────────────┘          │
│                              │                                    │
│                    ┌─────────▼─────────┐                         │
│                    │   Firebase Auth +  │                         │
│                    │   Firestore DB     │                         │
│                    └─────────┬─────────┘                         │
│                              │                                    │
│            ┌─────────────────▼─────────────────┐                 │
│            │         Celery Worker               │                │
│            │                                     │                │
│            │  analyze_business_website()          │                │
│            │     ↓ website_analyzer.py           │                │
│            │     ↓ agent/analyzer.py (LLM)       │                │
│            │     ↓ agent/opportunity_generator   │                │
│            │     ↓ agent/decision_engine (LLM)   │                │
│            │     → Actions: pending_approval      │                │
│            │                                     │                │
│            │  execute_approved_action()           │                │
│            │     ↓ Connector Layer               │                │
│            │     ↓ Measurement + Learning         │                │
│            └─────────────────────────────────────┘                │
└─────────────────────────────────────────────────────────────────┘
                              │
                  ┌───────────▼───────────┐
                  │    Redis (broker +     │
                  │    Celery backend +    │
                  │    rate-limit store)   │
                  └───────────────────────┘
```

---

## Core Agent Pipeline

The full autonomous cycle is triggered by a single API call: `POST /api/business/<id>/analyze`.

| Step | Module | Description |
|------|--------|-------------|
| **1. Fetch** | `website_analyzer.fetch_website_html()` | SSRF-safe HTTP fetch with DNS pinning, redirect validation, and 2 MB cap |
| **2. Parse** | `website_analyzer.analyze_html()` | Extracts title, meta description, headings (H1–H3), and up to 100 links |
| **3. Profile** | `agent/analyzer.py` → Groq LLM | Builds a structured business profile (summary, audience, value prop, strengths/weaknesses) |
| **4. Opportunities** | `agent/opportunity_generator.py` → Groq LLM | Generates 0–5 ranked, evidence-grounded growth opportunities with `problem_key`, impact, and confidence score |
| **5. Validate** | `agent/opportunity_validation.py` | Schema validates and deduplicates opportunities before persisting |
| **6. Decide** | `agent/decision_engine.py` → Groq LLM | Converts each opportunity into a concrete action plan, informed by historical learnings |
| **7. Await approval** | Firestore + REST API | Actions stored as `pending_approval`; user must explicitly approve via `POST /api/business/<id>/actions/<id>/approve` |
| **8. Execute** | `services/execution_engine.py` + Connectors | Runs the approved action through the appropriate connector |
| **9. Measure** | `services/measurement_service.py` | Records success/failure metric against the execution |
| **10. Learn** | `services/learning_service.py` → Groq LLM | Generates a structured learning from the measurement; stored for future decision cycles |

---

## Feature Breakdown

### Authentication & Security

Located in `routes/auth.py` and `routes/auth_api.py`:

- **Dual auth surface**: A server-rendered HTML flow (`/login`, `/register`) for web UI, plus a JSON API (`/api/auth/login`, `/api/auth/register`, `/api/auth/me`) for SPAs.
- **CSRF protection**: Login form embeds a one-time HMAC-compared token (`_login_csrf`); constant-time comparison prevents timing attacks.
- **IP-based brute-force protection**: Redis-first rate limiter with in-memory fallback. After 5 failed login attempts, the IP is locked out for 15 minutes. Registration is also capped at 3 accounts per IP per hour.
- **Device binding**: On login, the user's `device_id` (JavaScript-generated) is stored in Firestore. Logins from unexpected devices trigger an audit log entry in `security_logs`.
- **Session token rotation**: A new cryptographic session token is generated on every login and stored in Firestore. Logging in from another device invalidates all previous sessions immediately.
- **Session hardening**: Cookies are `HttpOnly`, `SameSite=Lax`, and `Secure` in production. Sessions are 30-minute rolling, with no-cache headers on every response.
- **Password security**: Passwords are hashed with Werkzeug (bcrypt-derived). Minimum 8-character policy enforced.
- **`login_required` decorator** (`decorators.py`): Verifies session token against Firestore on every protected request.

---

### Business Management

Routes in `routes/user.py`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | List all businesses owned by the authenticated user |
| `/api/business` | POST | Create a new business record |
| `/api/business/<id>` | PATCH | Update business name, website, industry, description |
| `/api/business/<id>` | DELETE | Delete a business (owner-only) |

Business records include: `name`, `website_url`, `industry`, `description`, `owner_id`, timestamps. Website URLs are validated and sanitised through `validations.py` before storage.

---

### Website Analysis

Entry point: `POST /api/business/<id>/analyze` — queues a Celery task and returns `run_id` + `task_id` immediately (HTTP 202).

The `website_analyzer.py` module implements a multi-layer SSRF defence:

- **Scheme whitelist**: Only `http://` and `https://` accepted.
- **Port whitelist**: Only ports 80 and 443.
- **IP blocklist**: All RFC-1918 private ranges, loopback, link-local, documentation, multicast, and reserved blocks.
- **DNS rebinding prevention**: Hostname resolved once at validation time; the resolved IP is then *pinned* on the thread via a custom `socket.getaddrinfo` dispatcher. All redirect hops are re-validated independently.
- **Redirect validation**: Up to 5 redirects, each individually validated against the full security policy.
- **Size cap**: 2 MB decompressed HTML maximum (streaming read, no full buffer).
- **Control-character rejection**: Guards against CVE-2023-24329-class attacks (null bytes, control chars in URLs).
- **Credential stripping**: URLs containing `user:password@` are rejected.

Run status is tracked in `businesses/<id>/agent_runs/<run_id>` with fields: `status`, `analysis_status`, `observation_id`, `opportunity_ids`, `actions_created`, timestamps.

---

### Opportunity Generation

`agent/opportunity_generator.py` calls Groq with the `OPPORTUNITY_GENERATION_SYSTEM_PROMPT` to identify up to 5 growth opportunities.

Each opportunity has:
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

- Opportunities are sorted by `potential_impact` then `confidence`, descending.
- `agent/opportunity_validation.py` schema-validates every field and deduplicates by `problem_key`.
- The LLM is strictly grounded: it must cite evidence from the business analysis; speculative opportunities below ~0.3 confidence are excluded.

---

### Decision Engine & Action Planning

`agent/decision_engine.py` converts each validated opportunity into one concrete proposed action.

The model is given:
1. The full business analysis
2. The opportunity details
3. Up to 20 recent historical learnings (filtered by `learning_type: marketing`)

The output schema has 13 required fields including `action_type` (one of `website | github | content | seo | social | email | research | other`), `requires_approval: true` (hardcoded), `expected_outcome` (metrics to monitor, not a promised result), and optional execution fields (`content_type`, `page_url`, `content`, `target_path` for GitHub actions).

**Historical learning discipline**: The model is forbidden from implying causation from past measurements. Evidence language like "was associated with" or "was observed alongside" is enforced in the system prompt.

---

### Action Approval & Execution

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/business/<id>/actions` | GET | List all actions (filterable by `status`) |
| `/api/business/<id>/actions/<action_id>` | GET | Get single action detail |
| `/api/business/<id>/actions/<action_id>/approve` | POST | Approve action (atomic Firestore transaction) |
| `/api/business/<id>/actions/<action_id>/reject` | POST | Reject action |
| `/api/business/<id>/executions/<execution_id>` | GET | Poll execution status |

The **approve endpoint** uses a Firestore transaction to guarantee idempotency: if already approved, the existing `execution_id` is returned without creating a duplicate. Only `pending_approval` actions can be approved; only `approved` actions can execute.

On approval, an `executions/<execution_id>` document is created (`status: queued`) and `execute_approved_action.delay()` is dispatched to Celery.

The **execution engine** (`services/execution_engine.py`):
1. Verifies execution exists and action is `approved`
2. Routes to the correct connector via `get_connector(action)`
3. On success: updates execution to `completed`, records a measurement, generates a learning
4. On failure: updates execution to `failed` with error detail

---

### Connector Layer

All connectors live in `connectors/` and implement a `BaseConnector.execute()` interface.

| Connector | Action Type | What it does |
|-----------|------------|--------------|
| **GitHubConnector** | `github` | Creates a branch (`agent/<title>-<exec_id[:12]>`), writes/updates a single file, uses `difflib` to refuse destructive changes (>50% line deletion or <25% content remaining) |
| **WebsiteConnector** | `website` | Updates a web page via the website API |
| **InstagramConnector** | `social` | Posts content to a connected Instagram Business account |
| **DryRunConnector** | `dry_run` | No-op connector for pipeline testing without side effects |

**GitHub safety guards**:
- `target_path` must be relative (no leading `/`, no `..` traversal)
- Destructive replacement check: if existing file ≥ 20 lines, new content must be ≥ 25% of original length AND ≤ 50% line deletion
- Branch naming: `agent/<action-title-slug>-<execution_id[:12]>`

---

### Measurements & Learning Loop

After every successful execution:

1. `measurement_service.record_measurement()` creates a document in `businesses/<id>/measurements/` with `metric: execution_success`, `value: 1`, `source: execution_engine`.

2. `learning_service.create_learning_from_measurement()` calls `agent/learning_generator.py` (Groq LLM) to synthesise a structured learning:
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

3. Learnings are stored with `measurement_id` as the document ID, making the operation **idempotent** via a Firestore transaction (won't create duplicates if retried).

4. Future decision engine calls fetch up to 20 recent learnings, closing the feedback loop.

---

### Social & Code Integrations

#### GitHub OAuth
Routes in `routes/github_connections.py`:

| Endpoint | Description |
|----------|-------------|
| `GET /api/connections/github/connect?business_id=` | Initiates OAuth; generates PKCE-style `state`, redirects to GitHub |
| `GET /api/connections/github/callback` | Exchanges `code` for token, fetches account info, creates connection in Firestore |
| `GET /api/connections/github/repositories?business_id=` | Lists repos accessible by the connected account |
| `PATCH /api/connections/github/repository?business_id=` | Selects a repo + captures `default_branch` |

State is stored in the user session (`github_oauth_state`, `github_oauth_business_id`) and verified with `secrets.compare_digest` on callback.

#### Instagram OAuth
Routes in `routes/instagram_connections.py`:

| Endpoint | Description |
|----------|-------------|
| `GET /api/connections/instagram?business_id=` | Initiates OAuth; generates state, redirects to Instagram |
| `GET /api/connections/instagram/callback` | Exchanges code for token, stores connection |
| `GET /api/connections/instagram/status?business_id=` | Returns connection status and account info |

Required scopes: `instagram_business_basic`, `instagram_business_content_publish`.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Web Framework** | Flask 3.1 |
| **Database** | Google Cloud Firestore (NoSQL, real-time) |
| **Auth Provider** | Firebase Admin SDK |
| **Task Queue** | Celery 5.6 |
| **Broker / Cache** | Redis 8 |
| **LLM Provider** | Groq API (Llama 3.3 70B / configurable model) |
| **HTML Parsing** | BeautifulSoup4 |
| **Token Encryption** | Python `cryptography` (Fernet) |
| **Password Hashing** | Werkzeug (`pbkdf2:sha256`) |
| **HTTP Client** | `requests` |
| **CORS** | `flask-cors` |
| **DB Migrations** | Flask-Migrate + Alembic |
| **SQL ORM** | Flask-SQLAlchemy + psycopg2 |
| **Observability** | OpenTelemetry API |
| **Proxy Support** | `werkzeug.middleware.proxy_fix` |

---

## Project Structure

```
backend/
├── app.py                        # Flask app factory, blueprint registration, error handlers
├── task.py                       # Celery tasks (analyze_business_website, execute_approved_action, run_agent_cycle)
├── firebase.py                   # Firebase Admin SDK init, Firestore client
├── redis_helpers.py              # Redis rate-limiting helpers (login attempts, registration throttle)
├── decorators.py                 # login_required session guard decorator
├── validations.py                # Input validators (URL, email, etc.)
├── website_analyzer.py           # SSRF-safe HTTP fetcher + HTML parser
│
├── agent/                        # LLM agent modules
│   ├── analyzer.py               # Website observation → business profile (Groq)
│   ├── opportunity_generator.py  # Business profile → growth opportunities (Groq)
│   ├── opportunity_validation.py # Schema validation + deduplication
│   ├── decision_engine.py        # Opportunity → concrete action plan (Groq)
│   ├── learning_generator.py     # Measurement → structured learning (Groq)
│   └── prompts.py                # All LLM system + user prompt templates
│
├── routes/                       # Flask blueprints
│   ├── auth.py                   # HTML-rendered auth (login, register, logout)
│   ├── auth_api.py               # JSON API auth (/api/auth/*)
│   ├── user.py                   # Business CRUD + agent run management
│   ├── github_connections.py     # GitHub OAuth + repo management
│   ├── instagram_connections.py  # Instagram OAuth + status
│   └── business_api.py           # Business-level API helpers
│
├── services/                     # Business logic layer
│   ├── execution_engine.py       # Action execution orchestrator
│   ├── opportunity_service.py    # Persist opportunities to Firestore
│   ├── opportunity_action_service.py  # Generate actions for all opportunities
│   ├── action_service.py         # Create/read action records
│   ├── action_generation_service.py  # Action generation helpers
│   ├── measurement_service.py    # Record execution measurements
│   ├── learning_service.py       # Create learnings from measurements
│   ├── connection_service.py     # Manage provider connections (GitHub, Instagram)
│   ├── instagram_service.py      # Instagram API helpers
│   └── token_encryption.py      # Fernet-based token encryption for stored credentials
│
├── connectors/                   # Action execution connectors
│   ├── __init__.py               # get_connector() factory
│   ├── base.py                   # BaseConnector abstract class
│   ├── github.py                 # GitHub: branch + file update
│   ├── github_api.py             # Raw GitHub REST API wrapper
│   ├── instagram.py              # Instagram connector
│   ├── instagram_api.py          # Raw Instagram Graph API wrapper
│   ├── website.py                # Website page update connector
│   ├── website_api.py            # Website API wrapper
│   └── dry_run.py                # No-op test connector
│
├── config/
│   └── instagram.py              # Instagram OAuth config + validation
│
├── templates/                    # Jinja2 HTML templates
├── static/                       # Frontend SPA assets
├── tests/                        # Test suite
├── scripts/                      # Utility scripts
├── requirements.txt
└── .env                          # Environment configuration (never commit)
```

---

## API Reference

### Authentication

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/auth/register` | — | Register new account |
| `POST` | `/api/auth/login` | — | Login, receive session cookie |
| `POST` | `/api/auth/logout` | session | Invalidate session |
| `GET`  | `/api/auth/me` | session | Get current user profile |
| `GET`  | `/login` | — | Login page (HTML) |
| `GET`  | `/register` | — | Registration page (HTML) |
| `GET`  | `/logout` | session | Logout (HTML redirect) |

### Businesses

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET`  | `/` | session | List user's businesses (HTML) |
| `POST` | `/api/business` | session | Create business |
| `PATCH`| `/api/business/<id>` | session | Update business |
| `DELETE`| `/api/business/<id>` | session | Delete business |

### Agent Runs & Analysis

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/business/<id>/analyze` | session | Trigger website analysis (async) → returns `run_id` |
| `GET`  | `/api/business/<id>/runs/latest` | session | Poll latest agent run status |

### Opportunities

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET`  | `/api/business/<id>/opportunities` | session | List all opportunities |
| `GET`  | `/api/business/<id>/opportunities/<opp_id>` | session | Get single opportunity |

### Actions

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET`  | `/api/business/<id>/actions` | session | List actions (optional `?status=` filter) |
| `GET`  | `/api/business/<id>/actions/<action_id>` | session | Get single action |
| `POST` | `/api/business/<id>/actions/<action_id>/approve` | session | Approve action → queues execution |
| `POST` | `/api/business/<id>/actions/<action_id>/reject` | session | Reject action |
| `POST` | `/api/business/<id>/actions/dry-run` | session | Create a dry-run test action |
| `POST` | `/api/business/<id>/actions/test-approval` | session | Create a pending-approval test action |

### Executions

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET`  | `/api/business/<id>/executions/<exec_id>` | session | Get execution status |
| `POST` | `/api/business/<id>/executions/test` | session | Manually queue an approved action |

### Measurements & Learnings

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET`  | `/api/business/<id>/measurements` | session | List measurements (optional `?execution_id=&metric=`) |
| `GET`  | `/api/business/<id>/learnings` | session | List learnings (optional `?execution_id=&outcome=`) |

### Integrations

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET`  | `/api/connections/github/connect` | session | Start GitHub OAuth |
| `GET`  | `/api/connections/github/callback` | session | GitHub OAuth callback |
| `GET`  | `/api/connections/github/repositories` | session | List connected GitHub repos |
| `PATCH`| `/api/connections/github/repository` | session | Select active repo |
| `GET`  | `/api/connections/instagram` | session | Start Instagram OAuth |
| `GET`  | `/api/connections/instagram/callback` | session | Instagram OAuth callback |
| `GET`  | `/api/connections/instagram/status` | session | Check Instagram connection status |

---

## Setup & Running Locally

### Prerequisites

- Python 3.11+
- Redis (running on `localhost:6379`)
- A Firebase project with Firestore enabled and a service account key
- A Groq API key
- (Optional) GitHub OAuth App credentials
- (Optional) Instagram App credentials

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

# 4. Configure environment variables
cp .env.example .env
# Edit .env with your credentials

# 5. Start Redis
redis-server &

# 6. Start the Celery worker (in a separate terminal)
celery -A task worker --loglevel=info

# 7. Start the Flask development server
python app.py
```

The API will be available at `http://localhost:5000`.

### Running in Production

Use a production WSGI server with HTTPS. Set `DEBUG=False`.

```bash
gunicorn -w 4 -b 0.0.0.0:8000 "app:app"
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | ✅ | Flask session secret — use a long random string in production |
| `FIREBASE_CREDENTIALS` | ✅ | Absolute path to Firebase service account JSON |
| `GROQ_API_KEY` | ✅ | Groq API key for LLM calls |
| `GROQ_MODEL` | — | Groq model ID (default: `llama-3.3-70b-versatile`) |
| `REDIS_URL` | — | Redis connection URL (default: `redis://localhost:6379/0`) |
| `TOKEN_ENCRYPTION_KEY` | ✅ | Fernet key for encrypting OAuth access tokens at rest |
| `DEBUG` | — | `True` / `False` (default `True`; set `False` in production) |
| `PORT` | — | HTTP port (default `5000`) |
| `GITHUB_CLIENT_ID` | — | GitHub OAuth App client ID |
| `GITHUB_CLIENT_SECRET` | — | GitHub OAuth App client secret |
| `GITHUB_REDIRECT_URI` | — | GitHub OAuth callback URL |
| `INSTAGRAM_CLIENT_ID` | — | Instagram App ID |
| `INSTAGRAM_CLIENT_SECRET` | — | Instagram App secret |
| `INSTAGRAM_REDIRECT_URI` | — | Instagram OAuth callback URL |
| `INSTAGRAM_OAUTH_AUTHORIZE_URL` | — | Instagram auth endpoint |
| `INSTAGRAM_OAUTH_TOKEN_URL` | — | Instagram token endpoint |
| `INSTAGRAM_API_BASE_URL` | — | Instagram Graph API base URL |
| `INSTAGRAM_OAUTH_SCOPES` | — | Required scopes (e.g. `instagram_business_basic instagram_business_content_publish`) |

> ⚠️ **Never commit `.env` or the Firebase service account JSON to version control.**

---

## Security Hardening

| Concern | Mitigation |
|---------|-----------|
| SSRF | Per-hop URL validation, IP blocklist (all private/loopback/link-local ranges), DNS rebinding prevention via thread-local IP pinning, port whitelist {80, 443}, 2 MB HTML cap |
| Prompt injection | System prompts explicitly instruct LLM to treat scraped content as data, not instructions; content is XML-tagged to separate user data from instructions |
| Brute force | Redis-backed IP lockout (5 attempts → 15 min lockout), registration throttle (3/hour/IP), in-memory fallback |
| CSRF | One-time HMAC token on login form, constant-time comparison |
| Session hijacking | Session token stored in Firestore; new token on every login invalidates previous sessions; `HttpOnly`, `SameSite=Lax` cookies |
| OAuth state forgery | `secrets.compare_digest` validation of OAuth state parameter |
| Destructive GitHub writes | Line count and deletion-ratio safety checks before any file update |
| Path traversal | GitHub `target_path` validated: no leading `/`, no `..` components |
| Token exposure | OAuth access tokens encrypted at rest with Fernet (`TOKEN_ENCRYPTION_KEY`) |
| Account takeover | Device ID binding with audit logging for suspicious device access |
| IDOR | Every endpoint verifies `owner_id` matches `session["user_id"]` before any read/write |

---

## Background Task Queue

The Celery application (`task.py`) defines three tasks:

| Task | Name | Trigger |
|------|------|---------|
| `analyze_business_website` | `tasks.analyze_business_website` | `POST /api/business/<id>/analyze` |
| `execute_approved_action` | `tasks.execute_approved_action` | `POST /api/business/<id>/actions/<id>/approve` |
| `run_agent_cycle` | `tasks.run_agent_cycle` | Internal orchestration |

Both broker and result backend use Redis. To monitor tasks in development:

```bash
celery -A task flower  # Flower web UI at localhost:5555
```

---

## Firestore Data Model

```
users/{uid}
  ├── email, username, role, status
  ├── password_hash
  ├── active_session_token, bound_device_id, last_ip
  └── subscription_status, subscription_expiry, created_at, last_login

businesses/{business_id}
  ├── owner_id, name, website_url, industry, description
  ├── created_at, updated_at
  │
  ├── agent_runs/{run_id}
  │   └── status, analysis_status, observation_id, opportunity_ids, task_id, timestamps
  │
  ├── observations/{obs_id}
  │   └── source_url, final_url, analysis{title, headings, links, meta_description}, created_at
  │
  ├── opportunities/{opp_id}
  │   └── title, description, problem_key, evidence[], potential_impact, confidence, type
  │
  ├── actions/{action_id}
  │   └── action_type, status (pending_approval → approved → running → completed|failed)
  │       requires_approval, content, target_path, opportunity_id, ...
  │
  ├── executions/{exec_id}
  │   └── action_id, status (queued → running → completed|failed), result, task_id, timestamps
  │
  ├── measurements/{measurement_id}
  │   └── metric, value, execution_id, source, created_at
  │
  ├── learnings/{learning_id}
  │   └── observation, outcome, learning, confidence, learning_type, direction, measurement_id
  │
  └── connections/{connection_id}
      └── provider (github|instagram), access_token (Fernet-encrypted), repository, status

security_logs/{log_id}
  └── type (device_mismatch), device_id, user_id, ip, timestamp
```

---

*Built with Flask · Celery · Firestore · Redis · Groq*
