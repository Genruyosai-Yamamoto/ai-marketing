# Opportunity Generator — Testing Design

Date: 2026-09-15
Status: Approved (design review)
Branch: `feat/opportunity-generator-tests`

## Purpose

Test the `agent/opportunity_generator` module both automatically and live:
ship deterministic unit tests against a mocked Groq client as a repeatable
baseline, then run a one-off live chain behind a script that exercises real
Groq so output quality can be eyeballed.

## Context

- `agent/opportunity_generator.py`, `agent/analyzer.py`, and `agent/prompts.py`
  exist but are **untracked** in git and wired into **nothing** — `task.py`
  stops at observations. This spec makes the module testable and establishes
  the branch that finally tracks the `agent/` package.
- `groq` 1.7.0 is installed in the venv but missing from `requirements.txt`.
- `.env` provides `GROQ_API_KEY` and `GROQ_MODEL`.
- `website_analyzer.analyze_html()` currently emits `description` while
  `agent/analyzer.py` reads `analysis.get("meta_description")` — the live
  chain would always feed an empty description. Fix: `analyze_html` also
  emits `meta_description` (same value), matching the prompt schema.

## Decisions (recorded)

1. **Test scope:** both mocked unit tests *and* a live Groq run.
2. **Live-run input:** full chain `observation → analyze_observation →
   generate_opportunities` (not a canned analysis).
3. **`meta_description` mismatch:** fixed at the source — `analyze_html`
   emits `meta_description` alongside `description`.
4. **Validation depth:** runtime schema validation is built into
   `generate_opportunities` via a **separate, reusable** validator module.
5. **Ordering/count behavior:** **strict** — any violation raises `ValueError`
   with a precise message. No normalization, truncation, or partial acceptance.
6. **Structure:** Approach A — validator-first.

## Components

### New: `agent/opportunity_validation.py` (pure, no Groq, no I/O)

- Module constants:
  - `_IMPACT_RANKS = {"low": 0, "medium": 1, "high": 2}`
  - `_ALLOWED_TYPES = {"website", "content", "seo", "conversion", "social", "other"}`
- `validate_opportunity_item(item) -> dict`:
  - `item` must be a `dict` with all 7 required keys present: `title`,
    `description`, `problem`, `evidence`, `potential_impact`, `confidence`,
    `type`. Extra keys are tolerated (not rejected).
  - `title`, `description`, `problem`: non-empty `str`.
  - `evidence`: non-empty `list` of non-empty `str` (enforces grounding).
  - `potential_impact` ∈ `{low, medium, high}`.
  - `type` ∈ `_ALLOWED_TYPES`.
  - `confidence` is `int`/`float` (not `bool`), `0 <= c <= 1`.
  - Violations raise `ValueError` with a precise message naming the item
    index and the defect (see Error handling).
- `validate_opportunities(items) -> list`:
  - `items` must be a `list` (non-list raises "must be a JSON array").
  - `0 <= len(items) <= 5`; empty list is valid.
  - Each item passes `validate_opportunity_item`.
  - Ordering enforced strictly: `(impact_rank, confidence)` non-increasing
    across indices; violation raises.

### Modified: `agent/opportunity_generator.py`

After the existing JSON parse + list check, call
`validate_opportunities(opportunities)` before returning. Existing error
messages unchanged.

### Modified: `website_analyzer.py`

`analyze_html` returns `meta_description` alongside `description` (same
value).

### New: `scripts/live_opportunity_flow.py`

Hallway live chain, **no Firestore/Redis/Celery/Flask writes**:
1. `fetch_website_html("https://example.com")` → `analyze_html(html)`
2. Build observation dict `{source_url, final_url, analysis}` shaped like
   `task.py` output.
3. `analyze_observation(observation)` → real Groq → 8-field
   `business_analysis`.
4. `generate_opportunities(business_analysis)` → real Groq → validated
   opportunity list.
5. Print each stage's JSON labeled (`OBSERVATION`, `ANALYSIS`,
   `OPPORTUNITIES`); exit `0` on success. Reads `GROQ_API_KEY`/`GROQ_MODEL`
   from `.env`.

### Modified: `requirements.txt`

Add `groq`.

## Data flow

- **Unit side:** fake `client.chat.completions.create` → canned `content` →
  module parses JSON → list check → `validate_opportunities` → validated
  list or `ValueError` at the exact failing point.
- **Live side:** example.com fetch (existing SSRF-pinned path) → observation
  → Groq analysis → Groq opportunities → validator → printed output.

## Error handling

- `generate_opportunities` messages (unchanged):
  - `ValueError("Groq returned an empty response")`
  - `ValueError("Groq returned invalid opportunity JSON")`
  - `ValueError("Opportunity response must be a JSON array")`
- Validator messages (each names the item index and defect):
  - `"Opportunity N: missing key '<name>'"`
  - `"Opportunity N: '<key>' must be <expected>"` (type mismatches)
  - `"Opportunity N: '<key>' must not be empty"`
  - `"Opportunity N: potential_impact 'critical' not in {low, medium, high}"`
    (same pattern for `type`)
  - `"Opportunity N: confidence 1.7 out of range [0, 1]"`
  - `"expected at most 5 opportunities, got 7"`
  - `"opportunities out of order at index 2"`
- Validator's own non-list check uses the same "must be a JSON array" message
  so the contract is consistent.
- Live script: exceptions propagate with traceback + non-zero exit; printed
  stage label pinpoints the failure. Never echo the API key; printed content
  is only model output.

## Testing

### `tests/test_opportunity_validation.py` (pure)

- Valid 5-item list in correct order → passes, identical result.
- `[]` → passes.
- Each violation raises the exact message: missing each of the 7 keys;
  non-dict item; non-string/empty `title`/`description`/`problem`; empty or
  non-string `evidence`; bad `potential_impact`; bad `type`; `confidence` as
  string / `1.2` / `-0.1`; `7` items; out-of-order; extra keys tolerated.
- Non-list input → "must be a JSON array".

### `tests/test_opportunity_generator.py` (fake Groq client)

- Valid array → validated opportunities returned.
- `content=None` → "Groq returned an empty response".
- `"not json"` → "Groq returned invalid opportunity JSON".
- `'{"a": 1}'` → "Opportunity response must be a JSON array".
- Array with `confidence: 2` → validator `ValueError`.
- Build-args: `model` from `GROQ_MODEL` (default `llama-3.3-70b-versatile`);
  system message is `OPPORTUNITY_GENERATION_SYSTEM_PROMPT`; user message
  embeds the serialized `business_analysis`.

### `tests/test_website_analyzer_fields.py`

- `analyze_html` on canned HTML → both `description` and `meta_description`
  present and equal.

### Live run

- `scripts/live_opportunity_flow.py` run once with the real key (manual,
  outside pytest). Success = exit 0 + `OBSERVATION`/`ANALYSIS`/`OPPORTUNITIES`
  JSON printed + opportunities pass the validator. Failure = traceback +
  non-zero exit.

### Verification gate

- Full `pytest -q` passes (existing 10 + new tests).
- Live script exits 0.
- No secrets committed (`agent/` and `scripts/` are code only; existing
  `.gitignore` protections remain).

## Out of scope

- Wiring the `agent/` pipeline into `task.py` or any route.
- Storing opportunities in Firestore.
- Retry, partial acceptance, or normalization of model output.
- Unit tests for `analyze_observation`/`agent/analyzer.py` (exercised only via
  the live chain).