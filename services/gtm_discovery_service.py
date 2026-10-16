"""
Autonomous GTM Competitor Discovery Service.

Discovers relevant direct market competitors for a business using:
1. Google Search Console organic search queries (high-impression/high-intent keywords).
2. Fallback to business industry and keywords in Firestore.
3. Organic search query resolution and strict filtering against non-commercial domains.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from firebase import db
from connectors.google_search_console import GoogleSearchConsoleAPI
from services.connection_service import get_connection

logger = logging.getLogger(__name__)

# Non-commercial or generic platform domains excluded from competitor benchmarking
EXCLUDED_DOMAINS: frozenset[str] = frozenset({
    "wikipedia.org",
    "youtube.com",
    "youtu.be",
    "reddit.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "medium.com",
    "yelp.com",
    "amazon.com",
    "github.com",
    "quora.com",
    "pinterest.com",
    "tiktok.com",
    "apple.com",
    "google.com",
    "microsoft.com",
    "yahoo.com",
    "bloom.app",
    "blom.ai",
    "blom.app",
})


def _extract_clean_domain(url: str) -> str | None:
    """Extract and normalize the domain name from a URL."""
    if not url:
        return None
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc or parsed.path
        if not netloc:
            return None
        # Strip port and credentials if present
        domain = netloc.split("@")[-1].split(":")[0].lower()
        if domain.startswith("www."):
            domain = domain[4:]
        domain = domain.rstrip(".")
        if not domain or "." not in domain:
            return None
        return domain
    except Exception:
        return None


def filter_competitor_domains(
    search_results: list[dict[str, Any]],
    exclude_domain: str | None = None,
) -> list[dict[str, str]]:
    """
    Filter raw search results to produce clean, unique direct competitor domains.

    Strips aggregators, social platforms, Wikipedia, and the user's own domain.
    """
    normalized_exclude = _extract_clean_domain(exclude_domain) if exclude_domain else None
    seen_domains: set[str] = set()
    competitors: list[dict[str, str]] = []

    for item in search_results:
        link = item.get("link") or item.get("url") or ""
        domain = _extract_clean_domain(link)
        if not domain:
            continue

        if normalized_exclude and (domain == normalized_exclude or domain.endswith("." + normalized_exclude)):
            continue

        # Check against blocked/aggregator domains
        is_excluded = any(
            domain == blocked or domain.endswith("." + blocked)
            for blocked in EXCLUDED_DOMAINS
        )
        if is_excluded:
            continue

        if domain not in seen_domains:
            seen_domains.add(domain)
            competitors.append({
                "domain": domain,
                "url": f"https://{domain}",
            })

    return competitors


def get_gtm_seed_queries(business_id: str, user_id: str) -> list[str]:
    """
    Retrieve seed queries for competitor discovery.

    Prioritizes real Google Search Console organic traffic data, then falls back
    to registered business industry and target keywords in Firestore.
    """
    # 1. Try Google Search Console
    try:
        connection = get_connection(
            business_id=business_id,
            user_id=user_id,
            provider="google_search_console",
        )
        if connection and connection.get("site_id") and connection.get("refresh_token"):
            google = GoogleSearchConsoleAPI.from_refresh_token(
                refresh_token=connection["refresh_token"],
                access_token=connection.get("access_token"),
                token_expiry=connection.get("token_expires_at"),
            )
            # Fetch last 28 days of query performance
            end_date = date.today() - timedelta(days=3)
            start_date = end_date - timedelta(days=28)
            rows = google.get_search_analytics(
                site_url=connection["site_id"],
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                dimensions=["query"],
                row_limit=15,
            )
            if rows:
                queries: list[str] = []
                for row in rows:
                    keys = row.get("keys")
                    if keys and keys[0]:
                        query_text = str(keys[0]).strip()
                        if query_text and len(query_text) > 3 and query_text not in queries:
                            queries.append(query_text)
                if queries:
                    return queries[:8]
    except Exception as exc:
        logger.warning(
            "Could not fetch GSC queries for business %s: %s",
            business_id,
            exc,
        )

    # 2. Fallback to Firestore business document
    business_ref = db.collection("businesses").document(business_id)
    doc = business_ref.get()
    if not doc.exists:
        return ["growth marketing platform", "saas landing page optimization"]

    data = doc.to_dict() or {}
    queries: list[str] = []

    # Direct keywords
    for key in ("target_keywords", "keywords"):
        kws = data.get(key)
        if isinstance(kws, list):
            for kw in kws:
                if isinstance(kw, str) and kw.strip():
                    queries.append(kw.strip())

    industry = data.get("industry") or ""
    name = data.get("name") or ""

    if industry:
        queries.append(f"{industry.strip()} software")
        queries.append(f"best {industry.strip()} tools")
    if name:
        queries.append(f"{name.strip()} alternatives")

    if not queries:
        queries = ["b2b saas platform", "growth marketing automation"]

    return queries[:8]


def search_organic_competitors(query: str, max_results: int = 10) -> list[dict[str, str]]:
    """
    Search organic search results for a given query.
    Uses HTML search parsing with graceful fallback on network error.
    """
    results: list[dict[str, str]] = []
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }
        # HTML search query
        resp = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers=headers,
            timeout=8,
        )
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", class_="result__url"):
                href = a.get("href")
                if href:
                    results.append({"link": href.strip()})
                    if len(results) >= max_results:
                        break
    except Exception as exc:
        logger.warning("Organic search lookup error for '%s': %s", query, exc)

    return results


def discover_competitors(
    business_id: str,
    user_id: str,
    max_competitors: int = 2,
) -> list[dict[str, str]]:
    """
    End-to-end competitor discovery workflow for a business.
    """
    business_ref = db.collection("businesses").document(business_id)
    doc = business_ref.get()
    if not doc.exists:
        raise ValueError("Business not found")

    data = doc.to_dict() or {}
    if data.get("owner_id") != user_id:
        raise PermissionError("You do not have permission to access this business")

    user_website = data.get("website_url") or ""
    user_domain = _extract_clean_domain(user_website)

    seed_queries = get_gtm_seed_queries(business_id, user_id)
    raw_results: list[dict[str, str]] = []

    for query in seed_queries[:3]:
        search_hits = search_organic_competitors(query, max_results=8)
        raw_results.extend(search_hits)

    filtered = filter_competitor_domains(raw_results, exclude_domain=user_domain)
    return filtered[:max_competitors]
