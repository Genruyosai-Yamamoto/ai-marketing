"""
Tests for:
  POST /api/connections/search-console/select-property
"""
import pytest
from unittest.mock import MagicMock


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
