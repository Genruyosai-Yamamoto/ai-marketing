import json
import os

from groq import Groq

from agent.prompts import DECISION_ENGINE_SYSTEM_PROMPT
from services.learning_service import get_business_learnings


client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)

def validate_action(action):
    if not isinstance(action, dict):
        raise ValueError(
            "Action response must be a JSON object"
        )

    required_fields = {
        "action_title",
        "action_type",
        "objective",
        "description",
        "reasoning",
        "expected_outcome",
        "required_inputs",
        "requires_approval",
        "content_type",
        "page_url",
        "content",
    }

    missing_fields = required_fields - action.keys()

    if missing_fields:
        raise ValueError(
            f"Decision Engine response is missing required fields: "
            f"{sorted(missing_fields)}"
        )

    for field in set(action.keys()) - required_fields:
        action.pop(field)

    for field in ("content_type", "page_url", "content"):
        if action[field] is not None and not isinstance(action[field], str):
            raise ValueError(
                f"{field} must be a string or None"
            )

    if not isinstance(action["action_title"], str):
        raise ValueError("action_title must be a string")

    if action["action_type"] not in {
        "website",
        "content",
        "seo",
        "social",
        "email",
        "research",
        "other",
    }:
        raise ValueError(
            f"Invalid action_type: {action['action_type']}"
        )

    if not isinstance(action["objective"], str):
        raise ValueError("objective must be a string")

    if not isinstance(action["description"], str):
        raise ValueError("description must be a string")

    if not isinstance(action["reasoning"], str):
        raise ValueError("reasoning must be a string")

    if not isinstance(action["expected_outcome"], str):
        raise ValueError("expected_outcome must be a string")

    if not isinstance(action["required_inputs"], list):
        raise ValueError("required_inputs must be a list")

    if not all(
        isinstance(item, str)
        for item in action["required_inputs"]
    ):
        raise ValueError(
            "Every required_inputs item must be a string"
        )

    if not isinstance(action["requires_approval"], bool):
        raise ValueError(
            "requires_approval must be a boolean"
        )

    if action["requires_approval"] is not True:
        raise ValueError(
            "requires_approval must be true"
        )

    return action

def generate_action(
    opportunity,
    business_analysis,
    business_id,
):
    """
    Generate a proposed action for a growth opportunity.

    Historical learnings are provided to the model as additional
    context. This function does not execute anything.
    It only creates a proposed action for later approval.
    """

    if not business_id:
        raise ValueError("business_id is required")

    learnings = get_business_learnings(
        business_id=business_id,
        limit=20,
        learning_type="marketing",
    )

    prompt = f"""
Business understanding:

{json.dumps(
    business_analysis,
    indent=2,
    ensure_ascii=False,
)}

Growth opportunity:

{json.dumps(
    opportunity,
    indent=2,
    ensure_ascii=False,
)}

Historical marketing learnings:

{json.dumps(
    learnings,
    indent=2,
    ensure_ascii=False,
)}

Use historical marketing learnings as supporting evidence
when determining the most appropriate action for this opportunity.

A learning represents an observed relationship between an action
and a measured outcome. It does not prove that the action caused
the outcome and does not guarantee the same result in the future.

Prefer relevant historical evidence when it applies to the
current opportunity, but still consider the current business
analysis and opportunity evidence.
"""

    response = client.chat.completions.create(
        model=os.getenv(
            "GROQ_MODEL",
            "llama-3.3-70b-versatile",
        ),
        messages=[
            {
                "role": "system",
                "content": DECISION_ENGINE_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.2,
    )

    result = response.choices[0].message.content

    result = result.strip()

    if result.startswith("```"):
        lines = result.splitlines()

        if lines and lines[0].startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        result = "\n".join(lines).strip()

    try:
        action = json.loads(result)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Groq returned invalid action JSON"
        ) from exc

    return validate_action(action)

    return action