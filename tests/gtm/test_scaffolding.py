import pytest

def test_gtm_scaffolding_imports():
    import tests.gtm.conftest as conftest_module
    assert hasattr(conftest_module, "mock_gtm_business_doc")
    assert hasattr(conftest_module, "mock_playwright_page")
    assert hasattr(conftest_module, "mock_vision_response")

def test_gtm_fixtures_usable(mock_gtm_business_doc, mock_playwright_page, mock_vision_response):
    assert mock_gtm_business_doc.exists is True
    data = mock_gtm_business_doc.to_dict()
    assert data["owner_id"] == "user-1"
    assert data["website_url"] == "https://example.com"
    assert mock_playwright_page.screenshot() == b"fake-webp-bytes"
    assert mock_vision_response["gtm_scores"]["overall"] == 80

def test_reexported_search_console_fixtures(client, auth_client):
    assert client is not None
    assert auth_client is not None

