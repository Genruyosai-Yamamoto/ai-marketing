from datetime import datetime

from flask import Blueprint, current_app, jsonify, request
from google.cloud.firestore_v1.base_query import FieldFilter
from werkzeug.security import generate_password_hash

import routes.auth as auth
from firebase import db

api_auth_bp = Blueprint("api_auth", __name__)


@api_auth_bp.route("/api/auth/register", methods=["POST"])
def api_register():
    try:
        data = request.get_json(silent=True) or {}
        username = (data.get("username") or "").strip()
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""
        ip = auth._get_ip(request)

        if not all([username, email, password]):
            return jsonify({"success": False, "error": "All fields are required."}), 400

        if len(password) < 8:
            return jsonify({"success": False, "error": "Password must be at least 8 characters."}), 400

        if not auth.check_registration_limit(ip):
            return jsonify({"success": False, "error": "Too many registrations from this IP. Try again later."}), 429

        existing = db.collection("users").where(filter=FieldFilter("email", "==", email)).limit(1).get()
        if existing:
            return jsonify({"success": False, "error": "Email already registered. Please login or use another email."}), 409

        user_data = {
            "username": username,
            "email": email,
            "role": "user",
            "password_hash": generate_password_hash(password),
            "active_session_token": None,
            "bound_device_id": None,
            "subscription_status": False,
            "subscription_expiry": None,
            "status": "Active",
            "created_at": datetime.utcnow().isoformat(),
            "last_login": None,
        }

        uid, error = auth.create_firebase_user_and_firestore(email, password, user_data)
        if error is not None:
            if "already registered" in error.lower():
                return jsonify({"success": False, "error": "Email already registered. Please login or use another email."}), 409
            return jsonify({"success": False, "error": "Registration failed. Try again later."}), 500

        auth.log_registration(ip)
        return jsonify({"success": True, "user_id": uid}), 201
    except Exception as exc:
        current_app.logger.error(f"API register error: {exc}")
        return jsonify({"success": False, "error": "Internal server error."}), 500