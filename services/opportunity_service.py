from datetime import datetime
import re
from firebase import db
from google.cloud.firestore_v1.base_query import FieldFilter

def _normalize_text(value):
    if not value:
        return ""

    value = value.lower().strip()
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"[^\w\s]", "", value)

    return value

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

    business = business_doc.to_dict()

    if business.get("owner_id") != owner_id:
        raise ValueError(
            "Owner does not have access to this business"
        )

    existing_opportunity = find_existing_opportunity(
        business_id=business_id,
        opportunity=opportunity,
    )

    if existing_opportunity:
        return {
            **existing_opportunity,
            "already_exists": True,
        }

    now = datetime.utcnow().isoformat()

    opportunity_data = {
        "business_id": business_id,
        "owner_id": owner_id,
        "title": opportunity["title"],
        "description": opportunity["description"],
        "problem_key": opportunity.get("problem_key"),
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
        "already_exists": False,
    }

def find_existing_opportunity(
    business_id,
    opportunity,
):
    if not business_id:
        raise ValueError("business_id is required")

    if not isinstance(opportunity, dict):
        raise ValueError("opportunity must be a dictionary")

    opportunity_type = opportunity.get("type")
    problem_key = opportunity.get("problem_key")
    problem = opportunity.get("problem")

    if not opportunity_type:
        return None

    business_ref = (
        db.collection("businesses")
        .document(business_id)
    )

    opportunity_docs = (
        business_ref
        .collection("opportunities")
        .where(
            filter=FieldFilter(
                "type",
                "==",
                opportunity_type,
            )
        )
        .stream()
    )

    normalized_problem = _normalize_text(problem)

    for opportunity_doc in opportunity_docs:
        existing = opportunity_doc.to_dict()

        existing_problem_key = existing.get("problem_key")

        # New opportunities: use the stable problem key.
        if problem_key and existing_problem_key:
            if existing_problem_key == problem_key:
                return {
                    "id": opportunity_doc.id,
                    **existing,
                }

        # Backward compatibility for old opportunities.
        existing_problem = _normalize_text(
            existing.get("problem")
        )

        if (
            not problem_key
            and normalized_problem
            and existing_problem == normalized_problem
        ):
            return {
                "id": opportunity_doc.id,
                **existing,
            }

    return None