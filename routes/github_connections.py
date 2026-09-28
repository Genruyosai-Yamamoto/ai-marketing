import os
import secrets
from firebase import db
from flask import Blueprint, jsonify, redirect, request, session
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from services.connection_service import create_github_connection
from connectors.github_api import GitHubAPI

# Where to send the browser back to after the OAuth callback.
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

def _oauth_serializer():
    # Signs the OAuth state with the app SECRET_KEY so the callback can trust
    # the user_id/business_id inside it without relying on the session cookie.
    return URLSafeTimedSerializer(os.getenv("SECRET_KEY"), salt="github-oauth-state")

github_connections_bp = Blueprint(
    "github_connections",
    __name__,
)


@github_connections_bp.route("/api/connections/github/callback", methods=["GET"])
def github_callback():
    code = request.args.get("code")
    state = request.args.get("state")

    if not code or not state:
        return redirect(f"{FRONTEND_URL}/connections?github=error")

    # Verify + decode the signed state (valid for 10 minutes). No session needed.
    try:
        payload = _oauth_serializer().loads(state, max_age=600)
    except (BadSignature, SignatureExpired):
        return redirect(f"{FRONTEND_URL}/connections?github=error")

    user_id = payload.get("user_id")
    business_id = payload.get("business_id")

    if not user_id or not business_id:
        return redirect(f"{FRONTEND_URL}/connections?github=error")

    try:
        token_data = GitHubAPI.exchange_code_for_token(code)
        github = GitHubAPI(access_token=token_data["access_token"])
        account = github.get_authenticated_user()

        business_ref = db.collection("businesses").document(business_id)
        business_doc = business_ref.get()

        if not business_doc.exists:
            return redirect(f"{FRONTEND_URL}/connections?github=error")

        business = business_doc.to_dict()
        if business.get("owner_id") != user_id:
            return redirect(f"{FRONTEND_URL}/connections?github=error")

        create_github_connection(
            business_id=business_id,
            user_id=user_id,
            access_token=token_data["access_token"],
            owner=account["login"],
            repo=request.args.get("repo"),
            default_branch=request.args.get("default_branch"),
        )

        return redirect(f"{FRONTEND_URL}/connections?github=connected")

    except Exception as exc:
        print("DEBUG github_callback error:", exc)
        return redirect(f"{FRONTEND_URL}/connections?github=error")
        
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

        # Encode who + which business into a SIGNED state token instead of the
    # session. GitHub echoes this back to the callback unchanged, so the callback
    # can trust it (signature-verified) without needing the session cookie --
    # which is what fixes the localhost vs 127.0.0.1 session split.
    state = _oauth_serializer().dumps({
        "user_id": user_id,
        "business_id": business_id,
    })

    authorization_url = GitHubAPI.get_authorization_url(state)

    return jsonify({
        "success": True,
        "authorization_url": authorization_url,
    })
    
@github_connections_bp.route(
    "/api/connections/github/repository",
    methods=["PATCH"],
)
def select_github_repository():
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

    data = request.get_json(silent=True) or {}

    repository = data.get("repository")

    if not repository:
        return jsonify({
            "success": False,
            "error": "Missing repository",
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

        owner, repo = repository.split("/", 1)

        github_repo = github.get_repository(
            owner=owner,
            repo=repo,
        )

        if owner != connection.get("account_id"):
            return jsonify({
                "success": False,
                "error": (
                    "Repository does not belong to the connected "
                    "GitHub account"
                ),
            }), 403

        connection_ref = (
            db.collection("businesses")
            .document(business_id)
            .collection("connections")
            .document(connection["id"])
        )

        connection_ref.update({
            "repository": github_repo["full_name"],
            "default_branch": github_repo["default_branch"],
        })

        return jsonify({
            "success": True,
            "repository": github_repo["full_name"],
            "default_branch": github_repo["default_branch"],
        })

    except ValueError:
        return jsonify({
            "success": False,
            "error": "Repository must use owner/repository format",
        }), 400

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