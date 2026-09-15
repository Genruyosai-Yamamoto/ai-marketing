import pytest

import agent.opportunity_validation as v


def _valid_item(**overrides):
    item = {
        "title": "Missing pricing page",
        "description": "No pricing information visible on the site.",
        "problem": "Pricing transparency gap on the home page.",
        "evidence": ["No pricing links found in navigation"],
        "potential_impact": "high",
        "confidence": 0.9,
        "type": "conversion",
    }
    item.update(overrides)
    return item


def test_valid_full_list_passes():
    items = [
        _valid_item(potential_impact="high", confidence=0.9),
        _valid_item(potential_impact="medium", confidence=0.8),
        _valid_item(potential_impact="medium", confidence=0.5),
        _valid_item(potential_impact="low", confidence=0.7),
        _valid_item(potential_impact="low", confidence=0.4),
    ]
    assert v.validate_opportunities(items) == items


def test_empty_list_valid():
    assert v.validate_opportunities([]) == []


@pytest.mark.parametrize("key", v._REQUIRED_KEYS)
def test_missing_key_raises(key):
    item = _valid_item()
    del item[key]
    with pytest.raises(ValueError, match=f"missing key '{key}'"):
        v.validate_opportunity_item(item, 0)


def test_non_dict_item_raises():
    with pytest.raises(ValueError, match="Opportunity 0: must be a dict"):
        v.validate_opportunity_item(42)


@pytest.mark.parametrize("key", ["title", "description", "problem"])
@pytest.mark.parametrize("bad", ["", "   ", 42, None])
def test_string_fields_reject_bad_values(key, bad):
    with pytest.raises(ValueError, match=f"'{key}' must be a non-empty string"):
        v.validate_opportunity_item(_valid_item(**{key: bad}))


@pytest.mark.parametrize("bad", [[], ["ok", 3], ["ok", ""], "nope"])
def test_evidence_rejects_bad_values(bad):
    with pytest.raises(ValueError, match="'evidence' must be a non-empty list of strings"):
        v.validate_opportunity_item(_valid_item(evidence=bad))


def test_bad_potential_impact_raises():
    with pytest.raises(ValueError, match=r"potential_impact 'critical' not in"):
        v.validate_opportunity_item(_valid_item(potential_impact="critical"))


@pytest.mark.parametrize("bad", [{}, [], ["high"]])
def test_unhashable_potential_impact_raises(bad):
    with pytest.raises(ValueError, match="potential_impact"):
        v.validate_opportunity_item(_valid_item(potential_impact=bad))


def test_bad_type_raises():
    with pytest.raises(ValueError, match=r"type 'ads' not in"):
        v.validate_opportunity_item(_valid_item(type="ads"))


@pytest.mark.parametrize("bad", [{}, [], ["website"]])
def test_unhashable_type_raises(bad):
    with pytest.raises(ValueError, match="type"):
        v.validate_opportunity_item(_valid_item(type=bad))


@pytest.mark.parametrize("bad", ["0.5", True, None])
def test_confidence_must_be_number(bad):
    with pytest.raises(ValueError, match="'confidence' must be a number"):
        v.validate_opportunity_item(_valid_item(confidence=bad))


@pytest.mark.parametrize("bad", [1.2, -0.1, 2])
def test_confidence_out_of_range_raises(bad):
    with pytest.raises(ValueError, match=r"confidence -?[\d.]+ out of range \[0, 1\]"):
        v.validate_opportunity_item(_valid_item(confidence=bad))


def test_more_than_five_raises():
    items = [_valid_item(tag=i) for i in range(6)]
    with pytest.raises(ValueError, match="expected at most 5 opportunities, got 6"):
        v.validate_opportunities(items)


def test_out_of_order_raises():
    items = [
        _valid_item(potential_impact="low", confidence=0.4),
        _valid_item(potential_impact="high", confidence=0.9),
    ]
    with pytest.raises(ValueError, match="opportunities out of order at index 1"):
        v.validate_opportunities(items)


# Ordering is non-increasing, not strictly decreasing: identical (impact,
# confidence) pairs are allowed in any quantity and must pass validation.
def test_ties_are_permitted():
    items = [
        _valid_item(potential_impact="high", confidence=0.9),
        _valid_item(potential_impact="high", confidence=0.9),
    ]
    assert v.validate_opportunities(items) == items


def test_extra_keys_tolerated():
    item = _valid_item(extra="anything")
    assert v.validate_opportunity_item(item) == item


def test_non_list_raises():
    with pytest.raises(ValueError, match="must be a JSON array"):
        v.validate_opportunities({"title": "x"})