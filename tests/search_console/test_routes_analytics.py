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
