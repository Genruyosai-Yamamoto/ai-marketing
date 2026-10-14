import secrets
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, session, current_app
from services.connection_service import create_connection

from firebase import db
from connectors.google_search_console import GoogleSearchConsoleAPI


search_console_connections_bp = Blueprint(
    "search_console_connections",
    __name__,
)


@search_console_connections_bp.route(
    "/api/connections/search-console/connect",
    methods=["GET"],
)
def search_console_connect():
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({
            "success": False,
            "error": "Authentication required",
        }), 401

    business_id = request.args.get("business_id")

    if not business_id:
        return jsonify({
            "success": False,
            "error": "Missing business_id",
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

    state = secrets.token_urlsafe(32)

    session["search_console_oauth_state"] = state
    session["search_console_oauth_business_id"] = business_id

    authorization_url, code_verifier = (
        GoogleSearchConsoleAPI.get_authorization_url(state)
    )

    session["search_console_oauth_code_verifier"] = code_verifier

    return jsonify({
        "success": True,
        "authorization_url": authorization_url,
    })

@search_console_connections_bp.route(
    "/api/connections/search-console/callback",
    methods=["GET"],
)
def search_console_callback():
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({
            "success": False,
            "error": "Authentication required",
        }), 401

    # Handle authorization errors returned by Google.
    if request.args.get("error"):
        session.pop("search_console_oauth_state", None)
        session.pop("search_console_oauth_business_id", None)

        return jsonify({
            "success": False,
            "error": "Google authorization was not completed",
        }), 400

    code = request.args.get("code")
    state = request.args.get("state")
    expected_state = session.get("search_console_oauth_state")

    if not code or not state:
        return jsonify({
            "success": False,
            "error": "Missing authorization code or OAuth state",
        }), 400

    if not expected_state or not secrets.compare_digest(
        state,
        expected_state,
    ):
        return jsonify({
            "success": False,
            "error": "Invalid OAuth state",
        }), 400

    # Consume state once validated.
    
    # Consume OAuth state and PKCE verifier once validated.
    session.pop("search_console_oauth_state", None)

    business_id = session.pop(
        "search_console_oauth_business_id",
        None,
    )

    code_verifier = session.pop(
        "search_console_oauth_code_verifier",
        None,
    )

    if not code_verifier:
        return jsonify({
            "success": False,
            "error": "Missing OAuth code verifier. Please reconnect Google Search Console.",
        }), 400


    if not business_id:
        return jsonify({
            "success": False,
            "error": "Missing business context",
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

    try:
       
        credentials = (
            GoogleSearchConsoleAPI.exchange_code_for_credentials(
                code=code,
                state=state,
                code_verifier=code_verifier,
            )
        )


        if not credentials.refresh_token:
            return jsonify({
                "success": False,
                "error": (
                    "Google did not return a refresh token. "
                    "Revoke Blom's existing Google access and "
                    "try connecting again."
                ),
            }), 400

        # Verify that the credentials can access Search Console
        # before saving the connection.
        google = GoogleSearchConsoleAPI(credentials)
        sites = google.list_sites()

        connection_data = {
            "access_token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "token_expires_at": (
                credentials.expiry.isoformat()
                if credentials.expiry
                else None
            ),
            "granted_scopes": credentials.scopes or [],
            "properties_count": len(sites),
        }

        connection = create_connection(
            business_id=business_id,
            user_id=user_id,
            provider="google_search_console",
            connection_data=connection_data,
        )

        return jsonify({
            "success": True,
            "message": "Google Search Console connected successfully",
            "connection": {
                "id": connection["id"],
                "provider": connection["provider"],
                "status": connection["status"],
                "properties_count": len(sites),
            },
        }), 200

    except Exception:
        current_app.logger.exception(
            "Google Search Console OAuth callback failed"
        )
        return jsonify({
            "success": False,
            "error": "Google Search Console connection failed. Check server logs.",
        }), 500


@search_console_connections_bp.route(
    "/api/connections/search-console/properties",
    methods=["GET"],
)
def search_console_properties():
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({
            "success": False,
            "error": "Authentication required",
        }), 401

    business_id = request.args.get("business_id")

    if not business_id:
        return jsonify({
            "success": False,
            "error": "Missing business_id",
        }), 400

    try:
        from services.connection_service import get_connection

        connection = get_connection(
            business_id=business_id,
            user_id=user_id,
            provider="google_search_console",
        )

        google = GoogleSearchConsoleAPI.from_refresh_token(
            refresh_token=connection["refresh_token"],
            access_token=connection.get("access_token"),
            token_expiry=connection.get("token_expires_at"),
        )

        sites = google.list_sites()

        return jsonify({
            "success": True,
            "properties": [
                {
                    "site_url": site.get("siteUrl"),
                    "permission_level": site.get("permissionLevel"),
                }
                for site in sites
            ],
        }), 200

    except PermissionError as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), 403

    except ValueError as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), 404

    except Exception:
        return jsonify({
            "success": False,
            "error": "Unable to retrieve Search Console properties",
        }), 500
        
@search_console_connections_bp.route(
    "/api/connections/search-console/select-property",
    methods=["POST"],
)
def select_search_console_property():
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({
            "success": False,
            "error": "Authentication required",
        }), 401

    data = request.get_json(silent=True) or {}
    business_id = data.get("business_id")
    site_url = data.get("site_url")

    if not business_id or not site_url:
        return jsonify({
            "success": False,
            "error": "Missing business_id or site_url",
        }), 400

    try:
        from services.connection_service import get_connection

        connection = get_connection(
            business_id=business_id,
            user_id=user_id,
            provider="google_search_console",
        )

        google = GoogleSearchConsoleAPI.from_refresh_token(
            refresh_token=connection["refresh_token"],
            access_token=connection.get("access_token"),
            token_expiry=connection.get("token_expires_at"),
        )

        # Only allow properties accessible to this Google account.
        sites = google.list_sites()
        allowed_sites = {
            site.get("siteUrl")
            for site in sites
            if site.get("siteUrl")
        }

        if site_url not in allowed_sites:
            return jsonify({
                "success": False,
                "error": "This property is not accessible to the connected Google account",
            }), 403

        connection_ref = (
            db.collection("businesses")
            .document(business_id)
            .collection("connections")
            .document(connection["id"])
        )

        connection_ref.update({
            "site_id": site_url,
            "updated_at": datetime.now(timezone.utc),
        })

        return jsonify({
            "success": True,
            "message": "Search Console property selected successfully",
            "site_url": site_url,
        }), 200

    except PermissionError as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), 403

    except ValueError as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), 404

    except Exception:
        current_app.logger.exception(
            "Failed to select Search Console property"
        )
        return jsonify({
            "success": False,
            "error": "Unable to select Search Console property",
        }), 500

@search_console_connections_bp.route(
    "/api/connections/search-console/analytics",
    methods=["GET"],
)
def search_console_analytics():
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({
            "success": False,
            "error": "Authentication required",
        }), 401

    business_id = request.args.get("business_id")
    if not business_id:
        return jsonify({
            "success": False,
            "error": "Missing business_id",
        }), 400

    try:
        from services.connection_service import get_connection
        from datetime import date, timedelta

        connection = get_connection(
            business_id=business_id,
            user_id=user_id,
            provider="google_search_console",
        )

        site_url = connection.get("site_id")
        if not site_url:
            return jsonify({
                "success": False,
                "error": "No Search Console property selected",
            }), 400

        google = GoogleSearchConsoleAPI.from_refresh_token(
            refresh_token=connection["refresh_token"],
            access_token=connection.get("access_token"),
            token_expiry=connection.get("token_expires_at"),
        )

        # Recent complete dates: Search Console data can be delayed.
        end_date = date.today() - timedelta(days=3)
        start_date = end_date - timedelta(days=27)

        rows = google.get_search_analytics(
            site_url=site_url,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        )

        query_rows = google.get_search_analytics(
            site_url=site_url,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            dimensions=["query"],
            row_limit=25,
        )

        page_rows = google.get_search_analytics(
            site_url=site_url,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            dimensions=["page"],
            row_limit=25,
        )

        def serialize_rows(rows):
            return [
                {
                    "keys": row.get("keys", []),
                    "clicks": row.get("clicks", 0),
                    "impressions": row.get("impressions", 0),
                    "ctr": row.get("ctr", 0),
                    "position": row.get("position", 0),
                }
                for row in rows
            ]

        totals = {
            "clicks": 0,
            "impressions": 0,
            "ctr": 0,
            "position": 0,
        }

        if rows:
            totals = {
                "clicks": rows[0].get("clicks", 0),
                "impressions": rows[0].get("impressions", 0),
                "ctr": rows[0].get("ctr", 0),
                "position": rows[0].get("position", 0),
            }

        return jsonify({
            "success": True,
            "site_url": site_url,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "top_queries": serialize_rows(query_rows),
            "top_pages": serialize_rows(page_rows),
            "totals": totals,
            "rows_returned": len(rows),
        }), 200

    except PermissionError as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), 403

    except ValueError as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), 404

    except Exception:
        current_app.logger.exception(
            "Search Console analytics request failed"
        )
        return jsonify({
            "success": False,
            "error": "Unable to retrieve Search Console analytics",
        }), 500