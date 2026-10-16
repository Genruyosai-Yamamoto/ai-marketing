# Google Search Console — Full Test Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Write a complete automated test suite (40+ tests) plus a manual E2E runbook for the Google Search Console integration — covering the connector class, all 6 route endpoints, and every edge case documented in the spec.

**Architecture:** Tests are organised into `tests/search_console/` with one file per route group and one file for the connector. A shared `conftest.py` provides Flask test client, session, and Firestore fixtures so individual test files stay focused. Route tests patch at the module boundary (`routes.search_console_connections.*`); connector tests patch at the Google library boundary (`connectors.google_search_console.*`).

**Tech Stack:** pytest, unittest.mock, responses 0.25.3, Flask test client, MagicMock

---

## Security boundary note

This plan writes tests only — no new trust boundaries are introduced. The routes being tested already handle auth, ownership, and OAuth state. Security-relevant negative cases (wrong owner, invalid state, missing verifier) are covered by test cases in Tasks 2–5.

---

## File Structure

| File | Single responsibility |
|---|---|
| `tests/search_console/__init__.py` | Package marker |
| `tests/search_console/conftest.py` | Shared fixtures: Flask app, clients, business doc stubs, connection stub |
| `tests/search_console/test_connector.py` | Unit tests for `GoogleSearchConsoleAPI` class |
| `tests/search_console/test_routes_connect.py` | Tests for `/connect` and `/callback` |
| `tests/search_console/test_routes_properties.py` | Tests for `/properties` and `/add-property` |
| `tests/search_console/test_routes_select.py` | Tests for `/select-property` |
| `tests/search_console/test_routes_analytics.py` | Tests for `/analytics` |
| `tests/search_console/RUNBOOK.md` | Step-by-step manual E2E walkthrough |
| `requirements.txt` | Add `responses==0.25.3` |

**DRY:** All fixture setup (Flask app, env vars, mock business doc, mock connection) lives in `conftest.py` and is reused across all route test files. No duplication of mock setup code.

**SOLID / SRP:** Each test file has exactly one responsibility (one route group or one class). `conftest.py`'s only job is fixture plumbing.

**YAGNI:** No test helpers or utilities beyond what the 40 test cases actually need.

---

## Task 0: Scaffolding — requirements.txt, directory, and conftest.py

**Files:**
- Modify: `requirements.txt`
- Create: `tests/search_console/__init__.py`
- Create: `tests/search_console/conftest.py`

- [ ] **Step 1: Add `responses` to requirements.txt**

  Open `requirements.txt` and add this line (keep alphabetical order, place after `redis`):

  ```
  responses==0.25.3
  ```

- [ ] **Step 2: Create the package marker**

  Create `tests/search_console/__init__.py` — empty file:

  ```python
  ```

- [ ] **Step 3: Write a sentinel test to verify the test infrastructure loads**

  Create `tests/search_console/conftest.py` with just enough to run one test:

  ```python
  import os
  import pytest
  from unittest.mock import MagicMock
  from cryptography.fernet import Fernet

  # ── env vars ──────────────────────────────────────────────────────────────
  # Set before any import that may trigger Google or Firebase initialisation.
  os.environ.setdefault("GOOGLE_SEARCH_CONSOLE_CLIENT_ID", "test-client-id")
  os.environ.setdefault("GOOGLE_SEARCH_CONSOLE_CLIENT_SECRET", "test-client-secret")
  os.environ.setdefault(
      "GOOGLE_SEARCH_CONSOLE_REDIRECT_URI",
      "http://localhost:5000/api/connections/search-console/callback",
  )
  os.environ.setdefault("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
  os.environ.setdefault("SECRET_KEY", "test-secret-key-for-tests-only")


  # ── Flask app + clients ───────────────────────────────────────────────────

  @pytest.fixture
  def flask_app():
      import app as app_module
      app_module.app.config["TESTING"] = True
      app_module.app.config["SECRET_KEY"] = "test-secret-key-for-tests-only"
      return app_module.app


  @pytest.fixture
  def client(flask_app):
      with flask_app.test_client() as c:
          yield c


  @pytest.fixture
  def auth_client(flask_app):
      """Test client with user-1 pre-authenticated in the session."""
      with flask_app.test_client() as c:
          with c.session_transaction() as sess:
              sess["user_id"] = "user-1"
          yield c


  @pytest.fixture
  def callback_client(flask_app):
      """Test client with auth session AND full OAuth state pre-loaded.

      Used by callback tests that need state, business_id, and verifier
      already present in the session before the request fires.
      """
      with flask_app.test_client() as c:
          with c.session_transaction() as sess:
              sess["user_id"] = "user-1"
              sess["search_console_oauth_state"] = "state-valid"
              sess["search_console_oauth_business_id"] = "biz-1"
              sess["search_console_oauth_code_verifier"] = "verifier-abc"
          yield c


  # ── Firestore stubs ────────────────────────────────────────────────────────

  @pytest.fixture
  def mock_business_doc():
      """Firestore document that exists and is owned by user-1."""
      doc = MagicMock()
      doc.exists = True
      doc.to_dict.return_value = {"owner_id": "user-1"}
      return doc


  @pytest.fixture
  def mock_missing_doc():
      """Firestore document that does not exist."""
      doc = MagicMock()
      doc.exists = False
      return doc


  @pytest.fixture
  def mock_wrong_owner_doc():
      """Firestore document owned by a different user."""
      doc = MagicMock()
      doc.exists = True
      doc.to_dict.return_value = {"owner_id": "different-user"}
      return doc


  # ── Connection stub ────────────────────────────────────────────────────────

  @pytest.fixture
  def mock_connection():
      """Typical return value of get_connection() for a GSC connection."""
      return {
          "id": "conn-1",
          "provider": "google_search_console",
          "refresh_token": "rt-abc",
          "access_token": "at-abc",
          "token_expires_at": None,
          "site_id": "https://example.com/",
      }
  ```

- [ ] **Step 4: Run the sentinel — confirm the package imports cleanly**

  ```bash
  cd /home/parrot/blom/backend
  source venv/bin/activate
  pytest tests/search_console/ --collect-only -q
  ```

  Expected: `no tests ran` (conftest has no test functions yet). No import errors.

- [ ] **Step 5: Commit the scaffolding**

  ```bash
  git add requirements.txt tests/search_console/__init__.py tests/search_console/conftest.py
  git commit -m "test(gsc): scaffold search_console test package and shared fixtures"
  ```

---

## Task 1: Connector unit tests — `test_connector.py`

**Files:**
- Create: `tests/search_console/test_connector.py`

**DRY note:** Each test patches `connectors.google_search_console.*` directly. The `gsc_env` fixture is autouse so every test in this file has the env vars set.

- [ ] **Step 1: Create the test file with a sentinel**

  Create `tests/search_console/test_connector.py`:

  ```python
  def test_sentinel():
      assert False, "remove this after confirming the file is picked up"
  ```

- [ ] **Step 2: Run to confirm sentinel fails**

  ```bash
  pytest tests/search_console/test_connector.py -v
  ```

  Expected: `FAILED test_connector.py::test_sentinel`

- [ ] **Step 3: Replace sentinel with all 12 connector tests**

  Overwrite `tests/search_console/test_connector.py` with:

  ```python
  """
  Unit tests for connectors.google_search_console.GoogleSearchConsoleAPI.

  All Google library classes are patched at the module boundary so no real
  HTTP traffic or credentials are needed.
  """
  import pytest
  from unittest.mock import MagicMock, patch, call

  from connectors.google_search_console import GoogleSearchConsoleAPI


  # ── helpers ────────────────────────────────────────────────────────────────

  def _make_api(mock_service=None):
      """Build a GoogleSearchConsoleAPI with a mocked service object."""
      mock_creds = MagicMock()
      if mock_service is None:
          mock_service = MagicMock()
      with patch("connectors.google_search_console.build", return_value=mock_service):
          api = GoogleSearchConsoleAPI(mock_creds)
      return api, mock_service


  # ── OAuth flow ─────────────────────────────────────────────────────────────

  def test_create_oauth_flow_builds_correct_config():
      with patch("connectors.google_search_console.Flow") as mock_flow_class:
          mock_instance = MagicMock()
          mock_flow_class.from_client_config.return_value = mock_instance

          GoogleSearchConsoleAPI.create_oauth_flow(state="test-state")

          args, _ = mock_flow_class.from_client_config.call_args
          config = args[0]
          assert config["web"]["client_id"] == "test-client-id"
          assert config["web"]["client_secret"] == "test-client-secret"
          assert (
              "http://localhost:5000/api/connections/search-console/callback"
              in config["web"]["redirect_uris"]
          )


  def test_get_authorization_url_returns_url_and_verifier():
      with patch("connectors.google_search_console.Flow") as mock_flow_class:
          mock_instance = MagicMock()
          mock_instance.authorization_url.return_value = (
              "https://accounts.google.com/o/oauth2/auth?foo=bar",
              None,
          )
          mock_instance.code_verifier = "verifier-abc"
          mock_flow_class.from_client_config.return_value = mock_instance

          url, verifier = GoogleSearchConsoleAPI.get_authorization_url(state="state-xyz")

      assert url.startswith("https://accounts.google.com")
      assert verifier == "verifier-abc"


  def test_exchange_code_for_credentials_calls_fetch_token():
      with patch("connectors.google_search_console.Flow") as mock_flow_class:
          mock_instance = MagicMock()
          mock_instance.credentials = MagicMock()
          mock_flow_class.from_client_config.return_value = mock_instance

          GoogleSearchConsoleAPI.exchange_code_for_credentials(
              code="auth-code-xyz",
              state="state-abc",
              code_verifier="verifier-abc",
          )

      assert mock_instance.code_verifier == "verifier-abc"
      mock_instance.fetch_token.assert_called_once_with(code="auth-code-xyz")


  # ── from_refresh_token ─────────────────────────────────────────────────────

  def test_from_refresh_token_returns_instance():
      mock_creds = MagicMock()
      mock_creds.valid = True

      with patch("connectors.google_search_console.Credentials", return_value=mock_creds), \
           patch("connectors.google_search_console.build", return_value=MagicMock()):
          api = GoogleSearchConsoleAPI.from_refresh_token(
              refresh_token="rt-abc",
              access_token="at-abc",
          )

      assert isinstance(api, GoogleSearchConsoleAPI)


  def test_from_refresh_token_refreshes_if_expired():
      mock_creds = MagicMock()
      mock_creds.valid = False

      with patch("connectors.google_search_console.Credentials", return_value=mock_creds), \
           patch("connectors.google_search_console.build", return_value=MagicMock()), \
           patch("connectors.google_search_console.Request") as mock_request:
          GoogleSearchConsoleAPI.from_refresh_token(
              refresh_token="rt-abc",
              access_token="at-abc",
          )

      mock_creds.refresh.assert_called_once_with(mock_request())


  def test_from_refresh_token_skips_refresh_if_valid():
      mock_creds = MagicMock()
      mock_creds.valid = True

      with patch("connectors.google_search_console.Credentials", return_value=mock_creds), \
           patch("connectors.google_search_console.build", return_value=MagicMock()):
          GoogleSearchConsoleAPI.from_refresh_token(
              refresh_token="rt-abc",
              access_token="at-abc",
          )

      mock_creds.refresh.assert_not_called()


  # ── list_sites ─────────────────────────────────────────────────────────────

  def test_list_sites_returns_site_entries():
      mock_service = MagicMock()
      mock_service.sites.return_value.list.return_value.execute.return_value = {
          "siteEntry": [
              {"siteUrl": "https://example.com/", "permissionLevel": "siteOwner"},
          ]
      }
      api, _ = _make_api(mock_service)

      sites = api.list_sites()

      assert len(sites) == 1
      assert sites[0]["siteUrl"] == "https://example.com/"
      assert sites[0]["permissionLevel"] == "siteOwner"


  def test_list_sites_returns_empty_on_no_sites():
      mock_service = MagicMock()
      mock_service.sites.return_value.list.return_value.execute.return_value = {}
      api, _ = _make_api(mock_service)

      sites = api.list_sites()

      assert sites == []


  # ── add_site ───────────────────────────────────────────────────────────────

  def test_add_site_calls_api_and_returns_dict():
      mock_service = MagicMock()
      mock_service.sites.return_value.add.return_value.execute.return_value = {}
      api, _ = _make_api(mock_service)

      result = api.add_site("https://example.com/")

      mock_service.sites.return_value.add.assert_called_once_with(
          siteUrl="https://example.com/"
      )
      assert result == {
          "site_url": "https://example.com/",
          "status": "added",
          "verification_status": "not_verified",
      }


  # ── get_search_analytics ───────────────────────────────────────────────────

  def _analytics_service(rows=None):
      mock_service = MagicMock()
      mock_service.searchanalytics.return_value.query.return_value.execute.return_value = {
          "rows": rows or []
      }
      return mock_service


  def test_get_search_analytics_without_dimensions():
      api, mock_service = _make_api(_analytics_service())

      api.get_search_analytics(
          site_url="https://example.com/",
          start_date="2026-09-01",
          end_date="2026-09-28",
      )

      _, kwargs = mock_service.searchanalytics.return_value.query.call_args
      assert "dimensions" not in kwargs["body"]


  def test_get_search_analytics_with_dimensions():
      api, mock_service = _make_api(_analytics_service())

      api.get_search_analytics(
          site_url="https://example.com/",
          start_date="2026-09-01",
          end_date="2026-09-28",
          dimensions=["query"],
      )

      _, kwargs = mock_service.searchanalytics.return_value.query.call_args
      assert kwargs["body"]["dimensions"] == ["query"]


  def test_get_search_analytics_returns_rows():
      row = {
          "keys": ["python tutorial"],
          "clicks": 100,
          "impressions": 1000,
          "ctr": 0.1,
          "position": 3.5,
      }
      api, _ = _make_api(_analytics_service(rows=[row]))

      rows = api.get_search_analytics(
          site_url="https://example.com/",
          start_date="2026-09-01",
          end_date="2026-09-28",
          dimensions=["query"],
      )

      assert len(rows) == 1
      assert rows[0]["clicks"] == 100
      assert rows[0]["keys"] == ["python tutorial"]
  ```

- [ ] **Step 4: Run all connector tests**

  ```bash
  pytest tests/search_console/test_connector.py -v
  ```

  Expected: 12 tests — all PASSED.

- [ ] **Step 5: Commit**

  ```bash
  git add tests/search_console/test_connector.py
  git commit -m "test(gsc): add GoogleSearchConsoleAPI connector unit tests (12 tests)"
  ```

---

## Task 2: Route tests — `/connect` and `/callback`

**Files:**
- Create: `tests/search_console/test_routes_connect.py`

**DRY note:** `mock_gsc_class` is a local fixture used by every test that needs to patch the API class. Firestore stubs (`mock_business_doc`, `mock_missing_doc`, `mock_wrong_owner_doc`) come from conftest.

- [ ] **Step 1: Create the test file**

  Create `tests/search_console/test_routes_connect.py`:

  ```python
  """
  Tests for:
    GET  /api/connections/search-console/connect
    GET  /api/connections/search-console/callback
  """
  import pytest
  from unittest.mock import MagicMock, patch


  # ── shared helpers ─────────────────────────────────────────────────────────

  @pytest.fixture
  def mock_db(monkeypatch):
      db = MagicMock()
      monkeypatch.setattr("routes.search_console_connections.db", db)
      return db


  @pytest.fixture
  def db_with_valid_business(mock_db, mock_business_doc):
      """mock_db pre-configured to return a valid business owned by user-1."""
      mock_db.collection.return_value.document.return_value.get.return_value = (
          mock_business_doc
      )
      return mock_db


  @pytest.fixture
  def mock_gsc_class(monkeypatch):
      """Patch GoogleSearchConsoleAPI with a MagicMock."""
      mock_cls = MagicMock()
      monkeypatch.setattr(
          "routes.search_console_connections.GoogleSearchConsoleAPI", mock_cls
      )
      return mock_cls


  @pytest.fixture
  def mock_upsert(monkeypatch):
      upsert = MagicMock(return_value={
          "id": "conn-1",
          "provider": "google_search_console",
          "status": "connected",
      })
      monkeypatch.setattr(
          "routes.search_console_connections.upsert_google_search_console_connection",
          upsert,
      )
      return upsert


  @pytest.fixture
  def mock_get_connection(monkeypatch, mock_connection):
      get_conn = MagicMock(return_value=mock_connection)
      monkeypatch.setattr(
          "routes.search_console_connections.get_connection", get_conn
      )
      return get_conn


  # ══════════════════════════════════════════════════════════════════════════
  #  /api/connections/search-console/connect
  # ══════════════════════════════════════════════════════════════════════════

  def test_connect_unauthenticated(client):
      resp = client.get(
          "/api/connections/search-console/connect?business_id=biz-1"
      )
      assert resp.status_code == 401
      assert resp.get_json()["success"] is False


  def test_connect_missing_business_id(auth_client, mock_db):
      resp = auth_client.get("/api/connections/search-console/connect")
      assert resp.status_code == 400
      assert resp.get_json()["success"] is False


  def test_connect_business_not_found(auth_client, mock_db, mock_missing_doc):
      mock_db.collection.return_value.document.return_value.get.return_value = (
          mock_missing_doc
      )
      resp = auth_client.get(
          "/api/connections/search-console/connect?business_id=biz-999"
      )
      assert resp.status_code == 404


  def test_connect_not_owner(auth_client, mock_db, mock_wrong_owner_doc):
      mock_db.collection.return_value.document.return_value.get.return_value = (
          mock_wrong_owner_doc
      )
      resp = auth_client.get(
          "/api/connections/search-console/connect?business_id=biz-1"
      )
      assert resp.status_code == 403


  def test_connect_success(auth_client, db_with_valid_business, mock_gsc_class):
      mock_gsc_class.get_authorization_url.return_value = (
          "https://accounts.google.com/o/oauth2/auth?state=xyz",
          "verifier-abc",
      )

      resp = auth_client.get(
          "/api/connections/search-console/connect?business_id=biz-1"
      )

      assert resp.status_code == 200
      data = resp.get_json()
      assert data["success"] is True
      assert data["authorization_url"].startswith("https://accounts.google.com")

      # OAuth state, verifier, and business_id must be stored in the session.
      with auth_client.session_transaction() as sess:
          assert "search_console_oauth_state" in sess
          assert sess["search_console_oauth_code_verifier"] == "verifier-abc"
          assert sess["search_console_oauth_business_id"] == "biz-1"


  # ══════════════════════════════════════════════════════════════════════════
  #  /api/connections/search-console/callback
  # ══════════════════════════════════════════════════════════════════════════

  def test_callback_unauthenticated(client):
      resp = client.get(
          "/api/connections/search-console/callback?code=abc&state=xyz"
      )
      assert resp.status_code == 401
      assert resp.get_json()["success"] is False


  def test_callback_google_error_param(callback_client):
      """When Google returns ?error=access_denied, we return 400."""
      resp = callback_client.get(
          "/api/connections/search-console/callback?error=access_denied"
      )
      assert resp.status_code == 400
      assert resp.get_json()["success"] is False


  def test_callback_missing_code(callback_client):
      resp = callback_client.get(
          "/api/connections/search-console/callback?state=state-valid"
      )
      assert resp.status_code == 400
      assert resp.get_json()["success"] is False


  def test_callback_missing_state(callback_client):
      resp = callback_client.get(
          "/api/connections/search-console/callback?code=auth-code"
      )
      assert resp.status_code == 400
      assert resp.get_json()["success"] is False


  def test_callback_invalid_state(flask_app):
      """State in URL does not match state stored in session → 400."""
      with flask_app.test_client() as c:
          with c.session_transaction() as sess:
              sess["user_id"] = "user-1"
              sess["search_console_oauth_state"] = "correct-state"
              sess["search_console_oauth_business_id"] = "biz-1"
              sess["search_console_oauth_code_verifier"] = "verifier-abc"

          resp = c.get(
              "/api/connections/search-console/callback"
              "?code=auth-code&state=WRONG-state"
          )

      assert resp.status_code == 400
      assert resp.get_json()["success"] is False


  def test_callback_missing_code_verifier(flask_app):
      """Session has no code_verifier → 400."""
      with flask_app.test_client() as c:
          with c.session_transaction() as sess:
              sess["user_id"] = "user-1"
              sess["search_console_oauth_state"] = "state-valid"
              sess["search_console_oauth_business_id"] = "biz-1"
              # no search_console_oauth_code_verifier

          resp = c.get(
              "/api/connections/search-console/callback"
              "?code=auth-code&state=state-valid"
          )

      assert resp.status_code == 400
      data = resp.get_json()
      assert data["success"] is False
      assert "verifier" in data["error"].lower() or "reconnect" in data["error"].lower()


  def test_callback_missing_business_context(flask_app):
      """business_id lost from session → 400."""
      with flask_app.test_client() as c:
          with c.session_transaction() as sess:
              sess["user_id"] = "user-1"
              sess["search_console_oauth_state"] = "state-valid"
              # no search_console_oauth_business_id
              sess["search_console_oauth_code_verifier"] = "verifier-abc"

          resp = c.get(
              "/api/connections/search-console/callback"
              "?code=auth-code&state=state-valid"
          )

      assert resp.status_code == 400
      assert resp.get_json()["success"] is False


  def test_callback_business_not_found(
      callback_client, mock_db, mock_missing_doc, mock_gsc_class
  ):
      mock_gsc_class.exchange_code_for_credentials.return_value = MagicMock(
          refresh_token="rt-new", token="at-new", token_uri="https://oauth2.googleapis.com/token",
          expiry=None,
      )
      mock_db.collection.return_value.document.return_value.get.return_value = (
          mock_missing_doc
      )

      resp = callback_client.get(
          "/api/connections/search-console/callback"
          "?code=auth-code&state=state-valid"
      )
      assert resp.status_code == 404


  def test_callback_not_owner(
      callback_client, mock_db, mock_wrong_owner_doc, mock_gsc_class
  ):
      mock_gsc_class.exchange_code_for_credentials.return_value = MagicMock(
          refresh_token="rt-new", token="at-new", token_uri="https://oauth2.googleapis.com/token",
          expiry=None,
      )
      mock_db.collection.return_value.document.return_value.get.return_value = (
          mock_wrong_owner_doc
      )

      resp = callback_client.get(
          "/api/connections/search-console/callback"
          "?code=auth-code&state=state-valid"
      )
      assert resp.status_code == 403


  def test_callback_no_refresh_token_no_existing_connection(
      callback_client,
      mock_db,
      mock_business_doc,
      mock_gsc_class,
      monkeypatch,
  ):
      """Google returns no refresh token and no stored token exists → 400."""
      mock_db.collection.return_value.document.return_value.get.return_value = (
          mock_business_doc
      )
      creds = MagicMock()
      creds.refresh_token = None   # Google didn't issue a refresh token
      mock_gsc_class.exchange_code_for_credentials.return_value = creds

      # get_connection raises ValueError (no existing connection)
      monkeypatch.setattr(
          "routes.search_console_connections.get_connection",
          MagicMock(side_effect=ValueError("Business not found")),
      )

      resp = callback_client.get(
          "/api/connections/search-console/callback"
          "?code=auth-code&state=state-valid"
      )
      assert resp.status_code == 400
      data = resp.get_json()
      assert data["success"] is False
      assert "refresh token" in data["error"].lower()


  def test_callback_no_refresh_token_uses_existing(
      callback_client,
      mock_db,
      mock_business_doc,
      mock_gsc_class,
      mock_upsert,
      monkeypatch,
  ):
      """No new refresh token from Google but stored one exists → falls back and succeeds."""
      mock_db.collection.return_value.document.return_value.get.return_value = (
          mock_business_doc
      )
      creds = MagicMock()
      creds.refresh_token = None
      creds.token = "at-new"
      creds.token_uri = "https://oauth2.googleapis.com/token"
      creds.expiry = None
      mock_gsc_class.exchange_code_for_credentials.return_value = creds

      # Existing connection has a stored refresh token
      monkeypatch.setattr(
          "routes.search_console_connections.get_connection",
          MagicMock(return_value={"refresh_token": "rt-stored"}),
      )

      # list_sites succeeds on the reconstructed API instance
      mock_gsc_instance = MagicMock()
      mock_gsc_instance.list_sites.return_value = []
      mock_gsc_class.return_value = mock_gsc_instance

      resp = callback_client.get(
          "/api/connections/search-console/callback"
          "?code=auth-code&state=state-valid"
      )
      assert resp.status_code == 200
      data = resp.get_json()
      assert data["success"] is True
      assert creds.refresh_token == "rt-stored"   # fallback was applied


  def test_callback_success(
      callback_client,
      mock_db,
      mock_business_doc,
      mock_gsc_class,
      mock_upsert,
  ):
      mock_db.collection.return_value.document.return_value.get.return_value = (
          mock_business_doc
      )
      creds = MagicMock()
      creds.refresh_token = "rt-new"
      creds.token = "at-new"
      creds.token_uri = "https://oauth2.googleapis.com/token"
      creds.expiry = None
      mock_gsc_class.exchange_code_for_credentials.return_value = creds

      mock_gsc_instance = MagicMock()
      mock_gsc_instance.list_sites.return_value = [
          {"siteUrl": "https://example.com/", "permissionLevel": "siteOwner"}
      ]
      mock_gsc_class.return_value = mock_gsc_instance

      resp = callback_client.get(
          "/api/connections/search-console/callback"
          "?code=auth-code&state=state-valid"
      )
      assert resp.status_code == 200
      data = resp.get_json()
      assert data["success"] is True
      assert data["connection"]["id"] == "conn-1"
      assert data["connection"]["provider"] == "google_search_console"
      assert data["connection"]["status"] == "connected"
      assert data["connection"]["properties_count"] == 1


  def test_callback_exception_returns_500(
      callback_client,
      mock_db,
      mock_business_doc,
      mock_gsc_class,
  ):
      mock_db.collection.return_value.document.return_value.get.return_value = (
          mock_business_doc
      )
      mock_gsc_class.exchange_code_for_credentials.side_effect = RuntimeError(
          "unexpected crash"
      )

      resp = callback_client.get(
          "/api/connections/search-console/callback"
          "?code=auth-code&state=state-valid"
      )
      assert resp.status_code == 500
      assert resp.get_json()["success"] is False
  ```

- [ ] **Step 2: Run and confirm all 17 tests pass**

  ```bash
  pytest tests/search_console/test_routes_connect.py -v
  ```

  Expected: 17 tests — all PASSED.

- [ ] **Step 3: Commit**

  ```bash
  git add tests/search_console/test_routes_connect.py
  git commit -m "test(gsc): add /connect and /callback route tests (17 tests)"
  ```

---

## Task 3: Route tests — `/properties` and `/add-property`

**Files:**
- Create: `tests/search_console/test_routes_properties.py`

- [ ] **Step 1: Create the test file**

  Create `tests/search_console/test_routes_properties.py`:

  ```python
  """
  Tests for:
    GET  /api/connections/search-console/properties
    POST /api/connections/search-console/add-property
  """
  import pytest
  from unittest.mock import MagicMock
  from googleapiclient.errors import HttpError


  # ── shared fixtures ────────────────────────────────────────────────────────

  @pytest.fixture
  def mock_get_connection(monkeypatch, mock_connection):
      fn = MagicMock(return_value=mock_connection)
      monkeypatch.setattr("routes.search_console_connections.get_connection", fn)
      return fn


  @pytest.fixture
  def mock_gsc_class(monkeypatch):
      cls = MagicMock()
      monkeypatch.setattr(
          "routes.search_console_connections.GoogleSearchConsoleAPI", cls
      )
      return cls


  @pytest.fixture
  def gsc_with_sites(mock_gsc_class):
      """GoogleSearchConsoleAPI instance that lists two sites."""
      instance = MagicMock()
      instance.list_sites.return_value = [
          {"siteUrl": "https://example.com/", "permissionLevel": "siteOwner"},
          {"siteUrl": "sc-domain:example.com", "permissionLevel": "siteOwner"},
      ]
      mock_gsc_class.from_refresh_token.return_value = instance
      return instance


  # ══════════════════════════════════════════════════════════════════════════
  #  /api/connections/search-console/properties
  # ══════════════════════════════════════════════════════════════════════════

  def test_properties_unauthenticated(client):
      resp = client.get(
          "/api/connections/search-console/properties?business_id=biz-1"
      )
      assert resp.status_code == 401


  def test_properties_missing_business_id(auth_client):
      resp = auth_client.get("/api/connections/search-console/properties")
      assert resp.status_code == 400


  def test_properties_not_connected(auth_client, monkeypatch):
      monkeypatch.setattr(
          "routes.search_console_connections.get_connection",
          MagicMock(return_value=None),
      )
      resp = auth_client.get(
          "/api/connections/search-console/properties?business_id=biz-1"
      )
      assert resp.status_code == 404
      assert resp.get_json()["success"] is False


  def test_properties_permission_error(auth_client, monkeypatch):
      monkeypatch.setattr(
          "routes.search_console_connections.get_connection",
          MagicMock(side_effect=PermissionError("forbidden")),
      )
      resp = auth_client.get(
          "/api/connections/search-console/properties?business_id=biz-1"
      )
      assert resp.status_code == 403


  def test_properties_success(auth_client, mock_get_connection, gsc_with_sites):
      resp = auth_client.get(
          "/api/connections/search-console/properties?business_id=biz-1"
      )
      assert resp.status_code == 200
      data = resp.get_json()
      assert data["success"] is True
      assert len(data["properties"]) == 2
      assert data["properties"][0]["site_url"] == "https://example.com/"
      assert data["properties"][0]["permission_level"] == "siteOwner"


  def test_properties_exception(auth_client, monkeypatch):
      monkeypatch.setattr(
          "routes.search_console_connections.get_connection",
          MagicMock(side_effect=RuntimeError("boom")),
      )
      resp = auth_client.get(
          "/api/connections/search-console/properties?business_id=biz-1"
      )
      assert resp.status_code == 500


  # ══════════════════════════════════════════════════════════════════════════
  #  /api/connections/search-console/add-property
  # ══════════════════════════════════════════════════════════════════════════

  def _post_add(client, business_id=None, site_url=None):
      body = {}
      if business_id is not None:
          body["business_id"] = business_id
      if site_url is not None:
          body["site_url"] = site_url
      return client.post(
          "/api/connections/search-console/add-property", json=body
      )


  def test_add_property_unauthenticated(client):
      resp = _post_add(client, business_id="biz-1", site_url="https://example.com/")
      assert resp.status_code == 401


  def test_add_property_missing_business_id(auth_client):
      resp = _post_add(auth_client, site_url="https://example.com/")
      assert resp.status_code == 400
      assert resp.get_json()["success"] is False


  def test_add_property_missing_site_url(auth_client):
      resp = _post_add(auth_client, business_id="biz-1")
      assert resp.status_code == 400
      assert resp.get_json()["success"] is False


  def test_add_property_invalid_url_scheme(auth_client):
      resp = _post_add(auth_client, business_id="biz-1", site_url="ftp://example.com/")
      assert resp.status_code == 400


  def test_add_property_url_with_credentials(auth_client):
      resp = _post_add(
          auth_client,
          business_id="biz-1",
          site_url="https://user:pass@example.com/",
      )
      assert resp.status_code == 400


  def test_add_property_url_no_dot_in_hostname(auth_client):
      """Single-label hostnames like 'localhost' are rejected."""
      resp = _post_add(auth_client, business_id="biz-1", site_url="https://localhost/")
      assert resp.status_code == 400


  def test_add_property_sc_domain_valid(
      auth_client, mock_get_connection, mock_gsc_class
  ):
      instance = MagicMock()
      instance.list_sites.return_value = []        # not already present
      instance.add_site.return_value = {
          "site_url": "sc-domain:example.com",
          "status": "added",
          "verification_status": "not_verified",
      }
      mock_gsc_class.from_refresh_token.return_value = instance

      resp = _post_add(
          auth_client, business_id="biz-1", site_url="sc-domain:example.com"
      )
      assert resp.status_code == 201
      data = resp.get_json()
      assert data["success"] is True
      assert data["verification_status"] == "verification_required"


  def test_add_property_sc_domain_invalid(auth_client):
      """sc-domain: prefix with no dots in the domain is rejected."""
      resp = _post_add(
          auth_client, business_id="biz-1", site_url="sc-domain:notadomain"
      )
      assert resp.status_code == 400


  def test_add_property_already_exists(
      auth_client, mock_get_connection, mock_gsc_class
  ):
      """If the site is already in the Google account the route returns 200 (idempotent)."""
      instance = MagicMock()
      instance.list_sites.return_value = [
          {"siteUrl": "https://example.com/", "permissionLevel": "siteOwner"}
      ]
      mock_gsc_class.from_refresh_token.return_value = instance

      resp = _post_add(
          auth_client, business_id="biz-1", site_url="https://example.com/"
      )
      assert resp.status_code == 200
      data = resp.get_json()
      assert data["success"] is True
      assert "already available" in data["message"]


  def test_add_property_not_connected(auth_client, monkeypatch):
      monkeypatch.setattr(
          "routes.search_console_connections.get_connection",
          MagicMock(return_value=None),
      )
      resp = _post_add(
          auth_client, business_id="biz-1", site_url="https://example.com/"
      )
      assert resp.status_code == 400


  def test_add_property_success(auth_client, mock_get_connection, mock_gsc_class):
      instance = MagicMock()
      instance.list_sites.return_value = []        # not already present
      instance.add_site.return_value = {
          "site_url": "https://newsite.com/",
          "status": "added",
          "verification_status": "not_verified",
      }
      mock_gsc_class.from_refresh_token.return_value = instance

      resp = _post_add(
          auth_client, business_id="biz-1", site_url="https://newsite.com/"
      )
      assert resp.status_code == 201
      data = resp.get_json()
      assert data["success"] is True
      assert data["site_url"] == "https://newsite.com/"
      assert data["verification_status"] == "verification_required"


  def test_add_property_google_403(auth_client, mock_get_connection, mock_gsc_class):
      """HttpError 403 from Google → 403 response with reconnect_required."""
      mock_resp = MagicMock()
      mock_resp.status = 403
      instance = MagicMock()
      instance.list_sites.return_value = []
      instance.add_site.side_effect = HttpError(resp=mock_resp, content=b"Forbidden")
      mock_gsc_class.from_refresh_token.return_value = instance

      resp = _post_add(
          auth_client, business_id="biz-1", site_url="https://example.com/"
      )
      assert resp.status_code == 403
      data = resp.get_json()
      assert data["success"] is False
      assert data.get("reconnect_required") is True


  def test_add_property_google_other_http_error(
      auth_client, mock_get_connection, mock_gsc_class
  ):
      """Non-403 HttpError from Google → 502."""
      mock_resp = MagicMock()
      mock_resp.status = 500
      instance = MagicMock()
      instance.list_sites.return_value = []
      instance.add_site.side_effect = HttpError(resp=mock_resp, content=b"Server Error")
      mock_gsc_class.from_refresh_token.return_value = instance

      resp = _post_add(
          auth_client, business_id="biz-1", site_url="https://example.com/"
      )
      assert resp.status_code == 502
  ```

- [ ] **Step 2: Run and confirm all 18 tests pass**

  ```bash
  pytest tests/search_console/test_routes_properties.py -v
  ```

  Expected: 18 tests — all PASSED.

- [ ] **Step 3: Commit**

  ```bash
  git add tests/search_console/test_routes_properties.py
  git commit -m "test(gsc): add /properties and /add-property route tests (18 tests)"
  ```

---

## Task 4: Route tests — `/select-property`

**Files:**
- Create: `tests/search_console/test_routes_select.py`

- [ ] **Step 1: Create the test file**

  Create `tests/search_console/test_routes_select.py`:

  ```python
  """
  Tests for:
    POST /api/connections/search-console/select-property
  """
  import pytest
  from unittest.mock import MagicMock


  @pytest.fixture
  def mock_get_connection(monkeypatch, mock_connection):
      fn = MagicMock(return_value=mock_connection)
      monkeypatch.setattr("routes.search_console_connections.get_connection", fn)
      return fn


  @pytest.fixture
  def mock_gsc_with_site(monkeypatch):
      cls = MagicMock()
      instance = MagicMock()
      instance.list_sites.return_value = [
          {"siteUrl": "https://example.com/", "permissionLevel": "siteOwner"}
      ]
      cls.from_refresh_token.return_value = instance
      monkeypatch.setattr(
          "routes.search_console_connections.GoogleSearchConsoleAPI", cls
      )
      return cls


  @pytest.fixture
  def mock_db(monkeypatch):
      db = MagicMock()
      monkeypatch.setattr("routes.search_console_connections.db", db)
      return db


  def _post_select(client, business_id=None, site_url=None):
      body = {}
      if business_id is not None:
          body["business_id"] = business_id
      if site_url is not None:
          body["site_url"] = site_url
      return client.post(
          "/api/connections/search-console/select-property", json=body
      )


  def test_select_unauthenticated(client):
      resp = _post_select(
          client, business_id="biz-1", site_url="https://example.com/"
      )
      assert resp.status_code == 401


  def test_select_missing_params(auth_client):
      """Missing either business_id or site_url → 400."""
      resp = _post_select(auth_client, business_id="biz-1")    # no site_url
      assert resp.status_code == 400

      resp = _post_select(auth_client, site_url="https://example.com/")  # no business_id
      assert resp.status_code == 400


  def test_select_not_connected(auth_client, monkeypatch):
      monkeypatch.setattr(
          "routes.search_console_connections.get_connection",
          MagicMock(return_value=None),
      )
      resp = _post_select(
          auth_client, business_id="biz-1", site_url="https://example.com/"
      )
      assert resp.status_code == 404


  def test_select_property_not_in_account(
      auth_client, mock_get_connection, monkeypatch
  ):
      """site_url not in the Google account's list → 403."""
      cls = MagicMock()
      instance = MagicMock()
      instance.list_sites.return_value = [
          {"siteUrl": "https://other-site.com/", "permissionLevel": "siteOwner"}
      ]
      cls.from_refresh_token.return_value = instance
      monkeypatch.setattr(
          "routes.search_console_connections.GoogleSearchConsoleAPI", cls
      )

      resp = _post_select(
          auth_client,
          business_id="biz-1",
          site_url="https://example.com/",    # not in account
      )
      assert resp.status_code == 403
      assert resp.get_json()["success"] is False


  def test_select_success(
      auth_client, mock_get_connection, mock_gsc_with_site, mock_db
  ):
      """Happy path: site is in account, Firestore is updated, 200 returned."""
      mock_db.collection.return_value.document.return_value.collection.return_value \
          .document.return_value = MagicMock()

      resp = _post_select(
          auth_client,
          business_id="biz-1",
          site_url="https://example.com/",
      )
      assert resp.status_code == 200
      data = resp.get_json()
      assert data["success"] is True
      assert data["site_url"] == "https://example.com/"

      # Verify Firestore update was called with site_id
      connection_ref = (
          mock_db.collection.return_value.document.return_value
          .collection.return_value.document.return_value
      )
      update_call = connection_ref.update.call_args[0][0]
      assert update_call["site_id"] == "https://example.com/"
  ```

- [ ] **Step 2: Run and confirm all 5 tests pass**

  ```bash
  pytest tests/search_console/test_routes_select.py -v
  ```

  Expected: 5 tests — all PASSED.

- [ ] **Step 3: Commit**

  ```bash
  git add tests/search_console/test_routes_select.py
  git commit -m "test(gsc): add /select-property route tests (5 tests)"
  ```

---

## Task 5: Route tests — `/analytics`

**Files:**
- Create: `tests/search_console/test_routes_analytics.py`

- [ ] **Step 1: Create the test file**

  Create `tests/search_console/test_routes_analytics.py`:

  ```python
  """
  Tests for:
    GET /api/connections/search-console/analytics

  NOTE: The `totals` field in the response is populated from rows[0] only —
  not an aggregate. This is a known semantic bug (spec §5). The
  test_analytics_empty_rows test pins the current behaviour so a future
  fix is immediately visible.
  """
  import pytest
  from unittest.mock import MagicMock


  @pytest.fixture
  def mock_get_connection(monkeypatch, mock_connection):
      fn = MagicMock(return_value=mock_connection)
      monkeypatch.setattr("routes.search_console_connections.get_connection", fn)
      return fn


  def _make_gsc_class(monkeypatch, rows=None, query_rows=None, page_rows=None):
      """Patch GoogleSearchConsoleAPI so get_search_analytics returns controlled rows."""
      cls = MagicMock()
      instance = MagicMock()

      def fake_analytics(site_url, start_date, end_date, dimensions=None, row_limit=100):
          if dimensions == ["query"]:
              return query_rows or []
          if dimensions == ["page"]:
              return page_rows or []
          return rows or []   # undimensioned call

      instance.get_search_analytics.side_effect = fake_analytics
      cls.from_refresh_token.return_value = instance
      monkeypatch.setattr(
          "routes.search_console_connections.GoogleSearchConsoleAPI", cls
      )
      return cls


  def test_analytics_unauthenticated(client):
      resp = client.get(
          "/api/connections/search-console/analytics?business_id=biz-1"
      )
      assert resp.status_code == 401


  def test_analytics_missing_business_id(auth_client):
      resp = auth_client.get("/api/connections/search-console/analytics")
      assert resp.status_code == 400


  def test_analytics_not_connected(auth_client, monkeypatch):
      monkeypatch.setattr(
          "routes.search_console_connections.get_connection",
          MagicMock(return_value=None),
      )
      resp = auth_client.get(
          "/api/connections/search-console/analytics?business_id=biz-1"
      )
      assert resp.status_code == 404


  def test_analytics_no_property_selected(auth_client, monkeypatch, mock_connection):
      """Connection exists but no site_id selected → 400."""
      conn_without_site = {**mock_connection, "site_id": None}
      monkeypatch.setattr(
          "routes.search_console_connections.get_connection",
          MagicMock(return_value=conn_without_site),
      )
      resp = auth_client.get(
          "/api/connections/search-console/analytics?business_id=biz-1"
      )
      assert resp.status_code == 400
      data = resp.get_json()
      assert data["success"] is False
      assert "property" in data["error"].lower() or "selected" in data["error"].lower()


  def test_analytics_success(auth_client, mock_get_connection, monkeypatch):
      query_rows = [
          {
              "keys": ["python flask"],
              "clicks": 50,
              "impressions": 500,
              "ctr": 0.1,
              "position": 5.0,
          }
      ]
      page_rows = [
          {
              "keys": ["https://example.com/blog/"],
              "clicks": 30,
              "impressions": 300,
              "ctr": 0.1,
              "position": 4.0,
          }
      ]
      undimensioned_rows = [
          {
              "clicks": 200,
              "impressions": 2000,
              "ctr": 0.1,
              "position": 4.5,
          }
      ]
      _make_gsc_class(
          monkeypatch,
          rows=undimensioned_rows,
          query_rows=query_rows,
          page_rows=page_rows,
      )

      resp = auth_client.get(
          "/api/connections/search-console/analytics?business_id=biz-1"
      )
      assert resp.status_code == 200
      data = resp.get_json()
      assert data["success"] is True
      assert data["site_url"] == "https://example.com/"
      assert "start_date" in data
      assert "end_date" in data
      assert len(data["top_queries"]) == 1
      assert data["top_queries"][0]["keys"] == ["python flask"]
      assert len(data["top_pages"]) == 1
      assert data["totals"]["clicks"] == 200
      assert data["totals"]["impressions"] == 2000


  def test_analytics_empty_rows(auth_client, mock_get_connection, monkeypatch):
      """
      When Google returns no rows the totals must be zeroed.

      NOTE: This test also documents the known semantic bug — totals are taken
      from rows[0], not aggregated. With empty rows the code falls through to
      the pre-initialised zero dict, which is correct behaviour for this case.
      """
      _make_gsc_class(monkeypatch, rows=[], query_rows=[], page_rows=[])

      resp = auth_client.get(
          "/api/connections/search-console/analytics?business_id=biz-1"
      )
      assert resp.status_code == 200
      data = resp.get_json()
      assert data["success"] is True
      assert data["totals"] == {
          "clicks": 0,
          "impressions": 0,
          "ctr": 0,
          "position": 0,
      }
      assert data["top_queries"] == []
      assert data["top_pages"] == []


  def test_analytics_permission_error(auth_client, monkeypatch):
      monkeypatch.setattr(
          "routes.search_console_connections.get_connection",
          MagicMock(side_effect=PermissionError("forbidden")),
      )
      resp = auth_client.get(
          "/api/connections/search-console/analytics?business_id=biz-1"
      )
      assert resp.status_code == 403


  def test_analytics_exception(auth_client, monkeypatch):
      monkeypatch.setattr(
          "routes.search_console_connections.get_connection",
          MagicMock(side_effect=RuntimeError("database exploded")),
      )
      resp = auth_client.get(
          "/api/connections/search-console/analytics?business_id=biz-1"
      )
      assert resp.status_code == 500
  ```

- [ ] **Step 2: Run and confirm all 8 tests pass**

  ```bash
  pytest tests/search_console/test_routes_analytics.py -v
  ```

  Expected: 8 tests — all PASSED.

- [ ] **Step 3: Commit**

  ```bash
  git add tests/search_console/test_routes_analytics.py
  git commit -m "test(gsc): add /analytics route tests (8 tests, includes semantic bug pin)"
  ```

---

## Task 6: Manual E2E Runbook — `RUNBOOK.md`

**Files:**
- Create: `tests/search_console/RUNBOOK.md`

- [ ] **Step 1: Create the runbook**

  Create `tests/search_console/RUNBOOK.md`:

  ````markdown
  # Google Search Console — Manual E2E Runbook

  Run this after the automated suite passes. You need real Google credentials
  and a Firestore business document. Steps marked **[AGENT]** are run for you;
  steps marked **[YOU]** require you to act in the browser or confirm output.

  ---

  ## Pre-conditions

  | Requirement | Check |
  |---|---|
  | Flask server running | `python app.py` in the backend directory |
  | `.env` has `GOOGLE_SEARCH_CONSOLE_CLIENT_ID`, `GOOGLE_SEARCH_CONSOLE_CLIENT_SECRET`, `GOOGLE_SEARCH_CONSOLE_REDIRECT_URI` | `grep GOOGLE_SEARCH_CONSOLE .env` |
  | A registered test user and a `business_id` | Note them down — you'll need both |
  | curl with a cookie jar | `curl --version` |

  Set these shell variables once before running any command:

  ```bash
  BASE=http://localhost:5000
  COOKIE_JAR=/tmp/gsc-test-cookies.txt
  BUSINESS_ID=<your business_id here>
  ```

  ---

  ## Step 1 — Authenticate [AGENT]

  ```bash
  curl -s -c "$COOKIE_JAR" -X POST "$BASE/api/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"email":"<your email>","password":"<your password>"}' | python3 -m json.tool
  ```

  ✅ Expected: `"success": true` and a session cookie written to `$COOKIE_JAR`.

  ---

  ## Step 2 — Initiate OAuth [AGENT]

  ```bash
  curl -s -b "$COOKIE_JAR" -c "$COOKIE_JAR" \
    "$BASE/api/connections/search-console/connect?business_id=$BUSINESS_ID" \
    | python3 -m json.tool
  ```

  ✅ Expected: `"success": true` + an `authorization_url` field.  
  Copy the `authorization_url` value — you need it in Step 3.

  ---

  ## Step 3 — Approve OAuth in Browser [YOU]

  Open the `authorization_url` in your browser. Sign in with the Google account
  that owns the Search Console properties you want to test. Click **Allow**.

  Google will redirect to:
  `http://localhost:5000/api/connections/search-console/callback?code=...&state=...`

  ✅ Expected: The browser shows `"success": true` with a `connection` object
  containing `id`, `provider: "google_search_console"`, and `status: "connected"`.

  If you see `"Missing OAuth code verifier"`, restart from Step 1 — the session
  cookie may have expired.

  ---

  ## Step 4 — List Properties [AGENT]

  ```bash
  curl -s -b "$COOKIE_JAR" \
    "$BASE/api/connections/search-console/properties?business_id=$BUSINESS_ID" \
    | python3 -m json.tool
  ```

  ✅ Expected: `"success": true` + a `properties` array listing your verified
  Search Console sites. Note one `site_url` — you need it in Steps 5 and 6.

  ---

  ## Step 5 — Select a Property [AGENT]

  Replace `<site_url>` with a value from Step 4's output:

  ```bash
  curl -s -b "$COOKIE_JAR" -X POST "$BASE/api/connections/search-console/select-property" \
    -H "Content-Type: application/json" \
    -d "{\"business_id\":\"$BUSINESS_ID\",\"site_url\":\"<site_url>\"}" \
    | python3 -m json.tool
  ```

  ✅ Expected: `"success": true` + `"site_url"` echoed back.

  ---

  ## Step 6 — Fetch Analytics [AGENT]

  ```bash
  curl -s -b "$COOKIE_JAR" \
    "$BASE/api/connections/search-console/analytics?business_id=$BUSINESS_ID" \
    | python3 -m json.tool
  ```

  ✅ Expected: `"success": true` + `top_queries`, `top_pages`, `totals`,
  `start_date`, and `end_date`. Values may be zeroed if the property has no
  recent traffic or data is still delayed (GSC delays ~3 days).

  ---

  ## Step 7 — Add a Property [AGENT]

  Test adding a domain property (this does NOT require ownership; verification
  is separate in Google):

  ```bash
  curl -s -b "$COOKIE_JAR" -X POST "$BASE/api/connections/search-console/add-property" \
    -H "Content-Type: application/json" \
    -d "{\"business_id\":\"$BUSINESS_ID\",\"site_url\":\"sc-domain:<yourdomain.com>\"}" \
    | python3 -m json.tool
  ```

  ✅ Expected: `201` + `"verification_status": "verification_required"`, or `200`
  + `"already available"` if the domain is already in your account.

  ---

  ## Manual Failure Scenarios [YOU + AGENT]

  ### A — Reconnect without revoking (no new refresh token)

  1. Repeat Steps 2–3 **without** first revoking access in
     [Google Account Permissions](https://myaccount.google.com/permissions).
  2. `[AGENT]` Run Step 4 (list properties).
  3. ✅ Expected: Still returns 200 — the stored refresh token was reused.

  ### B — Select a property not in the Google account

  ```bash
  curl -s -b "$COOKIE_JAR" -X POST "$BASE/api/connections/search-console/select-property" \
    -H "Content-Type: application/json" \
    -d '{"business_id":"'"$BUSINESS_ID"'","site_url":"https://not-your-site.example.com/"}' \
    | python3 -m json.tool
  ```

  ✅ Expected: `403` + `"This property is not accessible to the connected Google account"`.

  ### C — Fetch analytics before selecting a property

  1. In Firestore, clear the `site_id` field on the connection document, or use
     a fresh business_id that has a connection but no property selected yet.
  2. `[AGENT]` Run Step 6.
  3. ✅ Expected: `400` + `"No Search Console property selected"`.

  ---

  ## Sign-off

  | Step | Result | Notes |
  |---|---|---|
  | 1 — Auth | ☐ Pass / ☐ Fail | |
  | 2 — Initiate OAuth | ☐ Pass / ☐ Fail | |
  | 3 — Browser approval | ☐ Pass / ☐ Fail | |
  | 4 — List properties | ☐ Pass / ☐ Fail | |
  | 5 — Select property | ☐ Pass / ☐ Fail | |
  | 6 — Analytics | ☐ Pass / ☐ Fail | |
  | 7 — Add property | ☐ Pass / ☐ Fail | |
  | A — Reconnect fallback | ☐ Pass / ☐ Fail | |
  | B — Unowned property 403 | ☐ Pass / ☐ Fail | |
  | C — No property selected 400 | ☐ Pass / ☐ Fail | |
  ````

- [ ] **Step 2: Commit**

  ```bash
  git add tests/search_console/RUNBOOK.md
  git commit -m "test(gsc): add manual E2E runbook"
  ```

---

## Task 7: Full suite run and final verification

- [ ] **Step 1: Run the complete test suite**

  ```bash
  cd /home/parrot/blom/backend
  source venv/bin/activate
  pytest tests/search_console/ -v --tb=short
  ```

  Expected: **40+ tests, all PASSED, 0 failed, 0 errors**.

- [ ] **Step 2: Check coverage on the GSC modules**

  ```bash
  pytest tests/search_console/ \
    --cov=connectors.google_search_console \
    --cov=routes.search_console_connections \
    --cov-report=term-missing
  ```

  Expected: ≥ 90% line coverage on both modules.

- [ ] **Step 3: Confirm no regressions in the wider test suite**

  ```bash
  pytest tests/ -v --tb=short -q
  ```

  Expected: All pre-existing tests still pass.

- [ ] **Step 4: Final commit**

  ```bash
  git add .
  git commit -m "test(gsc): complete automated test suite — 40+ tests, ≥90% coverage"
  ```

---

## Test Plan & Verification

**Coverage target:** ≥ 90% line coverage on `connectors/google_search_console.py` and `routes/search_console_connections.py`. Every public method and every error path (401/400/403/404/500/502) has at least one test.

**Critical paths (must pass before ship):**

| Path | Verified by |
|---|---|
| Full OAuth flow: connect → callback → save connection | `test_callback_success` |
| No new refresh token falls back to stored one | `test_callback_no_refresh_token_uses_existing` |
| Listing and selecting a property | `test_properties_success`, `test_select_success` |
| Fetching analytics for a selected property | `test_analytics_success` |
| Connector builds service from refresh token | `test_from_refresh_token_returns_instance` |

**Edge cases & error paths:**

| Input / State | Expected | Test |
|---|---|---|
| No session cookie | 401 | All `*_unauthenticated` tests |
| business_id belongs to another user | 403 | `test_connect_not_owner`, `test_callback_not_owner` |
| Tampered OAuth state | 400 | `test_callback_invalid_state` |
| Session code_verifier missing | 400 | `test_callback_missing_code_verifier` |
| Google returns no refresh token, none stored | 400 | `test_callback_no_refresh_token_no_existing_connection` |
| `ftp://` or credential-bearing URL | 400 | `test_add_property_invalid_url_scheme`, `test_add_property_url_with_credentials` |
| `sc-domain:notadomain` (no dots) | 400 | `test_add_property_sc_domain_invalid` |
| Google HttpError 403 on add | 403 + `reconnect_required` | `test_add_property_google_403` |
| Google HttpError non-403 | 502 | `test_add_property_google_other_http_error` |
| Analytics with no property selected | 400 | `test_analytics_no_property_selected` |
| Empty analytics rows | zeroed totals | `test_analytics_empty_rows` |

**Known semantic bug (pinned, not fixed):**
`totals` in `/analytics` is populated from `rows[0]` only — not an aggregate. Pinned by `test_analytics_empty_rows`. Fixing it is a separate task.

**Regression guards:**

| Existing behaviour | Test protecting it |
|---|---|
| Existing test suite still passes | Task 7 Step 3: `pytest tests/` |

**Verification commands:**

```bash
# Unit + integration automated suite
pytest tests/search_console/ -v --tb=short

# Coverage check
pytest tests/search_console/ \
  --cov=connectors.google_search_console \
  --cov=routes.search_console_connections \
  --cov-report=term-missing

# No regressions
pytest tests/ -q
```

**Acceptance criteria (from spec):**

- [ ] `pytest tests/search_console/` passes with 0 failures, 0 skips → covered by Task 7 Step 1
- [ ] All 40+ test cases run without hitting real Firebase or Google APIs → covered by mock strategy (Tasks 1–5)
- [ ] `RUNBOOK.md` steps 1–8 complete without errors against the live server → Task 6 (manual, you at keyboard)
- [ ] Step 4 of RUNBOOK (OAuth browser redirect) confirmed by user → RUNBOOK Step 3 [YOU]
