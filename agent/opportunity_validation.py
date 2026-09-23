import re


def _normalize_problem_key(value):
    if not isinstance(value, str):
        return None

    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value)
    value = value.strip("_")

    if not value:
        return None

    return value

_IMPACT_RANKS = {"low": 0, "medium": 1, "high": 2}
_ALLOWED_TYPES = {"website", "content", "seo", "conversion", "social", "other"}
_REQUIRED_KEYS = {
    "title",
    "description",
    "problem",
    "problem_key",
    "evidence",
    "potential_impact",
    "confidence",
    "type",
}

_ALLOWED_PROBLEM_KEYS = {
    "social_proof",
    "pricing_transparency",
    "value_proposition",
    "support_information",
    "legal_information",
    "seo_visibility",
    "content_gap",
    "conversion_friction",
    "technical_issue",
    "audience_targeting",
    "other",
}


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

    if "problem_key" in item:
        problem_key = _normalize_problem_key(item["problem_key"])

        if not problem_key:
            raise ValueError(
                f"{prefix}: 'problem_key' must be a non-empty string"
            )

        if problem_key not in _ALLOWED_PROBLEM_KEYS:
            raise ValueError(
                f"{prefix}: problem_key {problem_key!r} "
                f"not in {sorted(_ALLOWED_PROBLEM_KEYS)}"
            )

        item["problem_key"] = problem_key

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

    items.sort(
        key=lambda item: (
            _IMPACT_RANKS[item["potential_impact"]],
            item["confidence"],
        ),
        reverse=True,
    )

    return items