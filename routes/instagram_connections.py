from urllib.parse import urlencode

import secrets
import requests
from flask import (
    Blueprint,
    jsonify,
    redirect,
    request,
    session,
)
from config.instagram import (
    INSTAGRAM_CLIENT_ID,
    INSTAGRAM_CLIENT_SECRET,
    INSTAGRAM_REDIRECT_URI,
    INSTAGRAM_OAUTH_AUTHORIZE_URL,
    INSTAGRAM_OAUTH_TOKEN_URL,
    validate_instagram_config,
)
from firebase import db
from services.connection_service import (
    create_connection,
)
from services.instagram_service import (
    get_instagram_account,
)
from config.instagram import (
    INSTAGRAM_OAUTH_SCOPES,
)
instagram_connections_bp = Blueprint( "instagram_connections", __name__,)

@instagram_connections_bp.route( "/api/connections/instagram", methods=["GET"],)
def connect_instagram():
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({
            "success": False,
            "error": "Authentication required",
        }), 401

    try:
        validate_instagram_config()
    except RuntimeError as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), 500

    business_id = request.args.get(
        "business_id",
        ""
    ).strip()

    if not business_id:
        return jsonify({
            "success": False,
            "error": "business_id is required",
        }), 400

    business_ref = (
        db.collection("businesses")
        .document(business_id)
    )

    business_doc = business_ref.get()

    if not business_doc.exists:
        return jsonify({
            "success": False,
            "error": "Business not found",
        }), 404

    business = business_doc.to_dict()

    if business.get("owner_id") != user_id:
        return jsonify({
            "success": False,
            "error": (
                "You do not have permission to "
                "connect Instagram for this business"
            ),
        }), 403

    state = secrets.token_urlsafe(32)

    session["instagram_oauth_state"] = state
    session["instagram_oauth_business_id"] = business_id

    params = {
        "client_id": INSTAGRAM_CLIENT_ID,
        "redirect_uri": INSTAGRAM_REDIRECT_URI,
        "response_type": "code",
        "scope": INSTAGRAM_OAUTH_SCOPES,
        "state": state,
    }

    authorization_url = (
        f"{INSTAGRAM_OAUTH_AUTHORIZE_URL}"
        f"?{urlencode(params)}"
    )

    return redirect(authorization_url)

@instagram_connections_bp.route( "/api/connections/instagram/callback", methods=["GET"], )
def instagram_callback():
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({
            "success": False,
            "error": "Authentication required",
        }), 401

    returned_state = request.args.get("state", "")
    code = request.args.get("code", "")

    if not returned_state:
        return jsonify({
            "success": False,
            "error": "Missing OAuth state",
        }), 400

    if not code:
        error = request.args.get(
            "error",
            "Instagram authorization was not completed",
        )

        return jsonify({
            "success": False,
            "error": error,
        }), 400

    expected_state = session.get(
        "instagram_oauth_state"
    )

    business_id = session.get(
        "instagram_oauth_business_id"
    )

    if not expected_state or not business_id:
        return jsonify({
            "success": False,
            "error": "Instagram OAuth session expired",
        }), 400

    if not secrets.compare_digest(
        returned_state,
        expected_state,
    ):
        return jsonify({
            "success": False,
            "error": "Invalid OAuth state",
        }), 400

    business_ref = (
        db.collection("businesses")
        .document(business_id)
    )

    business_doc = business_ref.get()

    if not business_doc.exists:
        return jsonify({
            "success": False,
            "error": "Business not found",
        }), 404

    business = business_doc.to_dict()

    if business.get("owner_id") != user_id:
        return jsonify({
            "success": False,
            "error": "You do not own this business",
        }), 403

    token_response = requests.post(
        INSTAGRAM_OAUTH_TOKEN_URL,
        data={
            "client_id": INSTAGRAM_CLIENT_ID,
            "client_secret": INSTAGRAM_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "redirect_uri": INSTAGRAM_REDIRECT_URI,
            "code": code,
        },
        timeout=10,
    )

    if not token_response.ok:
        return jsonify({
            "success": False,
            "error": "Instagram token exchange failed",
        }), 502

    token_data = token_response.json()

    access_token = token_data.get(
        "access_token"
    )

    if not access_token:
        return jsonify({
            "success": False,
            "error": "Instagram did not return an access token",
        }), 502

    connection = create_connection(
        business_id=business_id,
        user_id=user_id,
        provider="instagram",
        connection_data={
            "access_token": access_token,
            "account_id": account["account_id"],
            "username": account.get("username"),
            "expires_in": token_data.get(
                "expires_in"
            ),
        },
    )

    session.pop(
        "instagram_oauth_state",
        None,
    )

    session.pop(
        "instagram_oauth_business_id",
        None,
    )

    return jsonify({
        "success": True,
        "message": "Instagram connected successfully",
        "connection": {
            "id": connection["id"],
            "provider": connection["provider"],
            "account_id": connection.get(
                "account_id"
            ),
            "status": connection["status"],
        },
    }), 200
    
@instagram_connections_bp.route(
    "/api/connections/instagram/status",
    methods=["GET"],
)
def instagram_connection_status():
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({
            "success": False,
            "error": "Authentication required",
        }), 401

    business_id = request.args.get(
        "business_id",
        "",
    ).strip()

    if not business_id:
        return jsonify({
            "success": False,
            "error": "business_id is required",
        }), 400

    business_ref = (
        db.collection("businesses")
        .document(business_id)
    )

    business_doc = business_ref.get()

    if not business_doc.exists:
        return jsonify({
            "success": False,
            "error": "Business not found",
        }), 404

    business = business_doc.to_dict()

    if business.get("owner_id") != user_id:
        return jsonify({
            "success": False,
            "error": "You do not have permission to view this business",
        }), 403

    connections = (
        business_ref
        .collection("connections")
        .where("provider", "==", "instagram")
        .where("status", "==", "connected")
        .limit(1)
        .stream()
    )

    connection_doc = next(
        connections,
        None,
    )

    if not connection_doc:
        return jsonify({
            "success": True,
            "connected": False,
            "connection": None,
        }), 200

    connection = connection_doc.to_dict()

    return jsonify({
        "success": True,
        "connected": True,
        "connection": {
            "id": connection_doc.id,
            "provider": connection.get(
                "provider"
            ),
            "username": connection.get(
                "username"
            ),
            "account_id": connection.get(
                "account_id"
            ),
            "status": connection.get(
                "status"
            ),
        },
    }), 200