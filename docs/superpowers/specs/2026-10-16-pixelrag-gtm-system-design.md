# Visual GTM Operating System: PixelRAG Integration & Autonomous Competitor Intelligence

**Date:** 2026-10-16  
**Status:** Approved  
**Author:** Antigravity Team  
**Scope:** Backend Architecture, PixelRAG Tiling, Autonomous Competitor Discovery, Vision GTM Engine, and Executive Dossier Generation

---

## 1. Executive Summary & Vision

Blom is evolving from a traditional SEO and reactive text-based website analyzer into an **Autonomous Visual Go-To-Market (GTM) Operating System**. 

Traditional text-based web scraping (DOM/HTML extraction) suffers from over 36% information loss when evaluating websites: it flattens pricing tables, discards visual hierarchy, strips social proof badges, and ignores critical spatial relationships above the fold. 

By integrating **PixelRAG** (a visual document and webpage retrieval framework), Blom captures, tiles, and analyzes web pages in pure pixel space. Combined with **Google Search Console** organic query data, Blom automatically identifies competing websites, captures them as high-resolution visual tiles, and utilizes Vision-Language Models (VLMs) to generate deep competitive positioning teardowns, conversion rate optimization (CRO) audits, and concrete GTM execution campaigns.

---

## 2. Core Architecture & Component Responsibilities

The system is implemented as a native, modular pipeline within Blom's existing Flask + Celery backend.

```
                          ┌─────────────────────────────────────────┐
                          │         Celery Background Worker        │
                          │          tasks.run_gtm_analysis         │
                          └────────────────────┬────────────────────┘
                                               │
               ┌───────────────────────────────┼───────────────────────────────┐
               ▼                               ▼                               ▼
┌───────────────────────────────┐┌───────────────────────────────┐┌───────────────────────────────┐
│     GTM Discovery Service     ││       PixelRAG Service        ││     GSC Analytics Service     │
│ (`services/gtm_discovery.py`) ││ (`services/pixelrag_service`) ││(`connectors/google_search_...`)│
│  - Pulls top organic queries  ││  - Headless Playwright capture││  - Extracts actual queries,   │
│  - Resolves SERP competitors  ││  - Viewport & vertical tiling ││    CTR, impressions, & pages  │
│  - Filters aggregators/social ││  - Generates manifest & tiles ││                               │
└──────────────┬────────────────┘└─────────────┬─────────────────┘└──────────────┬────────────────┘
               │                               │                                 │
               └───────────────────────┬───────┴─────────────────────────────────┘
                                       ▼
                       ┌───────────────────────────────┐
                       │   Visual GTM Engine (agent/)  │
                       │     (`agent/gtm_engine.py`)   │
                       │  - Vision LLM multi-tile read │
                       │  - Evaluates 4 GTM Pillars    │
                       │  - Comparative teardown       │
                       └───────────────┬───────────────┘
                                       │
               ┌───────────────────────┴───────────────────────┐
               ▼                                               ▼
┌───────────────────────────────┐               ┌───────────────────────────────┐
│  Enriched Opportunities &     │               │     Executive GTM Dossier     │
│  Blom Action Engine           │               │ (`services/gtm_dossier.py`)   │
│  - `opportunities` collection │               │  - Markdown & PDF report      │
│  - Visual tile references     │               │  - 30-Day tactical roadmap    │
│  - One-click copy experiments │               │  - Head-to-head GTM matrix    │
└───────────────────────────────┘               └───────────────────────────────┘
```

### Component Breakdown

| Module | File Path | Primary Responsibility |
|---|---|---|
| **PixelRAG Service** | `services/pixelrag_service.py` | Playwright-based browser rendering, cookie/modal dismissal, vertical scroll capture, tile slicing (1280×800), image optimization, and manifest generation. |
| **GTM Discovery Service** | `services/gtm_discovery_service.py` | Extracts top queries from GSC (or industry fallback), executes competitor discovery search, and filters out non-commercial domains (Wikipedia, social media, directory aggregators). |
| **GTM Intelligence Engine** | `agent/gtm_engine.py` | Formulates visual prompts comparing user and competitor tiles across the 4 GTM pillars, calling Vision LLM endpoints. |
| **Executive Dossier Generator** | `services/gtm_dossier_service.py` | Assembles audit scores, side-by-side tile callouts, positioning teardowns, and actionable copy variants into an executive Markdown report. |
| **GTM Celery Task** | `task.py` (`tasks.run_gtm_analysis`) | Orchestrates asynchronous end-to-end execution, tracks run progress in Firestore, and updates error/completion states. |
| **API Blueprint** | `routes/gtm_routes.py` | REST API endpoints for triggering runs, listing historical audits, retrieving run telemetry, and downloading dossiers. |

---

## 3. Data Flow & Tiling Pipeline

When a GTM analysis is triggered for a `business_id`:

1. **Query Extraction**:
   - The worker inspects the business's active Google Search Console connection.
   - It fetches the top 10 search queries ranked by clicks and impressions over the last 28 days.
   - If GSC is not connected, it falls back to the business's registered industry, target audience, and primary keywords in Firestore.

2. **Autonomous Competitor Discovery**:
   - `gtm_discovery_service.py` queries organic search results for the top high-intent commercial keywords.
   - A filtering pipeline strips out irrelevant domains (e.g. `wikipedia.org`, `youtube.com`, `reddit.com`, `linkedin.com`, `medium.com`, `yelp.com`).
   - The top 2 direct business/SaaS competitors are selected for visual benchmarking.

3. **PixelRAG Tiling**:
   - For the user's `website_url` and each competitor URL, Playwright launches an isolated Chromium page context.
   - Configuration:
     - Viewport: `1280 × 800`
     - Device Scale Factor: `1.5` (high-DPI for legible typography)
     - Max Page Height Cap: `8,000px` (maximum 6 sequential tiles to protect memory)
   - Navigation runs with a strict 15-second timeout and `domcontentloaded` fallback.
   - Common cookie banners and overlays are dismissed automatically.
   - The page is scrolled vertically in steps to trigger lazy images, then sliced into sequential tiles:
     - `tile_0001_hero.webp`: Viewport 0–800px (Navigation, H1, Subhead, Primary CTA, Hero visual)
     - `tile_0002_value.webp`: Viewport 800–1600px (Core value proposition, feature breakdown)
     - `tile_0003_social.webp`: Viewport 1600–2400px (Social proof, customer logos, testimonials)
     - `tile_0004_pricing.webp`: Viewport 2400–3200px (Pricing matrix, tiers, or bottom CTA)
   - Stored in: `static/tiles/{business_id}/{run_id}/{domain_slug}/` with an accompanying `manifest.json`.

---

## 4. Visual GTM Analysis & The 4 Evaluation Pillars

The GTM Engine passes visual tiles into a Vision LLM to perform deep comparative analysis across four foundational GTM pillars:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        THE 4 GTM PILLARS                               │
├────────────────────────────────┬───────────────────────────────────────┤
│ 1. Above-The-Fold Clarity      │ Hero headline contrast, value clarity,│
│                                │ reading ease, primary CTA salience.   │
├────────────────────────────────┼───────────────────────────────────────┤
│ 2. Pricing & Packaging         │ Friction assessment (free trial vs.   │
│                                │ demo wall), tier transparency.        │
├────────────────────────────────┼───────────────────────────────────────┤
│ 3. Social Proof & Trust        │ Customer logos, G2/Trustpilot badges, │
│                                │ quantifiable metric proof points.     │
├────────────────────────────────┼───────────────────────────────────────┤
│ 4. CRO & CTA Conversion Flow   │ Button prominence, form friction,     │
│                                │ secondary vs. primary CTA conflicts.  │
└────────────────────────────────┴───────────────────────────────────────┘
```

### Vision LLM Comparative Evaluation Prompt
The Vision LLM receives the user's hero & value tiles alongside competitor tiles with instructions to:
1. Score each domain from 0 to 100 on each of the 4 pillars.
2. Identify **Positioning Blind Spots**: Where the user's messaging is vague, generic, or defensively weaker than competitors.
3. Identify **Visual CRO Friction**: Elements causing cognitive friction (e.g., low-contrast CTA buttons, lack of trust badges above the fold).
4. Formulate **Actionable Copy Tests**: High-converting alternative H1s, subheads, and CTA microcopy directly countering competitor strengths.

---

## 5. Data Models & Firestore Schema

### Subcollection: `businesses/{business_id}/gtm_runs/{run_id}`
```json
{
  "id": "run-gtm-1001",
  "business_id": "djoP699Aysz0ILtsHFkS",
  "status": "completed",
  "created_at": "2026-10-16T20:00:00Z",
  "completed_at": "2026-10-16T20:01:15Z",
  "user_website": {
    "url": "https://example.com",
    "domain": "example.com",
    "tiles_dir": "static/tiles/djoP699Aysz0ILtsHFkS/run-gtm-1001/example_com/",
    "tiles": ["tile_0001_hero.webp", "tile_0002_value.webp", "tile_0003_social.webp"]
  },
  "competitors_analyzed": [
    {
      "domain": "competitor-a.com",
      "url": "https://competitor-a.com",
      "tiles": ["tile_0001_hero.webp", "tile_0002_value.webp"],
      "strengths": ["Instant interactive product demo above fold", "Visible transparent pricing"],
      "weaknesses": ["Vague CTA copy ('Get Started' without trial duration)"]
    }
  ],
  "gtm_scores": {
    "overall": 76,
    "above_the_fold": 72,
    "pricing_clarity": 80,
    "social_proof": 68,
    "cro_friction": 84
  },
  "dossier_markdown_path": "static/dossiers/djoP699Aysz0ILtsHFkS/run-gtm-1001.md",
  "opportunities_count": 4
}
```

### Enriched Opportunity: `businesses/{business_id}/opportunities/{opp_id}`
Existing opportunities remain 100% backwards-compatible, enriched with visual and competitive fields:
```json
{
  "id": "opp-2001",
  "business_id": "djoP699Aysz0ILtsHFkS",
  "type": "gtm_positioning",
  "title": "Sharpen Hero Value Proposition Against CompetitorA",
  "problem": "Hero headline 'Modern Software for Modern Teams' has low informational density compared to CompetitorA's 'Save 12 Hours Every Week on Lead Qualification'.",
  "potential_impact": "High",
  "confidence": 0.89,
  "visual_evidence": {
    "user_tile": "/static/tiles/djoP699Aysz0ILtsHFkS/run-gtm-1001/example_com/tile_0001_hero.webp",
    "competitor_tile": "/static/tiles/djoP699Aysz0ILtsHFkS/run-gtm-1001/competitor_a_com/tile_0001_hero.webp",
    "target_element": "h1_hero"
  },
  "suggested_actions": [
    {
      "action_type": "copy_test",
      "headline_variant_a": "Qualify Inbound Leads 3x Faster With Automated AI Workflows",
      "headline_variant_b": "The Inbound GTM Engine That Converts Prospects While You Sleep",
      "cta_text": "Start Free 14-Day Audit"
    }
  ]
}
```

---

## 6. API Endpoints (`routes/gtm_routes.py`)

All routes require session authentication and business ownership verification:

* `POST /api/gtm/run`  
  **Payload**: `{"business_id": "..."}`  
  **Response**: `202 Accepted` with `{"success": true, "run_id": "..."}`. Triggers Celery background worker.
* `GET /api/gtm/runs?business_id=...`  
  **Response**: `200 OK` with array of past GTM audit summaries, scores, and timestamps.
* `GET /api/gtm/runs/<run_id>`  
  **Response**: `200 OK` with full run telemetry, competitor breakdowns, score gauges, and tile paths.
* `GET /api/gtm/runs/<run_id>/dossier`  
  **Response**: `200 OK` returning the generated executive GTM Dossier in Markdown and rendered HTML.

---

## 7. Resilience & Error Handling

1. **Crawl & Render Safeguards**:
   - Per-page navigation timeout: 15 seconds max.
   - Max concurrent browser contexts: 3.
   - Memory watchdog: browser context is destroyed immediately after tile extraction to avoid memory leaks.
2. **Competitor Crawl Graceful Degradation**:
   - If a competitor site fails to load, blocks requests, or encounters Cloudflare anti-bot checks, the engine logs the warning and proceeds with the audit using the user's site tiles and available search metadata without failing the job.
3. **Vision API Resilience**:
   - Automatic retry with exponential backoff on Vision API rate-limit errors (429/503).
   - Text fallback analyzer if Vision API is completely unreachable.

---

## 8. Verification & Testing Plan

1. **Unit Tests (`tests/gtm/test_pixelrag_service.py`)**:
   - Tiling logic with mocked Playwright page and screenshot slices.
   - Handling of page timeouts, non-200 responses, and oversized heights.
2. **Unit Tests (`tests/gtm/test_gtm_discovery.py`)**:
   - Organic keyword filtering and competitor domain extraction from mock search results.
3. **Unit Tests (`tests/gtm/test_gtm_engine.py`)**:
   - Parsing of Vision LLM comparative responses into the 4 GTM pillars and opportunity schema.
4. **Integration & Route Tests (`tests/gtm/test_gtm_routes.py`)**:
   - Auth & ownership checks (401 unauthenticated, 403 unauthorized, 404 missing business).
   - Task dispatch validation and dossier delivery.
5. **Coverage Target**:
   - ≥90% line coverage across all new GTM services, engine modules, and route handlers.
