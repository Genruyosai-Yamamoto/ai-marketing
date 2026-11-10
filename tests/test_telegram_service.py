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



def test_task_py_passes_event_types_on_gtm_analysis():
    from task import run_gtm_analysis

    business_doc = MagicMock()
    business_doc.exists = True
    business_doc.to_dict.return_value = {
        "website_url": "https://example.com",
        "name": "Acme",
    }
    mock_run_ref = MagicMock()

    mock_db = MagicMock()
    def doc_lookup(doc_id):
        mock_doc = MagicMock()
        if doc_id == "biz_1":
            mock_doc.get.return_value = business_doc
            mock_doc.collection.return_value.document.return_value = mock_run_ref
        return mock_doc

    mock_db.collection.return_value.document.side_effect = doc_lookup

    with patch("task.db", mock_db), \
         patch("services.telegram_service.notify_business") as mock_notify, \
         patch("services.pixelrag_service.render_and_tile_page", return_value={"tiles": []}), \
         patch("services.gtm_discovery_service.discover_competitors", return_value=[]), \
         patch("services.gtm_discovery_service.get_gtm_seed_queries", return_value=[]), \
         patch("agent.gtm_engine.analyze_gtm_tiles", return_value={"gtm_scores": {"overall": 80}, "opportunities": [{"title": "opp"}]}), \
         patch("services.opportunity_service.create_opportunity", return_value={"id": "opp_1"}), \
         patch("services.gtm_dossier_service.generate_gtm_dossier_markdown", return_value="# Dossier"), \
         patch("services.gtm_dossier_service.save_dossier_to_file", return_value="/tmp/dossier.md"):

        # Success case
        run_gtm_analysis("biz_1", "user_1", "run_123")
        mock_notify.assert_called_with(
            "biz_1",
            (
                "✅ BLOM GTM analysis completed!\n"
                "Run: run_123\n"
                "Opportunities created: 1\n"
                "Your results are available in your BLOM dashboard."
            ),
            event_type="gtm_completed",
        )

        # Failure case
        with patch("agent.gtm_engine.analyze_gtm_tiles", side_effect=RuntimeError("Engine failure")):
            with pytest.raises(RuntimeError):
                run_gtm_analysis("biz_1", "user_1", "run_456")

        mock_notify.assert_called_with(
            "biz_1",
            (
                "⚠️ Your BLOM GTM analysis failed.\n"
                "Run: run_456\n"
                "Please check your BLOM dashboard and try again."
            ),
            event_type="gtm_failed",
        )
