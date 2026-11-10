import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from google.cloud import firestore
from firebase import db
from connectors.telegram_bot import send_message

ALLOWED_EVENT_TYPES = {
    "gtm_completed",
    "gtm_failed",
    "opportunity_created",
    "action_executed",
}

DEFAULT_PREFERENCES = {k: True for k in ALLOWED_EVENT_TYPES}


def _now():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def create_link_token(business_id, user_id):
    business_ref = db.collection("businesses").document(business_id)
    business_doc = business_ref.get()
    if not business_doc.exists:
        raise ValueError("Business not found")
    if (business_doc.to_dict() or {}).get("owner_id") != user_id:
        raise PermissionError("You do not own this business")

    raw_token = secrets.token_urlsafe(24)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires_at = _now() + timedelta(minutes=10)
    db.collection("telegram_link_tokens").document(token_hash).set({
        "token_hash": token_hash,
        "business_id": business_id,
        "user_id": user_id,
        "created_at": _iso(_now()),
        "expires_at": _iso(expires_at),
        "used": False,
    })
    username = (os.getenv("TELEGRAM_BOT_USERNAME") or "").strip().lstrip("@")
    if not username:
        # Token is still stored, but don't expose a link that cannot work.
        db.collection("telegram_link_tokens").document(token_hash).delete()
        raise RuntimeError("TELEGRAM_BOT_USERNAME is not configured")
    return {
        "link": f"https://t.me/{username}?start={raw_token}",
        "expires_at": _iso(expires_at),
    }


def consume_link_token(raw_token, chat_id, telegram_user_id, username=None):
    """
    Atomically consumes a one-time Telegram linking token.

    Prevents:
    - Reusing an expired or consumed token.
    - Simultaneous requests consuming the same token.
    - Replacing a different Telegram account already connected
      to the business.
    """
    if not raw_token or len(raw_token) > 128:
        return False

    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    token_ref = db.collection("telegram_link_tokens").document(token_hash)

    transaction = db.transaction()

    @firestore.transactional
    def _consume(transaction):
        # All reads happen before writes.
        token_doc = token_ref.get(transaction=transaction)

        if not token_doc.exists:
            return False

        data = token_doc.to_dict() or {}

        if data.get("used"):
            return False

        try:
            expires_at = datetime.fromisoformat(data["expires_at"])
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
        except (KeyError, ValueError, TypeError):
            transaction.delete(token_ref)
            return False

        if expires_at <= _now():
            transaction.delete(token_ref)
            return False

        business_id = data.get("business_id")
        user_id = data.get("user_id")

        if not business_id or not user_id:
            transaction.delete(token_ref)
            return False

        business_ref = (
            db.collection("businesses").document(business_id)
        )

        connection_ref = (
            business_ref.collection("connections").document("telegram")
        )

        business_doc = business_ref.get(transaction=transaction)
        connection_doc = connection_ref.get(transaction=transaction)

        if not business_doc.exists:
            transaction.delete(token_ref)
            return False

        business_data = business_doc.to_dict() or {}

        if business_data.get("owner_id") != user_id:
            transaction.delete(token_ref)
            return False

        # Never silently replace another Telegram account.
        if connection_doc.exists:
            existing = connection_doc.to_dict() or {}

            if (
                existing.get("provider") == "telegram"
                and existing.get("status") == "connected"
                and str(existing.get("telegram_user_id"))
                    != str(telegram_user_id)
            ):
                return False

        now = _iso(_now())

        transaction.set(connection_ref, {
            "provider": "telegram",
            "status": "connected",
            "chat_id": str(chat_id),
            "telegram_user_id": str(telegram_user_id),
            "telegram_username": username,
            "linked_by_user_id": user_id,
            "preferences": dict(DEFAULT_PREFERENCES),
            "created_at": now,
            "updated_at": now,
        })

        transaction.update(token_ref, {
            "used": True,
            "used_at": now,
        })

        return True

    linked = _consume(transaction)

    if linked:
        try:
            send_message(
                chat_id,
                "✅ Your Telegram chat is linked to BLOM! "
                "You'll receive important business alerts and GTM updates here."
            )
        except Exception:
            # Connection is already saved; notification can be retried.
            pass

    return linked


def get_telegram_connection(business_id, user_id):
    business_ref = db.collection("businesses").document(business_id)
    business_doc = business_ref.get()
    if not business_doc.exists:
        raise ValueError("Business not found")
    if (business_doc.to_dict() or {}).get("owner_id") != user_id:
        raise PermissionError("You do not own this business")
    doc = business_ref.collection("connections").document("telegram").get()
    if not doc.exists:
        return None
    data = doc.to_dict() or {}
    if data.get("provider") != "telegram" or data.get("status") != "connected":
        return None
    return data


def disconnect_telegram(business_id, user_id):
    business_ref = db.collection("businesses").document(business_id)
    business_doc = business_ref.get()

    if not business_doc.exists:
        raise ValueError("Business not found")

    if (business_doc.to_dict() or {}).get("owner_id") != user_id:
        raise PermissionError("You do not own this business")

    connection_ref = (
        business_ref.collection("connections").document("telegram")
    )

    connection_ref.set({
        "provider": "telegram",
        "status": "disconnected",
        "disconnected_at": _iso(_now()),
        "updated_at": _iso(_now()),
    })


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

