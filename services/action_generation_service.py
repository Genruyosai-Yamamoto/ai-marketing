from agent.decision_engine import generate_action
from services.action_service import create_action


def generate_and_create_action(
    business_id,
    opportunity_id,
    business_analysis,
):
    if not business_id:
        raise ValueError("business_id is required")

    if not opportunity_id:
        raise ValueError("opportunity_id is required")

    if not business_analysis:
        raise ValueError("business_analysis is required")

    from firebase import db

    opportunity_ref = (
        db.collection("businesses")
        .document(business_id)
        .collection("opportunities")
        .document(opportunity_id)
    )

    opportunity_doc = opportunity_ref.get()

    if not opportunity_doc.exists:
        raise ValueError("Opportunity not found")

    opportunity = opportunity_doc.to_dict()

    action = generate_action(
        opportunity=opportunity,
        business_analysis=business_analysis,
        business_id=business_id,
    )

    return create_action(
        business_id=business_id,
        opportunity_id=opportunity_id,
        action=action,
        owner_id=opportunity.get("owner_id"),
    )