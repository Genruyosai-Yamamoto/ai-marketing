import json
import pytest
from unittest.mock import MagicMock, patch, call
from services.pixelrag_service import (
    render_and_tile_page,
    get_tile_filename,
    dismiss_cookie_banners,
    PixelRAGNavigationError,
    PixelRAGError,
)


def test_render_and_tile_page_creates_tiles_and_manifest(tmp_path):
    with patch("services.pixelrag_service.sync_playwright") as mock_pw:
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_pw.return_value.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page

        mock_page.evaluate.side_effect = [2400]  # page height
        mock_page.screenshot.return_value = b"fake-webp-bytes"

        manifest = render_and_tile_page("https://example.com", str(tmp_path))

        assert manifest["url"] == "https://example.com"
        assert manifest["page_height"] == 2400
        assert len(manifest["tiles"]) == 3
        assert manifest["tiles"][0]["filename"] == "tile_0001_hero.webp"
        assert manifest["tiles"][1]["filename"] == "tile_0002_value.webp"
        assert manifest["tiles"][2]["filename"] == "tile_0003_social.webp"
        assert (tmp_path / "tile_0001_hero.webp").exists()
        assert (tmp_path / "manifest.json").exists()


def test_render_and_tile_page_caps_at_max_height(tmp_path):
    with patch("services.pixelrag_service.sync_playwright") as mock_pw:
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_pw.return_value.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page

        mock_page.evaluate.side_effect = [12000]  # Large page height
        mock_page.screenshot.return_value = b"tile-content"

        manifest = render_and_tile_page("https://longpage.com", str(tmp_path), max_height=8000)

        assert manifest["page_height"] == 12000
        assert manifest["max_height"] == 8000
        # 8000 / 800 = 10 tiles capped
        assert len(manifest["tiles"]) == 10
        assert manifest["tiles"][-1]["scroll_bottom"] == 8000
        assert manifest["tiles"][9]["filename"] == "tile_0010_extra_1.webp"


def test_render_and_tile_page_wheel_exception_tolerated(tmp_path):
    with patch("services.pixelrag_service.sync_playwright") as mock_pw:
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_pw.return_value.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page

        mock_page.evaluate.side_effect = [800]
        mock_page.mouse.wheel.side_effect = Exception("scroll failed")
        mock_page.screenshot.return_value = b"tile-content"

        manifest = render_and_tile_page("https://wheeltest.com", str(tmp_path))

        assert manifest["page_height"] == 800
        assert len(manifest["tiles"]) == 1


def test_render_and_tile_page_empty_page(tmp_path):
    with patch("services.pixelrag_service.sync_playwright") as mock_pw:
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_pw.return_value.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page

        mock_page.evaluate.side_effect = [0]  # Empty page height

        manifest = render_and_tile_page("https://emptypage.com", str(tmp_path))

        assert manifest["page_height"] == 0
        assert manifest["tiles"] == []
        assert (tmp_path / "manifest.json").exists()
        with open(tmp_path / "manifest.json", "r") as f:
            saved_manifest = json.load(f)
        assert saved_manifest["tiles"] == []


def test_render_and_tile_page_invalid_page_height_eval(tmp_path):
    with patch("services.pixelrag_service.sync_playwright") as mock_pw:
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_pw.return_value.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page

        mock_page.evaluate.side_effect = ["invalid-int"]

        manifest = render_and_tile_page("https://badpage.com", str(tmp_path))

        assert manifest["page_height"] == 0
        assert manifest["tiles"] == []


def test_render_and_tile_page_navigation_timeout_fallback(tmp_path):
    with patch("services.pixelrag_service.sync_playwright") as mock_pw:
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_pw.return_value.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page

        # First goto times out, second succeeds with domcontentloaded
        mock_page.goto.side_effect = [TimeoutError("networkidle timeout"), None]
        mock_page.evaluate.side_effect = [800]
        mock_page.screenshot.return_value = b"tile-data"

        manifest = render_and_tile_page("https://slowsite.com", str(tmp_path))

        assert manifest["page_height"] == 800
        assert len(manifest["tiles"]) == 1
        assert mock_page.goto.call_count == 2
        mock_page.goto.assert_has_calls([
            call("https://slowsite.com", timeout=15000, wait_until="networkidle"),
            call("https://slowsite.com", timeout=15000, wait_until="domcontentloaded"),
        ])


def test_render_and_tile_page_navigation_failure_raises(tmp_path):
    with patch("services.pixelrag_service.sync_playwright") as mock_pw:
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_pw.return_value.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page

        # Both attempts fail
        mock_page.goto.side_effect = [
            Exception("networkidle failed"),
            Exception("domcontentloaded failed"),
        ]

        with pytest.raises(PixelRAGNavigationError, match="Failed to navigate to"):
            render_and_tile_page("https://deadsite.com", str(tmp_path))


def test_render_and_tile_page_empty_url(tmp_path):
    with pytest.raises(ValueError, match="URL must be a non-empty string"):
        render_and_tile_page("", str(tmp_path))

    with pytest.raises(ValueError, match="URL must be a non-empty string"):
        render_and_tile_page("   ", str(tmp_path))


def test_dismiss_cookie_banners_clicks_found_banner():
    mock_page = MagicMock()
    mock_btn = MagicMock()
    mock_page.query_selector.side_effect = lambda sel: mock_btn if sel == "#accept-cookie" else None

    dismiss_cookie_banners(mock_page)

    mock_btn.click.assert_called_once_with(timeout=1000)


def test_dismiss_cookie_banners_handles_click_failure():
    mock_page = MagicMock()
    mock_btn1 = MagicMock()
    mock_btn1.click.side_effect = Exception("element detached")
    mock_btn2 = MagicMock()

    def query_selector_mock(sel):
        if sel == "#accept-cookie":
            return mock_btn1
        if sel == "#accept-cookies":
            return mock_btn2
        return None

    mock_page.query_selector.side_effect = query_selector_mock

    dismiss_cookie_banners(mock_page)

    mock_btn1.click.assert_called_once()
    mock_btn2.click.assert_called_once_with(timeout=1000)


def test_get_tile_filename_standard_and_overflow():
    assert get_tile_filename(1) == "tile_0001_hero.webp"
    assert get_tile_filename(2) == "tile_0002_value.webp"
    assert get_tile_filename(3) == "tile_0003_social.webp"
    assert get_tile_filename(4) == "tile_0004_pricing.webp"
    # Overflow beyond TILE_LABELS length
    assert get_tile_filename(15) == "tile_0015_section_15.webp"
