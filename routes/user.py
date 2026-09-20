from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, jsonify
from firebase_admin import auth as admin_auth
from firebase import db
from google.cloud.firestore_v1.base_query import FieldFilter
from task import analyze_business_website
from datetime import datetime
import uuid
from firebase_admin import firestore
from datetime import datetime
from task import execute_approved_action
from google.cloud import firestore
from task import execute_approved_action
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
    
@user_bp.route("/api/business/<business_id>/opportunities",methods=["GET"])
def get_business_opportunities(business_id):
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
            "error": "You do not have permission to view this business"
        }), 403

    opportunities_ref = (
        business_ref
        .collection("opportunities")
        .where("owner_id", "==", user_id)
    )

    opportunities = []

    for doc in opportunities_ref.stream():
        opportunity = doc.to_dict()

        opportunities.append({
            "id": doc.id,
            **opportunity,
        })

    return jsonify({
        "success": True,
        "business_id": business_id,
        "opportunities": opportunities,
    }), 200
    
@user_bp.route("/api/business/<business_id>/opportunities/<opportunity_id>", methods=["GET"])
def get_opportunity(business_id, opportunity_id):
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
            "error": "You do not have permission to view this business"
        }), 403

    opportunity_ref = (
        business_ref
        .collection("opportunities")
        .document(opportunity_id)
    )

    opportunity_doc = opportunity_ref.get()

    if not opportunity_doc.exists:
        return jsonify({
            "success": False,
            "error": "Opportunity not found"
        }), 404

    opportunity = opportunity_doc.to_dict()

    if opportunity.get("owner_id") != user_id:
        return jsonify({
            "success": False,
            "error": "You do not have permission to view this opportunity"
        }), 403

    return jsonify({
        "success": True,
        "opportunity": {
            "id": opportunity_doc.id,
            **opportunity,
        },
    }), 200
    
@user_bp.route("/api/business/<business_id>/runs/latest", methods=["GET"])
def get_latest_run(business_id):
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
            "error": "You do not have permission to view this business"
        }), 403

    runs = list(business_ref.collection("agent_runs").stream())

    if not runs:
        return jsonify({
            "success": True,
            "business_id": business_id,
            "run": None,
        }), 200

    latest = max(runs, key=lambda run: run.to_dict().get("created_at", ""))
    latest_data = latest.to_dict()

    return jsonify({
        "success": True,
        "business_id": business_id,
        "run": {
            "run_id": latest.id,
            "status": latest_data.get("status"),
            "observation_id": latest_data.get("observation_id"),
            "opportunity_ids": latest_data.get("opportunity_ids"),
            "error": latest_data.get("error"),
            "created_at": latest_data.get("created_at"),
            "completed_at": latest_data.get("completed_at"),
        },
    }), 200

@user_bp.route( "/api/business/<business_id>/actions/<action_id>/approve", methods=["POST"],)
def approve_action(business_id, action_id):
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({
            "success": False,
            "error": "Authentication required",
        }), 401

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
            "error": "You do not have permission to modify this business",
        }), 403

    action_ref = (
        business_ref
        .collection("actions")
        .document(action_id)
    )

    action_doc = action_ref.get()

    if not action_doc.exists:
        return jsonify({
            "success": False,
            "error": "Action not found",
        }), 404

    action = action_doc.to_dict()

    if action.get("owner_id") != user_id:
        return jsonify({
            "success": False,
            "error": "You do not have permission to modify this action",
        }), 403

    # ---------------------------------------------------------
    # Atomic approval
    # ---------------------------------------------------------

    transaction = db.transaction()

    @firestore.transactional
    def approve_transaction(transaction):
        snapshot = action_ref.get(transaction=transaction)

        if not snapshot.exists:
            raise ValueError("Action not found")

        current_action = snapshot.to_dict()

        if current_action.get("owner_id") != user_id:
            raise PermissionError(
                "You do not have permission to modify this action"
            )

        current_status = current_action.get("status")

        if current_status == "approved":
            return {
                "already_approved": True,
                "execution_id": current_action.get("execution_id"),
            }

        if current_status != "pending_approval":
            raise ValueError(
                "Only pending actions can be approved"
            )

        now = datetime.utcnow().isoformat()

        execution_ref = (
            business_ref
            .collection("executions")
            .document()
        )

        execution_id = execution_ref.id

        transaction.update(
            action_ref,
            {
                "status": "approved",
                "approved_at": now,
                "approved_by": user_id,
                "execution_id": execution_id,
                "updated_at": now,
            },
        )

        transaction.set(
            execution_ref,
            {
                "business_id": business_id,
                "owner_id": user_id,
                "action_id": action_id,
                "status": "queued",
                "created_at": now,
                "updated_at": now,
            },
        )

        return {
            "already_approved": False,
            "execution_id": execution_id,
        }

    try:
        result = approve_transaction(transaction)

    except PermissionError as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), 403

    except ValueError as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), 400

    # ---------------------------------------------------------
    # Already approved = do NOT create another execution
    # ---------------------------------------------------------

    if result["already_approved"]:
        execution_id = result.get("execution_id")

        return jsonify({
            "success": True,
            "message": "Action has already been approved",
            "action_id": action_id,
            "execution_id": execution_id,
            "status": "approved",
            "already_approved": True,
        }), 200

    # ---------------------------------------------------------
    # Queue exactly one newly-created execution
    # ---------------------------------------------------------

    execution_id = result["execution_id"]

    try:
        task = execute_approved_action.delay(
            business_id,
            execution_id,
        )

        execution_ref = (
            business_ref
            .collection("executions")
            .document(execution_id)
        )

        execution_ref.update({
            "task_id": task.id,
            "updated_at": datetime.utcnow().isoformat(),
        })

    except Exception as exc:
        execution_ref = (
            business_ref
            .collection("executions")
            .document(execution_id)
        )

        execution_ref.update({
            "status": "failed",
            "error": f"Failed to queue execution: {str(exc)}",
            "updated_at": datetime.utcnow().isoformat(),
        })

        return jsonify({
            "success": False,
            "error": "Action was approved, but execution could not be queued",
            "action_id": action_id,
            "execution_id": execution_id,
        }), 500

    return jsonify({
        "success": True,
        "message": "Action approved and execution queued",
        "action_id": action_id,
        "execution_id": execution_id,
        "task_id": task.id,
        "status": "approved",
        "next_phase": "execution",
        "already_approved": False,
    }), 202
    
@user_bp.route( "/api/business/<business_id>/actions/<action_id>/reject",methods=["POST"] )
def reject_action(business_id, action_id):
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
            "error": "You do not have permission to modify this business"
        }), 403

    action_ref = (
        business_ref
        .collection("actions")
        .document(action_id)
    )

    action_doc = action_ref.get()

    if not action_doc.exists:
        return jsonify({
            "success": False,
            "error": "Action not found"
        }), 404

    action = action_doc.to_dict()

    if action.get("owner_id") != user_id:
        return jsonify({
            "success": False,
            "error": "You do not have permission to modify this action"
        }), 403

    if action.get("status") != "pending_approval":
        return jsonify({
            "success": False,
            "error": "Only pending actions can be rejected"
        }), 400

    now = datetime.utcnow().isoformat()

    action_ref.update({
        "status": "rejected",
        "rejected_at": now,
        "rejected_by": user_id,
        "updated_at": now,
    })

    return jsonify({
        "success": True,
        "message": "Action rejected",
        "action_id": action_id,
        "status": "rejected",
    }), 200

@user_bp.route( "/api/business/<business_id>/actions/<action_id>", methods=["GET"])
def get_action(business_id, action_id):
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
            "error": "You do not have permission to view this business"
        }), 403

    action_ref = (
        business_ref
        .collection("actions")
        .document(action_id)
    )

    action_doc = action_ref.get()

    if not action_doc.exists:
        return jsonify({
            "success": False,
            "error": "Action not found"
        }), 404

    action = action_doc.to_dict()

    if action.get("owner_id") != user_id:
        return jsonify({
            "success": False,
            "error": "You do not have permission to view this action"
        }), 403

    return jsonify({
        "success": True,
        "action": {
            "id": action_doc.id,
            **action,
        },
    }), 200

@user_bp.route( "/api/business/<business_id>/actions", methods=["GET"] )
def get_business_actions(business_id):
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
            "error": "You do not have permission to view this business"
        }), 403

    actions_query = (
        business_ref
        .collection("actions")
        .where("owner_id", "==", user_id)
    )

    status = request.args.get("status")

    if status:
        actions_query = actions_query.where(
            "status",
            "==",
            status
        )

    actions = []

    for doc in actions_query.stream():
        actions.append({
            "id": doc.id,
            **doc.to_dict(),
        })

    return jsonify({
        "success": True,
        "business_id": business_id,
        "actions": actions,
    }), 200
    
@user_bp.route(
    "/api/business/<business_id>/executions/test",
    methods=["POST"],
)
def test_action_execution(business_id):
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({
            "success": False,
            "error": "Authentication required",
        }), 401

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
            "error": "You do not have permission to execute actions for this business",
        }), 403

    data = request.get_json(silent=True) or {}
    action_id = data.get("action_id", "").strip()

    if not action_id:
        return jsonify({
            "success": False,
            "error": "action_id is required",
        }), 400

    action_ref = (
        business_ref
        .collection("actions")
        .document(action_id)
    )

    action_doc = action_ref.get()

    if not action_doc.exists:
        return jsonify({
            "success": False,
            "error": "Action not found",
        }), 404

    action = action_doc.to_dict()

    if action.get("owner_id") != user_id:
        return jsonify({
            "success": False,
            "error": "You do not have permission to execute this action",
        }), 403

    if action.get("status") != "approved":
        return jsonify({
            "success": False,
            "error": "Only approved actions can be executed",
        }), 400

    execution_ref = (
        business_ref
        .collection("executions")
        .document()
    )

    execution_id = execution_ref.id

    now = datetime.utcnow().isoformat()

    execution_ref.set({
        "business_id": business_id,
        "owner_id": user_id,
        "action_id": action_id,
        "status": "queued",
        "created_at": now,
        "updated_at": now,
    })

    task = execute_approved_action.delay(
        business_id,
        execution_id,
    )

    execution_ref.update({
        "task_id": task.id,
    })

    return jsonify({
        "success": True,
        "message": "Action execution queued",
        "execution_id": execution_id,
        "task_id": task.id,
        "status": "queued",
    }), 202
    
@user_bp.route(
    "/api/business/<business_id>/actions/dry-run",
    methods=["POST"],
)
def create_dry_run_action(business_id):
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({
            "success": False,
            "error": "Authentication required",
        }), 401

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
            "error": "You do not have permission to modify this business",
        }), 403

    now = datetime.utcnow().isoformat()

    action_ref = (
        business_ref
        .collection("actions")
        .document()
    )

    action = {
        "business_id": business_id,
        "owner_id": user_id,
        "action_type": "dry_run",
        "title": "Execution pipeline test",
        "description": "Safe dry-run test of the action execution pipeline.",
        "requires_approval": True,
        "status": "approved",
        "created_at": now,
        "updated_at": now,
    }

    action_ref.set(action)

    return jsonify({
        "success": True,
        "message": "Dry-run action created",
        "action": {
            "id": action_ref.id,
            **action,
        },
    }), 201
    
@user_bp.route(
    "/api/business/<business_id>/executions/<execution_id>",
    methods=["GET"],
)
def get_execution_status(business_id, execution_id):
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({
            "success": False,
            "error": "Authentication required",
        }), 401

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
            "error": "You do not have permission to view this business",
        }), 403

    execution_ref = (
        business_ref
        .collection("executions")
        .document(execution_id)
    )

    execution_doc = execution_ref.get()

    if not execution_doc.exists:
        return jsonify({
            "success": False,
            "error": "Execution not found",
        }), 404

    execution = execution_doc.to_dict()

    if execution.get("owner_id") != user_id:
        return jsonify({
            "success": False,
            "error": "You do not have permission to view this execution",
        }), 403

    return jsonify({
        "success": True,
        "execution": {
            "id": execution_doc.id,
            **execution,
        },
    }), 200
    
@user_bp.route(
    "/api/business/<business_id>/actions/test-approval",
    methods=["POST"],
)
def create_test_approval_action(business_id):
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({
            "success": False,
            "error": "Authentication required",
        }), 401

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
            "error": "You do not have permission to modify this business",
        }), 403

    now = datetime.utcnow().isoformat()

    action_ref = (
        business_ref
        .collection("actions")
        .document()
    )

    action = {
        "business_id": business_id,
        "owner_id": user_id,
        "title": "Test approval workflow",
        "action_type": "dry_run",
        "objective": "Verify the approval-to-execution workflow.",
        "description": "Safe development test of action approval and execution.",
        "reasoning": "Used to verify the production approval pipeline without external side effects.",
        "expected_outcome": "Dry-run execution completes successfully.",
        "required_inputs": [],
        "requires_approval": True,
        "status": "pending_approval",
        "created_at": now,
        "updated_at": now,
    }

    action_ref.set(action)

    return jsonify({
        "success": True,
        "message": "Test approval action created",
        "action": {
            "id": action_ref.id,
            **action,
        },
    }), 201
    
@user_bp.route(
    "/api/business/<business_id>/measurements",
    methods=["GET"],
)
def get_business_measurements(business_id):
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({
            "success": False,
            "error": "Authentication required",
        }), 401

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

    measurements_query = (
        business_ref
        .collection("measurements")
    )

    execution_id = request.args.get("execution_id")

    if execution_id:
        measurements_query = measurements_query.where(
            "execution_id",
            "==",
            execution_id,
        )

    metric = request.args.get("metric")

    if metric:
        measurements_query = measurements_query.where(
            "metric",
            "==",
            metric,
        )

    measurements = []

    for doc in measurements_query.stream():
        measurement = doc.to_dict()

        measurements.append({
            "id": doc.id,
            **measurement,
        })

    return jsonify({
        "success": True,
        "business_id": business_id,
        "measurements": measurements,
    }), 200
    
@user_bp.route(
    "/api/business/<business_id>/learnings",
    methods=["GET"],
)
def get_business_learnings(business_id):
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({
            "success": False,
            "error": "Authentication required",
        }), 401

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

    learnings_query = (
        business_ref
        .collection("learnings")
    )

    execution_id = request.args.get("execution_id")

    if execution_id:
        learnings_query = learnings_query.where(
            "execution_id",
            "==",
            execution_id,
        )

    outcome = request.args.get("outcome")

    if outcome:
        learnings_query = learnings_query.where(
            "outcome",
            "==",
            outcome,
        )

    learnings = []

    for doc in learnings_query.stream():
        learning = doc.to_dict()

        learnings.append({
            "id": doc.id,
            **learning,
        })

    return jsonify({
        "success": True,
        "business_id": business_id,
        "learnings": learnings,
    }), 200
    

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

