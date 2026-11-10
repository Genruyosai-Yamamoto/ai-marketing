import hmac
import os

from flask import Blueprint, current_app, jsonify, request, session

from connectors.telegram_bot import get_me, set_webhook
from services.telegram_service import (
    create_link_token,
    consume_link_token,
    get_telegram_connection,
    disconnect_telegram,
    get_telegram_preferences,
    update_telegram_preferences,
)

telegram_bp = Blueprint("telegram_bp", __name__)


@telegram_bp.post("/api/connections/telegram/link")
def telegram_create_link():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify(success=False, error="Authentication required"), 401
    payload = request.get_json(silent=True) or {}
    business_id = payload.get("business_id")
    if not business_id:
        return jsonify(success=False, error="Missing business_id"), 400
    try:
        result = create_link_token(business_id, user_id)
        return jsonify(success=True, **result), 200
    except PermissionError:
        return jsonify(success=False, error="You do not own this business"), 403
    except ValueError as exc:
        return jsonify(success=False, error=str(exc)), 404
    except RuntimeError as exc:
        current_app.logger.warning("Telegram linking is not configured: %s", exc)
        return jsonify(success=False, error="Telegram bot is not fully configured"), 503


@telegram_bp.get("/api/connections/telegram/status")
def telegram_status():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify(success=False, error="Authentication required"), 401
    business_id = request.args.get("business_id")
    if not business_id:
        return jsonify(success=False, error="Missing business_id"), 400
    try:
        connection = get_telegram_connection(business_id, user_id)
        if not connection:
            return jsonify(success=True, connected=False), 200
        return jsonify(
            success=True,
            connected=True,
            telegram_username=connection.get("telegram_username"),
            linked_at=connection.get("created_at"),
        ), 200
    except PermissionError:
        return jsonify(success=False, error="You do not own this business"), 403
    except ValueError as exc:
        return jsonify(success=False, error=str(exc)), 404


@telegram_bp.post("/api/connections/telegram/disconnect")
def telegram_disconnect():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify(success=False, error="Authentication required"), 401
    payload = request.get_json(silent=True) or {}
    business_id = payload.get("business_id")
    if not business_id:
        return jsonify(success=False, error="Missing business_id"), 400
    try:
        disconnect_telegram(business_id, user_id)
        return jsonify(success=True, connected=False), 200
    except PermissionError:
        return jsonify(success=False, error="You do not own this business"), 403
    except ValueError as exc:
        return jsonify(success=False, error=str(exc)), 404


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
        msg = str(exc)
        status = 404 if "not found" in msg.lower() or "not connected" in msg.lower() else 400
        return jsonify(success=False, error=msg), status


@telegram_bp.post("/api/telegram/webhook")
def telegram_webhook():
    expected = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    supplied = request.headers.get(
        "X-Telegram-Bot-Api-Secret-Token", ""
    )

    if not expected or not supplied or not hmac.compare_digest(
        expected, supplied
    ):
        return jsonify(ok=False), 403

    update = request.get_json(silent=True) or {}
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    sender = message.get("from") or {}

    text = (message.get("text") or "").strip()
    chat_id = chat.get("id")
    telegram_user_id = sender.get("id")

    if not chat_id or not telegram_user_id or not text:
        return jsonify(ok=True), 200

    from connectors.telegram_bot import send_message

    # Only private chats may be connected to a BLOM business.
    if chat.get("type") != "private":
        if text.startswith("/start"):
            try:
                send_message(
                    chat_id,
                    "Please open a private chat with the BLOM bot to connect your account."
                )
            except Exception:
                current_app.logger.exception(
                    "Telegram private-chat response failed"
                )
        return jsonify(ok=True), 200

    # Customer linking through a short-lived, one-time token.
    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        token = parts[1].strip() if len(parts) == 2 else ""

        if token and consume_link_token(
            token,
            chat_id=chat_id,
            telegram_user_id=telegram_user_id,
            username=sender.get("username"),
        ):
            return jsonify(ok=True), 200

        try:
            send_message(
                chat_id,
                "This connection link is invalid or expired. "
                "Generate a fresh link from your BLOM account."
            )
        except Exception:
            current_app.logger.exception(
                "Telegram /start response failed"
            )

        return jsonify(ok=True), 200

    if text in ("/help", "/status"):
        try:
            send_message(
                chat_id,
                "I'm BLOM's Telegram assistant. "
                "Connect me from your authenticated BLOM account "
                "to receive business alerts and GTM analysis updates."
            )
        except Exception:
            current_app.logger.exception(
                "Telegram help response failed"
            )

    return jsonify(ok=True), 200


@telegram_bp.post("/api/telegram/webhook/register")
def telegram_register_webhook():
    # This administrative endpoint is protected by a separate server secret,
    # not by a user session. Call only from an admin/operator environment.
    expected = os.getenv("TELEGRAM_WEBHOOK_ADMIN_SECRET", "")
    supplied = request.headers.get("X-BLOM-Admin-Secret", "")
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        return jsonify(success=False, error="Forbidden"), 403

    token = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    base_url = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    if not token or not base_url:
        return jsonify(success=False, error="Missing webhook configuration"), 503
    try:
        bot = get_me()
        result = set_webhook(f"{base_url}/api/telegram/webhook", token)
        return jsonify(success=True, bot_username=bot.get("username"), webhook_set=bool(result)), 200
    except Exception:
        current_app.logger.exception("Could not register Telegram webhook")
        return jsonify(success=False, error="Could not register Telegram webhook"), 502
