from datetime import datetime

from firebase import db


def create_learning(
    business_id,
    execution_id,
    observation,
    outcome,
    learning,
    confidence,
):
    """
    Create a learning record from an execution outcome.

    Args:
        business_id: Business associated with the execution.
        execution_id: Execution that produced the outcome.
        observation: What happened.
        outcome: High-level result, e.g. success or failure.
        learning: What the agent should remember.
        confidence: Confidence score between 0 and 1.

    Returns:
        Dictionary containing the created learning.
    """

    if not business_id:
        raise ValueError("business_id is required")

    if not execution_id:
        raise ValueError("execution_id is required")

    if not observation:
        raise ValueError("observation is required")

    if not outcome:
        raise ValueError("outcome is required")

    if not learning:
        raise ValueError("learning is required")

    if confidence is None:
        raise ValueError("confidence is required")

    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        raise ValueError("confidence must be a number")

    if confidence < 0 or confidence > 1:
        raise ValueError("confidence must be between 0 and 1")

    business_ref = (
        db.collection("businesses")
        .document(business_id)
    )

    business_doc = business_ref.get()

    if not business_doc.exists:
        raise ValueError("Business not found")

    execution_ref = (
        business_ref
        .collection("executions")
        .document(execution_id)
    )

    execution_doc = execution_ref.get()

    if not execution_doc.exists:
        raise ValueError("Execution not found")

    execution = execution_doc.to_dict()

    now = datetime.utcnow().isoformat()

    learning_ref = (
        business_ref
        .collection("learnings")
        .document()
    )

    learning_data = {
        "business_id": business_id,
        "execution_id": execution_id,
        "action_id": execution.get("action_id"),
        "observation": observation,
        "outcome": outcome,
        "learning": learning,
        "confidence": confidence,
        "created_at": now,
    }

    learning_ref.set(learning_data)

    return {
        "id": learning_ref.id,
        **learning_data,
    }