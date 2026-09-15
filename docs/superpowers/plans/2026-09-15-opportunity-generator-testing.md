# Opportunity Generator Testing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `agent/opportunity_generator` module testable — deterministic unit tests against a mocked Groq client, runtime schema validation of Groq's output, and a live chain script (example.com → observation → analysis → opportunities) that proves it against the real API.

**Architecture:** A pure, reusable `agent/opportunity_validation.py` module validates each opportunity item and the list as a whole (strict — any violation raises). `agent/opportunity_generator.py` parses Groq output then calls the validator before returning. `website_analyzer.analyze_html()` gains a `meta_description` field so `agent/analyzer.py` receives real description data. `scripts/live_opportunity_flow.py` chains fetch → analyze → generate behind one script (no Firestore/Redis/Celery/Flask).

**Tech Stack:** Python 3.13, groq 1.7.0, BeautifulSoup, requests, pytest, python-dotenv.

**Branch:** `feat/opportunity-generator-tests` (already checked out in `git`).

## Global Constraints

- Validation is **strict**: any structural/order/count violation raises `ValueError` with a precise message. No normalization, truncation, or partial acceptance.
- `potential_impact` must be exactly one of `low | medium | high`; `type` exactly one of `website | content | seo | conversion | social | other`; `confidence` an `int`/`float` (not `bool`) in `[0, 1]`; `evidence` a non-empty list of non-empty strings.
- Existing `generate_opportunities` error messages stay byte-for-byte unchanged:
  - `"Groq returned an empty response"`
  - `"Groq returned invalid opportunity JSON"`
  - `"Opportunity response must be a JSON array"`
- The validator's own non-list check uses the same `"Opportunity response must be a JSON array"` message.
- `groq` SDK raises `GroqError` at construction when `GROQ_API_KEY` is unset — in `tests/test_opportunity_generator.py` the module must be imported only **after** `monkeypatch.setenv("GROQ_API_KEY", "test-key")` (never at module top level of the test file).
- The live script must load `.env` via `python-dotenv` before importing `agent` modules, and **must not** write anything to Firestore, Redis, or disk outputs (stdout only).
- Run pytest from the backend root (`./venv/bin/python -m pytest -q`). Backend root is on `sys.path` via `tests/conftest.py`.
- Existing `.gitignore` rules (`.env`, `ai-agent-*.json`, `venv/`) protect secrets — never `git add` them.

---

### Task 1: Reusable opportunity validator

**Files:**
- Create: `agent/opportunity_validation.py`
- Test: `tests/test_opportunity_validation.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `agent.opportunity_validation.validate_opportunity_item(item: dict, index: int = 0) -> dict`
  - `agent.opportunity_validation.validate_opportunities(items: list) -> list`
  - Module constants `_IMPACT_RANKS`, `_ALLOWED_TYPES`, `_REQUIRED_KEYS`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_opportunity_validation.py`:

```python
import pytest

import agent.opportunity_validation as v


def _valid_item(**overrides):
    item = {
        "title": "Missing pricing page",
        "description": "No pricing information visible on the site.",
        "problem": "Pricing transparency gap on the home page.",
        "evidence": ["No pricing links found in navigation"],
        "potential_impact": "high",
        "confidence": 0.9,
        "type": "conversion",
    }
    item.update(overrides)
    return item


def test_valid_full_list_passes():
    items = [
        _valid_item(potential_impact="high", confidence=0.9),
        _valid_item(potential_impact="medium", confidence=0.8),
        _valid_item(potential_impact="medium", confidence=0.5),
        _valid_item(potential_impact="low", confidence=0.7),
        _valid_item(potential_impact="low", confidence=0.4),
    ]
    assert v.validate_opportunities(items) == items


def test_empty_list_valid():
    assert v.validate_opportunities([]) == []


@pytest.mark.parametrize("key", v._REQUIRED_KEYS)
def test_missing_key_raises(key):
    item = _valid_item()
    del item[key]
    with pytest.raises(ValueError, match=f"missing key '{key}'"):
        v.validate_opportunity_item(item, 0)


def test_non_dict_item_raises():
    with pytest.raises(ValueError, match="Opportunity 0: must be a dict"):
        v.validate_opportunity_item(42)


@pytest.mark.parametrize("key", ["title", "description", "problem"])
@pytest.mark.parametrize("bad", ["", "   ", 42, None])
def test_string_fields_reject_bad_values(key, bad):
    with pytest.raises(ValueError, match=f"'{key}' must be a non-empty string"):
        v.validate_opportunity_item(_valid_item(**{key: bad}))


@pytest.mark.parametrize("bad", [[], ["ok", 3], ["ok", ""], "nope"])
def test_evidence_rejects_bad_values(bad):
    with pytest.raises(ValueError, match="'evidence' must be a non-empty list of strings"):
        v.validate_opportunity_item(_valid_item(evidence=bad))


def test_bad_potential_impact_raises():
    with pytest.raises(ValueError, match=r"potential_impact 'critical' not in"):
        v.validate_opportunity_item(_valid_item(potential_impact="critical"))


def test_bad_type_raises():
    with pytest.raises(ValueError, match=r"type 'ads' not in"):
        v.validate_opportunity_item(_valid_item(type="ads"))


@pytest.mark.parametrize("bad", ["0.5", True, None])
def test_confidence_must_be_number(bad):
    with pytest.raises(ValueError, match="'confidence' must be a number"):
        v.validate_opportunity_item(_valid_item(confidence=bad))


@pytest.mark.parametrize("bad", [1.2, -0.1, 2])
def test_confidence_out_of_range_raises(bad):
    with pytest.raises(ValueError, match=r"confidence -?[\d.]+ out of range \[0, 1\]"):
        v.validate_opportunity_item(_valid_item(confidence=bad))


def test_more_than_five_raises():
    items = [_valid_item(tag=i) for i in range(6)]
    with pytest.raises(ValueError, match="expected at most 5 opportunities, got 6"):
        v.validate_opportunities(items)


def test_out_of_order_raises():
    items = [
        _valid_item(potential_impact="low", confidence=0.4),
        _valid_item(potential_impact="high", confidence=0.9),
    ]
    with pytest.raises(ValueError, match="opportunities out of order at index 1"):
        v.validate_opportunities(items)


def test_extra_keys_tolerated():
    item = _valid_item(extra="anything")
    assert v.validate_opportunity_item(item) == item


def test_non_list_raises():
    with pytest.raises(ValueError, match="must be a JSON array"):
        v.validate_opportunities({"title": "x"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/bin/python -m pytest tests/test_opportunity_validation.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent.opportunity_validation'`

- [ ] **Step 3: Write the implementation**

Create `agent/opportunity_validation.py`:

```python
_IMPACT_RANKS = {"low": 0, "medium": 1, "high": 2}
_ALLOWED_TYPES = {"website", "content", "seo", "conversion", "social", "other"}
_REQUIRED_KEYS = (
    "title",
    "description",
    "problem",
    "evidence",
    "potential_impact",
    "confidence",
    "type",
)


def validate_opportunity_item(item, index=0):
    """Validate one opportunity dict. Raises ValueError on any defect,
    otherwise returns the item unchanged. Extra keys are tolerated."""
    prefix = f"Opportunity {index}"

    if not isinstance(item, dict):
        raise ValueError(f"{prefix}: must be a dict")

    for key in ("title", "description", "problem"):
        value = item.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{prefix}: '{key}' must be a non-empty string")

    evidence = item.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError(f"{prefix}: 'evidence' must be a non-empty list of strings")
    for entry in evidence:
        if not isinstance(entry, str) or not entry.strip():
            raise ValueError(f"{prefix}: 'evidence' must be a non-empty list of strings")

    impact = item.get("potential_impact")
    if impact not in _IMPACT_RANKS:
        raise ValueError(
            f"{prefix}: potential_impact {impact!r} not in {sorted(_IMPACT_RANKS)}"
        )

    otype = item.get("type")
    if otype not in _ALLOWED_TYPES:
        raise ValueError(f"{prefix}: type {otype!r} not in {sorted(_ALLOWED_TYPES)}")

    confidence = item.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError(f"{prefix}: 'confidence' must be a number")
    if not 0 <= confidence <= 1:
        raise ValueError(f"{prefix}: confidence {confidence} out of range [0, 1]")

    return item


def validate_opportunities(items):
    """Validate an opportunity list: must be a list of 0-5 valid items,
    strictly ordered by (impact rank, confidence) both descending.
    Returns the items unchanged."""
    if not isinstance(items, list):
        raise ValueError("Opportunity response must be a JSON array")
    if len(items) > 5:
        raise ValueError(f"expected at most 5 opportunities, got {len(items)}")

    for index, item in enumerate(items):
        validate_opportunity_item(item, index)

    for index in range(1, len(items)):
        rank = _IMPACT_RANKS[items[index]["potential_impact"]]
        conf = items[index]["confidence"]
        prev_rank = _IMPACT_RANKS[items[index - 1]["potential_impact"]]
        prev_conf = items[index - 1]["confidence"]
        if rank > prev_rank or (rank == prev_rank and conf > prev_conf):
            raise ValueError(f"opportunities out of order at index {index}")

    return items
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./venv/bin/python -m pytest tests/test_opportunity_validation.py -q`
Expected: PASS (38 tests, including parametrized cases)

- [ ] **Step 5: Commit**

```bash
git add agent/opportunity_validation.py tests/test_opportunity_validation.py
git commit -m "feat: add reusable opportunity validation helpers"
```

---

### Task 2: Wire validator into generate_opportunities

**Files:**
- Modify: `agent/opportunity_generator.py:6` (import), `agent/opportunity_generator.py:63-68` (validate before return)
- Test: `tests/test_opportunity_generator.py`

**Interfaces:**
- Consumes: `validate_opportunities(items) -> list` from Task 1; `OPPORTUNITY_GENERATION_SYSTEM_PROMPT` (already imported in the module).
- Produces: `agent.opportunity_generator.generate_opportunities(business_analysis: dict) -> list` — now guaranteed validated.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_opportunity_generator.py`:

```python
import json

import pytest

from agent import prompts


class _Fake:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)


class _Choice:
    def __init__(self, content):
        self.message = _Fake(content=content)


class _Response:
    def __init__(self, content):
        self.choices = [_Choice(content)]


VALID_ITEM = {
    "title": "Missing pricing page",
    "description": "No pricing info visible.",
    "problem": "Pricing transparency gap.",
    "evidence": ["No pricing links found in navigation"],
    "potential_impact": "high",
    "confidence": 0.9,
    "type": "conversion",
}

ANALYSIS = {
    "business_summary": "ACME sells widgets.",
    "target_audience": "SMB owners.",
    "value_proposition": "Fast, reliable widgets.",
    "products_or_services": ["Widgets"],
    "strengths": ["Clear product page"],
    "weaknesses": ["No pricing info"],
    "marketing_signals": [],
    "missing_information": ["Pricing"],
}


@pytest.fixture
def og(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    import agent.opportunity_generator as module
    return module


@pytest.fixture
def fake_client(monkeypatch):
    state = {"calls": []}

    def build(content):
        def create(*, model=None, messages=None, temperature=None):
            state["calls"].append(
                {"model": model, "messages": messages, "temperature": temperature}
            )
            return _Response(content)

        return _Fake(chat=_Fake(completions=_Fake(create=create)))

    state["build"] = build
    return state


def test_valid_array_returns_validated_opportunities(og, fake_client, monkeypatch):
    payload = json.dumps([VALID_ITEM])
    monkeypatch.setattr(og, "client", fake_client["build"](payload))
    result = og.generate_opportunities(ANALYSIS)
    assert result == [VALID_ITEM]
    call = fake_client["calls"][0]
    assert call["model"] == "llama-3.3-70b-versatile"
    assert call["temperature"] == 0.2
    assert call["messages"][0]["content"] == prompts.OPPORTUNITY_GENERATION_SYSTEM_PROMPT
    assert "ACME sells widgets." in call["messages"][1]["content"]


def test_model_reads_groq_model_env(og, fake_client, monkeypatch):
    monkeypatch.setenv("GROQ_MODEL", "custom-model")
    monkeypatch.setattr(og, "client", fake_client["build"](json.dumps([VALID_ITEM])))
    og.generate_opportunities(ANALYSIS)
    assert fake_client["calls"][0]["model"] == "custom-model"


def test_empty_response_raises(og, fake_client, monkeypatch):
    monkeypatch.setattr(og, "client", fake_client["build"](None))
    with pytest.raises(ValueError, match="Groq returned an empty response"):
        og.generate_opportunities(ANALYSIS)


def test_invalid_json_raises(og, fake_client, monkeypatch):
    monkeypatch.setattr(og, "client", fake_client["build"]("not json"))
    with pytest.raises(ValueError, match="Groq returned invalid opportunity JSON"):
        og.generate_opportunities(ANALYSIS)


def test_non_array_raises(og, fake_client, monkeypatch):
    monkeypatch.setattr(og, "client", fake_client["build"]('{"a": 1}'))
    with pytest.raises(ValueError, match="Opportunity response must be a JSON array"):
        og.generate_opportunities(ANALYSIS)


def test_schema_violation_raises(og, fake_client, monkeypatch):
    broken = dict(VALID_ITEM, confidence=2)
    monkeypatch.setattr(og, "client", fake_client["build"](json.dumps([broken])))
    with pytest.raises(ValueError, match="confidence 2 out of range"):
        og.generate_opportunities(ANALYSIS)
```

- [ ] **Step 2: Run tests to verify the new behavior fails**

Run: `./venv/bin/python -m pytest tests/test_opportunity_generator.py -q`
Expected: 5 pass (the pre-existing module behavior), `test_schema_violation_raises` FAILS — validator not yet wired in, so `confidence: 2` is returned unvalidated.

- [ ] **Step 3: Wire the validator into the module**

Edit `agent/opportunity_generator.py`:

After the existing import `from agent.prompts import OPPORTUNITY_GENERATION_SYSTEM_PROMPT` (line 6), add:

```python
from agent.opportunity_validation import validate_opportunities
```

Replace the block:

```python
    if not isinstance(opportunities, list):
        raise ValueError(
            "Opportunity response must be a JSON array"
        )

    return opportunities
```

with:

```python
    if not isinstance(opportunities, list):
        raise ValueError(
            "Opportunity response must be a JSON array"
        )

    return validate_opportunities(opportunities)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./venv/bin/python -m pytest tests/test_opportunity_generator.py -q`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add agent/opportunity_generator.py tests/test_opportunity_generator.py
git commit -m "feat: validate Groq opportunities in generate_opportunities"
```

---

### Task 3: Emit meta_description from analyze_html

**Files:**
- Modify: `website_analyzer.py:375-380` (return dict of `analyze_html`)
- Test: `tests/test_website_analyzer_fields.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `website_analyzer.analyze_html(html: bytes) -> dict` — now includes both `description` and `meta_description` (same value); consumed by `agent/analyzer.py` and the live script.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_website_analyzer_fields.py`:

```python
from website_analyzer import analyze_html


HTML = b"""
<html><head>
<title>Example Domain</title>
<meta name="description" content="A nice description.">
</head><body>
<h1>Welcome</h1>
<a href="/pricing">Pricing</a>
</body></html>
"""


def test_analyze_html_emits_meta_description():
    analysis = analyze_html(HTML)
    assert analysis["description"] == "A nice description."
    assert analysis["meta_description"] == "A nice description."


def test_analyze_html_existing_fields_unchanged():
    analysis = analyze_html(HTML)
    assert analysis["title"] == "Example Domain"
    assert analysis["headings"] == ["Welcome"]
    assert analysis["links"] == [{"text": "Pricing", "href": "/pricing"}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/bin/python -m pytest tests/test_website_analyzer_fields.py -q`
Expected: FAIL — `KeyError: 'meta_description'`

- [ ] **Step 3: Implement the field**

Edit `website_analyzer.py`. In `analyze_html`, inside the returned dict (currently ending with `"links": links[:100]`), add the field after `"description"`:

```python
    return {
        "title": title,
        "description": description,
        "meta_description": description,
        "headings": headings[:50],
        "links": links[:100],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./venv/bin/python -m pytest tests/test_website_analyzer_fields.py -q`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add website_analyzer.py tests/test_website_analyzer_fields.py
git commit -m "feat: emit meta_description from analyze_html"
```

---

### Task 4: Live pipeline script + declare groq dependency

**Files:**
- Create: `scripts/live_opportunity_flow.py`
- Modify: `requirements.txt:30` (insert `groq==1.7.0` before `grpcio`)

**Interfaces:**
- Consumes: `website_analyzer.fetch_website_html(url)`, `website_analyzer.analyze_html(html)`, `agent.analyzer.analyze_observation(observation)`, `agent.opportunity_generator.generate_opportunities(business_analysis)`.
- Produces: nothing (stdout-only hallway run — no Firestore/Redis/Celery/Flask writes).

- [ ] **Step 1: Declare the groq dependency**

Edit `requirements.txt`. Insert the line `groq==1.7.0` between `googleapis-common-protos==1.75.3` and `grpcio==1.84.0` (keeps alphabetical order).

Verify: `grep -n groq requirements.txt` → `groq==1.7.0`

- [ ] **Step 2: Write the live script**

Create `scripts/live_opportunity_flow.py`:

```python
import json
import os
import sys

from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
load_dotenv()

from website_analyzer import analyze_html, fetch_website_html
from agent.analyzer import analyze_observation
from agent.opportunity_generator import generate_opportunities

SOURCE_URL = "https://example.com"


def main():
    html, final_url = fetch_website_html(SOURCE_URL)
    analysis = analyze_html(html)
    observation = {
        "source_url": SOURCE_URL,
        "final_url": final_url,
        "analysis": analysis,
    }
    print("=== OBSERVATION ===")
    print(json.dumps(observation, indent=2, ensure_ascii=False))

    business_analysis = analyze_observation(observation)
    print("=== ANALYSIS ===")
    print(json.dumps(business_analysis, indent=2, ensure_ascii=False))

    opportunities = generate_opportunities(business_analysis)
    print("=== OPPORTUNITIES ===")
    print(json.dumps(opportunities, indent=2, ensure_ascii=False))
    print(f"\n{len(opportunities)} opportunity(ies) - validator OK")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Sanity-compile the script**

Run: `./venv/bin/python -m py_compile scripts/live_opportunity_flow.py`
Expected: exit 0, no output.

- [ ] **Step 4: Run the live chain (real Groq)**

Run: `./venv/bin/python scripts/live_opportunity_flow.py`
Expected: three labeled JSON sections (`OBSERVATION`, `ANALYSIS`, `OPPORTUNITIES`), a closing `N opportunity(ies) - validator OK` line, exit 0. The `OPPORTUNITIES` section passed the strict validator on the way out.
If any traceback appears: read which stage label printed last (or none = fetch), inspect the message, fix, re-run.

- [ ] **Step 5: Commit**

```bash
git add scripts/live_opportunity_flow.py requirements.txt
git commit -m "test: add live opportunity pipeline script; declare groq"
```

---

### Task 5: Final verification and report

**Files:**
- None changed.

- [ ] **Step 1: Run the full test suite**

Run: `./venv/bin/python -m pytest -q`
Expected: all pass — 10 existing + 38 (Task 1) + 6 (Task 2) + 2 (Task 3) = **56 passed**.

- [ ] **Step 2: Confirm no secrets staged**

Run: `git status --short`
Expected: only `scripts/live_opportunity_flow.py`, `requirements.txt`, `agent/`, `tests/`, `website_analyzer.py`, `docs/` changes. No `.env`, no `ai-agent-*.json`, no `venv/`.
Verify ignores still intact: `git check-ignore .env ai-agent-86543-firebase-adminsdk-fbsvc-68c677eed5.json` → both paths printed.

- [ ] **Step 3: Confirm commit history**

Run: `git log --oneline`
Expected: the spec commit plus the four task commits on top, all on `feat/opportunity-generator-tests`.

- [ ] **Step 4: Report**

Summarize to the user: files changed and why, unit-test totals, live-chain result (observation → analysis → opportunities count + sample titles), the validation behaviors proven, and the branch/commit state. Note the live run costs one real Groq call; re-runnable via `./venv/bin/python scripts/live_opportunity_flow.py`.