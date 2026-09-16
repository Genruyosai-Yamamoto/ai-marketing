# Opportunity Pipeline Wiring — Design

Date: 2026-09-16
Status: Draft (pending user review)
Scope: Backend pipeline wiring, API fix, and tests. Dashboard deferred (out of scope).

## Goal

The opportunity-generator agent modules (`agent/analyzer.py`, `agent/opportunity_generator.py`, `agent/opportunity_validation.py`) exist and are unit-tested, but they are not connected into the live pipeline. The Celery task `tasks.analyze_business_website` stops after saving a website observation. As a result, no business understanding is produced, no opportunities are generated, and the opportunities REST API and dashboard have nothing to serve.

This effort wires the full pipeline into the Celery task, fixes the broken opportunities route, and adds tests for every stage.

## Target Pipeline

```
Business input
      ↓
Website Analyzer      (existing — website_analyzer.fetch_website_html / analyze_html)
      ↓
Observation           (existing — saved to Firestore observations/ subcollection)
      ↓
Groq Analyzer         (NEW in task — agent.analyzer.analyze_observation → business understanding)
      ↓
Opportunity Generator (NEW in task — agent.opportunity_generator.generate_opportunities → opportunities list)
      ↓
Opportunities         (NEW in task — validated, saved to Firestore opportunities/ subcollection)
      ↓
REST API             (fix dead route + add latest-run endpoint)
      ↓
Dashboard            (out of scope for this effort)
```

## Approach

Approach A: sequential stages in a single Celery task, with a try/except around the post-observation stages. Chosen over a multi-task `chain()` because the stages are fast (two Groq calls), sequential by nature, and the observation is already persisted before the Groq stages run, so partial results survive late failures.

## 1. Celery Task Pipeline (`task.py`)

Extend `tasks.analyze_business_website` in one sequential task:

1. `fetch_website_html` (existing)
2. `analyze_html` (existing)
3. Save observation doc (existing) — run stays `running`; not yet marked completed
4. `analyze_observation` (NEW) — Groq → business understanding dict
5. `generate_opportunities` (NEW) — Groq → validated opportunities list
6. Save one Firestore doc per opportunity (NEW)
7. Mark run `completed` with `observation_id` + `opportunity_ids` (single terminal transition)

The run keeps `status: "running"` through steps 3–6 so a polling consumer never sees a premature "completed". The existing post-observation "completed" update is replaced by the single terminal update in step 7.

**Import discipline.** `analyze_observation` and `generate_opportunities` are imported lazily inside the task function, not at `task.py` module top. Their modules construct a `Groq()` client at import time as a side effect; lazy import keeps `task.py` importable in tests and in any context without a `GROQ_API_KEY` set.

**Error handling.** The observation save stays inside the existing try/except (run → `failed` on failure). Steps 4–7 get their own try/except after the observation is saved; the terminal `completed` update lives only at the end of that try:

```python
try:
    analysis = analyze_observation(observation)          # observation is the saved doc payload
    opportunities = generate_opportunities(analysis)
    opportunity_ids = []
    for position, opp in enumerate(opportunities):
        opp_ref = business_ref.collection("opportunities").document()
        opp_ref.set({
            **opp,
            "business_id": business_id,
            "owner_id": user_id,
            "position": position,
            "created_at": datetime.utcnow().isoformat(),
        })
        opportunity_ids.append(opp_ref.id)
    run_ref.update({
        "status": "completed",
        "observation_id": observation_ref.id,
        "opportunity_ids": opportunity_ids,
        "completed_at": datetime.utcnow().isoformat(),
    })
except Exception as exc:
    run_ref.update({
        "status": "failed",
        "error": str(exc),
        "completed_at": datetime.utcnow().isoformat(),
    })
    raise
```

**Empty result semantics.** A valid but empty opportunities list (observed in the live run against `example.com`) still completes the run with `opportunity_ids: []` and writes no opportunity docs. The API returns `opportunities: []` and the run stays truthful.

## 2. Opportunity Storage (Firestore)

Each validated opportunity is one document:

```
businesses/{business_id}/opportunities/{opp_id}
```

Document shape — the validator's 7 required keys plus metadata:

```python
{
    "business_id": str,
    "owner_id": str,
    "title": str,
    "description": str,
    "problem": str,
    "evidence": [str, ...],            # non-empty list of strings
    "potential_impact": "low"|"medium"|"high",
    "confidence": float,               # 0.0–1.0
    "type": "website"|"content"|"seo"|"conversion"|"social"|"other",
    "position": int,                   # 0-based order from generate_opportunities
    "created_at": str,                 # ISO timestamp
}
```

- `position` preserves the generator's ranked order for API/dashboard rendering.
- The run record (`agent_runs/{run_id}`) gains `opportunity_ids: [str, ...]` alongside the existing `observation_id`.
- Extra keys from the generator beyond the 7 required are tolerated and persisted (validator behavior).

## 3. REST API (`routes/user.py`)

1. **Fix dead route.** Line 421 uses `@business_bp.route(...)`; `business_bp` is never defined, so `GET /api/business/<business_id>/opportunities/<opportunity_id>` is an unregistered dead route. Change the decorator to `@user_bp.route(...)`.

2. **Add latest-run endpoint** for the dashboard to poll analysis status:

```
GET /api/business/<business_id>/runs/latest
```

Response (owner-only; 403 otherwise; 404 if business missing). "Latest" is the most recently created run, by `created_at` descending, limit 1:

```python
{
    "success": True,
    "business_id": ...,
    "run": {
        "run_id": str,
        "status": "queued"|"running"|"completed"|"failed",
        "observation_id": str|None,
        "opportunity_ids": [str, ...]|None,
        "error": str|None,
        "created_at": str,
        "completed_at": str|None,
    },
}
```

3. **No changes** to `POST /api/business`, `PATCH/DELETE /api/business/<id>`, `POST /api/business/<id>/analyze`, `GET /api/business/<id>/opportunities`, or the auth routes. Ownership-check pattern stays consistent with existing routes.

## 4. Testing

New file `tests/test_task_pipeline.py` — targets the Celery task directly with the existing fake-db pattern (`FakeRef`/`FakeCollection` from `test_user_routes.py`) and monkeypatched stages. The module-level Groq client side effect is avoided via lazy imports (Section 1).

Cases:

1. **Happy path** — monkeypatch `fetch_website_html`, `analyze_html`, `analyze_observation`, `generate_opportunities`, and `task.db`:
   - observation doc written first,
   - each opportunity written with the 7 validator keys + `business_id`, `owner_id`, `position`, `created_at`,
   - run ends `completed` with `observation_id` and `opportunity_ids` in generator order.
2. **Observation Groq failure** — `analyze_observation` raises → observation still saved, run → `failed` with the error.
3. **Opportunity Groq failure** — `generate_opportunities` raises → observation still saved, run → `failed` with the error.
4. **Empty opportunities** — generator returns `[]` → run `completed` with `opportunity_ids: []`, zero opportunity docs.
5. **Invalid opportunity data** — generator/validator raises `ValueError` → run → `failed`.

Extend `tests/test_user_routes.py`:

6. `GET /api/business/b1/opportunities/opp1` → 200 (proves the previously dead route is registered and ownership-checked; currently silent 404/None).
7. `GET /api/business/b1/runs/latest` → 200 with run status/ids; 403 for non-owner; 404 for missing business.

## Out of Scope

- Dashboard UI (`/dashboard` JSON placeholder, `business.html` template) — deferred to a later effort.
- Firestore query index changes — `opportunities` reads are by parent document (no composite indexes needed).
- Multi-worker / chain-based pipeline architecture — Approach B was considered and rejected.