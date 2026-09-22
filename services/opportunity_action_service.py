from agent.decision_engine import generate_action
from services.action_service import create_action
from google.cloud.firestore_v1.base_query import FieldFilter

def create_action_from_opportunity(
    business_id,
    opportunity_id,
    owner_id,
    business_analysis,
):
    if not business_id:
        raise ValueError("business_id is required")

    if not opportunity_id:
        raise ValueError("opportunity_id is required")

    if not owner_id:
        raise ValueError("owner_id is required")

    if not isinstance(business_analysis, dict):
        raise ValueError("business_analysis must be a dictionary")

    from firebase import db

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

    opportunity_ref = (
        business_ref
        .collection("opportunities")
        .document(opportunity_id)
    )

    opportunity_doc = opportunity_ref.get()

    if not opportunity_doc.exists:
        raise ValueError("Opportunity not found")

    opportunity = opportunity_doc.to_dict()

    if opportunity.get("owner_id") != owner_id:
        raise ValueError(
            "You do not have permission to use this opportunity"
        )

    decision = generate_action(
        opportunity=opportunity,
        business_analysis=business_analysis,
        business_id=business_id,
    )

    action = create_action(
        business_id=business_id,
        opportunity_id=opportunity_id,
        action=decision,
        owner_id=owner_id,
    )

    return {
        "success": True,
        "opportunity_id": opportunity_id,
        "action": action,
    }

def generate_actions_for_opportunities(
    business_id,
    owner_id,
    business_analysis,
    opportunity_ids=None,
):
    if not business_id:
        raise ValueError("business_id is required")

    if not owner_id:
        raise ValueError("owner_id is required")

    if not isinstance(business_analysis, dict):
        raise ValueError("business_analysis must be a dictionary")

    from firebase import db

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

    if opportunity_ids is None:
        opportunity_docs = (
            business_ref
            .collection("opportunities")
            .where(
                filter=FieldFilter(
                    "status",
                    "==",
                    "identified",
                )
            )
            .stream()
        )
    else:
        opportunity_docs = []

        for opportunity_id in opportunity_ids:
            opportunity_ref = (
                business_ref
                .collection("opportunities")
                .document(opportunity_id)
            )

            opportunity_doc = opportunity_ref.get()

            if opportunity_doc.exists:
                opportunity_docs.append(opportunity_doc)

    created_actions = []
    existing_actions = []

    for opportunity_doc in opportunity_docs:
        opportunity_id = opportunity_doc.id

        existing_action_docs = (
            business_ref
            .collection("actions")
            .where(
                filter=FieldFilter(
                    "opportunity_id",
                    "==",
                    opportunity_id,
                )
            )
            .stream()
        )

        existing_action = None

        for action_doc in existing_action_docs:
            action_data = action_doc.to_dict()

            if action_data.get("status") in {
                "pending_approval",
                "approved",
                "running",
                "completed",
            }:
                existing_action = {
                    "id": action_doc.id,
                    **action_data,
                }
                break

        if existing_action:
            existing_actions.append(existing_action)
            continue

        result = create_action_from_opportunity(
            business_id=business_id,
            opportunity_id=opportunity_id,
            owner_id=owner_id,
            business_analysis=business_analysis,
        )

        created_actions.append(result["action"])

    return {
        "success": True,
        "business_id": business_id,
        "actions_created": len(created_actions),
        "actions_existing": len(existing_actions),
        "actions": created_actions,
        "existing_actions": existing_actions,
    }