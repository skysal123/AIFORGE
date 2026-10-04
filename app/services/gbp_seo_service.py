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
    analysis = _try_gemini_analysis(profile) or _local_score(profile)

    # Persist the raw Gemini output (when produced) to the same file the
    # CLI writes. Falls back to a normalized wrapper when only the local
    # scorer ran, so the file is always present.
    _write_analysis_file(analysis, profile)

    competitive = _competitive_summary(profile)

    return {
        "profile": profile,
        "analysis": analysis,
        "competitive": competitive,
        "gbp_json_path": str(gbp_json_path) if gbp_json_path else "",
        "analysis_path": str(ANALYSIS_FILE),
    }


def _write_analysis_file(analysis: dict, profile: dict, filename: str = "google_profile_analysis.json") -> None:
    """Write analysis to a JSON file."""
    out_path = BASE_DIR / filename
    try:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "profile": {k: v for k, v in profile.items() if k != "raw"},
                    "analysis": analysis,
                },
                fh,
                indent=2,
                ensure_ascii=False,
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not write %s: %s", out_path, exc)

def analyze_aeo(place_id: str) -> dict:
    """Run the full AEO analysis pipeline."""
    profile, error = get_profile(place_id)
    if profile is None:
        raise LookupError(error or "profile_not_found")

    analysis = None
    try:
        import AEO_analyser
        analysis = AEO_analyser.analyze_aeo(profile)
    except Exception as exc:
        log.warning("AEO Gemini analysis failed, falling back to local: %s", exc)

    if analysis is None:
        try:
            import AEO_analyser
            analysis = AEO_analyser.local_aeo_score(profile)
        except Exception as exc:
            log.error("AEO local score failed: %s", exc)
            raise RuntimeError("AEO analysis completely failed")

    _write_analysis_file(analysis, profile, "aeo_profile_analysis.json")

    return {
        "profile": profile,
        "analysis": analysis,
    }


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
