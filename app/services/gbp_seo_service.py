"""Service helpers for the GBP Report & SEO feature.

Reuses the existing ``gbp_lookup`` and ``SEO_analyser`` modules instead of
duplicating their logic, and re-uses the normalization / scoring helpers
already implemented in the gbp blueprint.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]  # C:\AIForge Technologies
ANALYSIS_FILE = BASE_DIR / "google_profile_analysis.json"
FAQ_JSONLD_FILE = BASE_DIR / "faq_jsonld.json"

# --------------------------------------------------------------------- #
# Thin re-exports of the blueprint's existing helpers                    #
# --------------------------------------------------------------------- #


def search_candidates(query: str) -> tuple[list[dict] | None, str | None]:
    """Run a Places text-search via the existing gbp blueprint helpers.

    Returns ``(cards, error_message)``.
    """
    from app.blueprints.gbp import routes as gbp_routes

    return gbp_routes._places_search(query)  # noqa: SLF001 — intentional reuse


def get_profile(place_id: str) -> tuple[dict | None, str | None]:
    """Fetch full GBP details for ``place_id`` (Places API or sample index)."""
    from app.blueprints.gbp import routes as gbp_routes

    return gbp_routes._profile_by_id(place_id)  # noqa: SLF001


def _build_profile_for_analyser(profile: dict) -> dict:
    from app.blueprints.gbp import routes as gbp_routes

    return gbp_routes._build_profile_for_analyser(profile)  # noqa: SLF001


def _try_gemini_analysis(profile: dict) -> dict | None:
    from app.blueprints.gbp import routes as gbp_routes

    return gbp_routes._try_gemini_analysis(profile)  # noqa: SLF001


def _local_score(profile: dict) -> dict:
    from app.blueprints.gbp import routes as gbp_routes

    return gbp_routes._local_score(profile)  # noqa: SLF001


def _competitive_summary(profile: dict) -> dict:
    from app.blueprints.gbp import routes as gbp_routes

    return gbp_routes._competitive_summary(profile)  # noqa: SLF001

# --------------------------------------------------------------------- #
# FAQPage JSON-LD generator                                             #
# --------------------------------------------------------------------- #


def build_faq_jsonld(profile: dict, analysis: dict | None = None) -> dict:
    """Build deterministic FAQPage JSON-LD from GBP profile + SEO analysis.

    No external API or LLM call is made here. The questions and answers are
    generated entirely from the GBP information that has already been fetched.

    Returns a dictionary ready to:
      - serialize as JSON
      - embed inside <script type="application/ld+json">
      - save as faq_jsonld.json
    """
    analysis = analysis or {}

    questions: list[dict] = []

    def add_question(question: str, answer: str | None) -> None:
        question = _clean_text(question)
        answer = _clean_text(answer or "")

        if not question or not answer:
            return

        # Prevent duplicate questions.
        if any(item["name"].lower() == question.lower() for item in questions):
            return

        questions.append(
            {
                "@type": "Question",
                "name": question,
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": answer,
                },
            }
        )

    name = _clean_text(profile.get("name") or "This business")
    address = _clean_text(profile.get("address"))
    phone = _clean_text(profile.get("phone"))
    website = _clean_text(profile.get("website"))

    rating = profile.get("rating")
    total_reviews = profile.get("total_reviews")

    categories = profile.get("categories") or []

    primary_category = (
        profile.get("primary_category_display")
        or profile.get("primary_category")
    )

    hours = profile.get("hours") or []
    reviews = profile.get("reviews") or []

    # --------------------------------------------------------------- #
    # 1. Hours
    # --------------------------------------------------------------- #

    hours_text = _format_faq_hours(hours)

    if hours_text:
        add_question(
            "What are your hours?",
            f"{name}'s business hours are: {hours_text}",
        )

    # --------------------------------------------------------------- #
    # 2. Location
    # --------------------------------------------------------------- #

    if address:
        add_question(
            "Where are you located?",
            f"{name} is located at {address}.",
        )

    # --------------------------------------------------------------- #
    # 3. Contact
    # --------------------------------------------------------------- #

    contact_parts = []

    if phone:
        contact_parts.append(f"phone: {phone}")

    if website:
        contact_parts.append(f"website: {website}")

    if contact_parts:
        add_question(
            "How can I contact you?",
            f"You can contact {name} using {', '.join(contact_parts)}.",
        )

    # --------------------------------------------------------------- #
    # 4. Primary category / service
    # --------------------------------------------------------------- #

    if primary_category:
        add_question(
            f"What does {name} offer?",
            f"{name} is listed as a {primary_category}.",
        )

    # --------------------------------------------------------------- #
    # 5. Categories / services
    # --------------------------------------------------------------- #

    service_names = []

    for category in categories:
        if isinstance(category, dict):
            category_name = (
                category.get("display_name")
                or category.get("name")
                or category.get("title")
            )
        else:
            category_name = str(category)

        category_name = _clean_text(category_name)

        if category_name and category_name.lower() not in {
            item.lower() for item in service_names
        }:
            service_names.append(category_name)

    # Avoid generating excessive FAQs.
    for service in service_names[:5]:
        add_question(
            f"Do you offer {service}?",
            f"Yes. {name} is listed under the {service} category.",
        )

    # --------------------------------------------------------------- #
    # 6. Reviews / customer feedback
    # --------------------------------------------------------------- #

    review_texts = []

    for review in reviews[:2]:
        if isinstance(review, dict):
            text = (
                review.get("text")
                or review.get("review")
                or review.get("comment")
            )
        else:
            text = str(review)

        text = _clean_text(text)

        if text:
            review_texts.append(text)

    if review_texts:
        review_answer = "Customers have shared the following feedback: " + " ".join(
            review_texts
        )

        add_question(
            "What do customers say?",
            review_answer,
        )

    # --------------------------------------------------------------- #
    # 7. Rating
    # --------------------------------------------------------------- #

    if rating is not None:
        try:
            rating_value = float(rating)
            rating_text = f"{rating_value:.1f}/5"
        except (TypeError, ValueError):
            rating_text = str(rating)

        if total_reviews:
            add_question(
                "How is the business rated?",
                f"{name} has a Google rating of {rating_text} based on "
                f"{total_reviews} review{'s' if str(total_reviews) != '1' else ''}.",
            )
        else:
            add_question(
                "How is the business rated?",
                f"{name} has a Google rating of {rating_text}.",
            )

    # --------------------------------------------------------------- #
    # 8. Areas served
    # --------------------------------------------------------------- #

    areas_answer = _extract_service_area(profile)

    if areas_answer:
        add_question(
            "What areas do you serve?",
            areas_answer,
        )

    # --------------------------------------------------------------- #
    # 9. Business description
    # --------------------------------------------------------------- #

    description = (
        profile.get("editorial_summary")
        or profile.get("generative_summary")
    )

    if description:
        add_question(
            f"What is {name} about?",
            str(description),
        )

    # Keep the output within a useful range.
    questions = questions[:12]

    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": questions,
    }


def _clean_text(value: Any) -> str:
    """Normalize arbitrary values into clean single-line text."""
    if value is None:
        return ""

    if isinstance(value, (list, tuple)):
        value = ", ".join(str(item) for item in value)

    if isinstance(value, dict):
        value = (
            value.get("text")
            or value.get("name")
            or value.get("display_name")
            or ""
        )

    return " ".join(str(value).split()).strip()


def _format_faq_hours(hours: list) -> str:
    """Convert GBP hours into a readable FAQ answer."""
    if not hours:
        return ""

    formatted = []

    for item in hours:
        if isinstance(item, dict):
            day = (
                item.get("day")
                or item.get("day_name")
                or item.get("weekday")
            )

            opening = (
                item.get("open")
                or item.get("open_time")
                or item.get("opens")
            )

            closing = (
                item.get("close")
                or item.get("close_time")
                or item.get("closes")
            )

            if day and opening and closing:
                formatted.append(
                    f"{_clean_text(day)}: "
                    f"{_clean_text(opening)}–{_clean_text(closing)}"
                )
            elif day:
                formatted.append(_clean_text(day))

        else:
            text = _clean_text(item)
            if text:
                formatted.append(text)

    return "; ".join(formatted)


def _extract_service_area(profile: dict) -> str:
    """Extract service-area information when available."""
    possible_keys = (
        "service_area",
        "service_areas",
        "areas_served",
        "area_served",
        "served_areas",
    )

    for key in possible_keys:
        value = profile.get(key)

        if value:
            if isinstance(value, list):
                values = [_clean_text(item) for item in value]
                values = [item for item in values if item]

                if values:
                    return f"{profile.get('name', 'The business')} serves {', '.join(values)}."

            text = _clean_text(value)

            if text:
                return f"{profile.get('name', 'The business')} serves {text}."

    return ""

# --------------------------------------------------------------------- #
# GBP JSON file (the same file the CLI produces)                         #
# --------------------------------------------------------------------- #


def save_gbp_json(profile: dict, out_path: Path | None = None) -> Path:
    """Save the GBP profile as a JSON list, matching the existing CLI output.

    ``gbp_lookup.py`` writes ``[asdict(profile)]`` to disk. We replicate
    that exact shape (list with one element) so ``SEO_analyser`` and any
    downstream consumers see the same file as the CLI.
    """
    if out_path is None:
        safe_name = _safe_filename(profile.get("name") or "business")
        out_path = BASE_DIR / f"{safe_name}_{profile.get('place_id', 'unknown')[:8]}.json"
    payload = [asdict(_coerce_to_profile(profile))] if _looks_like_dataclass(profile) else [profile]
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    return out_path


def _looks_like_dataclass(profile: dict) -> bool:
    return "raw" in profile and isinstance(profile.get("reviews"), list)


def _coerce_to_profile(profile: dict):
    """Build a GBPProfile from a dict (used only when called with the dict
    variant from ``_profile_by_id``)."""
    from gbp_lookup import GBPProfile

    return GBPProfile(
        place_id=profile.get("place_id"),
        name=profile.get("name"),
        address=profile.get("address"),
        phone=profile.get("phone"),
        website=profile.get("website"),
        google_maps_url=profile.get("google_maps_url"),
        primary_category=profile.get("primary_category"),
        primary_category_display=profile.get("primary_category_display"),
        categories=list(profile.get("categories") or []),
        rating=profile.get("rating"),
        total_reviews=profile.get("total_reviews"),
        review_summary=profile.get("review_summary"),
        reviews=list(profile.get("reviews") or []),
        hours=list(profile.get("hours") or []),
        open_now=profile.get("open_now"),
        editorial_summary=profile.get("editorial_summary"),
        generative_summary=profile.get("generative_summary"),
        photo_count=profile.get("photo_count"),
        photo_references=list(profile.get("photo_references") or []),
        business_status=profile.get("business_status"),
        raw=profile.get("raw") or {},
        source=profile.get("_engine", "places_api"),
    )


def _safe_filename(s: str) -> str:
    import re

    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("._-")
    return s or "query"

def _write_faq_jsonld_file(faq_jsonld: dict) -> None:
    """Persist the standalone FAQPage JSON-LD artifact."""
    try:
        with open(FAQ_JSONLD_FILE, "w", encoding="utf-8") as fh:
            json.dump(
                faq_jsonld,
                fh,
                indent=2,
                ensure_ascii=False,
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not write %s: %s", FAQ_JSONLD_FILE, exc)
# --------------------------------------------------------------------- #
# High-level: pick a business and run the full GBP -> AEO pipeline        #
# --------------------------------------------------------------------- #


def analyze_aeo(place_id: str, save_to_disk: bool = True) -> dict:
    """Run the full pipeline for AEO analysis.

    Returns a dict with the normalized profile and the AEO scoring payload.
    """
    profile, error = get_profile(place_id)
    if profile is None:
        raise LookupError(error or "profile_not_found")

    gbp_json_path: Path | None = None
    if save_to_disk:
        try:
            gbp_json_path = save_gbp_json(profile)
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not save GBP JSON: %s", exc)

    import AEO_analyser

    analysis = AEO_analyser.analyze_aeo(profile) or AEO_analyser.local_aeo_score(profile)
    faq_jsonld = build_faq_jsonld(profile, analysis)

    _write_faq_jsonld_file(faq_jsonld)
    _write_analysis_file(
        analysis,
        profile,
        faq_jsonld=faq_jsonld,
    )

    return {
        "profile": profile,
        "analysis": analysis,
        "faq_jsonld": faq_jsonld,
        "gbp_json_path": str(gbp_json_path) if gbp_json_path else "",
        "analysis_path": str(ANALYSIS_FILE),
    }


# --------------------------------------------------------------------- #
# High-level: pick a business and run the full GBP -> SEO pipeline       #
# --------------------------------------------------------------------- #


def select_and_analyze(place_id: str, save_to_disk: bool = True) -> dict:
    """Run the full pipeline: fetch GBP -> save JSON -> run SEO_analyser.

    Returns a dict with:
        ``profile``         – normalized GBP profile dict
        ``analysis``        – normalized analysis ready for the view template
        ``competitive``     – competitive summary
        ``gbp_json_path``   – path to the saved GBP JSON (str)
        ``analysis_path``   – path to ``google_profile_analysis.json`` (str)
    """
    profile, error = get_profile(place_id)
    if profile is None:
        raise LookupError(error or "profile_not_found")

    gbp_json_path: Path | None = None
    if save_to_disk:
        try:
            gbp_json_path = save_gbp_json(profile)
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not save GBP JSON: %s", exc)

    # Run the *existing* SEO_analyser via the blueprint helper. It already
    # imports the module and normalizes the result.
    # analysis = _try_gemini_analysis(profile) or _local_score(profile)

    # Persist the raw Gemini output (when produced) to the same file the
    # CLI writes. Falls back to a normalized wrapper when only the local
    # scorer ran, so the file is always present.
    # _write_analysis_file(analysis, profile)

    # competitive = _competitive_summary(profile)
    
    
    analysis = _try_gemini_analysis(profile) or _local_score(profile)

    faq_jsonld = build_faq_jsonld(profile, analysis)

    _write_faq_jsonld_file(faq_jsonld)

    _write_analysis_file(
        analysis,
        profile,
        faq_jsonld=faq_jsonld,
    )

    competitive = _competitive_summary(profile)

    # return {
    #     "profile": profile,
    #     "analysis": analysis,
    #     "competitive": competitive,
    #     "gbp_json_path": str(gbp_json_path) if gbp_json_path else "",
    #     "analysis_path": str(ANALYSIS_FILE),
    # }
    return {
    "profile": profile,
    "analysis": analysis,
    "competitive": competitive,
    "faq_jsonld": faq_jsonld,
    "gbp_json_path": str(gbp_json_path) if gbp_json_path else "",
    "analysis_path": str(ANALYSIS_FILE),
}


def _write_analysis_file(analysis: dict, profile: dict, faq_jsonld: dict | None = None) -> None:
    """Write ``google_profile_analysis.json`` in the same location the CLI
    script does. We persist the *normalized* analysis (the same shape the
    UI renders) so reloading the page from disk shows the same report."""
    try:
        with open(ANALYSIS_FILE, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "profile": {k: v for k, v in profile.items() if k != "raw"},
                    "analysis": analysis,
                    "faq_jsonld": faq_jsonld or build_faq_jsonld(profile, analysis),
                },
                fh,
                indent=2,
                ensure_ascii=False,
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not write %s: %s", ANALYSIS_FILE, exc)


# --------------------------------------------------------------------- #
# Read back the saved analysis                                          #
# --------------------------------------------------------------------- #


def load_saved_analysis() -> dict | None:
    """Return the saved ``google_profile_analysis.json`` if it exists."""
    if not ANALYSIS_FILE.exists():
        return None
    try:
        with open(ANALYSIS_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not read %s: %s", ANALYSIS_FILE, exc)
        return None
