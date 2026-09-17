from flask import Blueprint, jsonify, session

from firebase import db

business_api_bp = Blueprint("business_api", __name__)


@business_api_bp.route("/api/business", methods=["GET"])
def list_businesses():
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({
            "success": False,
            "error": "Authentication required",
        }), 401

    businesses = (
        db.collection("businesses")
        .where("owner_id", "==", user_id)
        .stream()
    )

    business_list = [
        {"id": doc.id, **doc.to_dict()}
        for doc in businesses
    ]

    return jsonify({
        "success": True,
        "businesses": business_list,
    }), 200


@business_api_bp.route("/api/business/<business_id>", methods=["GET"])
def get_business(business_id):
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

    return jsonify({
        "success": True,
        "business": {
            "id": business_doc.id,
            **business,
        },
    }), 200