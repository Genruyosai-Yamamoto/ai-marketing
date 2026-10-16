"""
Unit tests for services.gtm_dossier_service.
"""
from pathlib import Path
import pytest

from services.gtm_dossier_service import (
    generate_gtm_dossier_markdown,
    save_dossier_to_file,
)


def test_generate_gtm_dossier_markdown_includes_all_sections():
    mock_run = {
        "id": "run-123",
        "created_at": "2026-10-16T20:00:00",
        "user_website": {
            "domain": "mysite.com",
            "url": "https://mysite.com",
            "tiles": ["tile_0001_hero.webp", "tile_0002_value.webp"],
        },
        "competitors_analyzed": [
            {
                "domain": "rival.com",
                "strengths": ["Clear tiered pricing", "Hero video"],
                "weaknesses": ["No self-serve signup"],
            }
        ],
        "gtm_scores": {
            "overall": 78,
            "above_the_fold": 80,
            "pricing_clarity": 70,
            "social_proof": 75,
            "cro_friction": 85,
        },
        "blind_spots": [
            "Rival clearly highlights SOC2 and GDPR badges above fold"
        ],
        "opportunities": [
            {
                "title": "Add Compliance Badges Above Fold",
                "problem": "Trust barrier for enterprise buyers.",
                "problem_key": "social_proof",
                "potential_impact": "high",
                "confidence": 0.88,
                "evidence": ["Competitor embeds SOC2 badge directly below CTA"],
            }
        ],
    }

    md = generate_gtm_dossier_markdown(mock_run)
    assert "# Executive GTM Intelligence Dossier" in md
    assert "mysite.com" in md
    assert "Overall Score: 78" in md
    assert "30-Day Tactical Roadmap" in md
    assert "rival.com" in md
    assert "Clear tiered pricing" in md
    assert "Add Compliance Badges Above Fold" in md


def test_generate_gtm_dossier_markdown_handles_minimal_empty_run():
    md = generate_gtm_dossier_markdown({})
    assert "# Executive GTM Intelligence Dossier" in md
    assert "Overall Score: 50" in md
    assert "No competitor sites audited" in md


def test_save_dossier_to_file(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "services.gtm_dossier_service.DOSSIER_BASE_DIR",
        str(tmp_path),
    )

    rel_path = save_dossier_to_file(
        run_id="run-test",
        business_id="biz-test",
        markdown_content="# Test Dossier Content",
    )

    expected_file = tmp_path / "biz-test" / "run-test.md"
    assert expected_file.exists()
    assert expected_file.read_text(encoding="utf-8") == "# Test Dossier Content"
    assert "biz-test/run-test.md" in rel_path
