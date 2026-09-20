# Connector Routing Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add pytest coverage that pins the current connector routing behavior in `connectors/` and its consumption by `services/execution_engine.py`, with zero production code changes.

**Architecture:** Two new test files. `tests/test_connectors.py` unit-tests `get_connector` and `InstagramConnector.execute` directly (no db, no Groq). `tests/test_execution_engine.py` drives `execute_action(business_id, execution_id)` against a file-local fake Firestore using the **real** `get_connector`, proving routing end-to-end through the engine's `completed`/`failed`/pre-try paths.

**Tech Stack:** Python 3, pytest, existing fake-db pattern (`FakeRef`/`FakeCollection` copy from `tests/test_task_pipeline.py`), `firebase.py` (import-time side effect: needs `.env` `FIREBASE_CREDENTIALS`, already satisfied in this repo).

## Global Constraints

- **Zero production code changes.** Only create the two test files listed. Do not modify `connectors/base.py`, `connectors/__init__.py`, `connectors/instagram.py`, `services/execution_engine.py`, `task.py`, `routes/user.py`, any `agent/` module, or any existing test file.
- **Uncommitted user work is off-limits.** Never stage or touch the dirty files: `task.py`, `routes/user.py`, `tests/test_user_routes.py`, `tests/test_task_pipeline.py`, `agent/`, `connectors/`, `services/`, `scripts/`, `docs/superpowers/`. Commit steps stage ONLY the new test file for that task.
- **Do not stub `get_connector`.** The execution-engine tests must use the real router.
- **Fake db is file-local.** Copy the fake classes into `tests/test_execution_engine.py`; do not import them from `test_task_pipeline.py` or refactor fakes into a shared module.
- **Import `services.execution_engine` inside fixtures, not at module top** — it pulls in `firebase.py` (`.env` requirement). `import connectors` is side-effect-free and safe anywhere.
- Run everything with `./venv/bin/python -m pytest` from the repo root (`/home/parrot/blom/backend`).

---

### Task 1: Connector routing unit tests

**Files:**
- Create: `tests/test_connectors.py`
- Test: `tests/test_connectors.py`

**Interfaces:**
- Consumes: `connectors.get_connector(action)`, `connectors.instagram.InstagramConnector().execute(action)` — both already implemented, untouched by this plan.
- Produces: `tests/test_connectors.py` — 12 tests that later tasks and the full-suite run depend on.

- [ ] **Step 1: Write the test file**

Create `tests/test_connectors.py` with this exact content:

```python
import pytest

from connectors import get_connector
from connectors.instagram import InstagramConnector


UNROUTED_TYPES = ["website", "content", "seo", "email", "research", "other"]


def test_get_connector_social_returns_instagram_connector():
    connector = get_connector({"action_type": "social"})
    assert isinstance(connector, InstagramConnector)


@pytest.mark.parametrize("action_type", UNROUTED_TYPES)
def test_get_connector_unrouted_action_type_raises(action_type):
    with pytest.raises(ValueError, match="No connector available for action type"):
        get_connector({"action_type": action_type})


@pytest.mark.parametrize(
    "action",
    [{}, {"action_type": None}, {"action_type": ""}],
)
def test_get_connector_missing_or_blank_action_type_raises(action):
    with pytest.raises(ValueError, match="No connector available for action type"):
        get_connector(action)


def test_instagram_connector_accepts_social_action():
    result = InstagramConnector().execute({"action_type": "social"})
    assert result["success"] is True
    assert result["status"] == "not_implemented"
    assert result["message"]


def test_instagram_connector_rejects_non_social_action():
    with pytest.raises(ValueError, match="only supports social actions"):
        InstagramConnector().execute({"action_type": "email"})
```

- [ ] **Step 2: Run the tests**

Run: `./venv/bin/python -m pytest tests/test_connectors.py -v`
Expected: 12 passed (pytest reports `12 passed`; parametrized cases count individually).

- [ ] **Step 3: Sanity-check the tests actually assert the contract**

Temporarily assert a wrong contract and confirm the tests catch it, then restore:

```bash
# one-liner: prove test_get_connector_social_returns_instagram_connector fails if documented contract is wrong
./venv/bin/python -c "import connectors; assert connectors.get_connector({'action_type': 'social'}).__class__.__name__ == 'InstagramConnector'; print('contract check ok')"
```

Run: `./venv/bin/python -m pytest tests/test_connectors.py -q`
Expected: 12 passed.

- [ ] **Step 4: Commit the new test file only**

```bash
git add tests/test_connectors.py
git commit -m "test: pin connector routing and InstagramConnector contract"
```

---

### Task 2: Execution engine flow tests through the real router

**Files:**
- Create: `tests/test_execution_engine.py`
- Test: `tests/test_execution_engine.py`

**Interfaces:**
- Consumes: `services.execution_engine.db` (module global patched in fixture), `services.execution_engine.execute_action(business_id, execution_id)` (real `get_connector` inside, not stubbed). Uses Task 1's written contract only indirectly (the real router is exercised by both files).
- Produces: `tests/test_execution_engine.py` — 5 tests exercising `execute_action`'s `completed`, `failed`, and pre-try-raise paths against the real router.

- [ ] **Step 1: Write the test file**

Create `tests/test_execution_engine.py` with this exact content:

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


@pytest.fixture
def execution_env(monkeypatch):
    import services.execution_engine as execution_engine

    db = FakeTaskDb()
    monkeypatch.setattr(execution_engine, "db", db)
    return execution_engine, db


def test_execute_action_completed_social(execution_env):
    execution_engine, db = execution_env
    biz_ref = db.collection("businesses").document("b1")
    biz_ref.collection("executions").document("e1").set({"action_id": "a1"})
    biz_ref.collection("actions").document("a1").set(
        {"action_type": "social", "status": "approved"}
    )

    result = execution_engine.execute_action("b1", "e1")

    assert result["success"] is True
    assert result["status"] == "not_implemented"

    execution_ref = biz_ref.collection("executions").document("e1")
    assert execution_ref.data["status"] == "completed"
    assert execution_ref.data["result"] == result
    assert execution_ref.data["started_at"]
    assert execution_ref.data["completed_at"]
    assert execution_ref.data["updated_at"]


def test_execute_action_unrouted_type_marks_failed(execution_env):
    execution_engine, db = execution_env
    biz_ref = db.collection("businesses").document("b1")
    biz_ref.collection("executions").document("e1").set({"action_id": "a1"})
    biz_ref.collection("actions").document("a1").set(
        {"action_type": "email", "status": "approved"}
    )

    with pytest.raises(
        ValueError, match="No connector available for action type: email"
    ):
        execution_engine.execute_action("b1", "e1")

    execution_ref = biz_ref.collection("executions").document("e1")
    assert execution_ref.data["status"] == "failed"
    assert (
        execution_ref.data["error"]
        == "No connector available for action type: email"
    )
    assert execution_ref.data["completed_at"]


def test_execute_action_missing_execution_raises(execution_env):
    execution_engine, _ = execution_env

    with pytest.raises(ValueError, match="Execution not found"):
        execution_engine.execute_action("b1", "missing")


def test_execute_action_missing_action_raises(execution_env):
    execution_engine, db = execution_env
    biz_ref = db.collection("businesses").document("b1")
    biz_ref.collection("executions").document("e1").set({"action_id": "nope"})

    with pytest.raises(ValueError, match="Action not found"):
        execution_engine.execute_action("b1", "e1")


def test_execute_action_unapproved_action_raises(execution_env):
    execution_engine, db = execution_env
    biz_ref = db.collection("businesses").document("b1")
    biz_ref.collection("executions").document("e1").set({"action_id": "a1"})
    biz_ref.collection("actions").document("a1").set(
        {"action_type": "social", "status": "pending"}
    )

    with pytest.raises(ValueError, match="Action must be approved before execution"):
        execution_engine.execute_action("b1", "e1")
```

- [ ] **Step 2: Run the tests**

Run: `./venv/bin/python -m pytest tests/test_execution_engine.py -v`
Expected: 5 passed.

- [ ] **Step 3: Run both new files together**

Run: `./venv/bin/python -m pytest tests/test_connectors.py tests/test_execution_engine.py -v`
Expected: 17 passed.

- [ ] **Step 4: Commit the new test file only**

```bash
git add tests/test_execution_engine.py
git commit -m "test: pin execute_action routing flow through the real router"
```

---

### Task 3: Full-suite regression check

**Files:**
- None (verification only; triggers no edits).

**Interfaces:**
- Consumes: the two test files from Tasks 1–2 plus the existing suite (currently 76 tests).

- [ ] **Step 1: Run the full suite**

Run: `./venv/bin/python -m pytest -q`
Expected: `93 passed` (76 existing + 17 new). No failures, no errors.

- [ ] **Step 2: Confirm nothing outside the test files changed**

Run: `git status --short`
Expected: `tests/test_connectors.py` and `tests/test_execution_engine.py` now tracked (and staged/committed by Tasks 1–2); the pre-existing dirty files (`task.py`, `routes/user.py`, `tests/test_user_routes.py`, `tests/test_task_pipeline.py`, `agent/`, `connectors/`, `services/`, `scripts/`, unstaged `docs/superpowers/plans/`) remain untouched and unstaged.