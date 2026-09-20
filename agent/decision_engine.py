import json
import os

from groq import Groq

from agent.prompts import DECISION_ENGINE_SYSTEM_PROMPT


client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)


def generate_action(opportunity, business_analysis):
    """
    Generate a proposed action for a growth opportunity.

    This function does not execute anything.
    It only creates a proposed action for later approval.
    """

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

Determine the most appropriate action for this opportunity.
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

    if not result:
        raise ValueError("Groq returned an empty response")

    try:
        action = json.loads(result)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Groq returned invalid action JSON"
        ) from exc

    if not isinstance(action, dict):
        raise ValueError(
            "Action response must be a JSON object"
        )

    return action