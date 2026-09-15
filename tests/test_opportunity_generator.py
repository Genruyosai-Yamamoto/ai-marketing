import json

import pytest

from agent import prompts


class _Fake:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)


class _Choice:
    def __init__(self, content):
        self.message = _Fake(content=content)


class _Response:
    def __init__(self, content):
        self.choices = [_Choice(content)]


VALID_ITEM = {
    "title": "Missing pricing page",
    "description": "No pricing info visible.",
    "problem": "Pricing transparency gap.",
    "evidence": ["No pricing links found in navigation"],
    "potential_impact": "high",
    "confidence": 0.9,
    "type": "conversion",
}

ANALYSIS = {
    "business_summary": "ACME sells widgets.",
    "target_audience": "SMB owners.",
    "value_proposition": "Fast, reliable widgets.",
    "products_or_services": ["Widgets"],
    "strengths": ["Clear product page"],
    "weaknesses": ["No pricing info"],
    "marketing_signals": [],
    "missing_information": ["Pricing"],
}


@pytest.fixture
def og(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    import agent.opportunity_generator as module
    return module


@pytest.fixture
def fake_client(monkeypatch):
    state = {"calls": []}

    def build(content):
        def create(*, model=None, messages=None, temperature=None):
            state["calls"].append(
                {"model": model, "messages": messages, "temperature": temperature}
            )
            return _Response(content)

        return _Fake(chat=_Fake(completions=_Fake(create=create)))

    state["build"] = build
    return state


def test_valid_array_returns_validated_opportunities(og, fake_client, monkeypatch):
    payload = json.dumps([VALID_ITEM])
    monkeypatch.setattr(og, "client", fake_client["build"](payload))
    result = og.generate_opportunities(ANALYSIS)
    assert result == [VALID_ITEM]
    call = fake_client["calls"][0]
    assert call["model"] == "llama-3.3-70b-versatile"
    assert call["temperature"] == 0.2
    assert call["messages"][0]["content"] == prompts.OPPORTUNITY_GENERATION_SYSTEM_PROMPT
    assert "ACME sells widgets." in call["messages"][1]["content"]


def test_model_reads_groq_model_env(og, fake_client, monkeypatch):
    monkeypatch.setenv("GROQ_MODEL", "custom-model")
    monkeypatch.setattr(og, "client", fake_client["build"](json.dumps([VALID_ITEM])))
    og.generate_opportunities(ANALYSIS)
    assert fake_client["calls"][0]["model"] == "custom-model"


def test_empty_response_raises(og, fake_client, monkeypatch):
    monkeypatch.setattr(og, "client", fake_client["build"](None))
    with pytest.raises(ValueError, match="Groq returned an empty response"):
        og.generate_opportunities(ANALYSIS)


def test_invalid_json_raises(og, fake_client, monkeypatch):
    monkeypatch.setattr(og, "client", fake_client["build"]("not json"))
    with pytest.raises(ValueError, match="Groq returned invalid opportunity JSON"):
        og.generate_opportunities(ANALYSIS)


def test_non_array_raises(og, fake_client, monkeypatch):
    monkeypatch.setattr(og, "client", fake_client["build"]('{"a": 1}'))
    with pytest.raises(ValueError, match="Opportunity response must be a JSON array"):
        og.generate_opportunities(ANALYSIS)


def test_schema_violation_raises(og, fake_client, monkeypatch):
    broken = dict(VALID_ITEM, confidence=2)
    monkeypatch.setattr(og, "client", fake_client["build"](json.dumps([broken])))
    with pytest.raises(ValueError, match="confidence 2 out of range"):
        og.generate_opportunities(ANALYSIS)