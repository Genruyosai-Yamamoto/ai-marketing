import json
import os

from groq import Groq

from agent.prompts import OPPORTUNITY_GENERATION_SYSTEM_PROMPT
from agent.opportunity_validation import (
    validate_opportunity_item,
    validate_opportunities,
)
from dotenv import load_dotenv
load_dotenv()

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
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "opportunity_list",
                "schema": {
                    "type": "object",
                    "properties": {
                        "opportunities": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "description": {"type": "string"},
                                    "problem": {"type": "string"},
                                    "problem_key": {"type": "string"},
                                    "evidence": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                    "potential_impact": {
                                        "type": "string",
                                        "enum": ["low", "medium", "high"],
                                    },
                                    "confidence": {
                                        "type": "number",
                                        "minimum": 0,
                                        "maximum": 1,
                                    },
                                    "type": {
                                        "type": "string",
                                        "enum": [
                                            "website",
                                            "content",
                                            "seo",
                                            "conversion",
                                            "social",
                                            "other",
                                        ],
                                    },
                                },
                                "required": [
                                    "title",
                                    "description",
                                    "problem",
                                    "problem_key",
                                    "evidence",
                                    "potential_impact",
                                    "confidence",
                                    "type",
                                ],
                                "additionalProperties": False,
                            },
                        }
                    },
                    "required": ["opportunities"],
                    "additionalProperties": False,
                },
            },
        },
    )

    result = response.choices[0].message.content

    if not result:
        raise ValueError("Groq returned an empty response")

    try:
        payload = json.loads(result)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Groq returned invalid opportunity JSON"
        ) from exc

    if not isinstance(payload, dict):
        raise ValueError(
            "Opportunity response must be a JSON object"
        )

    opportunities = payload.get("opportunities")

    if not isinstance(opportunities, list):
        raise ValueError(
            "Opportunity response must contain an 'opportunities' array"
        )

    for index, opportunity in enumerate(opportunities):
        validate_opportunity_item(opportunity, index)

    opportunities = sorted(
        opportunities,
        key=lambda item: (
            {"low": 0, "medium": 1, "high": 2}[item["potential_impact"]],
            item["confidence"],
        ),
        reverse=True,
    )

    return validate_opportunities(opportunities)