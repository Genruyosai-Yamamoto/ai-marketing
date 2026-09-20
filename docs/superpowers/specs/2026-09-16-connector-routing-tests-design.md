# Connector Routing Tests — Design

Date: 2026-09-16
Status: Draft (pending user review)
Scope: Automated tests for the connector routing layer and the execution flow that consumes it. Zero production code changes.

## Goal

A connector system exists but is untested: `get_connector(action)` in `connectors/__init__.py` routes an approved action to a platform connector, and `services/execution_engine.py` drives the execution record through `running` → `completed`/`failed`.

This effort pins the **current** behavior with tests:

1. `connectors/__init__.py` — `get_connector` routing decisions and error contract.
2. `connectors/instagram.py` — the only concrete connector: accepted action type, rejections, and its not-implemented result.
3. `services/execution_engine.py` — the full `execute_action(business_id, execution_id)` flow through the **real** router: completed path, routing-failure path, and pre-try safety failures.

Real connectors (registry, fallback, implementations for `website | content | seo | email | research | other`) are explicitly out of scope — the user will implement them in a later effort. Today, only `social` routes to a connector; the other six raise `ValueError`, which the tests document.

## Current Behavior (the contract under test)

`connectors/__init__.py`:

```python
def get_connector(action):
    action_type = action.get("action_type")

    if action_type == "social":
        return InstagramConnector()

    raise ValueError(
        f"No connector available for action type: {action_type}"
    )
```

- `action_type == "social"` → `InstagramConnector()`
- any other value, `None` (missing key), or `""` → `ValueError("No connector available for action type: <value>")`

`connectors/instagram.py` — `InstagramConnector(BaseConnector).execute(action)`:

- rejects `action_type != "social"` with `ValueError("Instagram connector only supports social actions")`
- otherwise returns `{"success": True, "status": "not_implemented", "message": "Instagram execution is not implemented yet"}`

`services/execution_engine.py` — `execute_action(business_id, execution_id)`:

1. Reads `businesses/{business_id}/executions/{execution_id}`; raises `ValueError("Execution not found")` if missing.
2. Reads `action_id` off the execution; raises `ValueError("Execution has no action_id")` if absent.
3. Reads `businesses/{business_id}/actions/{action_id}`; raises `ValueError("Action not found")` if missing.
4. Safety check: raises `ValueError("Action must be approved before execution")` unless `action.status == "approved"`. Steps 1–4 run **before** the try/except, so they leave the execution record untouched (stays `queued`).
5. Marks the execution `running` (`started_at`, `updated_at`).
6. Inside try/except:
   - `get_connector(action)` then `connector.execute(action)` → marks execution `completed` with `result`, `completed_at`, `updated_at`; returns `result`.
   - any exception (e.g. the unrouted-type `ValueError` from `get_connector`) → marks execution `failed` with `error`, `completed_at`, `updated_at`; re-raises.

`services/execution_engine.py` binds `from firebase import db` and `from connectors import get_connector` at module top. Importing it pulls in `firebase.py`, which requires `FIREBASE_CREDENTIALS` from `.env` (already satisfied in this repo; same requirement as `task.py` today).

## Approach

Tests-only, asserting current behavior. No registry/fallback connectors, no changes to `get_connector`, `BaseConnector`, `InstagramConnector`, or `execute_action`.

Two new test files, following the repo's file-local fake-db pattern (`test_task_pipeline.py`, `test_user_routes.py` each define their own fakes):

- `tests/test_connectors.py` — pure unit tests of `get_connector`/`InstagramConnector`; no db, no Groq.
- `tests/test_execution_engine.py` — fake-db tests of `execute_action` using the **real** `get_connector` (not stubbed), so the routing is proven end-to-end through the engine.

Modules with import-time side effects (`services.execution_engine` pulls in `firebase`) are imported inside fixtures/functions, matching `test_task_pipeline.py`'s convention.

## 1. `tests/test_connectors.py`

No fixtures beyond pytest. `import connectors` is side-effect-free (no Groq construction, unlike `agent/` modules).

Cases:

1. **Social routes to Instagram** — `get_connector({"action_type": "social"})` returns an `InstagramConnector` instance.
2. **Unrouted types raise** — parametrized over `website`, `content`, `seo`, `email`, `research`, `other`: `pytest.raises(ValueError, match="No connector available for action type")`.
3. **Missing/blank action_type raises** — `get_connector({})`, `{"action_type": None}`, `{"action_type": ""}` each raise `ValueError`.
4. **Instagram accepts social** — `InstagramConnector().execute({"action_type": "social"})` returns `success is True`, `status == "not_implemented"`, and a message.
5. **Instagram rejects non-social** — `InstagramConnector().execute({"action_type": "email"})` raises `ValueError("Instagram connector only supports social actions")`.

## 2. `tests/test_execution_engine.py`

Reuses the `FakeTaskDb` shape from `test_task_pipeline.py` (snapshot with `exists`/`to_dict()`, refs with `get()`/`update()`/`set()`/`collection()`) as a file-local copy. Seeded data:

```
businesses/b1/executions/e1  → { "action_id": "a1" }
businesses/b1/actions/a1     → { "action_type": "social", "status": "approved" }
```

`services.execution_engine` is imported inside the fixture. `monkeypatch.setattr(execution_engine, "db", fake_db)`. `get_connector` stays real.

Cases:

1. **Completed social** — `execute_action("b1", "e1")` returns the not-implemented result; the execution record goes `running` (with `started_at`/`updated_at`) then `completed` (with `result`, `completed_at`, `updated_at`).
2. **Unrouted type fails** — action seeded with `action_type: "email"`: `get_connector` raises inside the try → `pytest.raises(ValueError)`; execution record ends `failed` with `error == "No connector available for action type: email"`.
3. **Pre-try safety failures** — each raises `ValueError` and leaves the execution record **untouched** (documents current behavior until the connector work):
   - missing execution doc → `"Execution not found"`
   - action doc missing → `"Action not found"`
   - `status == "pending"` → `"Action must be approved before execution"`

## Out of Scope / Deferred

- Real connectors for `website`, `content`, `seo`, `email`, `research`, `other`; registry + fallback mechanism (Approach A from brainstorming) — user will implement later.
- Changes to `BaseConnector`, `InstagramConnector`, `get_connector`, `execute_action`, `task.py`, `routes/user.py`, or any agent module.
- Tightening the pre-try failure behavior (currently leaves the record `queued`) — intentionally not addressed; it becomes relevant in the real-connector work.

## Verification

1. `./venv/bin/python -m pytest tests/test_connectors.py tests/test_execution_engine.py -v` → all pass.
2. `./venv/bin/python -m pytest -q` → full suite stays green (76 current tests pass; this effort only adds tests).
3. `./venv/bin/python -c "import connectors; import services.execution_engine"` → imports cleanly with `.env` present.