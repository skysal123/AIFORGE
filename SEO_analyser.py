import json
import os
import time
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    # Load GEMINI_API_KEY from a sibling .env if present.
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass  # python-dotenv not installed; rely on actual env vars


# =========================================================
# CONFIGURATION
# =========================================================

GEMINI_MODEL = "gemini-3-flash-preview"
# GEMINI_API_KEY is read lazily inside _get_client(); importing this
# module never fails when the key is missing.
INPUT_FILE = r"C:\SOE\skinangel.in_ChIJX7-W.json"
OUTPUT_FILE = "google_profile_analysis.json"


def _get_client():
    """Build a Gemini client on demand, or raise if no key is configured.

    Importing the module no longer requires GEMINI_API_KEY, so callers can
    catch this error and fall back to a local analyser.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY environment variable is not set. "
            "Add it to your .env (project root) or export it before running."
        )
    # Local import so the module loads even without google-genai installed.
    # http_options timeout must be >= the longest model call (gemini can take
    # 60s+ on big SEO analyses). 600s here is a comfortable ceiling.
    from google import genai
    from google.genai import types as genai_types
    return (
        genai.Client(
            api_key=api_key,
            http_options=genai_types.HttpOptions(timeout=600_000),  # 600s in ms
        ),
        GEMINI_MODEL,
    )


# =========================================================
# TIMING / LOGGING FUNCTIONS
# =========================================================

SCRIPT_START = time.perf_counter()


def timestamp():
    return datetime.now().strftime("%H:%M:%S")


def log(message):
    print(f"[{timestamp()}] {message}", flush=True)


def elapsed(start):
    return f"{time.perf_counter() - start:.2f}s"


# =========================================================
# LOAD GOOGLE BUSINESS PROFILE
# =========================================================

def load_profile(json_file):

    stage_start = time.perf_counter()

    log("=" * 60)
    log("STAGE 1: LOADING GOOGLE BUSINESS PROFILE")
    log("=" * 60)

    log(f"File: {json_file}")

    try:

        log("Opening JSON file...")

        with open(
            json_file,
            "r",
            encoding="utf-8"
        ) as file:

            profile = json.load(file)

        log("JSON file successfully loaded.")

        log(
            f"JSON object contains "
            f"{len(profile)} top-level fields."
        )

        log(
            f"Time taken: {elapsed(stage_start)}"
        )

        return profile

    except Exception as e:

        log(f"ERROR loading JSON: {e}")

        raise


# =========================================================
# ANALYZE GOOGLE BUSINESS PROFILE
# =========================================================

def analyze_google_profile(profile):

    total_start = time.perf_counter()

    log("")
    log("=" * 60)
    log("STAGE 2: PREPARING PROFILE DATA")
    log("=" * 60)

    # -----------------------------------------------------
    # Extract fields
    # -----------------------------------------------------

    log("Extracting business name...")

    business_name = profile.get(
        "name",
        profile.get("business_name", "")
    )

    log(f"Business Name: {business_name}")

    log("Extracting category...")

    category = profile.get(
        "category",
        ""
    )

    log(f"Primary Category: {category}")

    log("Extracting description...")

    description = profile.get(
        "description",
        ""
    )

    log(
        f"Description length: "
        f"{len(description)} characters"
    )

    log("Extracting services...")

    services = profile.get(
        "services",
        []
    )

    log(
        f"Services found: "
        f"{len(services)}"
    )

    log("Extracting reviews...")

    reviews = profile.get(
        "reviews",
        {}
    )

    log(
        f"Review data fields: "
        f"{len(reviews)}"
    )

    log("Extracting photos...")

    photos = profile.get(
        "photos",
        {}
    )

    log(
        f"Photo data fields: "
        f"{len(photos)}"
    )

    log("Extracting phone...")

    phone = profile.get(
        "phone",
        ""
    )

    log(f"Phone: {phone}")

    log("Extracting website...")

    website = profile.get(
        "website",
        ""
    )

    log(f"Website: {website}")

    log("Extracting email...")

    email = profile.get(
        "email",
        ""
    )

    log(f"Email: {email}")

    log("Extracting address...")

    address = profile.get(
        "address",
        ""
    )

    log(f"Address: {address}")

    log("Extracting business hours...")

    hours = profile.get(
        "hours",
        {}
    )

    log(
        f"Hours fields: "
        f"{len(hours)}"
    )

    log(
        f"Profile preparation completed "
        f"in {elapsed(total_start)}"
    )


    # =====================================================
    # BUILD PROMPT
    # =====================================================

    prompt_start = time.perf_counter()

    log("")
    log("=" * 60)
    log("STAGE 3: BUILDING AI PROMPT")
    log("=" * 60)

    log("Converting services to JSON...")

    services_json = json.dumps(
        services,
        indent=2,
        ensure_ascii=False
    )

    log("Converting hours to JSON...")

    hours_json = json.dumps(
        hours,
        indent=2,
        ensure_ascii=False
    )

    log("Converting reviews to JSON...")

    reviews_json = json.dumps(
        reviews,
        indent=2,
        ensure_ascii=False
    )

    log("Converting photos to JSON...")

    photos_json = json.dumps(
        photos,
        indent=2,
        ensure_ascii=False
    )


    prompt = f"""
You are an expert Google Business Profile and Local SEO consultant.

Your job is to analyze a Google Business Profile and identify
improvements that can help the business improve its relevance,
completeness, customer engagement and local search visibility.

IMPORTANT:

Do NOT promise Google ranking improvements.

Do NOT recommend keyword stuffing.

Do NOT recommend fake reviews.

Do NOT recommend changing the real-world business name simply
to insert keywords.

Recommendations must be realistic and appropriate for the
business domain.

---------------------------------------------------
BUSINESS INFORMATION
---------------------------------------------------

Business Name:
{business_name}

Primary Category:
{category}

Description:
{description}

Phone:
{phone}

Email:
{email}

Website:
{website}

Address:
{address}

Services:
{services_json}

Business Hours:
{hours_json}

Reviews:
{reviews_json}

Photos:
{photos_json}

----------------------------
SCORING GUIDE (use this exactly):
------------------------------

profile_completeness_percentage = round(
    (has_name + has_category + has_description + has_phone + has_website
     + has_address + has_hours + has_summary + photos>=5 + reviews>=20
     + has_services) / 11 * 100
)


Each component must be 1 if the field is present and meaningful, else 0.
Return integers only. Never return  empty.
---------------------------------------------------
TASK
---------------------------------------------------

Analyze the profile from a Local SEO perspective.

Identify:

1. Profile completeness
2. Business category relevance
3. Business description quality
4. Missing information
5. Service optimization
6. Review management
7. Review response opportunities
8. Photo/content opportunities
9. Contact information issues
10. Website/profile consistency
11. Local SEO opportunities
12. Potential problems
13. Priority of each recommendation

For every recommendation provide:

- issue
- why_it_matters
- recommended_action
- priority
- effort
- example

Priority must be:

HIGH
MEDIUM
LOW

Effort must be:

EASY
MEDIUM
HARD

Also provide:

- overall_score out of 100
- profile_completeness_percentage
- strengths
- weaknesses
- top_5_actions
- optimized_description
- suggested_services
- suggested_profile_categories

IMPORTANT:

Only suggest categories that genuinely represent the business.

Do not invent Google Business Profile categories.

If uncertain, mark the category as:

"VERIFY IN GOOGLE"

Return ONLY valid JSON.

Do not include markdown.
Mandotory fields in the JSON output: profile_completeness_percentage
"""


    prompt_length = len(prompt)

    log(
        f"Prompt created successfully."
    )

    log(
        f"Prompt size: "
        f"{prompt_length:,} characters"
    )

    # Rough token estimate
    estimated_tokens = prompt_length // 4

    log(
        f"Estimated input tokens: "
        f"~{estimated_tokens:,}"
    )

    log(
        f"Prompt preparation time: "
        f"{elapsed(prompt_start)}"
    )


    # =====================================================
    # SEND REQUEST TO GEMINI
    # =====================================================

    ollama_start = time.perf_counter()

    log("")
    log("=" * 60)
    log("STAGE 4: CALLING GEMINI")
    log("=" * 60)

    # Build (or refuse) the client lazily, so importing this module never
    # fails and so the .env file is consulted at call time.
    try:
        client, model_name = _get_client()
    except RuntimeError as exc:
        log(f"Gemini client unavailable: {exc}")
        raise

    log(
        f"Model: {model_name}"
    )

    log(
        "Sending request to Gemini..."
    )

    log(
        "IMPORTANT: The next step may take time "
        "depending on API/network response time."
    )

    log(
        "Waiting for model response..."
    )


    try:

        from google import genai  # local import so module imports without it
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                system_instruction=(
                    "You are a professional Local SEO and "
                    "Google Business Profile optimization "
                    "consultant."
                ),
                temperature=0.2
            )
        )


    except Exception as e:

        log(
            f"OLLAMA ERROR after "
            f"{elapsed(ollama_start)}"
        )

        log(
            f"Error: {e}"
        )

        raise


    ollama_time = elapsed(
        ollama_start
    )

    log("")
    log(
        f"Gemini response received!"
    )

    log(
        f"Gemini processing time: "
        f"{ollama_time}"
    )

    # =====================================================
    # GEMINI TOKEN USAGE
    # =====================================================

    try:
        usage = response.usage_metadata

        input_tokens = getattr(usage, "prompt_token_count", 0) or 0
        output_tokens = getattr(usage, "candidates_token_count", 0) or 0
        thinking_tokens = getattr(usage, "thoughts_token_count", 0) or 0
        total_tokens = getattr(usage, "total_token_count", 0) or 0

        log("")
        log("=" * 60)
        log("GEMINI TOKEN USAGE")
        log("=" * 60)
        log(f"Input tokens: {input_tokens:,}")
        log(f"Output tokens: {output_tokens:,}")
        log(f"Thinking tokens: {thinking_tokens:,}")
        log(f"Total tokens: {total_tokens:,}")

    except Exception as e:
        log(f"Could not read Gemini token usage: {e}")


    # =====================================================
    # EXTRACT MODEL RESPONSE
    # =====================================================

    extraction_start = time.perf_counter()

    log("")
    log("=" * 60)
    log("STAGE 5: EXTRACTING MODEL RESPONSE")
    log("=" * 60)

    try:

        result = response.text

        log(
            "Model response successfully extracted."
        )

        log(
            f"Response length: "
            f"{len(result):,} characters"
        )

        log(
            f"Response extraction time: "
            f"{elapsed(extraction_start)}"
        )

    except Exception as e:

        log(
            f"ERROR extracting model response: {e}"
        )

        raise


    # =====================================================
    # CLEAN RESPONSE
    # =====================================================

    cleaning_start = time.perf_counter()

    log("")
    log("=" * 60)
    log("STAGE 6: CLEANING MODEL RESPONSE")
    log("=" * 60)

    result = result.strip()

    log(
        f"Response starts with: "
        f"{result[:50]!r}"
    )

    if result.startswith("```json"):

        log(
            "Markdown JSON code block detected."
        )

        result = result[7:]

    elif result.startswith("```"):

        log(
            "Markdown code block detected."
        )

        result = result[3:]


    if result.endswith("```"):

        log(
            "Removing closing markdown block."
        )

        result = result[:-3]


    result = result.strip()

    log(
        f"Cleaned response length: "
        f"{len(result):,} characters"
    )

    log(
        f"Response cleaning time: "
        f"{elapsed(cleaning_start)}"
    )


    # =====================================================
    # PARSE JSON
    # =====================================================

    parsing_start = time.perf_counter()

    log("")
    log("=" * 60)
    log("STAGE 7: PARSING AI JSON")
    log("=" * 60)

    try:

        analysis = json.loads(
            result
        )

        log(
            "SUCCESS: Valid JSON received from Gemini."
        )

        if isinstance(
            analysis,
            dict
        ):

            log(
                f"Output contains "
                f"{len(analysis)} top-level fields."
            )

            log(
                "Output fields:"
            )

            for key in analysis.keys():

                log(
                    f"  -> {key}"
                )


        log(
            f"JSON parsing time: "
            f"{elapsed(parsing_start)}"
        )

        return analysis


    except json.JSONDecodeError as e:

        log("")
        log(
            "ERROR: Gemini did NOT return valid JSON."
        )

        log(
            f"JSON error: {e}"
        )

        log("")
        log(
            "RAW MODEL RESPONSE:"
        )

        print(
            result
        )

        raise


# =========================================================
# SAVE ANALYSIS
# =========================================================

def save_analysis(
    result,
    output_file
):

    save_start = time.perf_counter()

    log("")
    log("=" * 60)
    log("STAGE 8: SAVING ANALYSIS")
    log("=" * 60)

    log(
        f"Output file: "
        f"{output_file}"
    )

    log(
        "Writing JSON file..."
    )

    with open(
        output_file,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            result,
            file,
            indent=4,
            ensure_ascii=False
        )

    log(
        "JSON file successfully saved."
    )

    log(
        f"Save time: "
        f"{elapsed(save_start)}"
    )


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    log("")
    log("=" * 60)
    log("GOOGLE BUSINESS PROFILE SEO ANALYZER")
    log("=" * 60)

    log(
        f"Python script started."
    )

    log(
        f"Model: {GEMINI_MODEL}"
    )

    log(
        f"Input: {INPUT_FILE}"
    )

    log(
        f"Output: {OUTPUT_FILE}"
    )


    # -----------------------------------------------------
    # LOAD PROFILE
    # -----------------------------------------------------

    profile = load_profile(
        INPUT_FILE
    )


    # -----------------------------------------------------
    # DISPLAY BASIC INFORMATION
    # -----------------------------------------------------

    log("")
    log("=" * 60)
    log("PROFILE SUMMARY")
    log("=" * 60)

    log(
        f"Business: "
        f"{profile.get('name', 'Unknown')}"
    )

    log(
        f"Category: "
        f"{profile.get('primary_category_display') or profile.get('primary_category') or 'Unknown'}"
    )

    log(
        f"Website: "
        f"{profile.get('website', 'Not available')}"
    )


    # -----------------------------------------------------
    # RUN ANALYSIS
    # -----------------------------------------------------

    analysis = analyze_google_profile(
        profile
    )


    # -----------------------------------------------------
    # SAVE RESULT
    # -----------------------------------------------------

    save_analysis(
        analysis,
        OUTPUT_FILE
    )


    # =====================================================
    # FINAL SUMMARY
    # =====================================================

    total_time = elapsed(
        SCRIPT_START
    )

    log("")
    log("=" * 60)
    log("ANALYSIS COMPLETED SUCCESSFULLY")
    log("=" * 60)

    log(
        f"Total execution time: "
        f"{total_time}"
    )

    log(
        f"Results saved to:"
    )

    log(
        f"  {OUTPUT_FILE}"
    )

    log("=" * 60)