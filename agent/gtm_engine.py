"""
Visual GTM Intelligence Engine (agent.gtm_engine).

Orchestrates multi-tile comparative visual analysis using Vision-Language Models.
Evaluates user and competitor web screenshot tiles across 4 GTM pillars:
1. Above-The-Fold Clarity & Hero Messaging
2. Pricing Structure & Packaging Transparency
3. Social Proof & Trust Architecture
4. Conversion Rate Optimization (CRO) & Primary CTA Flow
"""
from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

logger = logging.getLogger(__name__)

GTM_SYSTEM_PROMPT = """You are an elite B2B Go-To-Market (GTM) strategist and Conversion Rate Optimization (CRO) expert.
You evaluate companies by visually analyzing screenshot tiles of their landing pages compared directly against top market competitors.

You evaluate 4 Core GTM Pillars:
1. Above-The-Fold Clarity: Headline contrast, value proposition clarity, reading ease, primary CTA salience. Can a visitor grasp what the product does in under 5 seconds?
2. Pricing Structure: Free trial vs sales call friction, self-serve tier transparency, anchor pricing.
3. Social Proof & Trust Architecture: Customer logos, verified review badges (G2/Trustpilot), quantifiable metrics.
4. CRO & CTA Conversion Flow: Button prominence, secondary vs primary conflict, form friction.

You MUST respond strictly with valid JSON conforming to the following structure:
{
  "gtm_scores": {
    "overall": <integer 0-100>,
    "above_the_fold": <integer 0-100>,
    "pricing_clarity": <integer 0-100>,
    "social_proof": <integer 0-100>,
    "cro_friction": <integer 0-100>
  },
  "blind_spots": [
    "<string describing a critical positioning or CRO weakness compared to competitors>"
  ],
  "competitor_insights": [
    {
      "domain": "<competitor domain>",
      "strengths": ["<strength>"],
      "weaknesses": ["<weakness>"]
    }
  ],
  "opportunities": [
    {
      "title": "<High-impact opportunity title>",
      "description": "<Detailed strategic description>",
      "problem": "<Direct competitive or visual friction problem identified>",
      "problem_key": "<one of: value_proposition, pricing_transparency, social_proof, conversion_friction>",
      "type": "<one of: conversion, website, seo>",
      "potential_impact": "<one of: high, medium, low>",
      "confidence": <float between 0.0 and 1.0>,
      "evidence": ["<specific visual detail observed in user vs competitor tiles>"]
    }
  ]
}
"""


def encode_tile_to_base64(file_path: str) -> str | None:
    """Encode an image file to a base64 data URI."""
    path = Path(file_path)
    if not path.is_file():
        return None
    try:
        data = path.read_bytes()
        encoded = base64.b64encode(data).decode("utf-8")
        ext = path.suffix.lower().lstrip(".") or "webp"
        mime = "image/webp" if ext == "webp" else f"image/{ext}"
        return f"data:{mime};base64,{encoded}"
    except Exception as exc:
        logger.warning("Could not encode image tile %s: %s", file_path, exc)
        return None


def parse_gtm_vision_output(raw_json: dict[str, Any] | str) -> dict[str, Any]:
    """Parse and normalize Vision LLM response to ensure all fields are complete and typed."""
    data = raw_json
    if isinstance(raw_json, str):
        try:
            data = json.loads(raw_json)
        except Exception:
            data = {}

    scores_raw = data.get("gtm_scores") if isinstance(data, dict) else {}
    if not isinstance(scores_raw, dict):
        scores_raw = {}

    def _clamp_score(val: Any) -> int:
        try:
            return max(0, min(100, int(val)))
        except (ValueError, TypeError):
            return 50

    gtm_scores = {
        "overall": _clamp_score(scores_raw.get("overall")),
        "above_the_fold": _clamp_score(scores_raw.get("above_the_fold")),
        "pricing_clarity": _clamp_score(scores_raw.get("pricing_clarity")),
        "social_proof": _clamp_score(scores_raw.get("social_proof")),
        "cro_friction": _clamp_score(scores_raw.get("cro_friction")),
    }

    raw_opps = data.get("opportunities") if isinstance(data, dict) else []
    validated_opps: list[dict[str, Any]] = []

    valid_problem_keys = {
        "value_proposition",
        "pricing_transparency",
        "social_proof",
        "conversion_friction",
        "seo_visibility",
        "content_gap",
    }
    valid_types = {"conversion", "website", "seo", "content"}

    if isinstance(raw_opps, list):
        for opp in raw_opps:
            if not isinstance(opp, dict):
                continue
            title = str(opp.get("title") or "").strip()
            problem = str(opp.get("problem") or "").strip()
            if not title or not problem:
                continue

            prob_key = str(opp.get("problem_key") or "conversion_friction").strip().lower()
            if prob_key not in valid_problem_keys:
                prob_key = "conversion_friction"

            opp_type = str(opp.get("type") or "conversion").strip().lower()
            if opp_type not in valid_types:
                opp_type = "conversion"

            impact = str(opp.get("potential_impact") or "high").strip().lower()
            if impact not in {"high", "medium", "low"}:
                impact = "high"

            try:
                confidence = float(opp.get("confidence", 0.85))
                confidence = max(0.1, min(1.0, confidence))
            except (ValueError, TypeError):
                confidence = 0.85

            evidence = opp.get("evidence")
            if not isinstance(evidence, list):
                evidence = [str(evidence)] if evidence else ["Visual tile comparison"]

            validated_opps.append({
                "title": title,
                "description": str(opp.get("description") or title),
                "problem": problem,
                "problem_key": prob_key,
                "type": opp_type,
                "potential_impact": impact,
                "confidence": confidence,
                "evidence": evidence,
            })

    blind_spots = data.get("blind_spots") if isinstance(data, dict) else []
    if not isinstance(blind_spots, list):
        blind_spots = []

    competitor_insights = data.get("competitor_insights") if isinstance(data, dict) else []
    if not isinstance(competitor_insights, list):
        competitor_insights = []

    return {
        "gtm_scores": gtm_scores,
        "blind_spots": blind_spots,
        "competitor_insights": competitor_insights,
        "opportunities": validated_opps,
    }


def build_gtm_multimodal_prompt(
    user_manifest: dict[str, Any],
    competitor_manifests: list[dict[str, Any]],
    search_queries: list[str],
) -> list[dict[str, Any]]:
    """Build multimodal message payload including images and textual query context."""
    user_url = user_manifest.get("url", "User Website")
    user_tiles = user_manifest.get("tiles", [])

    user_content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                f"Analyze the following User Website: {user_url}\n"
                f"Target Organic Search Queries: {', '.join(search_queries[:5])}\n\n"
                "Here are the sequential screenshot tiles for the USER'S WEBSITE:"
            ),
        }
    ]

    # Add up to 3 tiles for user site
    for tile in user_tiles[:3]:
        tile_path = tile.get("path")
        if tile_path:
            uri = encode_tile_to_base64(tile_path)
            if uri:
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": uri},
                })

    for idx, comp in enumerate(competitor_manifests[:2], start=1):
        comp_url = comp.get("url", f"Competitor {idx}")
        user_content.append({
            "type": "text",
            "text": f"\nHere are screenshot tiles for MARKET COMPETITOR {idx}: {comp_url}",
        })
        for tile in comp.get("tiles", [])[:2]:
            tile_path = tile.get("path")
            if tile_path:
                uri = encode_tile_to_base64(tile_path)
                if uri:
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": uri},
                    })

    user_content.append({
        "type": "text",
        "text": (
            "\nBased on the visual evidence across all tiles, evaluate the user's site against "
            "the competitors across the 4 GTM Pillars. Return your analysis in the requested JSON format."
        ),
    })

    return [
        {"role": "system", "content": GTM_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def analyze_gtm_tiles(
    user_manifest: dict[str, Any],
    competitor_manifests: list[dict[str, Any]],
    search_queries: list[str],
) -> dict[str, Any]:
    """Execute GTM visual evaluation via Vision LLM and return structured analysis."""
    messages = build_gtm_multimodal_prompt(
        user_manifest=user_manifest,
        competitor_manifests=competitor_manifests,
        search_queries=search_queries,
    )

    api_key = os.getenv("GROQ_API_KEY")
    client = Groq(api_key=api_key)

    model_name = os.getenv("GROQ_VISION_MODEL", "llama-3.2-11b-vision-preview")

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        raw_text = response.choices[0].message.content or "{}"
        return parse_gtm_vision_output(raw_text)
    except Exception as exc:
        logger.error("Vision LLM analysis failed: %s", exc)
        # Fallback structured defaults
        return parse_gtm_vision_output({})
