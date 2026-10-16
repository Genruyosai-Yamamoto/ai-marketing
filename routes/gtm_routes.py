"""
GTM Routes (routes.gtm_routes).

API Blueprint for Visual GTM Operating System:
- POST /api/gtm/run: Dispatch a background GTM visual analysis run
- GET /api/gtm/runs: List historical GTM runs for a business
- GET /api/gtm/runs/<run_id>: Get full run telemetry and visual scores
- GET /api/gtm/runs/<run_id>/dossier: Download executive Markdown dossier
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request, session, current_app, send_file
from firebase import db

gtm_bp = Blueprint("gtm_bp", __name__)


def _verify_business_ownership(business_id: str, user_id: str):
    """Verify that business exists and belongs to the authenticated user."""
    business_ref = db.collection("businesses").document(business_id)
    doc = business_ref.get()
    if not doc.exists:
        return None, (jsonify({"success": False, "error": "Business not found"}), 404)

    business_data = doc.to_dict() or {}
    if business_data.get("owner_id") != user_id:
        return None, (jsonify({"success": False, "error": "Unauthorized"}), 403)

    return business_data, None


@gtm_bp.route("/api/gtm/run", methods=["POST"])
def trigger_gtm_run():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    business_id = payload.get("business_id")
    if not business_id:
        return jsonify({"success": False, "error": "Missing business_id"}), 400

    business_data, error_resp = _verify_business_ownership(business_id, user_id)
    if error_resp:
        return error_resp

    now = datetime.utcnow().isoformat()
    run_ref = (
        db.collection("businesses")
        .document(business_id)
        .collection("gtm_runs")
        .document()
    )

    run_id = str(run_ref.id)
    initial_run_data = {
        "id": run_id,
        "business_id": business_id,
        "user_id": user_id,
        "status": "queued",
        "created_at": now,
        "website_url": business_data.get("website_url"),
    }
    run_ref.set(initial_run_data)

    try:
        from task import run_gtm_analysis
        task_res = run_gtm_analysis.delay(
            business_id=business_id,
            user_id=user_id,
            run_id=run_id,
        )
        run_ref.update({"celery_task_id": str(task_res.id)})
    except Exception as exc:
        current_app.logger.warning("Could not dispatch Celery task immediately: %s", exc)

    return jsonify({
        "success": True,
        "message": "GTM analysis queued successfully",
        "run_id": run_id,
    }), 202


@gtm_bp.route("/api/gtm/runs", methods=["GET"])
def list_gtm_runs():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    business_id = request.args.get("business_id")
    if not business_id:
        return jsonify({"success": False, "error": "Missing business_id"}), 400

    _, error_resp = _verify_business_ownership(business_id, user_id)
    if error_resp:
        return error_resp

    runs_ref = (
        db.collection("businesses")
        .document(business_id)
        .collection("gtm_runs")
        .order_by("created_at", direction="DESCENDING")
    )
    docs = runs_ref.stream()
    runs = [{"id": doc.id, **doc.to_dict()} for doc in docs]

    return jsonify({
        "success": True,
        "runs": runs,
    }), 200


@gtm_bp.route("/api/gtm/runs/<run_id>", methods=["GET"])
def get_gtm_run(run_id: str):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    business_id = request.args.get("business_id")
    if not business_id:
        return jsonify({"success": False, "error": "Missing business_id"}), 400

    _, error_resp = _verify_business_ownership(business_id, user_id)
    if error_resp:
        return error_resp

    run_ref = (
        db.collection("businesses")
        .document(business_id)
        .collection("gtm_runs")
        .document(run_id)
    )
    doc = run_ref.get()
    if not doc.exists:
        return jsonify({"success": False, "error": "GTM run not found"}), 404

    return jsonify({
        "success": True,
        "run": {"id": doc.id, **doc.to_dict()},
    }), 200


@gtm_bp.route("/api/gtm/runs/<run_id>/dossier", methods=["GET"])
def get_gtm_dossier(run_id: str):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    business_id = request.args.get("business_id")
    if not business_id:
        return jsonify({"success": False, "error": "Missing business_id"}), 400

    _, error_resp = _verify_business_ownership(business_id, user_id)
    if error_resp:
        return error_resp

    run_ref = (
        db.collection("businesses")
        .document(business_id)
        .collection("gtm_runs")
        .document(run_id)
    )
    doc = run_ref.get()
    if not doc.exists:
        return jsonify({"success": False, "error": "GTM run not found"}), 404

    run_data = doc.to_dict() or {}
    dossier_path = run_data.get("dossier_path")
    if not dossier_path or not Path(dossier_path).exists():
        # Generate inline if not yet saved to file
        from services.gtm_dossier_service import generate_gtm_dossier_markdown
        content = generate_gtm_dossier_markdown(run_data)
        return content, 200, {"Content-Type": "text/markdown; charset=utf-8"}

    return send_file(dossier_path, mimetype="text/markdown", as_attachment=False)
