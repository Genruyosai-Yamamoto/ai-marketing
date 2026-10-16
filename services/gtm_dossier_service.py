"""
Executive GTM Dossier Generator (services.gtm_dossier_service).

Synthesizes visual GTM audit findings, competitor comparisons, and tactical
recommendations into an executive Markdown and HTML report.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

DOSSIER_BASE_DIR = os.getenv("GTM_DOSSIER_DIR", "static/dossiers")


def generate_gtm_dossier_markdown(run_data: dict[str, Any]) -> str:
    """
    Format a complete executive GTM Dossier in Markdown.
    """
    run_id = run_data.get("id", "N/A")
    timestamp = run_data.get("created_at", "N/A")
    user_website = run_data.get("user_website") or {}
    user_domain = user_website.get("domain") or user_website.get("url") or "User Website"
    user_url = user_website.get("url", "")

    scores = run_data.get("gtm_scores") or {}
    overall = scores.get("overall", 50)
    above_fold = scores.get("above_the_fold", 50)
    pricing = scores.get("pricing_clarity", 50)
    social = scores.get("social_proof", 50)
    cro = scores.get("cro_friction", 50)

    blind_spots = run_data.get("blind_spots") or []
    competitors = run_data.get("competitors_analyzed") or []
    opportunities = run_data.get("opportunities") or []

    lines: list[str] = [
        f"# Executive GTM Intelligence Dossier: {user_domain}",
        f"**Audit Run:** `{run_id}` | **Date:** {timestamp}",
        f"**Target URL:** [{user_url}]({user_url})" if user_url else "",
        "",
        "---",
        "",
        "## 1. Executive Summary & GTM Health Score",
        "",
        f"### **Overall Score: {overall} / 100**",
        "",
        "| Evaluation Pillar | Score | Assessment |",
        "|---|:---:|---|",
        f"| **Above-The-Fold Clarity** | **{above_fold}/100** | Value prop clarity, hero headline contrast, reading speed. |",
        f"| **Pricing & Packaging Transparency** | **{pricing}/100** | Self-serve clarity vs sales-call friction. |",
        f"| **Social Proof & Trust Architecture** | **{social}/100** | Client logos, reviews, and quantifiable case studies. |",
        f"| **CRO & CTA Conversion Flow** | **{cro}/100** | Action button contrast, cognitive overload, form friction. |",
        "",
        "---",
        "",
        "## 2. Competitive Landscape Benchmark",
        "",
    ]

    if competitors:
        lines.append("| Competitor Domain | Key Strengths Observed | Critical Vulnerabilities |")
        lines.append("|---|---|---|")
        for comp in competitors:
            domain = comp.get("domain", "Unknown")
            strengths = ", ".join(comp.get("strengths") or ["None noted"])
            weaknesses = ", ".join(comp.get("weaknesses") or ["None noted"])
            lines.append(f"| **{domain}** | {strengths} | {weaknesses} |")
        lines.append("")
    else:
        lines.append("*No competitor sites audited in this run.*\n")

    lines.extend([
        "---",
        "",
        "## 3. Critical Positioning Blind Spots",
        "",
    ])

    if blind_spots:
        for spot in blind_spots:
            lines.append(f"- ⚠️ **{spot}**")
        lines.append("")
    else:
        lines.append("No immediate blind spots detected relative to audited benchmarks.\n")

    lines.extend([
        "---",
        "",
        "## 4. Prioritized 30-Day Tactical Roadmap",
        "",
    ])

    if opportunities:
        for idx, opp in enumerate(opportunities, start=1):
            title = opp.get("title", f"Opportunity {idx}")
            problem = opp.get("problem", "")
            impact = str(opp.get("potential_impact", "high")).upper()
            prob_key = opp.get("problem_key", "conversion_friction")
            evidence = opp.get("evidence") or []
            ev_text = " | ".join(evidence) if isinstance(evidence, list) else str(evidence)

            lines.append(f"### Priority {idx}: {title} `[{impact} IMPACT]`")
            lines.append(f"**Category:** `{prob_key}`")
            lines.append(f"**Identified Friction:** {problem}")
            if ev_text:
                lines.append(f"**Visual Evidence:** *{ev_text}*")
            lines.append("")
    else:
        lines.append("No high-friction items identified. Website demonstrates strong baseline GTM patterns.\n")

    lines.extend([
        "---",
        "*Generated automatically by Blom Autonomous Visual GTM Operating System.*",
    ])

    return "\n".join(line for line in lines if line is not None)


def save_dossier_to_file(run_id: str, business_id: str, markdown_content: str) -> str:
    """
    Save markdown dossier content to disk and return the relative path.
    """
    out_dir = Path(DOSSIER_BASE_DIR) / business_id
    out_dir.mkdir(parents=True, exist_ok=True)

    file_path = out_dir / f"{run_id}.md"
    file_path.write_text(markdown_content, encoding="utf-8")

    return str(file_path)
