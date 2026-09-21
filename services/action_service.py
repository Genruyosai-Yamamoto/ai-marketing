from datetime import datetime

from firebase import db


def create_action(
    business_id,
    opportunity_id,
    action,
    owner_id,
):
    if not business_id:
        raise ValueError("business_id is required")

    if not owner_id:
        raise ValueError("owner_id is required")

    if not opportunity_id:
        raise ValueError("opportunity_id is required")

    if not isinstance(action, dict):
        raise ValueError("action must be a dictionary")

    required_fields = {
        "action_title",
        "action_type",
        "objective",
        "description",
        "reasoning",
        "expected_outcome",
        "required_inputs",
        "requires_approval",
    }

    missing_fields = required_fields - action.keys()

    if missing_fields:
        raise ValueError(
            f"Action is missing required fields: "
            f"{sorted(missing_fields)}"
        )

    business_ref = db.collection("businesses").document(business_id)
    business_doc = business_ref.get()

    if not business_doc.exists:
        raise ValueError("Business not found")

    opportunity_ref = (
        business_ref
        .collection("opportunities")
        .document(opportunity_id)
    )

    opportunity_doc = opportunity_ref.get()

    if not opportunity_doc.exists:
        raise ValueError("Opportunity not found")

    opportunity = opportunity_doc.to_dict()

    now = datetime.utcnow().isoformat()

    action_data = {
        "business_id": business_id,
        "owner_id": owner_id,
        "opportunity_id": opportunity_id,
        "action_title": action["action_title"],
        "action_type": action["action_type"],
        "objective": action["objective"],
        "description": action["description"],
        "reasoning": action["reasoning"],
        "expected_outcome": action["expected_outcome"],
        "required_inputs": action["required_inputs"],
        "requires_approval": action["requires_approval"],
        "status": "pending_approval",
        "content_type": action["content_type"],
        "page_url": action["page_url"],
        "content": action["content"],
        "created_at": now,
        "updated_at": now,
    }

    action_ref = (
        business_ref
        .collection("actions")
        .document()
    )

    action_ref.set(action_data)

    return {
        "id": action_ref.id,
        **action_data,
    }