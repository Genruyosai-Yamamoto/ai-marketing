import os
import pytest
from unittest.mock import MagicMock

# ── Environment defaults for GTM tests ──────────────────────────────────────
os.environ.setdefault("GROQ_API_KEY", "test-groq-api-key")

# ── Re-export shared fixtures from search_console conftest ──────────────────
from tests.search_console.conftest import (
    flask_app,
    client,
    auth_client,
    callback_client,
    mock_business_doc,
    mock_missing_doc,
    mock_wrong_owner_doc,
    mock_connection,
)


# ── GTM-Specific Shared Fixtures ────────────────────────────────────────────

@pytest.fixture
def mock_gtm_business_doc():
    """Firestore business document fixture with owner_id and website_url."""
    doc = MagicMock()
    doc.exists = True
    doc.id = "biz-1"
    doc.to_dict.return_value = {
        "owner_id": "user-1",
        "website_url": "https://example.com",
        "business_name": "Example Corp",
        "industry": "Software",
    }
    return doc


@pytest.fixture
def mock_playwright_page():
    """MagicMock simulating Playwright Page, viewport settings, and screenshot buffers."""
    page = MagicMock()
    page.viewport_size = {"width": 1280, "height": 800}
    page.evaluate.return_value = 2400
    page.screenshot.return_value = b"fake-webp-bytes"
    page.goto.return_value = None
    page.wait_for_load_state.return_value = None
    page.query_selector_all.return_value = []
    page.locator.return_value.count.return_value = 0
    return page


@pytest.fixture
def mock_vision_response():
    """Dict simulating Vision LLM GTM evaluation output across the 4 pillars."""
    return {
        "gtm_scores": {
            "overall": 80,
            "above_the_fold": 75,
            "pricing_clarity": 85,
            "social_proof": 70,
            "cro_friction": 90,
        },
        "blind_spots": [
            "Competitor has explicit pricing, user does not",
        ],
        "opportunities": [
            {
                "title": "Add Transparent Pricing Tier Above The Fold",
                "problem": "Competitor Acme displays $29/mo while user requires contacting sales.",
                "type": "gtm_pricing",
                "potential_impact": "High",
                "confidence": 0.85,
            }
        ],
    }
