# Google Search Console Integration — Full Test Suite Design

**Date:** 2026-10-16  
**Status:** Approved  
**Scope:** Automated unit + integration tests, plus a manual E2E runbook for the Google Search Console integration in the Blom backend.

---

## 1. Context

The Google Search Console (GSC) integration lives across three files:

| File | Role |
|---|---|
| `connectors/google_search_console.py` | `GoogleSearchConsoleAPI` class — wraps Google OAuth flow and Search Console API calls |
| `routes/search_console_connections.py` | 6 Flask endpoints — connect, callback, properties, add-property, select-property, analytics |
| `services/connection_service.py` | `upsert_google_search_console_connection`, `get_connection` — Firestore persistence + token encryption |

Zero GSC-specific tests exist today. The existing test suite uses `pytest` + `unittest.mock`; this spec adds the `responses` library for HTTP-level mocking in connector tests.

---

## 2. Goals

1. **Full edge-case coverage** of all 6 GSC route endpoints via automated tests (no real Google credentials needed).
2. **Unit tests** for the `GoogleSearchConsoleAPI` connector class in isolation.
3. **A structured manual runbook** (`RUNBOOK.md`) for live E2E verification with real OAuth credentials, with the user at the keyboard for the browser-redirect step.
4. **Document one known semantic bug** in the analytics totals aggregation without breaking existing behaviour.

---

## 3. Architecture

### 3.1 File Layout

```
tests/
└── search_console/
    ├── __init__.py                  # empty
    ├── conftest.py                  # shared fixtures
    ├── test_connector.py            # GoogleSearchConsoleAPI unit tests
    ├── test_routes_connect.py       # /connect + /callback
    ├── test_routes_properties.py    # /properties + /add-property
    ├── test_routes_select.py        # /select-property
    ├── test_routes_analytics.py     # /analytics
    └── RUNBOOK.md                   # manual E2E walkthrough
```

### 3.2 Shared Fixtures (`conftest.py`)

```python
@pytest.fixture
def app()
    # Flask app with TESTING=True, SECRET_KEY="test-secret"
    # All Firebase and Google env vars stubbed

@pytest.fixture
def client(app)
    # app.test_client()

@pytest.fixture
def auth_session(client)
    # client with session["user_id"] = "user-1" pre-set via session_transaction()

@pytest.fixture
def mock_business()
    # MagicMock Firestore document: exists=True, to_dict() returns {"owner_id": "user-1"}

@pytest.fixture
def mock_connection()
    # Typical get_connection() return value:
    # {
    #   "id": "conn-1", "provider": "google_search_console",
    #   "refresh_token": "rt-abc", "access_token": "at-abc",
    #   "token_expires_at": None, "site_id": "https://example.com/"
    # }
```

### 3.3 Mocking Strategy

**Route tests** — patch at the module boundary, not inside the implementation:

| Target | Patch path |
|---|---|
| Flask session | `client.session_transaction()` |
| Firebase `db` | `routes.search_console_connections.db` |
| `GoogleSearchConsoleAPI` | `routes.search_console_connections.GoogleSearchConsoleAPI` |
| `get_connection` | `routes.search_console_connections.get_connection` |
| `upsert_google_search_console_connection` | `routes.search_console_connections.upsert_google_search_console_connection` |

**Connector tests** — patch at the Google library boundary:

| Target | Patch path |
|---|---|
| `Credentials` | `connectors.google_search_console.Credentials` |
| `build` | `connectors.google_search_console.build` |
| `Flow` | `connectors.google_search_console.Flow` |
| Token endpoint HTTP | `@responses.activate` on `POST https://oauth2.googleapis.com/token` |

### 3.4 Error Handling Contract

Every route tests this mapping explicitly:

| Raised by | Exception | Route response |
|---|---|---|
| `connection_service` | `PermissionError` | 403 |
| `connection_service` | `ValueError` | 404 |
| `GoogleSearchConsoleAPI` | `HttpError` with status 403 | 403 + `reconnect_required: true` |
| `GoogleSearchConsoleAPI` | `HttpError` other status | 502 |
| Any | `Exception` | 500 |

---

## 4. Test Cases

### 4.1 `test_connector.py` (12 tests)

| Test | Description |
|---|---|
| `test_create_oauth_flow_builds_correct_config` | Flow built with correct client_id, secret, redirect_uri from env |
| `test_get_authorization_url_returns_url_and_verifier` | Returns string URL + non-empty code_verifier |
| `test_exchange_code_for_credentials_calls_fetch_token` | `flow.fetch_token` called with the given code |
| `test_from_refresh_token_returns_instance` | Happy path — builds `GoogleSearchConsoleAPI` with valid credentials |
| `test_from_refresh_token_refreshes_if_expired` | Calls `credentials.refresh()` when `credentials.valid` is False |
| `test_from_refresh_token_skips_refresh_if_valid` | Does not call `credentials.refresh()` when token is still valid |
| `test_list_sites_returns_site_entries` | Returns `siteEntry` list from mocked API |
| `test_list_sites_returns_empty_on_no_sites` | Returns `[]` when response has no `siteEntry` key |
| `test_add_site_calls_api_and_returns_dict` | Calls `sites().add()` and returns `{"site_url", "status", "verification_status"}` |
| `test_get_search_analytics_without_dimensions` | Request body has no `dimensions` key |
| `test_get_search_analytics_with_dimensions` | `dimensions` key is present and matches input |
| `test_get_search_analytics_returns_rows` | Returns rows list from mocked response |

### 4.2 `test_routes_connect.py` (17 tests)

**`/api/connections/search-console/connect` (GET)**

| Test | Expected |
|---|---|
| `test_connect_unauthenticated` | 401 |
| `test_connect_missing_business_id` | 400 |
| `test_connect_business_not_found` | 404 |
| `test_connect_not_owner` | 403 |
| `test_connect_success` | 200 + `authorization_url`; state + verifier stored in session |

**`/api/connections/search-console/callback` (GET)**

| Test | Expected |
|---|---|
| `test_callback_unauthenticated` | 401 |
| `test_callback_google_error_param` | 400 when `?error=access_denied` |
| `test_callback_missing_code` | 400 |
| `test_callback_missing_state` | 400 |
| `test_callback_invalid_state` | 400 — state mismatch |
| `test_callback_missing_code_verifier` | 400 — no verifier in session |
| `test_callback_missing_business_context` | 400 — business_id lost from session |
| `test_callback_business_not_found` | 404 |
| `test_callback_not_owner` | 403 |
| `test_callback_no_refresh_token_no_existing_connection` | 400 |
| `test_callback_no_refresh_token_uses_existing` | 200 — falls back to stored refresh token |
| `test_callback_success` | 200 + `connection.id`, `connection.provider`, `connection.status` |
| `test_callback_exception_returns_500` | 500 on unexpected error |

### 4.3 `test_routes_properties.py` (18 tests)

**`/api/connections/search-console/properties` (GET)**

| Test | Expected |
|---|---|
| `test_properties_unauthenticated` | 401 |
| `test_properties_missing_business_id` | 400 |
| `test_properties_not_connected` | 404 |
| `test_properties_permission_error` | 403 |
| `test_properties_success` | 200 + list with `site_url` + `permission_level` |
| `test_properties_exception` | 500 |

**`/api/connections/search-console/add-property` (POST)**

| Test | Expected |
|---|---|
| `test_add_property_unauthenticated` | 401 |
| `test_add_property_missing_business_id` | 400 |
| `test_add_property_missing_site_url` | 400 |
| `test_add_property_invalid_url_scheme` | 400 (`ftp://example.com`) |
| `test_add_property_url_with_credentials` | 400 (`https://user:pass@example.com`) |
| `test_add_property_url_no_dot_in_hostname` | 400 (`https://localhost`) |
| `test_add_property_sc_domain_valid` | passes validation (`sc-domain:example.com`) |
| `test_add_property_sc_domain_invalid` | 400 (`sc-domain:notadomain`) |
| `test_add_property_already_exists` | 200 + "already available" message (idempotent) |
| `test_add_property_not_connected` | 400 |
| `test_add_property_success` | 201 + `verification_required` |
| `test_add_property_google_403` | 403 + `reconnect_required: true` |
| `test_add_property_google_other_http_error` | 502 |

### 4.4 `test_routes_select.py` (5 tests)

| Test | Expected |
|---|---|
| `test_select_unauthenticated` | 401 |
| `test_select_missing_params` | 400 |
| `test_select_not_connected` | 404 |
| `test_select_property_not_in_account` | 403 |
| `test_select_success` | 200 + Firestore `.update()` called with `site_id` |

### 4.5 `test_routes_analytics.py` (8 tests)

| Test | Expected |
|---|---|
| `test_analytics_unauthenticated` | 401 |
| `test_analytics_missing_business_id` | 400 |
| `test_analytics_not_connected` | 404 |
| `test_analytics_no_property_selected` | 400 |
| `test_analytics_success` | 200 + `top_queries`, `top_pages`, `totals`, `start_date`, `end_date` |
| `test_analytics_empty_rows` | 200 + zeroed totals (documents current single-row behaviour) |
| `test_analytics_permission_error` | 403 |
| `test_analytics_exception` | 500 |

---

## 5. Known Semantic Bug

**File:** `routes/search_console_connections.py`, lines 694–700  
**Description:** The `totals` field in the `/analytics` response is populated from `rows[0]` only — the first row of the undimensioned query — rather than an actual aggregate across all rows. The field name "totals" is therefore misleading; it returns one row's metrics.  
**Disposition:** Documented here and captured by `test_analytics_empty_rows`. The bug is **not fixed** in this spec — fixing it is a separate task outside the testing scope. The test pins the current behaviour so a future fix is detectable.

---

## 6. Manual E2E Runbook

**Pre-conditions:**
- Flask server running locally (`python app.py`)
- Valid `.env` with `GOOGLE_SEARCH_CONSOLE_CLIENT_ID`, `GOOGLE_SEARCH_CONSOLE_CLIENT_SECRET`, `GOOGLE_SEARCH_CONSOLE_REDIRECT_URI`
- A test user account registered in Firestore with a known `business_id`
- A tool with cookie-jar support (curl with `-c`/`-b` flags, or Postman with sessions)

**Steps:**

| # | Command / Action | What to verify |
|---|---|---|
| 1 | `POST /api/auth/login` with credentials | 200 + session cookie set |
| 2 | `GET /api/connections/search-console/connect?business_id=<id>` | 200 + `authorization_url` in JSON |
| 3 | Open `authorization_url` in browser, approve Google OAuth | Browser redirects to callback URL |
| 4 | *(Agent cannot do this step — user must approve in browser)* | Callback page returns 200 + connection details |
| 5 | `GET /api/connections/search-console/properties?business_id=<id>` | 200 + list of your Google properties |
| 6 | `POST /api/connections/search-console/add-property` `{"business_id":"<id>","site_url":"sc-domain:yourdomain.com"}` | 201 or 200 (if already exists) |
| 7 | `POST /api/connections/search-console/select-property` `{"business_id":"<id>","site_url":"<one from step 5>"}` | 200 + `site_url` in response |
| 8 | `GET /api/connections/search-console/analytics?business_id=<id>` | 200 + `top_queries`, `top_pages`, `totals` with real data |

**Manual failure scenarios to probe:**
- Repeat steps 2–4 without revoking access in Google → verify no refresh token is re-issued and fallback to stored token works
- Step 7 with a `site_url` not in your Google account → verify 403
- Step 8 before completing step 7 → verify 400 "No Search Console property selected"

---

## 7. Dependencies to Add

```
responses==0.25.3   # HTTP-level mocking for connector unit tests
```

Add to `requirements.txt`. No other new dependencies needed.

---

## 8. Success Criteria

- `pytest tests/search_console/` passes with zero failures and zero skips
- All 40+ test cases execute without hitting real Firebase or Google APIs
- `RUNBOOK.md` steps 1–8 complete without errors against the live server
- Step 4 (OAuth browser redirect) is confirmed by the user
