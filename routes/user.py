from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, jsonify
from firebase_admin import auth as admin_auth
from firebase import db
from google.cloud.firestore_v1.base_query import FieldFilter
from task import analyze_business_website
from datetime import datetime
import uuid
from firebase_admin import firestore

from validations import validate_website_url

user_bp = Blueprint("user", __name__, template_folder="../templates")

# ─────────────────────────────────────────────────────────────
# Business page
# ─────────────────────────────────────────────────────────────

@user_bp.route("/", methods=["GET"])
def business():
    user_id = session.get("user_id")

    if not user_id:
        return redirect(url_for("auth.login"))

    businesses = (
        db.collection("businesses")
        .where("owner_id", "==", user_id)
        .stream()
    )

    business_list = []

    for business_doc in businesses:
        data = business_doc.to_dict()

        business_list.append({
            "id": business_doc.id,
            **data
        })

    return render_template(
        "business.html",
        businesses=business_list
    )


# ─────────────────────────────────────────────────────────────
# Create business API
# ─────────────────────────────────────────────────────────────

@user_bp.route("/api/business", methods=["POST"])
def create_business():

    user_id = session.get("user_id")

    if not user_id:
        return jsonify({
            "success": False,
            "error": "Authentication required"
        }), 401

    data = request.get_json(silent=True)

    if not data:
        return jsonify({
            "success": False,
            "error": "Request body is required"
        }), 400

    name = data.get("name", "").strip()
    raw_website_url = data.get("website_url", "").strip()
    industry = data.get("industry", "").strip()
    description = data.get("description", "").strip()


    website_url = validate_website_url(raw_website_url)

    if raw_website_url and not website_url:
        return jsonify({
            "success": False,
            "error": "Invalid website URL"
        }), 400
    if not name:
        return jsonify({
            "success": False,
            "error": "Business name is required"
        }), 400

    now = datetime.utcnow().isoformat()

    business_data = {
        "owner_id": user_id,
        "name": name,
        "website_url": website_url,
        "industry": industry,
        "description": description,
        "created_at": now,
        "updated_at": now,
    }

    business_ref = db.collection("businesses").document()
    business_ref.set(business_data)

    return jsonify({
        "success": True,
        "message": "Business created successfully",
        "business": {
            "id": business_ref.id,
            **business_data
        }
    }), 201


# ─────────────────────────────────────────────────────────────
# Update business API
# ─────────────────────────────────────────────────────────────

@user_bp.route("/api/business/<business_id>", methods=["PATCH"])
def update_business(business_id):

    user_id = session.get("user_id")

    if not user_id:
        return jsonify({
            "success": False,
            "error": "Authentication required"
        }), 401

    business_ref = db.collection("businesses").document(business_id)
    business_doc = business_ref.get()

    if not business_doc.exists:
        return jsonify({
            "success": False,
            "error": "Business not found"
        }), 404

    business_data = business_doc.to_dict()

    # ─────────────────────────────────────────────────────────
    # Ownership check
    # ─────────────────────────────────────────────────────────

    if business_data.get("owner_id") != user_id:
        return jsonify({
            "success": False,
            "error": "You do not have permission to modify this business"
        }), 403

    # ─────────────────────────────────────────────────────────
    # Request body
    # ─────────────────────────────────────────────────────────

    data = request.get_json(silent=True)

    if not data:
        return jsonify({
            "success": False,
            "error": "Request body is required"
        }), 400

    allowed_fields = {
        "name",
        "website_url",
        "industry",
        "description"
    }

    updates = {
        key: value.strip() if isinstance(value, str) else value
        for key, value in data.items()
        if key in allowed_fields
    }

    if not updates:
        return jsonify({
            "success": False,
            "error": "No valid fields to update"
        }), 400

    # ─────────────────────────────────────────────────────────
    # Business name validation
    # ─────────────────────────────────────────────────────────

    if "name" in updates and not updates["name"]:
        return jsonify({
            "success": False,
            "error": "Business name cannot be empty"
        }), 400

    # ─────────────────────────────────────────────────────────
    # Website URL validation
    # ─────────────────────────────────────────────────────────

    if "website_url" in updates:

        raw_website_url = updates["website_url"]

        # Allow user to clear the website URL
        if raw_website_url == "":
            updates["website_url"] = None

        else:
            validated_url = validate_website_url(
                raw_website_url
            )

            if not validated_url:
                return jsonify({
                    "success": False,
                    "error": "Invalid or unsafe website URL"
                }), 400

            updates["website_url"] = validated_url

    # ─────────────────────────────────────────────────────────
    # Update timestamp
    # ─────────────────────────────────────────────────────────

    updates["updated_at"] = datetime.utcnow().isoformat()

    business_ref.update(updates)

    return jsonify({
        "success": True,
        "message": "Business updated successfully",
        "business_id": business_id,
        "updates": updates
    }), 200

# ─────────────────────────────────────────────────────────────
# Delete business API
# ─────────────────────────────────────────────────────────────

@user_bp.route("/api/business/<business_id>", methods=["DELETE"])
def delete_business(business_id):

    user_id = session.get("user_id")

    if not user_id:
        return jsonify({
            "success": False,
            "error": "Authentication required"
        }), 401

    # ─────────────────────────────────────────────────────────
    # Get business
    # ─────────────────────────────────────────────────────────

    business_ref = db.collection("businesses").document(business_id)
    business_doc = business_ref.get()

    if not business_doc.exists:
        return jsonify({
            "success": False,
            "error": "Business not found"
        }), 404

    business_data = business_doc.to_dict()

    # ─────────────────────────────────────────────────────────
    # Ownership check
    # ─────────────────────────────────────────────────────────

    if business_data.get("owner_id") != user_id:
        return jsonify({
            "success": False,
            "error": "You do not have permission to delete this business"
        }), 403

    # ─────────────────────────────────────────────────────────
    # Delete business
    # ─────────────────────────────────────────────────────────

    business_ref.delete()

    return jsonify({
        "success": True,
        "message": "Business deleted successfully",
        "business_id": business_id
    }), 200
    
# ─────────────────────────────────────────────────────────────
# Analyze website
# ─────────────────────────────────────────────────────────────

@user_bp.route(
    "/api/business/<business_id>/analyze",
    methods=["POST"]
)
def analyze_business(business_id):
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({
            "success": False,
            "error": "Authentication required"
        }), 401

    business_ref = db.collection("businesses").document(business_id)
    business_doc = business_ref.get()

    if not business_doc.exists:
        return jsonify({
            "success": False,
            "error": "Business not found"
        }), 404

    business = business_doc.to_dict()

    if business.get("owner_id") != user_id:
        return jsonify({
            "success": False,
            "error": "You do not have permission to analyze this business"
        }), 403

    if not business.get("website_url"):
        return jsonify({
            "success": False,
            "error": "This business does not have a website URL"
        }), 400

    # Create a run record
    run_ref = (
        business_ref
        .collection("agent_runs")
        .document()
    )

    run_id = run_ref.id

    run_ref.set({
        "business_id": business_id,
        "owner_id": user_id,
        "type": "website_analysis",
        "status": "queued",
        "created_at": datetime.utcnow().isoformat(),
    })

    # Send background job to Celery
    try:
        task = analyze_business_website.delay(
            business_id,
            user_id,
            run_id,
        )
    except Exception as exc:
        run_ref.update({
            "status": "failed",
            "error": str(exc),
            "failed_at": datetime.utcnow().isoformat(),
        })
        return jsonify({
            "success": False,
            "error": "Analysis job could not be queued",
            "detail": str(exc),
        }), 503

    # Store Celery task ID
    run_ref.update({
        "task_id": task.id,
    })

    return jsonify({
        "success": True,
        "message": "Website analysis started",
        "run_id": run_id,
        "task_id": task.id,
        "status": "queued",
    }), 202


# ─────────────────────────────────────────────────────────────
# Auth-redirect stubs (targets of auth.py:login redirects)
# ─────────────────────────────────────────────────────────────

@user_bp.route("/dashboard", methods=["GET"])
def dashboard():
    return jsonify({"success": True, "message": "Dashboard placeholder"}), 200


@user_bp.route("/create-profile", methods=["GET", "POST"])
def create_profile():
    return jsonify({"success": True, "message": "Profile placeholder"}), 200


@user_bp.route("/generate-logbook", methods=["GET"])
def generate_logbook():
    return jsonify({"success": True, "message": "Logbook placeholder"}), 200