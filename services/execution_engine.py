from datetime import datetime
from connectors import get_connector
from services.measurement_service import record_measurement
from services.learning_service import create_learning_from_measurement

from firebase import db


def execute_action(business_id, execution_id):

    business_ref = (
        db.collection("businesses")
        .document(business_id)
    )

    execution_ref = (
        business_ref
        .collection("executions")
        .document(execution_id)
    )

    execution_doc = execution_ref.get()

    if not execution_doc.exists:
        raise ValueError("Execution not found")

    execution = execution_doc.to_dict()
    
    if execution.get("status") == "completed":
        return execution.get("result")

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

    # Critical safety check
    if action.get("status") != "approved":
        raise ValueError(
            "Action must be approved before execution"
        )

    now = datetime.utcnow().isoformat()
    
    if execution.get("status") not in {"queued", "running"}:
        raise ValueError(
            f"Execution cannot start from status: {execution.get('status')}"
        )
    execution_ref.update({
        "status": "running",
        "started_at": now,
        "updated_at": now,
    })

    try:
        connector = get_connector(action)

        result = connector.execute(
            action,
            business_id,
            execution.get("owner_id"),
            execution_id=execution_id,
        )

        execution_ref.update({
            "status": "completed",
            "result": result,
            "completed_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        })
        measurement = record_measurement(
            business_id=business_id,
            execution_id=execution_id,
            metric="execution_success",
            value=1,
            source="execution_engine",
        )

        create_learning_from_measurement(
            business_id=business_id,
            measurement_id=measurement["id"],
        )

        return result

    except Exception as exc:
        execution_ref.update({
            "status": "failed",
            "error": str(exc),
            "completed_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        })

        raise