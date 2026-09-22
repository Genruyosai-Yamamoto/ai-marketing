import secrets
from firebase import db
from flask import Blueprint, jsonify, redirect, request, session
from services.connection_service import create_github_connection
from connectors.github_api import GitHubAPI


github_connections_bp = Blueprint(
    "github_connections",
    __name__,
)


@github_connections_bp.route("/api/connections/github/callback", methods=["GET"])
def github_callback():
    user_id = session.get("user_id")
    print("DEBUG github_callback user_id:", user_id)
    print("DEBUG github_callback session:", dict(session))

    if not user_id:
        return jsonify({
            "success": False,
            "error": "Authentication required",
        }), 401

    code = request.args.get("code")
    state = request.args.get("state")

    if not code:
        return jsonify({
            "success": False,
            "error": "Missing GitHub authorization code",
        }), 400

    if not state:
        return jsonify({
            "success": False,
            "error": "Missing OAuth state",
        }), 400

    expected_state = session.get("github_oauth_state")

    if not expected_state or not secrets.compare_digest(
        state,
        expected_state,
    ):
        return jsonify({
            "success": False,
            "error": "Invalid OAuth state",
        }), 400

    session.pop("github_oauth_state", None)
    
    try:
        business_id = session.pop("github_oauth_business_id", None)
        if not business_id:
            return jsonify({
                "success": False,
                "error": "Missing GitHub OAuth business context",
            }), 400
                
        token_data = GitHubAPI.exchange_code_for_token(code)

        github = GitHubAPI(
            access_token=token_data["access_token"]
        )

        account = github.get_authenticated_user()
        
            
        business_ref = db.collection("businesses").document(business_id)
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

        connection = create_github_connection(
            business_id=business_id,
            user_id=user_id,
            access_token=token_data["access_token"],
            owner=account["login"],
            repo=request.args.get("repo"),
            default_branch=request.args.get("default_branch"),
        )

        return jsonify({
            "success": True,
            "message": "GitHub OAuth identity verified successfully",
            "github_account": {
                "id": account.get("id"),
                "login": account.get("login"),
                "name": account.get("name"),
            },
            "scope": token_data.get("scope"),
        })

    except Exception as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), 500
        
@github_connections_bp.route(
    "/api/connections/github/repositories",
    methods=["GET"],
)
def github_repositories():
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
            provider="github",
        )

        if not connection:
            return jsonify({
                "success": False,
                "error": "GitHub connection not found",
            }), 404

        github = GitHubAPI(
            access_token=connection["access_token"]
        )

        repositories = github.list_repositories()

        return jsonify({
            "success": True,
            "repositories": repositories,
        })

    except PermissionError as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), 403

    except Exception as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), 500
        
@github_connections_bp.route("/api/connections/github/connect", methods=["GET"])
def github_connect():
    user_id = session.get("user_id")
    print("DEBUG github_connect user_id:", user_id)
    print("DEBUG github_connect session:", dict(session))
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

    state = secrets.token_urlsafe(32)

    session["github_oauth_state"] = state
    session["github_oauth_business_id"] = business_id

    authorization_url = GitHubAPI.get_authorization_url(state)

    return jsonify({
        "success": True,
        "authorization_url": authorization_url,
    })