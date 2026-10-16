"""
Unit tests for services.gtm_discovery_service.
"""
from unittest.mock import MagicMock, patch
import pytest

from services.gtm_discovery_service import (
    filter_competitor_domains,
    get_gtm_seed_queries,
    discover_competitors,
    EXCLUDED_DOMAINS,
)


def test_discover_competitors_filters_aggregators_and_extracts_domains():
    raw_results = [
        {"link": "https://en.wikipedia.org/wiki/SEO"},
        {"link": "https://www.youtube.com/watch?v=123"},
        {"link": "https://acme-competitor.com/features"},
        {"link": "https://beta-rival.io/pricing"},
        {"link": "https://reddit.com/r/marketing"},
        {"link": "https://example.com/blog"},  # user's own domain
        {"link": "https://acme-competitor.com/about"},  # duplicate domain
    ]

    competitors = filter_competitor_domains(raw_results, exclude_domain="example.com")
    assert competitors == [
        {"domain": "acme-competitor.com", "url": "https://acme-competitor.com"},
        {"domain": "beta-rival.io", "url": "https://beta-rival.io"},
    ]


def test_filter_competitor_domains_handles_subdomains_and_schemes():
    raw_results = [
        {"link": "http://sub.domain.competitor.org/path?q=1"},
        {"link": "https://www.social-aggregator.yelp.com/biz"},
        {"link": "invalid-url"},
        {"link": ""},
    ]
    competitors = filter_competitor_domains(raw_results)
    assert len(competitors) == 1
    assert competitors[0]["domain"] == "sub.domain.competitor.org"
    assert competitors[0]["url"] == "https://sub.domain.competitor.org"


def test_get_gtm_seed_queries_uses_gsc_when_connected():
    mock_conn = {
        "site_id": "https://mysite.com/",
        "refresh_token": "rt-123",
        "access_token": "at-123",
        "token_expires_at": None,
    }
    mock_gsc = MagicMock()
    mock_gsc.get_search_analytics.return_value = [
        {"keys": ["best ai seo software"], "clicks": 150, "impressions": 2000},
        {"keys": ["gtm audit platform"], "clicks": 90, "impressions": 1200},
    ]

    with patch("services.gtm_discovery_service.get_connection", return_value=mock_conn), \
         patch("services.gtm_discovery_service.GoogleSearchConsoleAPI.from_refresh_token", return_value=mock_gsc):
        queries = get_gtm_seed_queries(business_id="biz-1", user_id="user-1")

    assert "best ai seo software" in queries
    assert "gtm audit platform" in queries


def test_get_gtm_seed_queries_fallback_to_business_doc_when_no_gsc():
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {
        "owner_id": "user-1",
        "industry": "Marketing Automation",
        "keywords": ["lead qualification", "inbound marketing"],
        "name": "BlomAI",
    }

    with patch("services.gtm_discovery_service.get_connection", return_value=None), \
         patch("services.gtm_discovery_service.db.collection") as mock_db:
        mock_db.return_value.document.return_value.get.return_value = mock_doc
        queries = get_gtm_seed_queries(business_id="biz-1", user_id="user-1")

    assert len(queries) >= 2
    assert any("lead qualification" in q for q in queries)


def test_discover_competitors_end_to_end_orchestration():
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {
        "owner_id": "user-1",
        "website_url": "https://mysite.com",
    }

    search_return = [
        {"link": "https://mysite.com/features"},
        {"link": "https://en.wikipedia.org/wiki/Software"},
        {"link": "https://competitor-one.com/demo"},
        {"link": "https://competitor-two.io/pricing"},
        {"link": "https://competitor-three.com/"},
    ]

    with patch("services.gtm_discovery_service.db.collection") as mock_db, \
         patch("services.gtm_discovery_service.get_gtm_seed_queries", return_value=["ai seo platform"]), \
         patch("services.gtm_discovery_service.search_organic_competitors", return_value=search_return):
        mock_db.return_value.document.return_value.get.return_value = mock_doc

        competitors = discover_competitors("biz-1", "user-1", max_competitors=2)

    assert len(competitors) == 2
    assert competitors[0]["domain"] == "competitor-one.com"
    assert competitors[1]["domain"] == "competitor-two.io"


def test_discover_competitors_raises_if_business_missing():
    mock_doc = MagicMock()
    mock_doc.exists = False

    with patch("services.gtm_discovery_service.db.collection") as mock_db:
        mock_db.return_value.document.return_value.get.return_value = mock_doc
        with pytest.raises(ValueError, match="Business not found"):
            discover_competitors("missing-biz", "user-1")


def test_discover_competitors_raises_if_unauthorized():
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {"owner_id": "different-user"}

    with patch("services.gtm_discovery_service.db.collection") as mock_db:
        mock_db.return_value.document.return_value.get.return_value = mock_doc
        with pytest.raises(PermissionError, match="do not have permission"):
            discover_competitors("biz-1", "user-1")


def test_search_organic_competitors_parses_html():
    from services.gtm_discovery_service import search_organic_competitors

    html = """
    <html>
      <body>
        <a class="result__url" href="https://comp-a.com">comp-a.com</a>
        <a class="result__url" href="https://comp-b.com">comp-b.com</a>
      </body>
    </html>
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = html

    with patch("services.gtm_discovery_service.requests.get", return_value=mock_resp):
        hits = search_organic_competitors("b2b saas", max_results=2)

    assert len(hits) == 2
    assert hits[0]["link"] == "https://comp-a.com"


def test_search_organic_competitors_handles_network_error():
    from services.gtm_discovery_service import search_organic_competitors

    with patch("services.gtm_discovery_service.requests.get", side_effect=Exception("Timeout")):
        hits = search_organic_competitors("error query")
    assert hits == []


def test_get_gtm_seed_queries_handles_gsc_exception():
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {"industry": "FinTech"}

    with patch("services.gtm_discovery_service.get_connection", side_effect=Exception("DB down")), \
         patch("services.gtm_discovery_service.db.collection") as mock_db:
        mock_db.return_value.document.return_value.get.return_value = mock_doc
        queries = get_gtm_seed_queries("biz-1", "user-1")

    assert any("FinTech" in q for q in queries)


def test_get_gtm_seed_queries_empty_doc_fallback():
    mock_doc = MagicMock()
    mock_doc.exists = False

    with patch("services.gtm_discovery_service.get_connection", return_value=None), \
         patch("services.gtm_discovery_service.db.collection") as mock_db:
        mock_db.return_value.document.return_value.get.return_value = mock_doc
        queries = get_gtm_seed_queries("biz-1", "user-1")

    assert len(queries) >= 1

