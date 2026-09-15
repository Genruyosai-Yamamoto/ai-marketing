import hmac
import secrets
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from firebase_admin import auth as admin_auth
from firebase import db
from google.cloud.firestore_v1.base_query import FieldFilter
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

def login_required(f):
    """
    Protects routes by verifying the session token matches Firestore.
    If another device logs in, the stored token changes → this session
    is immediately invalidated on the next request.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in.", "warning")
            return redirect(url_for("auth.login"))

        user_id       = session["user_id"]
        session_token = session.get("session_token")

        if not user_id or not session_token:
            session.clear()
            flash("Please log in.", "warning")
            return redirect(url_for("auth.login"))

        try:
            user_doc = db.collection("users").document(user_id).get()
            if not user_doc.exists:
                session.clear()
                return redirect(url_for("auth.login"))

            user = user_doc.to_dict()

            stored_token = user.get("active_session_token")
            if not stored_token or not session_token:
                session.clear()
                flash("Session expired. Please log in again.", "warning")
                return redirect(url_for("auth.login"))

            if not hmac.compare_digest(stored_token, session_token):
                session.clear()
                flash(
                    "Your account was accessed from another device. "
                    "You have been logged out.",
                    "danger"
                )
                return redirect(url_for("auth.login"))

            if user.get("status") == "Disabled":
                session.clear()
                flash("Account disabled. Contact support.", "danger")
                return redirect(url_for("auth.login"))

        except Exception as e:
            current_app.logger.error(f"Session guard error: {e}")
            session.clear()
            return redirect(url_for("auth.login"))

        return f(*args, **kwargs)
    return decorated

