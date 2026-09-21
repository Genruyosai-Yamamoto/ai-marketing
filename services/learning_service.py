from datetime import datetime
from agent.learning_generator import generate_learning_from_measurement
from firebase import db


def create_learning(
    business_id,
    execution_id,
    observation,
    outcome,
    learning,
    confidence,
    learning_type,
    metric=None,
    previous_value=None,
    value=None,
    direction=None,
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
    
    if not learning_type:
        raise ValueError("learning_type is required")

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
    
    action_id = execution.get("action_id")

    if not action_id:
        raise ValueError("Execution has no action_id")

    action_ref = (
        business_ref
        .collection("actions")
        .document(action_id)
    )

    action_doc = action_ref.get()

    if not action_doc.exists:
        raise ValueError("Action not found")

    action = action_doc.to_dict()

    now = datetime.utcnow().isoformat()

    learning_ref = (
        business_ref
        .collection("learnings")
        .document()
    )

    learning_data = {
        "business_id": business_id,
        "execution_id": execution_id,
        "action_id": action_id,
        "action_type": action.get("action_type"),
        "learning_type": learning_type,
        "metric": metric,
        "previous_value": previous_value,
        "value": value,
        "direction": direction,
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

def create_learning_from_measurement(
    business_id,
    measurement_id,
):
    """
    Generate and persist a learning from an existing measurement.
    """

    if not business_id:
        raise ValueError("business_id is required")

    if not measurement_id:
        raise ValueError("measurement_id is required")

    business_ref = (
        db.collection("businesses")
        .document(business_id)
    )

    business_doc = business_ref.get()

    if not business_doc.exists:
        raise ValueError("Business not found")

    measurement_ref = (
        business_ref
        .collection("measurements")
        .document(measurement_id)
    )

    measurement_doc = measurement_ref.get()

    if not measurement_doc.exists:
        raise ValueError("Measurement not found")

    measurement = measurement_doc.to_dict()

    execution_id = measurement.get("execution_id")

    if not execution_id:
        raise ValueError(
            "Measurement has no execution_id"
        )

    generated_learning = generate_learning_from_measurement(
        measurement
    )

    return create_learning(
        business_id=business_id,
        execution_id=execution_id,
        observation=generated_learning["observation"],
        outcome=generated_learning["outcome"],
        learning=generated_learning["learning"],
        confidence=generated_learning["confidence"],
        learning_type=generated_learning["learning_type"],
        metric=generated_learning.get("metric"),
        previous_value=generated_learning.get("previous_value"),
        value=generated_learning.get("value"),
        direction=generated_learning.get("direction"),
    )
    
def get_business_learnings(
    business_id,
    limit=20,
    action_type=None,
    learning_type=None,
):
    """
    Retrieve recent learnings for a business.
    """

    if not business_id:
        raise ValueError("business_id is required")

    try:
        limit = int(limit)
    except (TypeError, ValueError):
        raise ValueError("limit must be a number")

    if limit <= 0:
        raise ValueError("limit must be greater than 0")

    business_ref = (
        db.collection("businesses")
        .document(business_id)
    )

    business_doc = business_ref.get()

    if not business_doc.exists:
        raise ValueError("Business not found")

    learnings_query = (
        business_ref
        .collection("learnings")
        .order_by("created_at", direction="DESCENDING")
        .limit(limit)
    )

    learnings = []

    for doc in learnings_query.stream():
        learning = doc.to_dict()

        learnings.append({
            "id": doc.id,
            **learning,
        })

    if action_type:
        learnings = [
            learning
            for learning in learnings
            if learning.get("action_type") == action_type
        ]
    
    if learning_type:
        learnings = [
            learning
            for learning in learnings
            if learning.get("learning_type") == learning_type
        ]

    return learnings