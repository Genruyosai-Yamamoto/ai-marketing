# Implementation Plan: Opportunity Pipeline Wiring

## Goal

Wire the opportunity-generator agent modules (`agent/analyzer.py`, `agent/opportunity_generator.py`) into the Celery task `tasks.analyze_business_website` so website analysis produces business understanding and validated opportunities persisted to Firestore; add a `runs/latest` endpoint; fix the dead (app-import-breaking) route; and test every stage.

Approved design: `docs/superpowers/specs/2026-09-16-opportunity-pipeline-wiring-design.md` (commit `035cfa7`).

## Architecture / Tech Stack

- Celery task (`task.py`, existing `analyze_business_website`) → sequential pipeline: `fetch_website_html` → `analyze_html` → save observation → `agent.analyzer.analyze_observation` (Groq) → `agent.opportunity_generator.generate_opportunities` (Groq) → save one Firestore doc per opportunity → single terminal `completed` update.
- Firestore storage: `businesses/{business_id}/opportunities/{opp_id}` docs + `opportunity_ids` on the run record.
- Flask + Blueprint routes in `routes/user.py`.
- pytest with an in-repo fake-db pattern (matching `tests/test_user_routes.py`).
- Python: `./venv/bin/python`; run tests from repo root.

## Global Constraints

1. **Do not** commit the user's concurrent uncommitted work: `agent/prompts.py`, `scripts/live_opportunity_flow.py`, `agent/decision_engine.py`, `connectors/`, `services/`.
2. `task.py` and `routes/user.py` are **shared** with concurrent user work:
   - `task.py` working tree already contains the user's `execute_approved_action` task (lines 6, 14–26) — untouched by this plan; do not modify or remove it.
   - `git add` of these files stages the user's lines too. Before the Task 1 / Task 3 commits, retag `git status`/`git diff` of `task.py` and `routes/user.py` and get explicit user sign-off that the shared files may be committed (or the user lands their work first, or the implementer stages hunks with `git add -p` — never silently sweep the user's in-flight code into a commit).
3. Current working tree is **broken at import**: `routes/user.py:478` uses the undefined `business_bp` (`NameError`), so `import app` fails and no route tests can run. Task 3 fixes this before adding any new route code.
4. The committed spec says the dead route is at line 421; reality check (verified 2026-09-16): `get_opportunity` at line 421 is already correctly registered with `@user_bp.route`. The single dead route in the current tree is `approve_action` at line 478 (`@business_bp.route`). Task 3 delivers the same design outcome (routes reachable, module importable) by fixing line 478; Task 3's test 6 still proves the opportunities-detail route is registered.
5. Lazy imports (`from agent.analyzer import analyze_observation`, `from agent.opportunity_generator import generate_opportunities`) stay **inside** the task function — never at `task.py` module top (those modules build a `Groq()` client at import time).
6. Never `git add` `.env`, `ai-agent-*.json`, `venv/`, `dump.rdb`, `.superpowers/`.
7. All changes go through the TDD cycle in their task. Each task ends green before the next starts.

## File Structure

- `task.py` — modify `analyze_business_website` (stages 4–7, terminal completed update, return `opportunity_ids`). No new files.
- `routes/user.py` — fix `approve_action` decorator at line 478; add `GET /api/business/<business_id>/runs/latest`.
- `tests/test_task_pipeline.py` — NEW. Fake-db + monkeypatched stages → the task pipeline.
- `tests/test_user_routes.py` — extend boot assertions + add seeded fake-db route tests.

---

## Task 1: Wire pipeline in `task.py` (happy path)

**Step 1 (TDD — red).** New file `tests/test_task_pipeline.py`:

```python
import pytest


class _Snapshot:
    def __init__(self, data):
        self.exists = data is not None
        self._data = dict(data) if data else {}

    def to_dict(self):
        return dict(self._data)


class _Ref:
    _auto = 0

    def __init__(self, path, data=None):
        self.path = list(path)
        self.id = self.path[-1]
        self._set_data = dict(data) if data else None
        self.updates = []
        self.children = {}

    def get(self):
        return _Snapshot(self._set_data)

    @property
    def data(self):
        state = dict(self._set_data or {})
        for update in self.updates:
            state.update(update)
        return state

    def set(self, data):
        self._set_data = dict(data)

    def update(self, data):
        self.updates.append(dict(data))

    def collection(self, name):
        if name not in self.children:
            self.children[name] = _Collection(self.path + [name])
        return self.children[name]


def _new_id():
    _Ref._auto += 1
    return f"doc{_Ref._auto}"


class _Collection:
    def __init__(self, path):
        self.path = list(path)
        self.docs = {}

    def document(self, doc_id=None):
        if doc_id is None:
            doc_id = _new_id()
        if doc_id not in self.docs:
            self.docs[doc_id] = _Ref(self.path + [doc_id])
        return self.docs[doc_id]


class FakeTaskDb:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        if name not in self.collections:
            self.collections[name] = _Collection([name])
        return self.collections[name]


VALID_OPPORTUNITY = {
    "title": "Add SEO",
    "description": "Desc",
    "problem": "Problem",
    "evidence": ["e1"],
    "potential_impact": "high",
    "confidence": 0.9,
    "type": "seo",
}


@pytest.fixture
def agent_modules(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    import agent.analyzer as analyzer_mod
    import agent.opportunity_generator as generator_mod
    return analyzer_mod, generator_mod


@pytest.fixture
def task_env(monkeypatch, agent_modules):
    import task as task_mod
    import website_analyzer as wa

    db = FakeTaskDb()
    biz_ref = db.collection("businesses").document("b1")
    biz_ref.set({"owner_id": "u1", "name": "Acme", "website_url": "https://acme.example"})
    biz_ref.collection("agent_runs").document("r1").set(
        {"business_id": "b1", "owner_id": "u1", "type": "website_analysis", "status": "queued"}
    )

    analyzer_mod, generator_mod = agent_modules
    monkeypatch.setattr(task_mod, "db", db)
    monkeypatch.setattr(
        wa, "fetch_website_html", lambda url: ("<html><title>Acme</title></html>", url)
    )
    monkeypatch.setattr(
        wa, "analyze_html",
        lambda html: {"title": "Acme", "headings": [], "links": [], "meta_description": "Acme"},
    )
    monkeypatch.setattr(
        analyzer_mod, "analyze_observation",
        lambda observation: {"business_summary": "Acme sells widgets."},
    )
    monkeypatch.setattr(generator_mod, "generate_opportunities", lambda analysis: [])
    return task_mod, db


def test_happy_path_persists_opportunities_and_completes_run(task_env, monkeypatch):
    task_mod, db = task_env
    import agent.opportunity_generator as generator_mod

    monkeypatch.setattr(generator_mod, "generate_opportunities", lambda analysis: [
        dict(VALID_OPPORTUNITY),
        dict(VALID_OPPORTUNITY, title="Use Instagram", type="social", confidence=0.4),
    ])

    result = task_mod.analyze_business_website.run("b1", "u1", "r1")

    biz_ref = db.collection("businesses").document("b1")
    run_ref = biz_ref.collection("agent_runs").document("r1")

    assert result["success"] is True
    assert result["run_id"] == "r1"
    assert len(result["opportunity_ids"]) == 2

    # observation saved before Groq stages
    obs_docs = list(biz_ref.collection("observations").docs.values())
    assert len(obs_docs) == 1
    assert obs_docs[0].data["analysis"]["title"] == "Acme"

    # single terminal completed transition, opportunity_ids in generator order
    completed = [u for u in run_ref.updates if u.get("status") == "completed"]
    assert completed == [run_ref.updates[-1]]
    assert run_ref.data["status"] == "completed"
    assert run_ref.data["observation_id"] == result["observation_id"]
    assert run_ref.data["opportunity_ids"] == result["opportunity_ids"]

    # one Firestore doc per opportunity with the validator keys + metadata
    opp_docs = sorted(
        biz_ref.collection("opportunities").docs.values(),
        key=lambda ref: ref.data["position"],
    )
    assert [ref.id for ref in opp_docs] == result["opportunity_ids"]
    first = opp_docs[0].data
    assert first["title"] == "Add SEO"
    assert first["business_id"] == "b1"
    assert first["owner_id"] == "u1"
    assert first["position"] == 0
    assert opp_docs[1].data["position"] == 1
    assert first["created_at"]
    for key in ("title", "description", "problem", "evidence",
                "potential_impact", "confidence", "type"):
        assert key in first
```

Run `./venv/bin/python -m pytest tests/test_task_pipeline.py -v` → the happy-path test fails (task still ends `completed` after observation only, returns no `opportunity_ids`).

**Step 2 (green).** Modify `task.py`, replacing the post-observation block (current lines 102–115: `# Mark run as completed` ... the `return {...}`) with:

```python
        # Step 4-7: business understanding + opportunities.
        # Lazy imports avoid constructing a Groq() client when task.py loads.
        from agent.analyzer import analyze_observation
        from agent.opportunity_generator import generate_opportunities

        try:
            analysis = analyze_observation(observation)

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

            # Single terminal completed transition
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

        return {
            "success": True,
            "observation_id": observation_ref.id,
            "opportunity_ids": opportunity_ids,
            "run_id": run_id,
        }
```

Leave the outer `try/except` untouched (its `failed` handler re-marks the run after the inner re-raise — idempotent, keep simple). Keep the user's `execute_approved_action` task and its import untouched.

**Step 3 (verify).** Re-run; suite + tasks: 1 test green. Do not commit yet (see Task 2).

---

## Task 2: Pipeline edge paths (tests only)

Append to `tests/test_task_pipeline.py`. No production code changes. All must pass against the Task 1 implementation.

**Step 1 — observation Groq failure** (observation persists, run → `failed`, no opportunity docs):

```python
def test_observation_groq_failure_marks_run_failed(task_env, monkeypatch):
    task_mod, db = task_env
    import agent.analyzer as analyzer_mod

    monkeypatch.setattr(
        analyzer_mod, "analyze_observation",
        lambda observation: (_ for _ in ()).throw(RuntimeError("groq down")),
    )

    with pytest.raises(RuntimeError, match="groq down"):
        task_mod.analyze_business_website.run("b1", "u1", "r1")

    biz_ref = db.collection("businesses").document("b1")
    run_ref = biz_ref.collection("agent_runs").document("r1")
    assert run_ref.data["status"] == "failed"
    assert run_ref.data["error"] == "groq down"
    assert len(biz_ref.collection("observations").docs) == 1
    assert not biz_ref.collection("opportunities").docs
```

**Step 2 — opportunity Groq failure** (`ValueError` from the generator/validator):

```python
def test_opportunity_groq_failure_marks_run_failed(task_env, monkeypatch):
    task_mod, db = task_env
    import agent.opportunity_generator as generator_mod

    monkeypatch.setattr(
        generator_mod, "generate_opportunities",
        lambda analysis: (_ for _ in ()).throw(ValueError("bad JSON")),
    )

    with pytest.raises(ValueError, match="bad JSON"):
        task_mod.analyze_business_website.run("b1", "u1", "r1")

    biz_ref = db.collection("businesses").document("b1")
    run_ref = biz_ref.collection("agent_runs").document("r1")
    assert run_ref.data["status"] == "failed"
    assert run_ref.data["error"] == "bad JSON"
    assert len(biz_ref.collection("observations").docs) == 1
    assert not biz_ref.collection("opportunities").docs
```

**Step 3 — invalid opportunity data** (same path as 2; validator rejects one item — simulated by the generator raising `ValueError`):

```python
def test_invalid_opportunity_data_marks_run_failed(task_env, monkeypatch):
    task_mod, db = task_env
    import agent.opportunity_generator as generator_mod

    broken = dict(VALID_OPPORTUNITY, confidence=2)

    def generate(analysis):
        from agent.opportunity_validation import validate_opportunities
        return validate_opportunities([broken], allow_empty=False)

    monkeypatch.setattr(generator_mod, "generate_opportunities", generate)

    with pytest.raises(ValueError, match="out of range"):
        task_mod.analyze_business_website.run("b1", "u1", "r1")

    biz_ref = db.collection("businesses").document("b1")
    run_ref = biz_ref.collection("agent_runs").document("r1")
    assert run_ref.data["status"] == "failed"
    assert len(biz_ref.collection("observations").docs) == 1
    assert not biz_ref.collection("opportunities").docs
```

> Check `agent/opportunity_validation.validate_opportunities`'s real signature before Step 3 — if it differs (e.g. no `allow_empty` param), call it with only the list argument and match on whatever message it raises for `confidence=2`. Alternatively keep Step 3 as a `ValueError("confidence 2 out of range")` raise identical to Step 2 per the spec's case 5; the plan marks it as generator/validator failure either way.

**Step 4 — empty opportunities** (valid `[]` → run `completed`, no docs):

```python
def test_empty_opportunities_completes_run_with_no_docs(task_env):
    task_mod, db = task_env

    result = task_mod.analyze_business_website.run("b1", "u1", "r1")

    biz_ref = db.collection("businesses").document("b1")
    run_ref = biz_ref.collection("agent_runs").document("r1")
    assert result["opportunity_ids"] == []
    assert run_ref.data["status"] == "completed"
    assert run_ref.data["opportunity_ids"] == []
    assert not biz_ref.collection("opportunities").docs
```

**Step 5 (verify).** `./venv/bin/python -m pytest tests/test_task_pipeline.py -v` → 5 tests green. Commit plan-scoped task changes under the shared-file constraint (Global Constraint 2).

---

## Task 3: Route fix + `runs/latest` endpoint

**Step 1 (TDD — red).** Extend `tests/test_user_routes.py`.

Add boot-rule assertions (extend `test_app_boots_and_blueprints_register`):

```python
    assert "/api/business/<business_id>/opportunities/<opportunity_id>" in rules
    assert "/api/business/<business_id>/runs/latest" in rules
```

Add a seeded read-only fake (supports `ref.get()`, `ref.collection()`, `document().get()`, `collection().stream()`) used only by the new tests (existing `FakeDb`/`FakeRef` stays untouched for the old analyze test):

```python
class SeedSnapshot:
    def __init__(self, data, doc_id):
        self.exists = data is not None
        self._data = dict(data) if data else {}
        self.id = doc_id

    def to_dict(self):
        return dict(self._data)


class SeedCollection:
    def __init__(self, db, path):
        self._db = db
        self.path = path

    def document(self, doc_id):
        return SeedRef(self._db, self.path + [doc_id])

    def stream(self):
        prefix = tuple(self.path)
        return [
            SeedSnapshot(data, path[-1])
            for path, data in self._db._seed.items()
            if len(path) == len(prefix) + 1 and path[: len(prefix)] == prefix
        ]


class SeedRef:
    def __init__(self, db, path):
        self._db = db
        self.path = path

    @property
    def id(self):
        return self.path[-1]

    def get(self):
        return SeedSnapshot(self._db._seed.get(tuple(self.path)), self.id)

    def collection(self, name):
        return SeedCollection(self._db, self.path + [name])


class SeedFakeDb:
    def __init__(self, seed):
        self._seed = {tuple(k): v for k, v in seed.items()}

    def collection(self, name):
        return SeedCollection(self, [name])
```

Add a seeded session fixture and the route tests:

```python
@pytest.fixture
def seeded(client, monkeypatch):
    import routes.user as routes_user

    seed = {
        ("businesses", "b1"): {
            "owner_id": "u1", "name": "A", "website_url": "https://a.example",
        },
        ("businesses", "b1", "opportunities", "opp1"): {
            "owner_id": "u1", "title": "Add SEO", "description": "d", "problem": "p",
            "evidence": ["e"], "potential_impact": "high", "confidence": 0.9,
            "type": "seo", "position": 0,
        },
        ("businesses", "b1", "agent_runs", "r1"): {
            "business_id": "b1", "owner_id": "u1", "type": "website_analysis",
            "status": "completed", "observation_id": "obs1",
            "opportunity_ids": ["opp1"],
            "created_at": "2026-09-16T00:00:00",
            "completed_at": "2026-09-16T00:00:01",
        },
        ("businesses", "b1", "agent_runs", "r2"): {
            "business_id": "b1", "owner_id": "u1", "type": "website_analysis",
            "status": "running",
            "created_at": "2026-09-16T01:00:00",
        },
    }
    monkeypatch.setattr(routes_user, "db", SeedFakeDb(seed))
    with client.session_transaction() as sess:
        sess["user_id"] = "u1"
    return routes_user


def test_get_opportunity_returns_200_for_owner(client, seeded):
    resp = client.get("/api/business/b1/opportunities/opp1")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["opportunity"]["id"] == "opp1"
    assert body["opportunity"]["title"] == "Add SEO"


def test_get_opportunity_403_for_non_owner(client, seeded, monkeypatch):
    import routes.user as routes_user
    seed = {
        ("businesses", "b2"): {"owner_id": "u2", "name": "B", "website_url": "https://b.example"},
        ("businesses", "b2", "opportunities", "opp1"): {"owner_id": "u2", "title": "T"},
    }
    monkeypatch.setattr(routes_user, "db", SeedFakeDb(seed))
    with client.session_transaction() as sess:
        sess["user_id"] = "u1"
    resp = client.get("/api/business/b2/opportunities/opp1")
    assert resp.status_code == 403


def test_get_latest_run_returns_most_recent(client, seeded):
    resp = client.get("/api/business/b1/runs/latest")
    assert resp.status_code == 200
    run = resp.get_json()["run"]
    assert run["run_id"] == "r2"
    assert run["status"] == "running"
    assert run["observation_id"] is None
    assert run["opportunity_ids"] is None


def test_get_latest_run_none_when_no_runs(client, seeded, monkeypatch):
    import routes.user as routes_user
    seed = {
        ("businesses", "b1"): {"owner_id": "u1", "name": "A", "website_url": "https://a.example"},
    }
    monkeypatch.setattr(routes_user, "db", SeedFakeDb(seed))
    with client.session_transaction() as sess:
        sess["user_id"] = "u1"
    resp = client.get("/api/business/b1/runs/latest")
    assert resp.status_code == 200
    assert resp.get_json()["run"] is None


def test_get_latest_run_404_missing_business(client, seeded):
    resp = client.get("/api/business/nope/runs/latest")
    assert resp.status_code == 404


def test_get_latest_run_403_non_owner(client, seeded, monkeypatch):
    import routes.user as routes_user
    seed = {
        ("businesses", "b2"): {"owner_id": "u2", "name": "B", "website_url": "https://b.example"},
    }
    monkeypatch.setattr(routes_user, "db", SeedFakeDb(seed))
    with client.session_transaction() as sess:
        sess["user_id"] = "u1"
    resp = client.get("/api/business/b2/runs/latest")
    assert resp.status_code == 403


def test_get_latest_run_401_without_session(client, seeded):
    with client.session_transaction() as sess:
        sess.clear()
    resp = client.get("/api/business/b1/runs/latest")
    assert resp.status_code == 401


def test_get_latest_run_returns_full_run_from_completed(client, seeded, monkeypatch):
    import routes.user as routes_user
    seed = {
        ("businesses", "b1"): {"owner_id": "u1", "name": "A", "website_url": "https://a.example"},
        ("businesses", "b1", "agent_runs", "r1"): {
            "business_id": "b1", "owner_id": "u1", "type": "website_analysis",
            "status": "completed", "observation_id": "obs1", "opportunity_ids": ["opp1"],
            "created_at": "2026-09-16T00:00:00", "completed_at": "2026-09-16T00:00:01",
        },
    }
    monkeypatch.setattr(routes_user, "db", SeedFakeDb(seed))
    with client.session_transaction() as sess:
        sess["user_id"] = "u1"
    resp = client.get("/api/business/b1/runs/latest")
    run = resp.get_json()["run"]
    assert run == {
        "run_id": "r1", "status": "completed", "observation_id": "obs1",
        "opportunity_ids": ["opp1"], "error": None,
        "created_at": "2026-09-16T00:00:00", "completed_at": "2026-09-16T00:00:01",
    }
```

Run `./venv/bin/python -m pytest tests/test_user_routes.py -v` → red (module import `NameError: business_bp` at line 478, and the two new rule assertions fail).

**Step 2 (green — dead route fix).** In `routes/user.py:478` change:

```python
@business_bp.route(
```

to:

```python
@user_bp.route(
```

(keep the rest of the `approve_action` decorator and body byte-for-byte as the user wrote them — only the blueprint name changes). This restores `import app` and registers the action route.

**Step 3 (green — new endpoint).** Insert after the `get_opportunity` function (after the `}), 200` ending it, ~line 477) and before the `approve_action` decorator:

```python
@user_bp.route("/api/business/<business_id>/runs/latest", methods=["GET"])
def get_latest_run(business_id):
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({
            "success": False,
            "error": "Authentication required"
        }), 401

    business_ref = db.collection("businesses").document(business_id)
    business_doc = business_ref.get()

    if not business_doc.exists:
        return jsonify({
            "success": False,
            "error": "Business not found"
        }), 404

    business = business_doc.to_dict()

    if business.get("owner_id") != user_id:
        return jsonify({
            "success": False,
            "error": "You do not have permission to view this business"
        }), 403

    runs = list(business_ref.collection("agent_runs").stream())

    if not runs:
        return jsonify({
            "success": True,
            "business_id": business_id,
            "run": None,
        }), 200

    latest = max(runs, key=lambda run: run.to_dict().get("created_at", ""))
    latest_data = latest.to_dict()

    return jsonify({
        "success": True,
        "business_id": business_id,
        "run": {
            "run_id": latest.id,
            "status": latest_data.get("status"),
            "observation_id": latest_data.get("observation_id"),
            "opportunity_ids": latest_data.get("opportunity_ids"),
            "error": latest_data.get("error"),
            "created_at": latest_data.get("created_at"),
            "completed_at": latest_data.get("completed_at"),
        },
    }), 200
```

No Firestore `where`/`order_by` (no composite indexes per spec §Out of Scope) — "latest" = max over `created_at` in the parent-document subcollection.

**Step 4 (verify).** `./venv/bin/python -m pytest tests/test_user_routes.py -v` → 8 old + 9 new tests green (incl. boot rules). Commit with shared-file sign-off (Global Constraint 2).

---

## Test Plan & Verification

| Check | Command | Expected |
|---|---|---|
| Task 1 red | `./venv/bin/python -m pytest tests/test_task_pipeline.py -v` | happy-path test fails on `opportunity_ids` |
| Task 1 green | same | 1 pass |
| Task 2 green | same | 5 passes |
| Task 3 red | `./venv/bin/python -m pytest tests/test_user_routes.py -v` | import NameError + rule assertions fail |
| Task 3 green | same | all pass |
| Module imports | `./venv/bin/python -c "import app"` | no NameError |
| Full suite | `./venv/bin/python -m pytest -q` | all green (baseline 63 passed; now ≥ 73 + new) |

## Coverage Target

100% statement coverage of every new/modified executable line:

- `task.py` pipeline stages 4–7: happy (2 opportunities), observation failure, opportunity failure, invalid data, empty `[]`, + pre-existing business-not-found / unauthorized / no-url paths (unchanged, already covered by prior behavior). Every branch of the new try/except and loop is exercised by the 5 `test_task_pipeline.py` tests.
- `routes/user.py` `get_latest_run`: 200 running, 200 completed (full payload), 200 null, 401, 403, 404 → every branch hit by the 7 endpoint tests.
- `routes/user.py` `approve_action` registerability: boot test asserts its rule if equivalence holds — if the rule appears as `/api/business/<business_id>/actions/<action_id>/approve`, add it to the boot assertions.

## Definition of Done

1. Pipeline produces and persists opportunities; run ends `completed` once with `observation_id` + `opportunity_ids`.
2. `import app` succeeds; opportunities detail route registered; `runs/latest` meets the spec response shape.
3. All new tests green, full suite green.
4. No user concurrent files committed without explicit sign-off.