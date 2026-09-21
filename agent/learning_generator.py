def generate_learning_from_measurement(measurement):
    """
    Generate a structured learning from a measurement.

    Supports:
    - operational execution measurements
    - marketing before/after measurements

    This version is deterministic and does not use an LLM.
    """

    if not measurement:
        raise ValueError("measurement is required")

    metric = measurement.get("metric")
    value = measurement.get("value")

    if not metric:
        raise ValueError("measurement metric is required")

    if value is None:
        raise ValueError("measurement value is required")

    # ---------------------------------------------------------
    # Operational measurement
    # ---------------------------------------------------------

    if metric == "execution_success":
        if value == 1:
            return {
                "learning_type": "operational",
                "observation": (
                    "The approved action completed successfully."
                ),
                "outcome": "success",
                "learning": (
                    "The action execution pathway completed successfully."
                ),
                "confidence": 1.0,
            }

        return {
            "learning_type": "operational",
            "observation": (
                "The approved action did not complete successfully."
            ),
            "outcome": "failure",
            "learning": (
                "The action execution pathway did not complete successfully."
            ),
            "confidence": 1.0,
        }

    # ---------------------------------------------------------
    # Marketing before/after measurement
    # ---------------------------------------------------------

    previous_value = measurement.get("previous_value")

    if previous_value is not None:
        try:
            previous_value = float(previous_value)
            current_value = float(value)
        except (TypeError, ValueError):
            raise ValueError(
                "previous_value and value must be numbers"
            )

        if current_value > previous_value:
            outcome = "positive"
            direction = "increase"

            observation = (
                f"The metric '{metric}' increased from "
                f"{previous_value} to {current_value}."
            )

            learning = (
                f"The measured '{metric}' was higher after the action."
            )

        elif current_value < previous_value:
            outcome = "negative"
            direction = "decrease"

            observation = (
                f"The metric '{metric}' decreased from "
                f"{previous_value} to {current_value}."
            )

            learning = (
                f"The measured '{metric}' was lower after the action."
            )

        else:
            outcome = "neutral"
            direction = "unchanged"

            observation = (
                f"The metric '{metric}' remained unchanged at "
                f"{current_value}."
            )

            learning = (
                f"The measured '{metric}' showed no change after the action."
            )

        return {
            "learning_type": "marketing",
            "metric": metric,
            "previous_value": previous_value,
            "value": current_value,
            "direction": direction,
            "observation": observation,
            "outcome": outcome,
            "learning": learning,
            "confidence": 0.7,
        }
        

    # ---------------------------------------------------------
    # Generic marketing measurement
    # ---------------------------------------------------------

    return {
        "learning_type": "marketing",
        "observation": (
            f"The metric '{metric}' was recorded with a value of {value}."
        ),
        "outcome": "measured",
        "learning": (
            f"The metric '{metric}' has been observed and should be "
            "considered in future decisions."
        ),
        "confidence": 0.5,
    }