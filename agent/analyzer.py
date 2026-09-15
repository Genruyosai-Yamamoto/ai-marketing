import json
import os

from groq import Groq

from agent.prompts import (
    OBSERVATION_ANALYSIS_SYSTEM_PROMPT,
    OBSERVATION_ANALYSIS_USER_PROMPT,
)


client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)


def analyze_observation(observation):
    """
    Analyze a website observation using Groq.

    Returns a structured dictionary containing the AI's
    understanding of the business.
    """

    analysis = observation.get("analysis", {})

    prompt = OBSERVATION_ANALYSIS_USER_PROMPT.format(
        source_url=observation.get("source_url", ""),
        final_url=observation.get("final_url", ""),
        title=analysis.get("title", ""),
        meta_description=analysis.get("meta_description", ""),
        headings=json.dumps(
            analysis.get("headings", []),
            ensure_ascii=False,
        ),
        links=json.dumps(
            analysis.get("links", []),
            ensure_ascii=False,
        ),
    )

    response = client.chat.completions.create(
        model=os.getenv(
            "GROQ_MODEL",
            "llama-3.3-70b-versatile",
        ),
        messages=[
            {
                "role": "system",
                "content": OBSERVATION_ANALYSIS_SYSTEM_PROMPT,
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
        parsed_result = json.loads(result)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Groq returned invalid JSON"
        ) from exc

    return parsed_result