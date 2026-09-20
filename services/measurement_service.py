from datetime import datetime

from firebase import db


def record_measurement(
    business_id,
    execution_id,
    metric,
    value,
    source,
):
    """
    Record a measurement for an execution.

    Args:
        business_id: The business the execution belongs to.
        execution_id: The execution being measured.
        metric: Name of the metric being recorded.
        value: Numeric or boolean metric value.
        source: Where the measurement came from.

    Returns:
        Dictionary containing the created measurement.
    """

    if not business_id:
        raise ValueError("business_id is required")

    if not execution_id:
        raise ValueError("execution_id is required")

    if not metric:
        raise ValueError("metric is required")

    if value is None:
        raise ValueError("value is required")

    if not source:
        raise ValueError("source is required")

    business_ref = db.collection("businesses").document(business_id)

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

    measurement_ref = (
        business_ref
        .collection("measurements")
        .document()
    )

    measurement = {
        "business_id": business_id,
        "execution_id": execution_id,
        "action_id": execution.get("action_id"),
        "metric": metric,
        "value": value,
        "source": source,
        "measured_at": now,
        "created_at": now,
    }

    measurement_ref.set(measurement)

    return {
        "id": measurement_ref.id,
        **measurement,
    }