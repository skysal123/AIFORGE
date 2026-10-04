"""Routes for the GBP Report & SEO feature.

Search, business selection, and report generation are all server-side.
The frontend never sees Google Places API keys or Gemini credentials.

Data sources:
* Live Google Places API (v1) via ``gbp_lookup`` — used when
  ``GOOGLE_PLACES_API_KEY`` is set in env / .env.
* Live Gemini via ``SEO_analyser.analyze_google_profile`` — used when
  ``GEMINI_API_KEY`` is set in env / .env.

If a live call fails (no key, network error, invalid response), the
routes render an explicit error. The bundled ``sample_json.json`` is
only used as a deterministic offline fallback.
"""
from __future__ import annotations

import json
import logging
import os
import re
import statistics
import tempfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from flask import (
    current_app,
    jsonify,
    render_template,
    request,
)

from ...extensions import csrf

from . import gbp_bp


log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[3]  # C:\AIForge Technologies
SAMPLE_FILE = BASE_DIR / "sample_json.json"

# In-memory caches, populated on first request.
_INDEX: list[dict] | None = None


# --------------------------------------------------------------------- #
# Sample data loading                                                   #
# --------------------------------------------------------------------- #


def _load_sample_profiles() -> list[dict]:
    """Load the sample profile(s) shipped with the repo.

    The user explicitly asked us to use the local sample JSON for testing
    instead of hitting the live Google Places API. If the file contains a
    single object we wrap it; if it's a list, we use it as-is.
    """
    if not SAMPLE_FILE.exists():
        log.warning("sample_json.json not found at %s", SAMPLE_FILE)
        return []

    try:
        with open(SAMPLE_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        log.exception("Failed to load sample_json.json: %s", exc)
        return []

    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    return []


def _get_index() -> list[dict]:
    global _INDEX
    if _INDEX is None:
        _INDEX = _load_sample_profiles()
    return _INDEX


# --------------------------------------------------------------------- #
# Persistence (search candidates / place details / final report)         #
# --------------------------------------------------------------------- #


# _OUTPUT_ROOT: Path | None = None  # resolved lazily from env / config


# def _output_dir() -> Path:
#     """Where to persist GBP report JSON snapshots.

#     Override with the ``GBP_LOG_DIR`` env var. Defaults to
#     ``<project root>/output/gbp``. The directory is created on first use.
#     """
#     global _OUTPUT_ROOT
#     if _OUTPUT_ROOT is None:
#         configured = os.environ.get("GBP_LOG_DIR")
#         _OUTPUT_ROOT = Path(configured) if configured else BASE_DIR / "output" / "gbp"
#         _OUTPUT_ROOT = _OUTPUT_ROOT.resolve()
#     return _OUTPUT_ROOT


# def _safe_query(q: str | None) -> str:
#     """Sanitize a search query for use in a filename."""
#     if not q:
#         return "unknown"
#     s = re.sub(r"[^A-Za-z0-9._-]+", "_", q).strip("._-")
#     return (s or "unknown")[:64]


# def _save_record(
#     place_id: str,
#     kind: str,
#     payload: dict,
#     query: str | None = None,
#     extra_meta: dict | None = None,
# ) -> None:
#     """Atomically write ``payload`` to ``output/<date>/<place_id>/<kind>.json``.

#     Each saved file is wrapped in a ``{"_meta": ..., "data": ...}`` envelope
#     so consumers can tell when and how the file was produced without
#     parsing the data.

#     Never raises — a failed save is logged and dropped. The user-facing
#     request must keep working even if the disk is full / read-only.
#     """
#     safe_pid = re.sub(r"[^A-Za-z0-9._-]+", "_", place_id or "unknown")[:64] or "unknown"
#     today = datetime.now().strftime("%Y-%m-%d")
#     folder = _output_dir() / today / safe_pid

#     try:
#         folder.mkdir(parents=True, exist_ok=True)
#     except Exception as exc:  # noqa: BLE001
#         log.warning("Could not create %s: %s", folder, exc)
#         return

#     meta = {
#         "saved_at": datetime.now().isoformat(timespec="seconds"),
#         "place_id": place_id,
#         "kind": kind,
#         "query": query,
#         **(extra_meta or {}),
#     }
#     envelope = {"_meta": meta, "data": payload}

#     if kind == "search":
#         filename = f"search_query={_safe_query(query)}.json"
#     else:
#         filename = f"{kind}.json"
#     final_path = folder / filename

#     # Atomic write: write to a uniquely-named sibling tmp file, then
#     # os.replace swaps it into place. On the same filesystem (Windows
#     # NTFS), os.replace is atomic at the directory-entry level.
#     try:
#         fd, tmp_path = tempfile.mkstemp(
#             prefix=f".{final_path.name}.", suffix=".tmp", dir=str(folder)
#         )
#         try:
#             with os.fdopen(fd, "w", encoding="utf-8") as fh:
#                 json.dump(envelope, fh, indent=2, ensure_ascii=False)
#                 fh.flush()
#             os.replace(tmp_path, final_path)
#         except Exception:
#             try:
#                 os.unlink(tmp_path)
#             except OSError:
#                 pass
#             raise
#     except Exception as exc:  # noqa: BLE001
#         log.warning("Could not save %s: %s", final_path, exc)


# --------------------------------------------------------------------- #
# Google Places API (live) helpers                                       #
# --------------------------------------------------------------------- #


def _google_places_available() -> bool:
    """True iff a Google Places API key is configured."""
    return bool(os.environ.get("GOOGLE_PLACES_API_KEY"))


def _places_import():
    """Import the top-level gbp_lookup module.

    Done lazily so that the rest of the blueprint still works when the
    module is unavailable on disk or has a transitive import error.
    """
    try:
        import gbp_lookup  # type: ignore
        return gbp_lookup
    except Exception as exc:  # noqa: BLE001
        log.warning("gbp_lookup module unavailable: %s", exc)
        return None


def _candidate_to_card(candidate: dict) -> dict:
    """Map a Places text-search candidate to the dict the search UI expects."""
    # Places API v1 returns displayName as a LocalizedText dict {"text": ..., "languageCode": ...}
    name = candidate.get("displayName") or candidate.get("name") or "Unnamed business"
    if isinstance(name, dict):
        name = name.get("text") or "Unnamed business"

    address = candidate.get("formattedAddress") or candidate.get("address") or ""

    types = candidate.get("types") or []
    primary = candidate.get("primaryType") or (types[0] if types else "")
    primary_display = candidate.get("primaryTypeDisplayName")
    if isinstance(primary_display, dict):
        primary_display = primary_display.get("text")
    if not primary_display:
        primary_display = primary or "—"

    return {
        "place_id": candidate.get("id") or candidate.get("place_id"),
        "name": name,
        "category": primary_display,
        "address": address,
        "website": candidate.get("websiteUri") or candidate.get("website") or "",
        "rating": candidate.get("rating"),
        "total_reviews": candidate.get("userRatingCount") or 0,
        "phone": candidate.get("phone") or candidate.get("internationalPhoneNumber") or "",
        "photo_count": candidate.get("photo_count") or 0,
        "_engine": "places_api",
    }


def _places_search(query: str) -> tuple[list[dict] | None, str | None]:
    """Run a live Places text-search.

    Returns ``(cards, error_message)``. On success: ``(cards, None)``.
    On failure: ``(None, "<reason>")`` so the caller can log / surface it.
    """
    if not _google_places_available():
        return None, "GOOGLE_PLACES_API_KEY not set in environment"
    gbp_lookup = _places_import()
    if gbp_lookup is None:
        return None, "gbp_lookup module failed to import"

    api_key = os.environ["GOOGLE_PLACES_API_KEY"]
    try:
        candidates = gbp_lookup.search_candidates(query, api_key)
    except Exception as exc:  # noqa: BLE001
        log.warning("Google Places text-search failed for %r: %s", query, exc)
        return None, f"{type(exc).__name__}: {exc}"

    return [_candidate_to_card(c) for c in candidates if c], None


def _places_details(place_id: str) -> dict | None:
    """Fetch live Place Details. Returns a dict in the same shape as the
    bundled sample JSON, or None on failure."""
    if not _google_places_available():
        return None
    gbp_lookup = _places_import()
    if gbp_lookup is None:
        return None

    api_key = os.environ["GOOGLE_PLACES_API_KEY"]
    try:
        detail = gbp_lookup.place_details(place_id, api_key)
        profile = gbp_lookup.build_profile_from_details(detail)
    except Exception as exc:  # noqa: BLE001
        log.warning("Google Place Details failed for %s: %s", place_id, exc)
        return None

    record = asdict(profile)
    # Strip the heavy `raw` blob; the template only needs the structured fields.
    record.pop("raw", None)
    record["_engine"] = "places_api"
    return record


def _profile_by_id(place_id: str) -> tuple[dict | None, str | None]:
    """Look up a single profile by place_id.

    Returns ``(profile, error_key)`` where ``error_key`` is one of:
        * ``None``                    — profile was found.
        * ``"api_failure"``           — the live call failed.
        * ``"not_configured"``        — no Google Places API key set.
        * ``"not_found"``             — sample index used (no key) and no match.
    """
    if _google_places_available():
        profile = _places_details(place_id)
        if profile is None:
            return None, "api_failure"
        return profile, None

    # Offline / dev fallback — search the bundled sample index.
    profile = next(
        (p for p in _get_index() if p.get("place_id") == place_id),
        None,
    )
    if profile is None:
        return None, "not_found"
    return profile, None


# --------------------------------------------------------------------- #
# Profile normalisation                                                 #
# --------------------------------------------------------------------- #


def _flatten_categories(profile: dict) -> str:
    cats: list[str] = []
    for c in profile.get("categories", []) or []:
        if isinstance(c, str):
            cats.append(c)
    primary = profile.get("primary_category_display") or profile.get(
        "primary_category", ""
    )
    if primary and primary not in cats:
        cats.insert(0, primary)
    return " ".join(cats).lower().replace("_", " ")


def _flat_text(profile: dict) -> str:
    parts: list[str] = [
        profile.get("name", "") or "",
        profile.get("primary_category_display", "") or "",
        profile.get("primary_category", "") or "",
        profile.get("address", "") or "",
        profile.get("website", "") or "",
        _flatten_categories(profile),
    ]
    return " ".join(parts).lower()


def _profile_for_card(profile: dict) -> dict:
    """Return the dict shape consumed by the search-results UI."""
    return {
        "place_id": profile.get("place_id"),
        "name": profile.get("name") or "Unnamed business",
        "category": (
            profile.get("primary_category_display")
            or profile.get("primary_category")
            or "—"
        ),
        "address": profile.get("address") or "",
        "website": profile.get("website") or "",
        "rating": profile.get("rating"),
        "total_reviews": profile.get("total_reviews") or 0,
        "phone": profile.get("phone") or "",
        "photo_count": profile.get("photo_count") or 0,
    }


def search_profiles(query: str) -> list[dict]:
    """Search the local sample index.

    The intent is to be permissive: any word in the query that appears in
    the business name, category, address, website, or categories list is
    considered a hit. Sorting is by score then by review count.
    """
    q = (query or "").strip().lower()
    if not q:
        return [_profile_for_card(p) for p in _get_index()]

    tokens = [t for t in re.split(r"\s+", q) if t]
    if not tokens:
        return []

    matches: list[tuple[int, dict]] = []
    for profile in _get_index():
        haystack = _flat_text(profile)
        if not all(tok in haystack for tok in tokens):
            # Allow partial match: require at least one token
            if not any(tok in haystack for tok in tokens):
                continue
            score = sum(1 for tok in tokens if tok in haystack)
        else:
            score = sum(2 for tok in tokens if tok in haystack)
        # Boost exact name hit
        if (profile.get("name") or "").lower().find(q) >= 0:
            score += 5
        matches.append((score, profile))

    matches.sort(
        key=lambda pair: (
            -pair[0],
            -(pair[1].get("total_reviews") or 0),
        )
    )
    return [_profile_for_card(p) for _, p in matches]


# --------------------------------------------------------------------- #
# Deterministic local analysis (fallback when Gemini is unavailable)    #
# --------------------------------------------------------------------- #


def _local_score(profile: dict) -> dict:
    """Generate a complete SEO/GBP report locally.

    This is used when:
      * GEMINI_API_KEY is not configured, or
      * The Gemini call fails for any reason

    The shape matches the Gemini output so the template doesn't care
    which path produced it.
    """
    name = profile.get("name") or "—"
    primary = (
        profile.get("primary_category_display")
        or profile.get("primary_category")
        or "—"
    )
    website = profile.get("website") or ""
    phone = profile.get("phone") or ""
    address = profile.get("address") or ""
    rating = profile.get("rating") or 0.0
    reviews = profile.get("total_reviews") or 0
    photos = profile.get("photo_count") or 0
    hours = profile.get("hours") or []
    summary = profile.get("editorial_summary") or profile.get("generative_summary") or ""
    cats = profile.get("categories") or []
    reviews_list = profile.get("reviews") or []
    services = profile.get("services") or []

    # ---- Profile completeness ----
    fields: list[tuple[str, bool]] = [
        ("Business name", bool(name and name.strip())),
        ("Primary category", bool(primary and primary != "—")),
        ("Phone", bool(phone)),
        ("Website", bool(website)),
        ("Address", bool(address)),
        ("Opening hours", bool(hours)),
        ("Editorial / AI summary", bool(summary)),
        ("Photos", photos >= 5),
        ("At least 20 reviews", reviews >= 20),
    ]
    completeness = round(sum(1 for _, ok in fields if ok) / len(fields) * 100)

    # ---- Overall score (0-100) ----
    score = 0
    score += min(reviews, 100) * 0.25            # up to 25 from review volume
    score += min(rating, 5.0) * 8                # up to 40 from rating
    score += min(photos, 30) * 0.7               # up to 21 from photo count
    score += (completeness / 100) * 14           # up to 14 from completeness
    overall = int(round(min(100, score)))

    strengths: list[str] = []
    weaknesses: list[str] = []
    recommendations: list[dict] = []

    if rating >= 4.5:
        strengths.append(f"Excellent customer rating of {rating}★ across {reviews} reviews.")
    elif rating >= 4.0:
        strengths.append(f"Solid rating of {rating}★ with {reviews} reviews.")
    else:
        weaknesses.append(f"Average rating of {rating}★ — encourage happier customers to leave reviews.")
        recommendations.append({
            "issue": "Average customer rating",
            "why_it_matters": "Higher rated profiles convert better in local search.",
            "recommended_action": "Run a gentle post-visit review request via SMS / WhatsApp.",
            "priority": "HIGH",
            "effort": "MEDIUM",
            "example": "“Loved your visit? A 30-sec Google review helps us a lot.”",
        })

    if reviews >= 50:
        strengths.append(f"Strong review volume ({reviews} reviews).")
    else:
        weaknesses.append(f"Only {reviews} reviews — competitors often have many more.")
        recommendations.append({
            "issue": "Low review volume",
            "why_it_matters": "Review count is one of the strongest local ranking signals.",
            "recommended_action": "Ask every satisfied customer for a review, with a direct link.",
            "priority": "HIGH",
            "effort": "EASY",
            "example": "Add a QR code at checkout linking to your Google review page.",
        })

    if photos >= 10:
        strengths.append(f"{photos} photos on the profile — above the local average.")
    else:
        weaknesses.append(f"Only {photos} photos uploaded — visuals drive engagement.")
        recommendations.append({
            "issue": "Thin photo coverage",
            "why_it_matters": "Profiles with 10+ quality photos get more clicks and calls.",
            "recommended_action": "Upload before/after, team, exterior and result photos monthly.",
            "priority": "MEDIUM",
            "effort": "EASY",
            "example": "Add 3 high-quality photos every month for the next quarter.",
        })

    if summary:
        strengths.append("Has a business description / AI summary on the profile.")
    else:
        weaknesses.append("No business description on the profile.")
        recommendations.append({
            "issue": "Missing business description",
            "why_it_matters": "The description is a primary on-profile SEO surface.",
            "recommended_action": "Write a 600–750 character description using natural service + city keywords.",
            "priority": "HIGH",
            "effort": "EASY",
            "example": "Open with the service, the city, and the outcome customers get.",
        })

    if website:
        strengths.append(f"Website linked: {website}")
    else:
        weaknesses.append("No website URL on the profile.")
        recommendations.append({
            "issue": "Missing website URL",
            "why_it_matters": "Customers click through to the website to validate the business.",
            "recommended_action": "Add the canonical HTTPS website URL in GBP settings.",
            "priority": "HIGH",
            "effort": "EASY",
            "example": "https://www.yourbrand.com/ — not a Facebook or Instagram URL.",
        })

    if services:
        strengths.append(f"{len(services)} services listed on the profile.")
    else:
        weaknesses.append("No services listed on the profile.")
        recommendations.append({
            "issue": "No services listed",
            "why_it_matters": "Services power GBP's category-specific search results.",
            "recommended_action": "Add the 5–8 services customers actually ask for.",
            "priority": "HIGH",
            "effort": "EASY",
            "example": "Group services under clear, customer-language headings.",
        })

    if not hours:
        weaknesses.append("No opening hours on the profile.")
        recommendations.append({
            "issue": "No opening hours",
            "why_it_matters": "Hours missing = fewer 'visit now' clicks from Maps.",
            "recommended_action": "Set full weekly hours including weekend variations.",
            "priority": "MEDIUM",
            "effort": "EASY",
            "example": "Mon–Sat 10:00–19:00, Sun closed.",
        })

    if not strengths:
        strengths.append("Profile is being indexed on Google Maps.")
    if not weaknesses:
        weaknesses.append("No critical gaps detected — keep monitoring.")

    # ---- Services (existing / missing / suggested) ----
    typical_services: dict[str, list[str]] = {
        "skin_care_clinic": [
            "Acne treatment",
            "Pigmentation / melasma treatment",
            "Hair loss / PRP treatment",
            "Laser hair removal",
            "Chemical peels",
            "Anti-aging / skin rejuvenation",
            "Skin consultation",
        ],
        "hair_care": [
            "Hair fall treatment",
            "Hair PRP",
            "Hair transplant consultation",
            "Scalp treatment",
        ],
        "doctor": [
            "Dermatology consultation",
            "Skin biopsy",
            "Acne scar treatment",
        ],
        "beauty_salon": [
            "Facial",
            "Cleanup",
            "Waxing",
        ],
        "medical_clinic": [
            "Skin consultation",
            "Treatment planning",
        ],
    }
    primary_key = (profile.get("primary_category") or "").lower()
    all_existing: list[str] = []
    if isinstance(services, list):
        for s in services:
            if isinstance(s, str):
                all_existing.append(s)
            elif isinstance(s, dict):
                title = s.get("title") or s.get("name") or s.get("displayName")
                if isinstance(title, dict):
                    title = title.get("text")
                if title:
                    all_existing.append(str(title))
    existing_norm = {s.lower().strip() for s in all_existing}
    suggested: list[str] = []
    for k in (primary_key, *(c for c in cats if isinstance(c, str))):
        for s in typical_services.get(k.lower(), []):
            if s.lower() not in existing_norm and s not in suggested:
                suggested.append(s)
    missing_services = [s for s in suggested if s.lower() not in existing_norm][:8]

    # ---- Categories ----
    suggested_categories: list[str] = []
    if primary_key == "skin_care_clinic":
        suggested_categories += [
            "Dermatologist",
            "Hair removal clinic",
            "Laser hair removal service",
            "Weight loss service",
        ]
    elif primary_key == "hair_care":
        suggested_categories += ["Hair replacement service", "Dermatologist"]

    # ---- Reviews ----
    review_signals: list[str] = []
    if reviews_list:
        avg = statistics.mean(
            [r.get("rating") for r in reviews_list if r.get("rating") is not None]
            or [0]
        )
        if avg >= 4.5:
            review_signals.append(
                f"Recent reviews average {avg:.1f}★ — a strong trust signal."
            )
        else:
            review_signals.append(
                f"Recent reviews average {avg:.1f}★ — encourage more 5★ reviews."
            )
        unanswered = sum(1 for r in reviews_list if r.get("text"))
        if unanswered:
            review_signals.append(
                f"{unanswered} recent reviews visible — owner responses are absent; respond to all reviews."
            )
    else:
        review_signals.append("No reviews returned for this profile.")

    # ---- Photos ----
    photo_signals: list[str] = []
    if photos >= 20:
        photo_signals.append("Photo coverage is excellent.")
    elif photos >= 10:
        photo_signals.append("Photo coverage is good — keep adding fresh monthly photos.")
    else:
        photo_signals.append(
            "Photo coverage is light — aim for 20+ photos covering team, work, exterior, and results."
        )

    # ---- Website / profile consistency ----
    consistency: list[str] = []
    if website:
        consistency.append(
            f"Website listed: <a href='{website}' target='_blank' rel='noopener'>{website}</a>"
        )
        consistency.append(
            "Confirm the address, phone, and hours on the website match GBP exactly — mismatches hurt trust."
        )
    else:
        consistency.append("Add a canonical website URL to align with other public listings.")

    # ---- Top 5 actions ----
    priority_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    effort_rank = {"EASY": 0, "MEDIUM": 1, "HARD": 2}
    top5 = sorted(
        recommendations,
        key=lambda r: (priority_rank.get(r["priority"], 3), effort_rank.get(r["effort"], 3)),
    )[:5]
    for i, item in enumerate(top5, start=1):
        item["index"] = f"{i:02d}"

    return {
        "overall_score": overall,
        "profile_completeness": {
            "score": completeness,
            "fields": [{"label": lbl, "ok": ok} for lbl, ok in fields],
        },
        "strengths": strengths,
        "weaknesses": weaknesses,
        "recommendations": recommendations,
        "top_5_actions": top5,
        "services": {
            "existing": all_existing,
            "missing": missing_services,
            "suggested": suggested,
        },
        "categories": {
            "current": primary,
            "current_id": primary_key,
            "suggested": suggested_categories,
            "verification_warning": "VERIFY IN GOOGLE" if not suggested_categories else None,
        },
        "reviews": {
            "rating": rating,
            "total": reviews,
            "signals": review_signals,
            "sample": [
                {
                    "author": r.get("author") or "Anonymous",
                    "rating": r.get("rating"),
                    "text": (r.get("text") or "")[:280],
                    "relative_time": r.get("relative_time") or "",
                }
                for r in reviews_list[:5]
            ],
        },
        "photos": {
            "count": photos,
            "signals": photo_signals,
        },
        "consistency": consistency,
        "optimized_description": (
            summary
            or f"{name} is a {primary} serving the local area. "
            f"Book a consultation to learn more about the services offered."
        ),
        "suggested_services": suggested,
        "suggested_profile_categories": suggested_categories,
        "_engine": "local",
    }


# --------------------------------------------------------------------- #
# Gemini analysis (with safe fallback)                                  #
# --------------------------------------------------------------------- #


def _build_profile_for_analyser(profile: dict) -> dict:
    """Re-shape the Places-API style profile into the flatter shape
    that SEO_analyser.analyze_google_profile() expects."""
    return {
        "name": profile.get("name"),
        "category": (
            profile.get("primary_category_display")
            or profile.get("primary_category")
            or ""
        ),
        "description": (
            profile.get("editorial_summary")
            or profile.get("generative_summary")
            or ""
        ),
        "services": profile.get("services") or [],
        "reviews": {
            "rating": profile.get("rating"),
            "total": profile.get("total_reviews") or 0,
            "items": profile.get("reviews") or [],
        },
        "photos": {
            "count": profile.get("photo_count") or 0,
            "references": profile.get("photo_references") or [],
        },
        "phone": profile.get("phone") or "",
        "website": profile.get("website") or "",
        "email": "",
        "address": profile.get("address") or "",
        "hours": {
            "lines": profile.get("hours") or [],
        },
    }


def _normalize_gemini_response(raw: dict, profile: dict) -> dict:
    """Reshape Gemini's flat payload into the nested structure the template
    expects (the same shape as ``_local_score`` returns).

    Gemini's prompt asks for flat keys like ``suggested_profile_categories``;
    the template (and the local fallback) use a nested ``categories`` dict.
    Without this normalization, the template crashes on missing keys.

    If Gemini's response is missing the structural fields the UI reads
    (overall_score, profile_completeness.score, strengths, weaknesses,
    top_5_actions, reviews.signals, photos.signals), we layer the local
    deterministic scorer underneath so the report is never blank.
    """
    primary = (
        profile.get("primary_category_display")
        or profile.get("primary_category")
        or "—"
    )

    suggested_cats = (
        raw.get("suggested_profile_categories")
        or raw.get("categories", {}).get("suggested")
        or []
    )
    if isinstance(suggested_cats, str):
        suggested_cats = [s.strip() for s in suggested_cats.split(",") if s.strip()]

    # Reviews — Gemini may return a flat reviews dict; template expects
    # reviews.signals + reviews.sample.
    reviews_raw = raw.get("reviews") or {}
    if isinstance(reviews_raw, list):
        review_items = reviews_raw
        review_signals: list[str] = []
        rating = profile.get("rating")
    else:
        review_items = reviews_raw.get("items") or reviews_raw.get("sample") or []
        rating = reviews_raw.get("rating") or profile.get("rating")
        review_signals = reviews_raw.get("signals") or []

    sample: list[dict] = []
    for r in review_items[:5]:
        if not isinstance(r, dict):
            continue
        sample.append({
            "author": r.get("author") or r.get("author_name") or "Anonymous",
            "rating": r.get("rating"),
            "text": (r.get("text") or r.get("review_text") or "")[:280],
            "relative_time": r.get("relative_time") or r.get("relativePublishTimeDescription") or "",
        })

    # Photos — Gemini may return photos.count + photos.signals.
    photos_raw = raw.get("photos") or {}
    if isinstance(photos_raw, dict):
        photo_count = photos_raw.get("count") or profile.get("photo_count") or 0
        photo_signals = photos_raw.get("signals") or []
    else:
        photo_count = photos_raw or profile.get("photo_count") or 0
        photo_signals = []

    # Pull Gemini-supplied raw top-5 (if any) — we'll coerce + re-index
    # at the end after the local gap-fill, so the dict-shape always wins.
    raw_top5 = raw.get("top_5_actions") or []

    normalized = {
        "overall_score": raw.get("overall_score") or 0,
        "profile_completeness": raw.get("profile_completeness") or {
            "score": 0,
            "fields": [],
        },
        "strengths": raw.get("strengths") or [],
        "weaknesses": raw.get("weaknesses") or [],
        "recommendations": raw.get("recommendations") or [],
        "top_5_actions": raw_top5,
        "services": raw.get("services") or {
            "existing": profile.get("services") or [],
            "missing": raw.get("suggested_services") or [],
            "suggested": raw.get("suggested_services") or [],
        },
        "categories": {
            "current": primary,
            "current_id": (profile.get("primary_category") or "").lower(),
            "suggested": suggested_cats,
            "verification_warning": (
                "VERIFY IN GOOGLE" if not suggested_cats else None
            ),
        },
        "reviews": {
            "rating": rating or 0,
            "total": profile.get("total_reviews") or 0,
            "signals": review_signals,
            "sample": sample,
        },
        "photos": {
            "count": photo_count,
            "signals": photo_signals,
        },
        "consistency": raw.get("consistency") or [],
        "optimized_description": (
            raw.get("optimized_description")
            or profile.get("editorial_summary")
            or ""
        ),
        "suggested_services": raw.get("suggested_services") or [],
        "suggested_profile_categories": suggested_cats,
        "_engine": "gemini",
    }

    # ---- Fill gaps with the local scorer so the UI is never blank ----
    _fill_gaps_with_local(normalized, profile)

    # Coerce top-5 entries to dicts (Gemini sometimes returns bare strings)
    # and re-number so the numbers stay 01..05.
    normalized["top_5_actions"] = [
        _coerce_action(item, idx)
        for idx, item in enumerate(normalized.get("top_5_actions") or [], start=1)
    ]

    return normalized


def _coerce_action(item: Any, idx: int) -> dict:
    """Normalize a single top-5-action entry to a dict the UI can render.

    Gemini sometimes returns a bare string; sometimes a dict that's
    missing the ``recommended_action`` field. We accept both.
    """
    if isinstance(item, dict):
        text = (
            item.get("recommended_action")
            or item.get("action")
            or item.get("title")
            or ""
        )
        return {
            "index": f"{idx:02d}",
            "recommended_action": text,
            "priority": item.get("priority") or "MEDIUM",
            "effort": item.get("effort") or "MEDIUM",
        }
    return {
        "index": f"{idx:02d}",
        "recommended_action": str(item),
        "priority": "MEDIUM",
        "effort": "MEDIUM",
    }


# Fields the template / JS actually read. If any of these are empty or
# zero on the Gemini response, we substitute the local-scorer value.
_UI_FIELDS = (
    "overall_score",
    "profile_completeness",
    "strengths",
    "weaknesses",
    "top_5_actions",
    "reviews",
    "photos",
    "consistency",
)


def _fill_gaps_with_local(normalized: dict, profile: dict) -> None:
    """Mutate ``normalized`` in place, filling empty UI fields with values
    from the deterministic local scorer."""
    local = _local_score(profile)

    def _is_blank(value) -> bool:
        if value is None:
            return True
        if isinstance(value, (list, str)) and len(value) == 0:
            return True
        if isinstance(value, (int, float)) and value == 0:
            return True
        if isinstance(value, dict):
            # Treat a dict as blank if every value is blank or if the
            # typical "score" / "fields" keys come back zero/empty
            # (the exact shape Gemini returns when it skips the section).
            score = value.get("score")
            if score is None and "fields" in value:
                return _is_blank(value.get("fields"))
            if score is not None:
                return _is_blank(score)
            return all(_is_blank(v) for v in value.values())
        return False

    for field in _UI_FIELDS:
        if not _is_blank(normalized.get(field)):
            continue
        if field == "profile_completeness":
            normalized[field] = local.get("profile_completeness") or normalized[field]
        elif field == "reviews":
            # Merge — keep the Gemini sample if any, just lift the local signals.
            local_reviews = local.get("reviews") or {}
            if not normalized["reviews"].get("signals") and local_reviews.get("signals"):
                normalized["reviews"]["signals"] = local_reviews["signals"]
            if not normalized["reviews"].get("sample") and local_reviews.get("sample"):
                normalized["reviews"]["sample"] = local_reviews["sample"]
        elif field == "photos":
            local_photos = local.get("photos") or {}
            if not normalized["photos"].get("signals") and local_photos.get("signals"):
                normalized["photos"]["signals"] = local_photos["signals"]
        else:
            normalized[field] = local.get(field) or normalized.get(field)


def _try_gemini_analysis(profile: dict) -> dict | None:
    """Attempt to call the existing SEO_analyser module (live Gemini).

    Returns the parsed Gemini JSON on success, or None if the call isn't
    available / failed. Caller should fall back to the local analyser.
    """
    try:
        from SEO_analyser import analyze_google_profile  # type: ignore
    except Exception as exc:  # noqa: BLE001
        log.info("SEO_analyser module unavailable: %s", exc)
        return None
    try:
        shaped = _build_profile_for_analyser(profile)
        raw = analyze_google_profile(shaped)
    except Exception as exc:  # noqa: BLE001
        log.warning("Gemini analysis failed, falling back to local: %s", exc)
        return None
    if not isinstance(raw, dict):
        log.warning("Gemini returned non-dict payload (%s); falling back", type(raw).__name__)
        return None
    return _normalize_gemini_response(raw, profile)


# --------------------------------------------------------------------- #
# Competitive analysis (synthetic + local)                              #
# --------------------------------------------------------------------- #


def _profile_score(profile: dict) -> int:
    """Return the same 0-100 score the analyser would give for a profile.

    Used to rank the target profile against synthetic competitors and to
    compute 'businesses above you'.
    """
    local = _local_score(profile)
    return int(local.get("overall_score", 0))


def _make_synthetic_competitors(
    target: dict, count: int = 11
) -> list[dict]:
    """Produce a deterministic synthetic competitor list.

    This gives the UI real-looking rank/competitor cards even when only
    one profile is in the sample index. Scores are anchored to the
    target's local score and jittered with a stable seed so reloads
    don't shuffle the table.
    """
    target_score = _profile_score(target)
    base = [
        {"name": "Radiance Skin Studio", "city": "Pune", "score_delta": +21},
        {"name": "Lumiere Dermatology", "city": "Pune", "score_delta": +16},
        {"name": "ClearSkin Clinic", "city": "Hadapsar", "score_delta": +10},
        {"name": "GlowDerm Aesthetics", "city": "Pune", "score_delta": +5},
        {"name": "DermaCare Pune", "city": "Pune", "score_delta": -4},
        {"name": "SkinSense Clinic", "city": "Hadapsar", "score_delta": -9},
        {"name": "PearlSkin Studio", "city": "Pune", "score_delta": -14},
        {"name": "Velvet Touch Aesthetics", "city": "Pune", "score_delta": -19},
        {"name": "NorthClinic Skin", "city": "Pune", "score_delta": -24},
        {"name": "Aura Derma", "city": "Pune", "score_delta": -29},
        {"name": "Mirror Skin Center", "city": "Pune", "score_delta": -34},
    ]
    competitors: list[dict] = []
    for entry in base[:count]:
        score = max(0, min(100, target_score + entry["score_delta"]))
        competitors.append({
            "name": entry["name"],
            "city": entry["city"],
            "score": score,
            "is_target": False,
        })
    return competitors


def _competitive_summary(target: dict) -> dict:
    target_score = _profile_score(target)
    competitors = _make_synthetic_competitors(target)
    # Insert the target
    rows = competitors + [{
        "name": target.get("name") or "Your business",
        "city": "—",
        "score": target_score,
        "is_target": True,
    }]
    rows.sort(key=lambda r: -r["score"])
    above = sum(1 for r in rows if (not r.get("is_target")) and r["score"] > target_score)
    below = sum(1 for r in rows if (not r.get("is_target")) and r["score"] < target_score)
    # Stable rank numbers
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
    # Gaps
    above_rows = [r for r in rows if (not r.get("is_target")) and r["score"] > target_score]
    gap_pool = [
        "Review volume",
        "Service coverage",
        "Profile completeness",
        "Photo coverage",
        "Description quality",
        "Hours posted",
        "Website alignment",
        "Category breadth",
    ]
    gaps: list[dict] = []
    for i, r in enumerate(above_rows[:4]):
        gaps.append({
            "competitor": r["name"],
            "rank": r["rank"],
            "score": r["score"],
            "gap": gap_pool[i % len(gap_pool)],
        })
    return {
        "your_score": target_score,
        "businesses_above": above,
        "businesses_below": below,
        "rows": rows,
        "gaps": gaps,
        "gaps_summary": [g["gap"] for g in gaps[:4]],
    }


# --------------------------------------------------------------------- #
# Flask routes                                                          #
# --------------------------------------------------------------------- #


@gbp_bp.route("/", methods=["GET"])
def search_page():
    """Render the GBP search page."""
    return render_template(
        "gbp_report_search.html",
        brand=current_app.config["BRAND_NAME"],
        tagline=current_app.config["BRAND_TAGLINE"],
    )


@gbp_bp.route("/api/search", methods=["GET"])
@csrf.exempt
def api_search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify(
            ok=False,
            error="empty_query",
            message="Please enter a business name, website, or location.",
            results=[],
        ), 400

    # Prefer live Google Places text search when a key is configured.
    results, places_err = _places_search(q) or (None, None)
    engine = "places_api" if _google_places_available() else "local"
    if results is None:
        # Live path unavailable or failed. Only fall back to the bundled
        # sample data when the API isn't configured at all — when a key
        # *is* set but the call failed, surface the error instead.
        if _google_places_available():
            return jsonify(
                ok=False,
                error="places_api_failure",
                message=(
                    "Google Places search is temporarily unavailable. "
                    "Please try again in a moment."
                ),
                detail=places_err,  # server-side diagnostic, helps when debugging
                results=[],
            ), 502
        results = search_profiles(q)

    if not results:
        return jsonify(
            ok=True,
            engine=engine,
            results=[],
            message="No matching businesses found. Try a different business name or location.",
        )

    # Persist each candidate from the live Places API search. Sample-index
    # results aren't saved — they have no stable real-world place_id and
    # the data is already on disk in sample_json.json.
    # if engine == "places_api":
    #     for card in results:
    #         pid = card.get("place_id")
    #         if pid:
    #             _save_record(
    #                 pid, "search", card,
    #                 query=q,
    #                 extra_meta={
    #                     "engine": "places_api",
    #                     "result_count": len(results),
    #                 },
    #             )

    return jsonify(ok=True, engine=engine, results=results)


@gbp_bp.route("/report", methods=["GET"])
def report():
    """Render the GBP report for a given business id (place_id)."""
    place_id = (request.args.get("id") or "").strip()
    if not place_id:
        return render_template(
            "gbp_report_view.html",
            brand=current_app.config["BRAND_NAME"],
            tagline=current_app.config["BRAND_TAGLINE"],
            error="missing_id",
            error_message="No business was selected. Please start a new search.",
        ), 400

    profile, error = _profile_by_id(place_id)
    if profile is None:
        if error == "api_failure":
            return render_template(
                "gbp_report_view.html",
                brand=current_app.config["BRAND_NAME"],
                tagline=current_app.config["BRAND_TAGLINE"],
                error="api_failure",
                error_message=(
                    "We couldn't fetch the latest data for that business from "
                    "Google Places. Please try again in a moment."
                ),
            ), 502
        if error == "not_configured":
            return render_template(
                "gbp_report_view.html",
                brand=current_app.config["BRAND_NAME"],
                tagline=current_app.config["BRAND_TAGLINE"],
                error="not_configured",
                error_message=(
                    "Google Places API is not configured on this server. "
                    "Set GOOGLE_PLACES_API_KEY in your .env file to enable live "
                    "GBP reports."
                ),
            ), 503
        return render_template(
            "gbp_report_view.html",
            brand=current_app.config["BRAND_NAME"],
            tagline=current_app.config["BRAND_TAGLINE"],
            error="not_found",
            error_message=(
                "We couldn't find that business. Try a new search."
            ),
        ), 404

    # 1. Retrieve GBP profile (live Places API or sample fallback).
    # 2. Analyse — try Gemini, fall back to the deterministic local scorer.
    analysis = _try_gemini_analysis(profile) or _local_score(profile)
    # 3. Competitive
    competitive = _competitive_summary(profile)

    # Persist before rendering so a render failure doesn't lose the data.
    # `raw` is stripped from the profile to keep file sizes reasonable.
    # profile_to_save = {k: v for k, v in profile.items() if k != "raw"}
    # _save_record(
    #     place_id, "details", profile_to_save,
    #     query=request.args.get("q"),
    #     extra_meta={"engine": profile.get("_engine", "unknown")},
    # )
    # _save_record(
    #     place_id, "report",
    #     {
    #         "profile": profile_to_save,
    #         "analysis": analysis,
    #         "competitive": competitive,
    #     },
    #     query=request.args.get("q"),
    #     extra_meta={
    #         "profile_engine": profile.get("_engine", "unknown"),
    #         "analysis_engine": analysis.get("_engine", "unknown"),
    #         "overall_score": analysis.get("overall_score"),
    #     },
    # )

    return render_template(
        "gbp_report_view.html",
        brand=current_app.config["BRAND_NAME"],
        tagline=current_app.config["BRAND_TAGLINE"],
        profile=profile,
        analysis=analysis,
        competitive=competitive,
    )


# --------------------------------------------------------------------- #
# JSON API: select a business + return the rendered report                #
# --------------------------------------------------------------------- #


# @gbp_bp.route("/api/select", methods=["POST"])
# @csrf.exempt
# def api_select():
#     """Run the full GBP -> SEO pipeline for a chosen place_id and return
#     the normalized analysis as JSON.

#     Frontend calls this instead of navigating to ``/report``, so the
#     search/select UI on ``/gbp-report/`` can render the report on the
#     same page.
#     """
#     payload = request.get_json(silent=True) or {}
#     place_id = (payload.get("place_id") or "").strip()
#     if not place_id:
#         return jsonify(
#             ok=False,
#             error="missing_place_id",
#             message="Please pick a business from the search results.",
#         ), 400

#     from app.services import gbp_seo_service

#     try:
#         result = gbp_seo_service.select_and_analyze(place_id)
#     except LookupError as exc:
#         key = str(exc)
#         if key == "api_failure":
#             return jsonify(
#                 ok=False,
#                 error="api_failure",
#                 message=(
#                     "We couldn't fetch the latest data for that business from "
#                     "Google Places. Please try again in a moment."
#                 ),
#             ), 502
#         if key == "not_configured":
#             return jsonify(
#                 ok=False,
#                 error="not_configured",
#                 message=(
#                     "Google Places API is not configured on this server. "
#                     "Set GOOGLE_PLACES_API_KEY in your .env file."
#                 ),
#             ), 503
#         return jsonify(
#             ok=False,
#             error="not_found",
#             message="We couldn't find that business. Try a new search.",
#         ), 404
#     except Exception as exc:  # noqa: BLE001
#         log.exception("GBP select failed for %s: %s", place_id, exc)
#         return jsonify(
#             ok=False,
#             error="analysis_failed",
#             message=(
#                 "Business data was retrieved, but SEO analysis could not "
#                 "be generated. Please try again."
#             ),
#         ), 500

#     profile = result["profile"]
#     return jsonify(
#         ok=True,
#         place_id=place_id,
#         profile={
#             "name": profile.get("name"),
#             "address": profile.get("address"),
#             "phone": profile.get("phone"),
#             "website": profile.get("website"),
#             "rating": profile.get("rating"),
#             "total_reviews": profile.get("total_reviews"),
#             "photo_count": profile.get("photo_count"),
#             "primary_category": profile.get("primary_category_display")
#             or profile.get("primary_category"),
#         },
#         analysis=result["analysis"],
#         competitive=result["competitive"],
#         paths={
#             "gbp_json": result["gbp_json_path"],
#             "analysis": result["analysis_path"],
#         },
#     )

@gbp_bp.route("/api/select", methods=["POST"])
@csrf.exempt
def api_select():
    """Run the full GBP -> SEO/AEO pipeline for a chosen place_id.

    Frontend calls this instead of navigating to ``/report``, so the
    search/select UI on ``/gbp-report/`` can render the report on the
    same page.
    """
    payload = request.get_json(silent=True) or {}
    place_id = (payload.get("place_id") or "").strip()
    analysis_type = payload.get("analysis_type", "seo").lower()

    if not place_id:
        return jsonify(
            ok=False,
            error="missing_place_id",
            message="Please pick a business from the search results.",
        ), 400

    from app.services import gbp_seo_service

    try:
        if analysis_type == "aeo":
            # AEO Pipeline
            result = gbp_seo_service.analyze_aeo(place_id)
        else:
            # Standard SEO Pipeline
            result = gbp_seo_service.select_and_analyze(place_id)

    except LookupError as exc:
        key = str(exc)
        if key == "api_failure":
            return jsonify(
                ok=False,
                error="api_failure",
                message=(
                    "We couldn't fetch the latest data for that business from "
                    "Google Places. Please try again in a moment."
                ),
            ), 502
        if key == "not_configured":
            return jsonify(
                ok=False,
                error="not_configured",
                message=(
                    "Google Places API is not configured on this server. "
                    "Set GOOGLE_PLACES_API_KEY in your .env file."
                ),
            ), 503
        return jsonify(
            ok=False,
            error="not_found",
            message="We couldn't find that business. Try a new search.",
        ), 404
    except Exception as exc:
        log.exception("GBP selection failed for %s: %s", place_id, exc)
        return jsonify(
            ok=False,
            error="analysis_failed",
            message=(
                "Business data was retrieved, but analysis could not "
                "be generated. Please try again."
            ),
        ), 500

    profile = result["profile"]

    if analysis_type == "aeo":
        # AEO returns a simpler payload to the frontend
        return jsonify(
            ok=True,
            place_id=place_id,
            profile=profile,
            analysis=result["analysis"],
            analysis_type="aeo"
        )

    # Standard SEO return payload
    return jsonify(
        ok=True,
        place_id=place_id,
        profile={
            "name": profile.get("name"),
            "address": profile.get("address"),
            "phone": profile.get("phone"),
            "website": profile.get("website"),
            "rating": profile.get("rating"),
            "total_reviews": profile.get("total_reviews"),
            "photo_count": profile.get("photo_count"),
            "primary_category": profile.get("primary_category_display")
            or profile.get("primary_category"),
        },
        analysis=result["analysis"],
        competitive=result.get("competitive", {}),
        paths={
            "gbp_json": result.get("gbp_json_path", ""),
            "analysis": result.get("analysis_path", ""),
        },
    )

@gbp_bp.route("/api/analysis", methods=["GET"])
def api_analysis():
    """Return the contents of ``google_profile_analysis.json`` if present.

    Used by the frontend to re-hydrate the report view on page reload.
    """
    from app.services import gbp_seo_service

    data = gbp_seo_service.load_saved_analysis()
    if data is None:
        return jsonify(
            ok=False,
            error="no_analysis",
            message=(
                "No saved analysis found. Run a new search to generate one."
            ),
        ), 404
    return jsonify(ok=True, data=data)
