_IMPACT_RANKS = {"low": 0, "medium": 1, "high": 2}
_ALLOWED_TYPES = {"website", "content", "seo", "conversion", "social", "other"}
_REQUIRED_KEYS = (
    "title",
    "description",
    "problem",
    "evidence",
    "potential_impact",
    "confidence",
    "type",
)


def validate_opportunity_item(item, index=0):
    """Validate one opportunity dict. Raises ValueError on any defect,
    otherwise returns the item unchanged. Extra keys are tolerated."""
    prefix = f"Opportunity {index}"

    if not isinstance(item, dict):
        raise ValueError(f"{prefix}: must be a dict")

    for key in _REQUIRED_KEYS:
        if key not in item:
            raise ValueError(f"{prefix}: missing key '{key}'")

    for key in ("title", "description", "problem"):
        value = item.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{prefix}: '{key}' must be a non-empty string")

    evidence = item.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError(f"{prefix}: 'evidence' must be a non-empty list of strings")
    for entry in evidence:
        if not isinstance(entry, str) or not entry.strip():
            raise ValueError(f"{prefix}: 'evidence' must be a non-empty list of strings")

    impact = item.get("potential_impact")
    if not isinstance(impact, str) or impact not in _IMPACT_RANKS:
        raise ValueError(
            f"{prefix}: potential_impact {impact!r} not in {sorted(_IMPACT_RANKS)}"
        )

    otype = item.get("type")
    if not isinstance(otype, str) or otype not in _ALLOWED_TYPES:
        raise ValueError(f"{prefix}: type {otype!r} not in {sorted(_ALLOWED_TYPES)}")

    confidence = item.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError(f"{prefix}: 'confidence' must be a number")
    if not 0 <= confidence <= 1:
        raise ValueError(f"{prefix}: confidence {confidence} out of range [0, 1]")

    return item


def validate_opportunities(items):
    """Validate an opportunity list: must be a list of 0-5 valid items,
    strictly ordered by (impact rank, confidence) both descending.
    Returns the items unchanged."""
    if not isinstance(items, list):
        raise ValueError("Opportunity response must be a JSON array")
    if len(items) > 5:
        raise ValueError(f"expected at most 5 opportunities, got {len(items)}")

    for index, item in enumerate(items):
        validate_opportunity_item(item, index)

    for index in range(1, len(items)):
        rank = _IMPACT_RANKS[items[index]["potential_impact"]]
        conf = items[index]["confidence"]
        prev_rank = _IMPACT_RANKS[items[index - 1]["potential_impact"]]
        prev_conf = items[index - 1]["confidence"]
        if rank > prev_rank or (rank == prev_rank and conf > prev_conf):
            raise ValueError(f"opportunities out of order at index {index}")

    return items