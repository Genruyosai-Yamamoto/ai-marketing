from datetime import datetime

from firebase import db


def create_opportunity(
    business_id,
    opportunity,
    owner_id,
):
    if not business_id:
        raise ValueError("business_id is required")

    if not owner_id:
        raise ValueError("owner_id is required")

    if not isinstance(opportunity, dict):
        raise ValueError("opportunity must be a dictionary")

    required_fields = {
        "title",
        "description",
        "problem",
        "evidence",
        "potential_impact",
        "confidence",
        "type",
    }

    missing_fields = required_fields - opportunity.keys()

    if missing_fields:
        raise ValueError(
            f"Opportunity is missing required fields: "
            f"{sorted(missing_fields)}"
        )

    business_ref = (
        db.collection("businesses")
        .document(business_id)
    )

    business_doc = business_ref.get()

    if not business_doc.exists:
        raise ValueError("Business not found")

    now = datetime.utcnow().isoformat()

    opportunity_data = {
        "business_id": business_id,
        "owner_id": owner_id,
        "title": opportunity["title"],
        "description": opportunity["description"],
        "problem": opportunity["problem"],
        "evidence": opportunity["evidence"],
        "potential_impact": opportunity["potential_impact"],
        "confidence": opportunity["confidence"],
        "type": opportunity["type"],
        "status": "identified",
        "created_at": now,
        "updated_at": now,
    }

    opportunity_ref = (
        business_ref
        .collection("opportunities")
        .document()
    )

    opportunity_ref.set(opportunity_data)

    return {
        "id": opportunity_ref.id,
        **opportunity_data,
    }