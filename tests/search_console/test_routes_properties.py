"""
Tests for:
  GET  /api/connections/search-console/properties
  POST /api/connections/search-console/add-property
"""
import pytest
from unittest.mock import MagicMock
from googleapiclient.errors import HttpError


# ── shared fixtures ────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _bridge_connection_service(monkeypatch):
    import routes.search_console_connections as r_mod
    import services.connection_service as s_mod

    monkeypatch.setattr(
        s_mod,
        "get_connection",
        lambda *args, **kwargs: r_mod.get_connection(*args, **kwargs),
    )


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
