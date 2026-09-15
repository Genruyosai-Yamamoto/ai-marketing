import json
import os
import sys

from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
load_dotenv()

from website_analyzer import analyze_html, fetch_website_html
from agent.analyzer import analyze_observation
from agent.opportunity_generator import generate_opportunities

SOURCE_URL = "https://example.com"


def main():
    html, final_url = fetch_website_html(SOURCE_URL)
    analysis = analyze_html(html)
    observation = {
        "source_url": SOURCE_URL,
        "final_url": final_url,
        "analysis": analysis,
    }
    print("=== OBSERVATION ===")
    print(json.dumps(observation, indent=2, ensure_ascii=False))

    business_analysis = analyze_observation(observation)
    print("=== ANALYSIS ===")
    print(json.dumps(business_analysis, indent=2, ensure_ascii=False))

    opportunities = generate_opportunities(business_analysis)
    print("=== OPPORTUNITIES ===")
    print(json.dumps(opportunities, indent=2, ensure_ascii=False))
    print(f"\n{len(opportunities)} opportunity(ies) - validator OK")


if __name__ == "__main__":
    main()