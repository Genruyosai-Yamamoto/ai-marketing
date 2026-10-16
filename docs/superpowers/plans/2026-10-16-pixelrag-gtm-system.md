# Visual GTM Operating System: PixelRAG Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade Blom into an autonomous Visual Go-To-Market (GTM) Operating System by integrating PixelRAG page-tiling, Search-Console-driven competitor discovery, Vision LLM comparative analysis across 4 GTM pillars, and executive dossier generation.

**Architecture:** A native modular pipeline executed asynchronously via Celery: Playwright renders and tiles web pages into vertical screenshot slices; a competitor discovery service queries top organic keywords from Google Search Console; a multi-tile Vision LLM engine evaluates user vs. competitor landing pages across 4 GTM pillars; and results populate enriched Blom opportunities and an executive Markdown/HTML GTM dossier.

**Tech Stack:** Python 3.13, Flask, Celery, Redis, Playwright, Pillow, Groq Vision API (`llama-3.2-11b-vision-preview`), Firestore, pytest, unittest.mock.

## Global Constraints

- Python package dependencies added must be pinned in `requirements.txt`.
- All new code must follow PEP 8 and Blom's existing service/route conventions.
- All Google Search Console existing routes and tests in `tests/search_console/` must remain passing (zero regressions).
- No hardcoded secrets; use environment variables from `.env`.
- Mock external network calls, Playwright browser instances, and Vision LLM APIs in automated tests.
- Target ≥90% line coverage across new GTM modules.

---

### Task 0: Scaffolding, Dependencies & Shared Fixtures

**Files:**
- Modify: `requirements.txt`
- Create: `tests/gtm/__init__.py`
- Create: `tests/gtm/conftest.py`

**Interfaces:**
- Consumes: Existing Flask test client and Firestore mocking fixtures from `tests/search_console/conftest.py`.
- Produces: Shared GTM fixtures for mock Playwright pages, mock Vision LLM responses, and mock GTM business docs.

- [ ] **Step 1: Write the failing test**

```python
# tests/gtm/test_scaffolding.py
import pytest

def test_gtm_scaffolding_imports():
    import tests.gtm.conftest as conftest_module
    assert hasattr(conftest_module, "mock_gtm_business_doc")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/pytest tests/gtm/test_scaffolding.py -v`
Expected: FAIL (ModuleNotFoundError or AttributeError)

- [ ] **Step 3: Add dependencies and create conftest.py**

Add `playwright==1.49.1` to `requirements.txt`.
Create `tests/gtm/__init__.py`.
Create `tests/gtm/conftest.py` with:
- `mock_gtm_business_doc`: Firestore business document fixture with `owner_id: "user-1"` and `website_url: "https://example.com"`.
- `mock_playwright_page`: MagicMock simulating Playwright Page, viewport settings, and screenshot buffers.
- `mock_vision_response`: Dict simulating Vision LLM GTM evaluation output.

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/pytest tests/gtm/test_scaffolding.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add requirements.txt tests/gtm/__init__.py tests/gtm/conftest.py tests/gtm/test_scaffolding.py
git commit -m "chore(gtm): scaffold GTM test package, dependencies, and shared fixtures"
```

---

### Task 1: PixelRAG Tiling Service

**Files:**
- Create: `services/pixelrag_service.py`
- Test: `tests/gtm/test_pixelrag_service.py`

**Interfaces:**
- Consumes: URL string, output directory string, optional height cap.
- Produces: `render_and_tile_page(url: str, output_dir: str, max_height: int = 8000) -> dict` returning a manifest with tile file paths, scroll depths, and page dimensions.

- [ ] **Step 1: Write the failing tests**

```python
# tests/gtm/test_pixelrag_service.py
import pytest
from unittest.mock import MagicMock, patch

def test_render_and_tile_page_creates_tiles_and_manifest(tmp_path):
    from services.pixelrag_service import render_and_tile_page

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
        assert (tmp_path / "tile_0001_hero.webp").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/pytest tests/gtm/test_pixelrag_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.pixelrag_service'`

- [ ] **Step 3: Write implementation of `services/pixelrag_service.py`**

Implement `render_and_tile_page` and helper functions:
- Launch headless Chromium with standard viewport (`1280 × 800`, `device_scale_factor=1.5`).
- Set navigation timeout (15s) with `domcontentloaded` fallback.
- Auto-dismiss common cookie banners (`#accept-cookie`, `[aria-label*="cookie"]`, `.cookie-banner`).
- Slices page into vertical sections of 800px height each, capped at `max_height` (default 8000px).
- Labels tiles sequentially: `tile_0001_hero.webp`, `tile_0002_value.webp`, `tile_0003_social.webp`, etc.
- Writes `manifest.json` in the destination directory and returns the manifest dictionary.

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/pytest tests/gtm/test_pixelrag_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/pixelrag_service.py tests/gtm/test_pixelrag_service.py
git commit -m "feat(gtm): implement PixelRAG page rendering and vertical tiling service"
```

---

### Task 2: Autonomous Competitor Discovery Service

**Files:**
- Create: `services/gtm_discovery_service.py`
- Test: `tests/gtm/test_gtm_discovery.py`

**Interfaces:**
- Consumes: `business_id: str`, `user_id: str`, top query strings from Google Search Console.
- Produces: `discover_competitors(business_id: str, user_id: str, max_competitors: int = 2) -> list[dict]` returning discovered competitor domains and URLs.

- [ ] **Step 1: Write the failing tests**

```python
# tests/gtm/test_gtm_discovery.py
import pytest
from unittest.mock import patch, MagicMock

def test_discover_competitors_filters_aggregators_and_extracts_domains():
    from services.gtm_discovery_service import filter_competitor_domains

    raw_results = [
        {"link": "https://en.wikipedia.org/wiki/SEO"},
        {"link": "https://www.youtube.com/watch?v=123"},
        {"link": "https://acme-competitor.com/features"},
        {"link": "https://beta-rival.io/pricing"},
        {"link": "https://reddit.com/r/marketing"},
    ]

    competitors = filter_competitor_domains(raw_results, exclude_domain="example.com")
    assert competitors == [
        {"domain": "acme-competitor.com", "url": "https://acme-competitor.com"},
        {"domain": "beta-rival.io", "url": "https://beta-rival.io"},
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/pytest tests/gtm/test_gtm_discovery.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation of `services/gtm_discovery_service.py`**

Implement:
- `EXCLUDED_DOMAINS` set (Wikipedia, YouTube, Reddit, LinkedIn, Twitter/X, Medium, Yelp, Amazon, GitHub, Blom's own domain).
- `filter_competitor_domains(search_results, exclude_domain) -> list[dict]`.
- `get_gtm_seed_queries(business_id, user_id) -> list[str]`: fetches top queries from Search Console if connected, else falls back to Firestore business industry/keywords.
- `discover_competitors(business_id, user_id, max_competitors=2) -> list[dict]`: executes organic search lookups for top queries, applies filters, and returns top competitor profiles.

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/pytest tests/gtm/test_gtm_discovery.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/gtm_discovery_service.py tests/gtm/test_gtm_discovery.py
git commit -m "feat(gtm): implement autonomous competitor discovery service"
```

---

### Task 3: Visual GTM Intelligence Engine

**Files:**
- Create: `agent/gtm_engine.py`
- Test: `tests/gtm/test_gtm_engine.py`

**Interfaces:**
- Consumes: User site tiles manifest, competitor tiles manifests, search query list.
- Produces: `analyze_gtm_tiles(user_manifest: dict, competitor_manifests: list[dict], search_queries: list[str]) -> dict` returning 4-pillar scores, positioning blind spots, CRO friction points, and structured opportunities.

- [ ] **Step 1: Write the failing tests**

```python
# tests/gtm/test_gtm_engine.py
import pytest
from unittest.mock import patch, MagicMock

def test_analyze_gtm_tiles_parses_4_pillars_and_opportunities():
    from agent.gtm_engine import parse_gtm_vision_output

    sample_llm_json = {
        "gtm_scores": {
            "overall": 80,
            "above_the_fold": 75,
            "pricing_clarity": 85,
            "social_proof": 70,
            "cro_friction": 90
        },
        "blind_spots": ["Competitor has explicit pricing, user does not"],
        "opportunities": [
            {
                "title": "Add Transparent Pricing Tier Above The Fold",
                "problem": "Competitor Acme displays $29/mo while user requires contacting sales.",
                "type": "gtm_pricing",
                "potential_impact": "High",
                "confidence": 0.85
            }
        ]
    }

    result = parse_gtm_vision_output(sample_llm_json)
    assert result["gtm_scores"]["overall"] == 80
    assert len(result["opportunities"]) == 1
    assert result["opportunities"][0]["type"] == "gtm_pricing"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/pytest tests/gtm/test_gtm_engine.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation of `agent/gtm_engine.py`**

Implement:
- Multimodal prompt builder: encodes key tiles (hero, pricing) as base64 data URIs.
- Prompt structure enforcing the 4 GTM Pillars: Above-the-fold clarity, Pricing architecture, Social proof credibility, CRO friction.
- Vision LLM client invocation using Groq multimodal API (`llama-3.2-11b-vision-preview`).
- JSON output validator & fallback parser normalizing output to Blom Opportunity schema.

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/pytest tests/gtm/test_gtm_engine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/gtm_engine.py tests/gtm/test_gtm_engine.py
git commit -m "feat(gtm): implement multi-tile visual GTM intelligence engine"
```

---

### Task 4: Executive Dossier Generator

**Files:**
- Create: `services/gtm_dossier_service.py`
- Test: `tests/gtm/test_gtm_dossier.py`

**Interfaces:**
- Consumes: GTM run dictionary (scores, competitor breakdowns, opportunities).
- Produces: `generate_gtm_dossier_markdown(run_data: dict) -> str` and `save_dossier_to_file(run_id: str, business_id: str, markdown_content: str) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/gtm/test_gtm_dossier.py
import pytest

def test_generate_gtm_dossier_markdown_includes_all_sections():
    from services.gtm_dossier_service import generate_gtm_dossier_markdown

    mock_run = {
        "id": "run-123",
        "user_website": {"domain": "mysite.com", "url": "https://mysite.com"},
        "competitors_analyzed": [{"domain": "rival.com"}],
        "gtm_scores": {"overall": 78, "above_the_fold": 80, "pricing_clarity": 70, "social_proof": 75, "cro_friction": 85},
        "opportunities": [{"title": "Hero Fix", "problem": "Low contrast", "potential_impact": "High"}]
    }

    md = generate_gtm_dossier_markdown(mock_run)
    assert "# Executive GTM Intelligence Dossier" in md
    assert "mysite.com" in md
    assert "Overall Score: 78" in md
    assert "30-Day Tactical Roadmap" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/pytest tests/gtm/test_gtm_dossier.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation of `services/gtm_dossier_service.py`**

Implement:
- `generate_gtm_dossier_markdown(run_data: dict) -> str`: Formats:
  1. Executive Summary & GTM Health Score gauges.
  2. Competitive Landscape Table (domain, strengths, weaknesses).
  3. Visual Teardown Findings (with relative image links to screenshot tiles).
  4. Prioritized 30-Day Tactical Roadmap (quick wins vs strategic positioning).
- `save_dossier_to_file(run_id, business_id, markdown_content) -> str`: saves file to `static/dossiers/{business_id}/{run_id}.md` and returns relative URL.

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/pytest tests/gtm/test_gtm_dossier.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/gtm_dossier_service.py tests/gtm/test_gtm_dossier.py
git commit -m "feat(gtm): implement executive GTM dossier markdown generator"
```

---

### Task 5: GTM API Routes & Celery Pipeline Integration

**Files:**
- Create: `routes/gtm_routes.py`
- Modify: `task.py` (add `tasks.run_gtm_analysis` Celery task)
- Modify: `app.py` (register `gtm_bp` blueprint)
- Test: `tests/gtm/test_gtm_routes.py`

**Interfaces:**
- Consumes: Flask request session, `business_id`.
- Produces: `POST /api/gtm/run`, `GET /api/gtm/runs`, `GET /api/gtm/runs/<run_id>`, `GET /api/gtm/runs/<run_id>/dossier`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/gtm/test_gtm_routes.py
import pytest
from unittest.mock import patch, MagicMock

def test_gtm_run_unauthenticated_returns_401(client):
    res = client.post("/api/gtm/run", json={"business_id": "biz-1"})
    assert res.status_code == 401

def test_gtm_run_authorized_dispatches_celery_task(auth_client, mock_gtm_business_doc):
    with patch("firebase.db.collection") as mock_db, \
         patch("task.run_gtm_analysis.delay") as mock_delay:
        mock_db.return_value.document.return_value.get.return_value = mock_gtm_business_doc
        res = auth_client.post("/api/gtm/run", json={"business_id": "biz-1"})
        assert res.status_code == 202
        assert res.json["success"] is True
        mock_delay.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/pytest tests/gtm/test_gtm_routes.py -v`
Expected: FAIL with 404 / route not found

- [ ] **Step 3: Implement `routes/gtm_routes.py`, `task.py` task, and register in `app.py`**

- `task.py`: add `@celery.task(bind=True, name="tasks.run_gtm_analysis")` coordinating PixelRAG tiling, discovery, GTM engine, and dossier persistence in Firestore subcollection `businesses/{id}/gtm_runs/{run_id}`.
- `routes/gtm_routes.py`:
  - `POST /api/gtm/run`: verifies auth & ownership, creates pending run in Firestore, dispatches task, returns `202`.
  - `GET /api/gtm/runs`: lists past runs for the business.
  - `GET /api/gtm/runs/<run_id>`: returns full run JSON.
  - `GET /api/gtm/runs/<run_id>/dossier`: serves the Markdown dossier.
- `app.py`: register `gtm_bp` under `/api/gtm`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/pytest tests/gtm/test_gtm_routes.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add routes/gtm_routes.py task.py app.py tests/gtm/test_gtm_routes.py
git commit -m "feat(gtm): add GTM REST API blueprint and background Celery task"
```

---

### Task 6: Full Suite Verification & Coverage Check

**Files:**
- Test all: `tests/gtm/` and regression check on `tests/search_console/`

**Interfaces:**
- Consumes: Complete test suite.
- Produces: Test execution report and coverage percentage ≥90% across all GTM files.

- [ ] **Step 1: Run complete GTM suite**

Run: `venv/bin/pytest tests/gtm/ -v --tb=short`
Expected: All tests pass, 0 failures, 0 skips.

- [ ] **Step 2: Check coverage for all new modules**

Run:
```bash
venv/bin/pytest tests/gtm/ \
  --cov=services.pixelrag_service \
  --cov=services.gtm_discovery_service \
  --cov=agent.gtm_engine \
  --cov=services.gtm_dossier_service \
  --cov=routes.gtm_routes \
  --cov-report=term-missing
```
Expected: Coverage ≥90% on each module.

- [ ] **Step 3: Run regression check on Search Console tests**

Run: `venv/bin/pytest tests/search_console/ -q --tb=short`
Expected: 62 passed, 0 failures.

- [ ] **Step 4: Final commit**

```bash
git add .
git commit -m "test(gtm): complete test suite and verify ≥90% coverage on GTM modules"
```
