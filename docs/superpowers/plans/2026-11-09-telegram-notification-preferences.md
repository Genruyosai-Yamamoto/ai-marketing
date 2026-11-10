# Telegram Notification Preferences Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement granular notification preferences on Telegram connections, a reusable preference-aware `notify_business` service, and REST API management endpoints.

**Architecture:** Extend `services/telegram_service.py` with allowed event types, preference getters/updaters, and strict event checking before dispatch. Expose `GET` and `PATCH /api/connections/telegram/preferences` routes in `routes/telegram_routes.py`, and wire callers in `task.py`.

**Tech Stack:** Python 3.13, Flask, Google Cloud Firestore, pytest, requests.

## Global Constraints
- `ALLOWED_EVENT_TYPES = {"gtm_completed", "gtm_failed", "opportunity_created", "action_executed"}`
- Default for all notification categories is `True`.
- Strict category checking: `notify_business` requires an `event_type` from `ALLOWED_EVENT_TYPES`; invalid or missing types return `False`.
- Complete error isolation: `notify_business` must never raise unhandled exceptions into Celery tasks or routes.
- Ownership enforcement: User must own the business to view or update preferences.
- Per user instruction: Do not make git commits during execution unless explicitly requested.

---

### Task 1: Core Preference Constants & Service Helpers

**Files:**
- Modify: `services/telegram_service.py`
- Test: `tests/test_telegram_service.py`

**Interfaces:**
- Produces:
  - `ALLOWED_EVENT_TYPES: set[str]`
  - `DEFAULT_PREFERENCES: dict[str, bool]`
  - `get_telegram_preferences(business_id: str, user_id: str) -> dict[str, bool]`
  - `update_telegram_preferences(business_id: str, user_id: str, updates: dict) -> dict[str, bool]`

- [ ] **Step 1: Write the failing tests for preference helpers**

Create `tests/test_telegram_service.py`:
```python
import pytest
from unittest.mock import MagicMock, patch
from services.telegram_service import (
    ALLOWED_EVENT_TYPES,
    DEFAULT_PREFERENCES,
    get_telegram_preferences,
    update_telegram_preferences,
)


@pytest.fixture
def mock_db():
    with patch("services.telegram_service.db") as mock:
        yield mock


def test_allowed_event_types_constants():
    expected = {"gtm_completed", "gtm_failed", "opportunity_created", "action_executed"}
    assert ALLOWED_EVENT_TYPES == expected
    assert DEFAULT_PREFERENCES == {k: True for k in expected}


def test_get_telegram_preferences_success_merges_defaults(mock_db):
    business_doc = MagicMock()
    business_doc.exists = True
    business_doc.to_dict.return_value = {"owner_id": "user_123"}

    conn_doc = MagicMock()
    conn_doc.exists = True
    conn_doc.to_dict.return_value = {
        "provider": "telegram",
        "status": "connected",
        "preferences": {"gtm_completed": False},
    }

    mock_db.collection.return_value.document.return_value.get.return_value = business_doc
    mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = conn_doc

    prefs = get_telegram_preferences("biz_1", "user_123")
    assert prefs["gtm_completed"] is False
    assert prefs["gtm_failed"] is True
    assert prefs["opportunity_created"] is True
    assert prefs["action_executed"] is True


def test_get_telegram_preferences_not_connected_raises(mock_db):
    business_doc = MagicMock()
    business_doc.exists = True
    business_doc.to_dict.return_value = {"owner_id": "user_123"}

    conn_doc = MagicMock()
    conn_doc.exists = False

    mock_db.collection.return_value.document.return_value.get.return_value = business_doc
    mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = conn_doc

    with pytest.raises(ValueError, match="Telegram is not connected for this business"):
        get_telegram_preferences("biz_1", "user_123")


def test_update_telegram_preferences_validates_payload(mock_db):
    business_doc = MagicMock()
    business_doc.exists = True
    business_doc.to_dict.return_value = {"owner_id": "user_123"}

    conn_doc = MagicMock()
    conn_doc.exists = True
    conn_doc.to_dict.return_value = {"provider": "telegram", "status": "connected", "preferences": {}}

    mock_db.collection.return_value.document.return_value.get.return_value = business_doc
    mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = conn_doc

    # Empty payload
    with pytest.raises(ValueError, match="Preferences payload cannot be empty"):
        update_telegram_preferences("biz_1", "user_123", {})

    # Unknown key
    with pytest.raises(ValueError, match="Invalid preference key: unknown_event"):
        update_telegram_preferences("biz_1", "user_123", {"unknown_event": True})

    # Non-boolean value
    with pytest.raises(ValueError, match="Preference value for gtm_completed must be boolean"):
        update_telegram_preferences("biz_1", "user_123", {"gtm_completed": "false"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_telegram_service.py -v`  
Expected: ImportError: cannot import name 'ALLOWED_EVENT_TYPES' from 'services.telegram_service'.

- [ ] **Step 3: Implement preference helpers in `services/telegram_service.py`**

In `services/telegram_service.py`:
```python
ALLOWED_EVENT_TYPES = {
    "gtm_completed",
    "gtm_failed",
    "opportunity_created",
    "action_executed",
}

DEFAULT_PREFERENCES = {k: True for k in ALLOWED_EVENT_TYPES}


def get_telegram_preferences(business_id, user_id):
    business_ref = db.collection("businesses").document(business_id)
    business_doc = business_ref.get()
    if not business_doc.exists:
        raise ValueError("Business not found")
    if (business_doc.to_dict() or {}).get("owner_id") != user_id:
        raise PermissionError("You do not own this business")

    conn_doc = business_ref.collection("connections").document("telegram").get()
    if not conn_doc.exists:
        raise ValueError("Telegram is not connected for this business")

    data = conn_doc.to_dict() or {}
    if data.get("provider") != "telegram" or data.get("status") != "connected":
        raise ValueError("Telegram is not connected for this business")

    raw_prefs = data.get("preferences") or {}
    return {
        event_type: bool(raw_prefs.get(event_type, True))
        for event_type in ALLOWED_EVENT_TYPES
    }


def update_telegram_preferences(business_id, user_id, updates):
    if not isinstance(updates, dict) or not updates:
        raise ValueError("Preferences payload cannot be empty")

    for k, v in updates.items():
        if k not in ALLOWED_EVENT_TYPES:
            raise ValueError(f"Invalid preference key: {k}")
        if not isinstance(v, bool):
            raise ValueError(f"Preference value for {k} must be boolean")

    business_ref = db.collection("businesses").document(business_id)
    business_doc = business_ref.get()
    if not business_doc.exists:
        raise ValueError("Business not found")
    if (business_doc.to_dict() or {}).get("owner_id") != user_id:
        raise PermissionError("You do not own this business")

    conn_ref = business_ref.collection("connections").document("telegram")
    conn_doc = conn_ref.get()
    if not conn_doc.exists:
        raise ValueError("Telegram is not connected for this business")

    data = conn_doc.to_dict() or {}
    if data.get("provider") != "telegram" or data.get("status") != "connected":
        raise ValueError("Telegram is not connected for this business")

    current_prefs = data.get("preferences") or {}
    merged = {
        event_type: bool(current_prefs.get(event_type, True))
        for event_type in ALLOWED_EVENT_TYPES
    }
    merged.update(updates)

    now = _iso(_now())
    conn_ref.update({
        "preferences": merged,
        "updated_at": now,
    })

    return merged
```

Also in `consume_link_token`, initialize `"preferences": dict(DEFAULT_PREFERENCES)` in the connection document data dict.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_telegram_service.py -v`  
Expected: PASS

---

### Task 2: Refactor `notify_business` with Preference Checking & Error Isolation

**Files:**
- Modify: `services/telegram_service.py`
- Test: `tests/test_telegram_service.py`

**Interfaces:**
- Consumes:
  - `ALLOWED_EVENT_TYPES`
  - `send_message(chat_id, message)`
- Produces:
  - `notify_business(business_id: str, message: str, event_type: str) -> bool`

- [ ] **Step 1: Write failing tests for `notify_business` with event_type and preference checks**

Append to `tests/test_telegram_service.py`:
```python
from services.telegram_service import notify_business


@patch("services.telegram_service.send_message")
def test_notify_business_success_when_enabled(mock_send, mock_db):
    conn_doc = MagicMock()
    conn_doc.exists = True
    conn_doc.to_dict.return_value = {
        "provider": "telegram",
        "status": "connected",
        "chat_id": "12345",
        "preferences": {"gtm_completed": True},
    }
    mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = conn_doc

    result = notify_business("biz_1", "Analysis finished", event_type="gtm_completed")
    assert result is True
    mock_send.assert_called_once_with("12345", "Analysis finished")


@patch("services.telegram_service.send_message")
def test_notify_business_suppressed_when_disabled(mock_send, mock_db):
    conn_doc = MagicMock()
    conn_doc.exists = True
    conn_doc.to_dict.return_value = {
        "provider": "telegram",
        "status": "connected",
        "chat_id": "12345",
        "preferences": {"gtm_completed": False},
    }
    mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = conn_doc

    result = notify_business("biz_1", "Analysis finished", event_type="gtm_completed")
    assert result is False
    mock_send.assert_not_called()


@patch("services.telegram_service.send_message")
def test_notify_business_defaults_to_true_when_missing_key(mock_send, mock_db):
    conn_doc = MagicMock()
    conn_doc.exists = True
    conn_doc.to_dict.return_value = {
        "provider": "telegram",
        "status": "connected",
        "chat_id": "12345",
        # no preferences key
    }
    mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = conn_doc

    result = notify_business("biz_1", "New opportunity", event_type="opportunity_created")
    assert result is True
    mock_send.assert_called_once_with("12345", "New opportunity")


@patch("services.telegram_service.send_message")
def test_notify_business_rejects_missing_or_invalid_event_type(mock_send, mock_db):
    result1 = notify_business("biz_1", "Hello", event_type="unknown_event")
    assert result1 is False

    result2 = notify_business("biz_1", "Hello", event_type=None)
    assert result2 is False

    mock_send.assert_not_called()


@patch("services.telegram_service.send_message")
def test_notify_business_safe_on_exception(mock_send, mock_db):
    conn_doc = MagicMock()
    conn_doc.exists = True
    conn_doc.to_dict.return_value = {
        "provider": "telegram",
        "status": "connected",
        "chat_id": "12345",
    }
    mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = conn_doc
    mock_send.side_effect = RuntimeError("Telegram API timeout")

    # Must NOT raise exception
    result = notify_business("biz_1", "Hello", event_type="gtm_completed")
    assert result is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_telegram_service.py -k "test_notify_business" -v`  
Expected: FAIL (because current `notify_business` takes 2 arguments `(business_id, message)` and does not take `event_type`).

- [ ] **Step 3: Update `notify_business` in `services/telegram_service.py`**

```python
import logging

logger = logging.getLogger(__name__)


def notify_business(business_id, message, event_type):
    """
    Best-effort preference-aware notification.
    Never raises an exception into callers.
    """
    try:
        if not event_type or event_type not in ALLOWED_EVENT_TYPES:
            logger.warning(
                "Skipping Telegram notification: invalid event_type '%s'",
                event_type,
            )
            return False

        doc = (
            db.collection("businesses").document(business_id)
            .collection("connections").document("telegram").get()
        )
        if not doc.exists:
            return False

        data = doc.to_dict() or {}
        if data.get("provider") != "telegram" or data.get("status") != "connected":
            return False

        chat_id = data.get("chat_id")
        if not chat_id:
            return False

        preferences = data.get("preferences") or {}
        if not preferences.get(event_type, True):
            logger.info(
                "Skipping Telegram notification for business %s: event %s is disabled",
                business_id,
                event_type,
            )
            return False

        send_message(chat_id, message)
        return True
    except Exception as exc:
        logger.warning(
            "Telegram notification failed for business %s (event: %s): %s",
            business_id,
            event_type,
            exc,
        )
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_telegram_service.py -k "test_notify_business" -v`  
Expected: PASS

---

### Task 3: REST API Endpoints in `routes/telegram_routes.py`

**Files:**
- Modify: `routes/telegram_routes.py`
- Test: `tests/test_telegram_service.py`

**Interfaces:**
- Consumes:
  - `get_telegram_preferences`
  - `update_telegram_preferences`
- Produces:
  - `GET /api/connections/telegram/preferences`
  - `PATCH /api/connections/telegram/preferences`

- [ ] **Step 1: Write failing route tests**

Append to `tests/test_telegram_service.py`:
```python
from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@patch("routes.telegram_routes.get_telegram_preferences")
def test_route_get_preferences_unauthorized(mock_get_prefs, client):
    res = client.get("/api/connections/telegram/preferences?business_id=biz_1")
    assert res.status_code == 401
    assert res.get_json()["error"] == "Authentication required"


@patch("routes.telegram_routes.get_telegram_preferences")
def test_route_get_preferences_missing_param(mock_get_prefs, client):
    with client.session_transaction() as sess:
        sess["user_id"] = "user_1"
    res = client.get("/api/connections/telegram/preferences")
    assert res.status_code == 400
    assert res.get_json()["error"] == "Missing business_id"


@patch("routes.telegram_routes.get_telegram_preferences")
def test_route_get_preferences_success(mock_get_prefs, client):
    with client.session_transaction() as sess:
        sess["user_id"] = "user_1"
    mock_get_prefs.return_value = {
        "gtm_completed": True,
        "gtm_failed": True,
        "opportunity_created": True,
        "action_executed": True,
    }
    res = client.get("/api/connections/telegram/preferences?business_id=biz_1")
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["preferences"]["gtm_completed"] is True


@patch("routes.telegram_routes.update_telegram_preferences")
def test_route_patch_preferences_validation(mock_update_prefs, client):
    with client.session_transaction() as sess:
        sess["user_id"] = "user_1"

    # Missing business_id
    res = client.patch("/api/connections/telegram/preferences", json={"preferences": {"gtm_completed": False}})
    assert res.status_code == 400

    # Missing preferences
    res = client.patch("/api/connections/telegram/preferences", json={"business_id": "biz_1"})
    assert res.status_code == 400

    # Service rejects invalid key
    mock_update_prefs.side_effect = ValueError("Invalid preference key: bad_key")
    res = client.patch(
        "/api/connections/telegram/preferences",
        json={"business_id": "biz_1", "preferences": {"bad_key": True}},
    )
    assert res.status_code == 400
    assert "Invalid preference key" in res.get_json()["error"]


@patch("routes.telegram_routes.update_telegram_preferences")
def test_route_patch_preferences_success(mock_update_prefs, client):
    with client.session_transaction() as sess:
        sess["user_id"] = "user_1"
    mock_update_prefs.return_value = {
        "gtm_completed": False,
        "gtm_failed": True,
        "opportunity_created": True,
        "action_executed": True,
    }
    res = client.patch(
        "/api/connections/telegram/preferences",
        json={"business_id": "biz_1", "preferences": {"gtm_completed": False}},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["preferences"]["gtm_completed"] is False
```

- [ ] **Step 2: Run route tests to verify they fail**

Run: `pytest tests/test_telegram_service.py -k "test_route_" -v`  
Expected: FAIL (404 Not Found on endpoint routes).

- [ ] **Step 3: Implement endpoints in `routes/telegram_routes.py`**

Import `get_telegram_preferences` and `update_telegram_preferences` from `services.telegram_service` and add endpoints:
```python
@telegram_bp.get("/api/connections/telegram/preferences")
def telegram_get_preferences():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify(success=False, error="Authentication required"), 401

    business_id = request.args.get("business_id")
    if not business_id:
        return jsonify(success=False, error="Missing business_id"), 400

    try:
        prefs = get_telegram_preferences(business_id, user_id)
        return jsonify(
            success=True,
            business_id=business_id,
            preferences=prefs,
        ), 200
    except PermissionError:
        return jsonify(success=False, error="You do not own this business"), 403
    except ValueError as exc:
        return jsonify(success=False, error=str(exc)), 404


@telegram_bp.patch("/api/connections/telegram/preferences")
def telegram_update_preferences():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify(success=False, error="Authentication required"), 401

    payload = request.get_json(silent=True) or {}
    business_id = payload.get("business_id")
    if not business_id:
        return jsonify(success=False, error="Missing business_id"), 400

    preferences = payload.get("preferences")
    if not isinstance(preferences, dict) or not preferences:
        return jsonify(success=False, error="Missing or invalid preferences dictionary"), 400

    try:
        updated = update_telegram_preferences(business_id, user_id, preferences)
        return jsonify(
            success=True,
            business_id=business_id,
            preferences=updated,
        ), 200
    except PermissionError:
        return jsonify(success=False, error="You do not own this business"), 403
    except ValueError as exc:
        # Distinguish 404 for missing business/connection vs 400 for validation
        msg = str(exc)
        status = 404 if "not found" in msg.lower() or "not connected" in msg.lower() else 400
        return jsonify(success=False, error=msg), status
```

- [ ] **Step 4: Run route tests to verify they pass**

Run: `pytest tests/test_telegram_service.py -k "test_route_" -v`  
Expected: PASS

---

### Task 4: Update GTM Task Callers and Verification

**Files:**
- Modify: `task.py`
- Test: `tests/test_telegram_service.py`

- [ ] **Step 1: Update callers in `task.py`**

In `task.py` inside `run_gtm_analysis`:
1. Line 412:
   ```python
   notify_business(
       business_id,
       (
           "✅ BLOM GTM analysis completed!\n"
           f"Run: {run_id}\n"
           f"Opportunities created: {len(created_opp_ids)}\n"
           "Your results are available in your BLOM dashboard."
       ),
       event_type="gtm_completed",
   )
   ```
2. Line 441:
   ```python
   notify_business(
       business_id,
       (
           "⚠️ Your BLOM GTM analysis failed.\n"
           f"Run: {run_id}\n"
           "Please check your BLOM dashboard and try again."
       ),
       event_type="gtm_failed",
   )
   ```

- [ ] **Step 2: Run all telegram tests**

Run: `pytest tests/test_telegram_service.py -v`  
Expected: PASS (all tests pass)
