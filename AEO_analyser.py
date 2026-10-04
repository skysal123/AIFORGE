import json
import os
import time
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

GEMINI_MODEL = "gemini-3-flash-preview"

def _get_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable is not set.")
    from google import genai
    from google.genai import types as genai_types
    return (
        genai.Client(
            api_key=api_key,
            http_options=genai_types.HttpOptions(timeout=600_000),
        ),
        GEMINI_MODEL,
    )

def analyze_aeo(profile):
    """Perform AEO analysis using Gemini."""
    # Extract and prepare data for prompt
    business_name = profile.get("name") or profile.get("business_name", "")
    category = profile.get("category") or profile.get("primary_category", "")
    description = profile.get("description", "")
    services = profile.get("services", [])
    reviews = profile.get("reviews", {})
    photos = profile.get("photos", {})
    phone = profile.get("phone", "")
    website = profile.get("website", "")
    address = profile.get("address", "")
    hours = profile.get("hours", {})

    services_json = json.dumps(services, indent=2, ensure_ascii=False)
    hours_json = json.dumps(hours, indent=2, ensure_ascii=False)
    reviews_json = json.dumps(reviews, indent=2, ensure_ascii=False)
    photos_json = json.dumps(photos, indent=2, ensure_ascii=False)

    prompt = f"""
You are an expert Answer Engine Optimization (AEO) specialist. Your goal is to analyze a Google Business Profile and determine how well it is optimized for AI-powered answer engines (like Perplexity, Gemini, and Search Generative Experience).

AEO focuses on "Answerability" — the ease with which an AI can extract a factual, trustworthy answer to a user's query.

---------------------------------------------------
BUSINESS INFORMATION
---------------------------------------------------
Business Name: {business_name}
Primary Category: {category}
Description: {description}
Phone: {phone}
Email: {profile.get("email", "")}
Website: {website}
Address: {address}
Services: {services_json}
Business Hours: {hours_json}
Reviews: {reviews_json}
Photos: {photos_json}

---------------------------------------------------
AEO SCORING RUBRIC (MANDATORY)
---------------------------------------------------
You must evaluate the profile across these 8 categories. The total score must sum to 100.

1. ENTITY (Max 15 points)
   - Evaluate: Business identity clarity, Category accuracy, Services list detail, Location precision.
2. ANSWERS (Max 20 points)
   - Evaluate: Presence of FAQ-like content, Coverage of common user questions, Intent matching, Answer quality.
3. CONTENT (Max 15 points)
   - Evaluate: Directness of information, Completeness of profile, Specificity of offerings, Logical structure.
4. SEMANTIC (Max 10 points)
   - Evaluate: Topic coverage, Entity relationships, Semantic richness of the description.
5. LOCAL (Max 10 points)
   - Evaluate: Local location signals, Service-area clarity, Local-specific query answerability.
6. SCHEMA (Max 10 points)
   - Evaluate: (Inferred from website/profile) LocalBusiness markup, Service schema, Relationship markup.
7. TRUST (Max 10 points)
   - Evaluate: Evidence of expertise, Customer review sentiment, Credentials/Certifications.
8. TECHNICAL (Max 10 points)
   - Evaluate: (Inferred from website) Crawlability, Indexability, Sitemap presence, Accessibility.

---------------------------------------------------
TASK
---------------------------------------------------
1. Analyze the profile against the AEO rubric.
2. Calculate a score for each of the 8 categories.
3. Provide a total overall_score (sum of all 8 categories).
4. For each category, provide a brief justification for the score.
5. Generate a list of AEO-specific recommendations to improve "Answerability".

Each recommendation must include:
- category (which of the 8 categories it improves)
- issue
- recommended_action
- priority (HIGH, MEDIUM, LOW)
- effort (EASY, MEDIUM, HARD)

Return ONLY valid JSON. Do not include markdown.

Required JSON Schema:
{{
  "overall_score": int,
  "breakdown": {{
    "ENTITY": {{ "score": int, "max": 15, "justification": str }},
    "ANSWERS": {{ "score": int, "max": 20, "justification": str }},
    "CONTENT": {{ "score": int, "max": 15, "justification": str }},
    "SEMANTIC": {{ "score": int, "max": 10, "justification": str }},
    "LOCAL": {{ "score": int, "max": 10, "justification": str }},
    "SCHEMA": {{ "score": int, "max": 10, "justification": str }},
    "TRUST": {{ "score": int, "max": 10, "justification": str }},
    "TECHNICAL": {{ "score": int, "max": 10, "justification": str }}
  }},
  "recommendations": [
    {{ "category": str, "issue": str, "recommended_action": str, "priority": str, "effort": str }}
  ],
  "summary": str
}}
"""

    try:
        client, model_name = _get_client()
        from google import genai
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                system_instruction="You are a professional AEO (Answer Engine Optimization) consultant specializing in AI-driven discovery.",
                temperature=0.2
            )
        )

        result = response.text.strip()
        if result.startswith("```json"):
            result = result[7:]
        elif result.startswith("```"):
            result = result[3:]
        if result.endswith("```"):
            result = result[:-3]

        return json.loads(result.strip())
    except Exception as e:
        print(f"AEO Gemini Analysis failed: {e}")
        return None

def local_aeo_score(profile):
    """Deterministic fallback for AEO scoring."""
    score = 0
    breakdown = {}

    # ENTITY (15)
    e_score = 0
    if profile.get("name"): e_score += 4
    if profile.get("category") or profile.get("primary_category"): e_score += 4
    if profile.get("services"): e_score += 4
    if profile.get("address"): e_score += 3
    breakdown["ENTITY"] = {"score": e_score, "max": 15, "justification": "Based on basic profile completeness."}
    score += e_score

    # ANSWERS (20)
    a_score = 0
    if profile.get("description") and len(profile.get("description", "")) > 200: a_score += 10
    if profile.get("reviews"): a_score += 10
    breakdown["ANSWERS"] = {"score": a_score, "max": 20, "justification": "Based on description length and review presence."}
    score += a_score

    # CONTENT (15)
    c_score = 0
    if profile.get("website"): c_score += 8
    if profile.get("description"): c_score += 7
    breakdown["CONTENT"] = {"score": c_score, "max": 15, "justification": "Based on website and description presence."}
    score += c_score

    # SEMANTIC (10), LOCAL (10), SCHEMA (10), TRUST (10), TECHNICAL (10)
    # Simple fallbacks for other categories
    for cat in ["SEMANTIC", "LOCAL", "SCHEMA", "TRUST", "TECHNICAL"]:
        # Give a baseline if basic info exists
        val = 5 if profile.get("name") else 0
        breakdown[cat] = {"score": val, "max": 10, "justification": "Baseline heuristic score."}
        score += val

    return {
        "overall_score": score,
        "breakdown": breakdown,
        "recommendations": [
            {"category": "SCHEMA", "issue": "Missing Schema", "recommended_action": "Add JSON-LD LocalBusiness markup.", "priority": "HIGH", "effort": "MEDIUM"}
        ],
        "summary": "Local heuristic analysis completed."
    }
