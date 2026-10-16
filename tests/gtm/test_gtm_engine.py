"""
Unit tests for agent.gtm_engine (Visual GTM Intelligence Engine).
"""
import base64
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from agent.gtm_engine import (
    encode_tile_to_base64,
    parse_gtm_vision_output,
    build_gtm_multimodal_prompt,
    analyze_gtm_tiles,
)


def test_encode_tile_to_base64(tmp_path):
    test_img = tmp_path / "tile_0001_hero.webp"
    test_img.write_bytes(b"sample-image-content")

    data_uri = encode_tile_to_base64(str(test_img))
    assert data_uri.startswith("data:image/webp;base64,")
    decoded = base64.b64decode(data_uri.split(",")[1])
    assert decoded == b"sample-image-content"


def test_encode_tile_missing_file_returns_none():
    assert encode_tile_to_base64("/non/existent/path.webp") is None


def test_parse_gtm_vision_output_normalizes_schema():
    raw_output = {
        "gtm_scores": {
            "overall": 82,
            "above_the_fold": 75,
            "pricing_clarity": 85,
            "social_proof": 70,
            "cro_friction": 90,
        },
        "blind_spots": ["Competitor has explicit pricing, user does not"],
        "competitor_insights": [
            {
                "domain": "competitor.com",
                "strengths": ["Transparent pricing", "Hero video"],
                "weaknesses": ["No free trial"],
            }
        ],
        "opportunities": [
            {
                "title": "Add Transparent Pricing Tier",
                "description": "Expose a self-serve $29/mo starter tier to match competitor.",
                "problem": "Competitor displays $29/mo while user requires sales call.",
                "problem_key": "pricing_transparency",
                "type": "conversion",
                "potential_impact": "high",
                "confidence": 0.85,
                "evidence": ["Competitor pricing tile demonstrates transparent tiers"],
            }
        ],
    }

    result = parse_gtm_vision_output(raw_output)
    assert result["gtm_scores"]["overall"] == 82
    assert result["gtm_scores"]["above_the_fold"] == 75
    assert len(result["opportunities"]) == 1
    opp = result["opportunities"][0]
    assert opp["title"] == "Add Transparent Pricing Tier"
    assert opp["problem_key"] == "pricing_transparency"
    assert opp["type"] == "conversion"


def test_parse_gtm_vision_output_handles_fallback_scores():
    # Incomplete or string-based JSON
    raw_output = {"gtm_scores": {}}
    result = parse_gtm_vision_output(raw_output)
    assert result["gtm_scores"]["overall"] == 50
    assert result["gtm_scores"]["above_the_fold"] == 50
    assert result["opportunities"] == []


def test_build_gtm_multimodal_prompt(tmp_path):
    user_tile = tmp_path / "tile_0001_hero.webp"
    user_tile.write_bytes(b"hero-bytes")

    user_manifest = {
        "url": "https://mysite.com",
        "tiles": [{"filename": "tile_0001_hero.webp", "path": str(user_tile)}],
    }
    competitor_manifests = [
        {
            "url": "https://rival.com",
            "tiles": [{"filename": "tile_0001_hero.webp", "path": str(user_tile)}],
        }
    ]
    queries = ["best gtm tool", "conversion audit"]

    messages = build_gtm_multimodal_prompt(user_manifest, competitor_manifests, queries)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    content = messages[1]["content"]
    assert isinstance(content, list)
    # Check that image items are included
    image_items = [item for item in content if item.get("type") == "image_url"]
    assert len(image_items) >= 2


def test_analyze_gtm_tiles_end_to_end(tmp_path):
    tile_file = tmp_path / "tile_0001_hero.webp"
    tile_file.write_bytes(b"image")

    user_manifest = {
        "url": "https://mysite.com",
        "tiles": [{"filename": "tile_0001_hero.webp", "path": str(tile_file)}],
    }
    competitor_manifests = [
        {
            "url": "https://rival.com",
            "tiles": [{"filename": "tile_0001_hero.webp", "path": str(tile_file)}],
        }
    ]

    mock_llm_response = MagicMock()
    mock_llm_response.choices = [
        MagicMock(
            message=MagicMock(
                content="""{
                    "gtm_scores": {"overall": 79, "above_the_fold": 80, "pricing_clarity": 75, "social_proof": 80, "cro_friction": 82},
                    "blind_spots": ["Competitor highlights customer logos above fold"],
                    "competitor_insights": [{"domain": "rival.com", "strengths": ["Customer logos"], "weaknesses": ["Vague H1"]}],
                    "opportunities": [
                        {
                            "title": "Elevate Customer Logos Above Fold",
                            "description": "Show 5 enterprise customer logos in the hero viewport.",
                            "problem": "Social proof is buried at 1800px scroll depth.",
                            "problem_key": "social_proof",
                            "type": "website",
                            "potential_impact": "high",
                            "confidence": 0.88,
                            "evidence": ["Competitor places G2 and client logos immediately under primary CTA"]
                        }
                    ]
                }"""
            )
        )
    ]

    with patch("agent.gtm_engine.Groq") as mock_groq:
        mock_groq.return_value.chat.completions.create.return_value = mock_llm_response
        result = analyze_gtm_tiles(user_manifest, competitor_manifests, ["marketing automation"])

    assert result["gtm_scores"]["overall"] == 79
    assert len(result["opportunities"]) == 1
    assert result["opportunities"][0]["problem_key"] == "social_proof"


def test_analyze_gtm_tiles_handles_llm_exception():
    with patch("agent.gtm_engine.Groq") as mock_groq:
        mock_groq.return_value.chat.completions.create.side_effect = Exception("API rate limit exceeded")
        result = analyze_gtm_tiles({}, [], [])

    assert result["gtm_scores"]["overall"] == 50
    assert result["opportunities"] == []


def test_parse_gtm_vision_output_with_raw_string_and_invalid_values():
    raw_str = """{
        "gtm_scores": {"overall": "bad", "above_the_fold": 120, "pricing_clarity": -10},
        "blind_spots": "not a list",
        "competitor_insights": "not a list",
        "opportunities": [
            "not a dict",
            {"title": "", "problem": "valid problem"},
            {
                "title": "Valid Opp",
                "problem": "Valid Prob",
                "problem_key": "invalid_key",
                "type": "invalid_type",
                "potential_impact": "invalid_impact",
                "confidence": "bad_float",
                "evidence": "single string not list"
            }
        ]
    }"""
    result = parse_gtm_vision_output(raw_str)
    assert result["gtm_scores"]["overall"] == 50
    assert result["gtm_scores"]["above_the_fold"] == 100
    assert result["gtm_scores"]["pricing_clarity"] == 0
    assert len(result["opportunities"]) == 1
    opp = result["opportunities"][0]
    assert opp["problem_key"] == "conversion_friction"
    assert opp["type"] == "conversion"
    assert opp["potential_impact"] == "high"
    assert opp["confidence"] == 0.85
    assert isinstance(opp["evidence"], list)

