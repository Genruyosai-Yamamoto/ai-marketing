import json
import os

from groq import Groq

from agent.prompts import OPPORTUNITY_GENERATION_SYSTEM_PROMPT
from agent.opportunity_validation import validate_opportunities


client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)


def generate_opportunities(business_analysis):
    """
    Generate growth opportunities from a structured
    business analysis.

    Returns a list of structured opportunities.
    """

    prompt = f"""
Analyze the following business understanding and identify
the most relevant growth opportunities.

Business understanding:

{json.dumps(business_analysis, indent=2, ensure_ascii=False)}

Return a JSON array containing opportunities.
"""

    response = client.chat.completions.create(
        model=os.getenv(
            "GROQ_MODEL",
            "llama-3.3-70b-versatile",
        ),
        messages=[
            {
                "role": "system",
                "content": OPPORTUNITY_GENERATION_SYSTEM_PROMPT,
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
        opportunities = json.loads(result)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Groq returned invalid opportunity JSON"
        ) from exc

    if not isinstance(opportunities, list):
        raise ValueError(
            "Opportunity response must be a JSON array"
        )

    return validate_opportunities(opportunities)