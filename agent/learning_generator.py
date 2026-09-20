def generate_learning_from_measurement(measurement):
    """
    Generate a structured learning from a measurement.

    This first version is deterministic.
    It does not use an LLM.
    """

    if not measurement:
        raise ValueError("measurement is required")

    metric = measurement.get("metric")
    value = measurement.get("value")

    if not metric:
        raise ValueError("measurement metric is required")

    if value is None:
        raise ValueError("measurement value is required")

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