import secrets
from datetime import datetime, timedelta

from flask import Blueprint, current_app, jsonify, request, session
from google.cloud.firestore_v1.base_query import FieldFilter
from werkzeug.security import check_password_hash, generate_password_hash

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


@api_auth_bp.route("/api/auth/login", methods=["POST"])
def api_login():
    try:
        data = request.get_json(silent=True) or {}
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""
        ip = auth._get_ip(request)

        redis_locked, redis_remaining = auth.redis_is_locked(ip)
        if redis_locked:
            remaining = int(int(redis_remaining or 0) / 60) + 1
            return jsonify({"success": False, "error": f"Too many failed attempts. Try again in {remaining} minute(s)."}), 423

        if ip in auth.locked_ips:
            if datetime.utcnow() < auth.locked_ips[ip]:
                remaining = int((auth.locked_ips[ip] - datetime.utcnow()).total_seconds() / 60) + 1
                return jsonify({"success": False, "error": f"Too many failed attempts. Try again in {remaining} minute(s)."}), 423
            auth._reset_attempts(ip)

        if not email or not password:
            return jsonify({"success": False, "error": "All fields are required."}), 400

        users = db.collection("users").where(filter=FieldFilter("email", "==", email)).limit(1).stream()
        user_doc = next(users, None)
        if not user_doc:
            auth._increment_attempts(ip)
            return jsonify({"success": False, "error": "Invalid credentials."}), 401

        user = user_doc.to_dict()

        if not check_password_hash(user.get("password_hash", ""), password):
            auth._increment_attempts(ip)
            return jsonify({"success": False, "error": "Invalid credentials."}), 401

        if user.get("status") == "Disabled":
            return jsonify({"success": False, "error": "Account disabled. Contact support."}), 403

        new_session_token = secrets.token_hex(64)

        db.collection("users").document(user_doc.id).update({
            "active_session_token": new_session_token,
            "last_login": datetime.utcnow().isoformat(),
            "last_ip": ip,
        })
        auth._reset_attempts(ip)

        session.clear()
        session.permanent = True
        current_app.permanent_session_lifetime = timedelta(minutes=30)

        session["user_id"] = user_doc.id
        session["email"] = email
        session["role"] = user.get("role", "user")
        session["session_token"] = new_session_token

        return jsonify({
            "success": True,
            "user_id": user_doc.id,
            "email": email,
            "role": user.get("role", "user"),
        }), 200
    except Exception as exc:
        current_app.logger.error(f"API login error: {exc}")
        return jsonify({"success": False, "error": "Internal server error."}), 500


@api_auth_bp.route("/api/auth/logout", methods=["POST"])
def api_logout():
    try:
        user_id = session.get("user_id")
        if user_id:
            try:
                db.collection("users").document(user_id).update({"active_session_token": None})
            except Exception as exc:
                current_app.logger.error(f"Logout Firestore error: {exc}")
        session.clear()
        return jsonify({"success": True, "message": "Logged out."}), 200
    except Exception as exc:
        current_app.logger.error(f"API logout error: {exc}")
        return jsonify({"success": False, "error": "Internal server error."}), 500


@api_auth_bp.route("/api/auth/me", methods=["GET"])
def api_me():
    try:
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"success": False, "error": "Authentication required"}), 401

        user_doc = db.collection("users").document(user_id).get()
        if not user_doc.exists:
            session.clear()
            return jsonify({"success": False, "error": "Authentication required"}), 401

        user = user_doc.to_dict()
        return jsonify({
            "success": True,
            "user": {
                "id": user_doc.id,
                "username": user.get("username"),
                "email": user.get("email"),
                "role": user.get("role"),
                "status": user.get("status"),
            },
        }), 200
    except Exception as exc:
        current_app.logger.error(f"API me error: {exc}")
        return jsonify({"success": False, "error": "Internal server error."}), 500