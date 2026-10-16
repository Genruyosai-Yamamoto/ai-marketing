"""PixelRAG Page Rendering & Vertical Tiling Service.

Renders web pages using headless Playwright Chromium, normalizes viewport
dimensions, handles lazy scrolling and cookie dismissal, slices pages into
sequential vertical tiles (WebP), and produces a structured manifest.json.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

TILE_LABELS = [
    "hero",
    "value",
    "social",
    "pricing",
    "features",
    "details",
    "testimonials",
    "faq",
    "footer",
    "extra_1",
    "extra_2",
    "extra_3",
]

COOKIE_SELECTORS = [
    "#accept-cookie",
    "#accept-cookies",
    "#cookie-accept",
    "#onetrust-accept-btn-handler",
    "[aria-label*='cookie' i]",
    "[aria-label*='consent' i]",
    ".cookie-banner button",
    ".cookie-banner",
    "button[id*='cookie' i]",
    "button[class*='cookie' i]",
]


class PixelRAGError(Exception):
    """Base exception for PixelRAG service errors."""
    pass


class PixelRAGNavigationError(PixelRAGError):
    """Raised when page navigation fails completely."""
    pass


def dismiss_cookie_banners(page) -> None:
    """Attempt to find and dismiss common cookie banners and modals."""
    for sel in COOKIE_SELECTORS:
        try:
            elem = page.query_selector(sel)
            if elem:
                elem.click(timeout=1000)
                break
        except Exception as e:
            logger.debug(f"Could not dismiss cookie banner with selector {sel}: {e}")
            continue


def get_tile_filename(index: int) -> str:
    """Generate sequential tile filename based on index (1-based)."""
    idx_0 = index - 1
    label = TILE_LABELS[idx_0] if 0 <= idx_0 < len(TILE_LABELS) else f"section_{index}"
    return f"tile_{index:04d}_{label}.webp"


def render_and_tile_page(
    url: str,
    output_dir: str,
    max_height: int = 8000,
    tile_height: int = 800,
    viewport_width: int = 1280,
    viewport_height: int = 800,
    device_scale_factor: float = 1.5,
    timeout_ms: int = 15000,
) -> Dict[str, Any]:
    """Render a web page using Playwright and slice into vertical tiles.

    Args:
        url: Webpage URL to render.
        output_dir: Local filesystem directory where tiles & manifest will be saved.
        max_height: Maximum pixel height to render and slice (default: 8000).
        tile_height: Height of each vertical tile slice in pixels (default: 800).
        viewport_width: Viewport width in pixels (default: 1280).
        viewport_height: Viewport height in pixels (default: 800).
        device_scale_factor: Device pixel ratio for crisp typography (default: 1.5).
        timeout_ms: Navigation timeout in milliseconds (default: 15000).

    Returns:
        dict: Manifest containing URL, page dimensions, tile metadata, and file paths.
    """
    if not url or not url.strip():
        raise ValueError("URL must be a non-empty string")

    output_dir_str = str(output_dir)
    os.makedirs(output_dir_str, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page(
                viewport={"width": viewport_width, "height": viewport_height},
                device_scale_factor=device_scale_factor,
            )

            # Navigation with domcontentloaded fallback
            try:
                page.goto(url, timeout=timeout_ms, wait_until="networkidle")
            except Exception as e:
                logger.warning(f"networkidle navigation failed for {url}, falling back to domcontentloaded: {e}")
                try:
                    page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                except Exception as err:
                    raise PixelRAGNavigationError(f"Failed to navigate to {url}: {err}") from err

            # Auto-dismiss cookie banners
            dismiss_cookie_banners(page)

            # Measure document height
            raw_height = page.evaluate("() => Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)")
            try:
                page_height = int(raw_height)
            except (TypeError, ValueError):
                page_height = 0

            tiles: List[Dict[str, Any]] = []

            if page_height > 0:
                clamped_height = min(page_height, max_height)
                offset = 0
                tile_idx = 1

                while offset < clamped_height:
                    current_slice_height = min(tile_height, clamped_height - offset)
                    filename = get_tile_filename(tile_idx)
                    file_path = os.path.join(output_dir_str, filename)

                    # Trigger lazy-load scroll
                    try:
                        page.mouse.wheel(0, current_slice_height)
                    except Exception:
                        pass

                    # Capture vertical slice
                    screenshot_bytes = page.screenshot(
                        clip={
                            "x": 0,
                            "y": offset,
                            "width": viewport_width,
                            "height": current_slice_height,
                        }
                    )

                    if isinstance(screenshot_bytes, bytes):
                        with open(file_path, "wb") as f:
                            f.write(screenshot_bytes)

                    tiles.append({
                        "index": tile_idx,
                        "filename": filename,
                        "path": file_path,
                        "scroll_top": offset,
                        "scroll_bottom": offset + current_slice_height,
                        "width": viewport_width,
                        "height": current_slice_height,
                    })

                    offset += current_slice_height
                    tile_idx += 1

            manifest_path = os.path.join(output_dir_str, "manifest.json")
            manifest = {
                "url": url,
                "page_height": page_height,
                "max_height": max_height,
                "viewport_width": viewport_width,
                "viewport_height": viewport_height,
                "device_scale_factor": device_scale_factor,
                "tiles": tiles,
                "manifest_path": manifest_path,
            }

            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)

            return manifest

        finally:
            browser.close()
