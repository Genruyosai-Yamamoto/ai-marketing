# Design Specification: Telegram Notification Preferences & Reusable notify_business Service

**Date**: 2026-11-09  
**Status**: Approved  
**Scope**: Backend (`services/telegram_service.py`, `routes/telegram_routes.py`, `task.py`, `tests/test_telegram_service.py`)

---

## 1. Overview & Objectives

BLOM integrates with Telegram to send automated operational alerts (e.g., GTM analysis completion/failure, opportunity creation, action execution). Currently, `notify_business(business_id, message)` performs an unconditioned send whenever a Telegram connection exists.

This specification introduces:
1. **Granular Notification Preferences**: Configurable per-business settings stored on the Telegram connection document in Firestore.
2. **Preference-Aware Dispatching**: An enhanced `notify_business(business_id, message, event_type)` service enforcing strict event categories, checking user preferences before sending, and guaranteeing complete error isolation (never crashes callers).
3. **REST Management Endpoints**: `GET` and `PATCH` endpoints allowing authenticated business owners to inspect and update notification toggles.
4. **Comprehensive Test Coverage**: Unit and integration tests covering positive delivery, preference suppression, validation, and error resilience.

---

## 2. Event Types & Preference Schema

### 2.1 Supported Event Types
The system supports 4 strict notification categories:
* `gtm_completed`: Analysis pipeline finished, results ready.
* `gtm_failed`: Analysis pipeline encountered an error.
* `opportunity_created`: New strategic opportunity discovered.
* `action_executed`: Approved action executed against connected platform.

```python
ALLOWED_EVENT_TYPES = {
    "gtm_completed",
    "gtm_failed",
    "opportunity_created",
    "action_executed",
}

DEFAULT_PREFERENCES = {
    event_type: True for event_type in ALLOWED_EVENT_TYPES
}
```

### 2.2 Firestore Storage
Preferences are stored on the Telegram connection document:
`businesses/{business_id}/connections/telegram`

Document structure:
```json
{
  "provider": "telegram",
  "status": "connected",
  "chat_id": "123456789",
  "telegram_user_id": "987654321",
  "telegram_username": "john_doe",
  "linked_by_user_id": "user_abc",
  "created_at": "2026-11-09T14:00:00Z",
  "updated_at": "2026-11-09T14:15:00Z",
  "preferences": {
    "gtm_completed": true,
    "gtm_failed": true,
    "opportunity_created": true,
    "action_executed": true
  }
}
```

### 2.3 Defaults & Backward Compatibility
* When linking a new Telegram chat via `consume_link_token`, `preferences` is initialized with all `DEFAULT_PREFERENCES`.
* If an existing connection document lacks the `preferences` map, or lacks a specific key, it evaluates to `True`.

---

## 3. Service Layer Architecture

Located in `services/telegram_service.py`.

### 3.1 `notify_business(business_id, message, event_type) -> bool`
* **Signature**:
  ```python
  def notify_business(business_id: str, message: str, event_type: str) -> bool:
  ```
* **Strict Validation**:
  * `event_type` is required and must exist in `ALLOWED_EVENT_TYPES`. If missing or invalid, logs a warning and returns `False` immediately.
* **Connection & Preference Check**:
  1. Fetch `businesses/{business_id}/connections/telegram`.
  2. If document does not exist, or `status != "connected"`, or `chat_id` is missing, return `False`.
  3. Extract `preferences` dict. If `preferences.get(event_type, True)` is `False`, do not dispatch; return `False`.
  4. Call `send_message(chat_id, message)`.
  5. Return `True` on success.
* **Error Isolation Guarantee**:
  * The entire body is protected by a broad `try...except Exception`. Any network failure, Firestore failure, or Telegram API exception logs an error and returns `False`. The calling worker or background task is never aborted.

### 3.2 `get_telegram_preferences(business_id: str, user_id: str) -> dict`
* Validates business existence and ownership (`business["owner_id"] == user_id`).
* Validates connection existence and `status == "connected"`. If not connected, raises `ValueError("Telegram is not connected for this business")`.
* Returns merged dictionary containing all keys in `ALLOWED_EVENT_TYPES` with their boolean statuses.

### 3.3 `update_telegram_preferences(business_id: str, user_id: str, updates: dict) -> dict`
* Validates business existence and ownership.
* Validates connection existence and `status == "connected"`.
* Validates `updates`:
  * Must be a dictionary.
  * All keys must be in `ALLOWED_EVENT_TYPES`. Unrecognized keys raise `ValueError(f"Invalid preference key: {k}")`.
  * All values must be boolean (`isinstance(v, bool)`). Non-boolean values raise `ValueError(f"Preference value for {k} must be boolean")`.
* Merges updates into current preferences, writes to Firestore under `preferences` field, and updates `updated_at`.
* Returns updated dictionary of preferences.

---

## 4. REST API Layer

Located in `routes/telegram_routes.py`.

### 4.1 `GET /api/connections/telegram/preferences`
* **Query Parameters**: `business_id` (string, required)
* **Authentication**: Session cookie (`session.get("user_id")`)
* **Responses**:
  * `401 Unauthorized`: No active session
  * `400 Bad Request`: Missing `business_id` query param
  * `403 Forbidden`: User does not own the business
  * `404 Not Found`: Business not found or Telegram not connected
  * `200 OK`:
    ```json
    {
      "success": true,
      "business_id": "biz_123",
      "preferences": {
        "gtm_completed": true,
        "gtm_failed": true,
        "opportunity_created": true,
        "action_executed": true
      }
    }
    ```

### 4.2 `PATCH /api/connections/telegram/preferences`
* **Request Body**:
  ```json
  {
    "business_id": "biz_123",
    "preferences": {
      "gtm_completed": false
    }
  }
  ```
* **Authentication**: Session cookie (`session.get("user_id")`)
* **Responses**:
  * `401 Unauthorized`: No active session
  * `400 Bad Request`: Missing `business_id`, invalid payload format, unknown preference keys, or non-boolean values
  * `403 Forbidden`: User does not own the business
  * `404 Not Found`: Business not found or Telegram not connected
  * `200 OK`: Returns `{ "success": true, "business_id": ..., "preferences": { ... } }` with updated values.

---

## 5. Celery Task Updates

In `task.py`:
* Update GTM completion notification:
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
* Update GTM failure notification:
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

---

## 6. Testing & Verification Plan

Create `tests/test_telegram_service.py` with pytest fixtures mocking Firebase Firestore and Telegram bot connectors:

### 6.1 Unit Tests (`services/telegram_service.py`)
1. **`test_notify_business_success`**: When `gtm_completed` preference is `True`, `send_message` is invoked with chat ID and text, returns `True`.
2. **`test_notify_business_suppressed_by_preference`**: When `gtm_completed` preference is `False`, `send_message` is never invoked, returns `False`.
3. **`test_notify_business_default_when_preferences_missing`**: For backward compatibility, missing `preferences` map delivers messages and returns `True`.
4. **`test_notify_business_invalid_or_missing_event_type`**: Invalid/missing event type returns `False` and skips delivery without throwing.
5. **`test_notify_business_disconnected`**: Connection with `status != "connected"` returns `False`.
6. **`test_notify_business_catches_api_error`**: `send_message` raising network or API errors is caught cleanly and returns `False`.
7. **`test_get_preferences_success_and_defaults`**: Returns all 4 keys correctly merged.
8. **`test_update_preferences_validation`**: Rejects invalid key names and non-boolean values with `ValueError`.
9. **`test_update_preferences_unconnected_raises`**: Updating preferences when Telegram is not connected raises `ValueError`.

### 6.2 Route Tests (`routes/telegram_routes.py`)
1. **`test_get_preferences_auth_and_ownership`**: Verifies 401, 403, 404, and 200 responses.
2. **`test_patch_preferences_validation`**: Verifies 400 for bad payloads and 200 for valid updates.
