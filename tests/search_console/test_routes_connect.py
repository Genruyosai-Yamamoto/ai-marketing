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
