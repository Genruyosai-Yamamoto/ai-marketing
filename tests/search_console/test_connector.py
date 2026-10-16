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
    env_overrides = {
        "GOOGLE_SEARCH_CONSOLE_CLIENT_ID": "test-client-id",
        "GOOGLE_SEARCH_CONSOLE_CLIENT_SECRET": "test-client-secret",
        "GOOGLE_SEARCH_CONSOLE_REDIRECT_URI": (
            "http://localhost:5000/api/connections/search-console/callback"
        ),
    }
    with patch("connectors.google_search_console.Flow") as mock_flow_class, \
         patch.dict("os.environ", env_overrides):
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
