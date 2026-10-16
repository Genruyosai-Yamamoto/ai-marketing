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
