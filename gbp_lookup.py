"""
Google Business Profile lookup tool.

Tries the official Google Places API first (clean, structured, reliable).
Falls back to Playwright-based scraping when an API key isn't available
or when you need data Places API doesn't expose (e.g. full Q&A lists,
all photos, complete review text).

Usage:
    python gbp_lookup.py "AIForge technologies"
    python gbp_lookup.py "AIForge technologies" --json out.json
    python gbp_lookup.py --file queries.txt --csv results.csv

Set GOOGLE_PLACES_API_KEY in your environment to enable the API path.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.parse
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

import requests

# Force UTF-8 stdout/stderr so we can print Unicode separators etc. on Windows.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass  # dotenv not installed; rely on actual env vars


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PLACES_TEXTSEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_DETAILS_URL_BASE = "https://places.googleapis.com/v1/places"
PLACES_PHOTO_URL = "https://places.googleapis.com/v1/{name}/media"

# Field mask for the new Places API (v1). Required on every Details call.
# The list below aligns with the GBPProfile dataclass — anything here gets
# copied into the profile record.
DETAIL_FIELDS = (
    "id,displayName,formattedAddress,internationalPhoneNumber,nationalPhoneNumber,"
    "websiteUri,googleMapsUri,rating,userRatingCount,priceLevel,"
    "regularOpeningHours,currentOpeningHours,types,primaryType,primaryTypeDisplayName,"
    "editorialSummary,generativeSummary,reviewSummary,reviews,photos,"
    "addressComponents,businessStatus,plusCode"
)

# Field mask used by the Text Search endpoint (must end with places.*).
SEARCH_FIELDS = (
    "places.id,places.displayName,places.formattedAddress,places.types,"
    "places.primaryType,places.primaryTypeDisplayName,places.rating,"
    "places.userRatingCount,places.businessStatus"
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class GBPProfile:
    """A normalized Google Business Profile record."""

    place_id: Optional[str] = None
    name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    google_maps_url: Optional[str] = None

    # Category info
    primary_category: Optional[str] = None
    primary_category_display: Optional[str] = None
    categories: list[str] = field(default_factory=list)

    # Ratings
    rating: Optional[float] = None
    total_reviews: Optional[int] = None
    review_summary: Optional[str] = None
    reviews: list[dict] = field(default_factory=list)

    # Hours
    hours: list[str] = field(default_factory=list)  # human-readable lines
    open_now: Optional[bool] = None

    # Description / summaries
    editorial_summary: Optional[str] = None
    generative_summary: Optional[str] = None

    # Photos
    photo_count: Optional[int] = None
    photo_references: list[str] = field(default_factory=list)

    # Status
    business_status: Optional[str] = None

    # Raw response for callers that want more
    raw: dict = field(default_factory=dict)
    source: str = "places_api"  # or "scrape"


# ---------------------------------------------------------------------------
# Places API path (preferred)
# ---------------------------------------------------------------------------


class PlacesAPIError(RuntimeError):
    """Raised when the Places API returns an error status."""


def _check_places_response(payload: dict) -> dict:
    """The new Places API (v1) returns errors inside the JSON body."""
    if "error" in payload:
        err = payload["error"]
        raise PlacesAPIError(
            f"Places API error code={err.get('code')!r}: {err.get('message')} "
            f"(status={err.get('status')!r})"
        )
    return payload


def textsearch(query: str, api_key: str, region: Optional[str] = None) -> list[dict]:
    """Run a Places text search and return the candidate results.

    The new Places API uses POST + JSON body and an X-Goog-Api-Key header.
    A field mask (X-Goog-FieldMask) is required.
    """
    body: dict[str, Any] = {"textQuery": query, "maxResultCount": 5}
    if region:
        body["regionCode"] = region.upper()  # e.g. "IN" for India

    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": SEARCH_FIELDS,
        "Content-Type": "application/json",
    }
    resp = requests.post(
        PLACES_TEXTSEARCH_URL, headers=headers, json=body, timeout=30
    )
    resp.raise_for_status()
    payload = _check_places_response(resp.json())
    return payload.get("places", [])


def place_details(place_id: str, api_key: str) -> dict:
    """Fetch full details for a place_id using the new Places API (v1)."""
    url = f"{PLACES_DETAILS_URL_BASE}/{place_id}"
    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": DETAIL_FIELDS,
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return _check_places_response(resp.json())


def _format_opening_hours(opening_hours: dict) -> list[str]:
    """Turn the new API's weekdayDescriptions into simple lines.

    New API shape:
        {"weekdayDescriptions": ["Monday: 9:00 AM – 6:00 PM", ...]}
    """
    return list(opening_hours.get("weekdayDescriptions", []) or [])


def _parse_address_components(components: list[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for c in components or []:
        long_text = (c.get("longText") or c.get("long_name") or "")
        for t in c.get("types", []):
            out.setdefault(t, long_text)
    return out


def _localized_text(field: Any) -> Optional[str]:
    """Extract the .text from a LocalizedText object (or pass through a string)."""
    if field is None:
        return None
    if isinstance(field, dict):
        return field.get("text")
    return str(field)


def build_profile_from_details(detail: dict, source: str = "places_api") -> GBPProfile:
    """Convert a new-API (v1) Place Details payload into a GBPProfile."""
    opening_hours = detail.get("regularOpeningHours") or {}
    current_opening_hours = detail.get("currentOpeningHours") or {}
    address_components = detail.get("addressComponents") or []

    types = detail.get("types", []) or []
    primary_category = detail.get("primaryType") or (types[0] if types else None)

    photos = detail.get("photos", []) or []
    # New API uses `name` (a resource path) on each photo, not photo_reference.
    photo_refs = [p.get("name") for p in photos if p.get("name")]

    reviews_raw = detail.get("reviews", []) or []
    reviews = []
    for r in reviews_raw:
        # `publishTime` is RFC 3339; we just keep it as a string for now.
        publish_time = r.get("publishTime") or r.get("relativePublishTimeDescription")
        reviews.append(
            {
                "author": _localized_text(r.get("authorAttribution", {}).get("displayName"))
                or r.get("author_name"),
                "rating": r.get("rating"),
                "text": _localized_text(r.get("text")),
                "time": publish_time,
                "relative_time": r.get("relativePublishTimeDescription"),
                "language": r.get("text", {}).get("languageCode") if isinstance(r.get("text"), dict) else None,
            }
        )

    editorial = detail.get("editorialSummary")
    generative = detail.get("generativeSummary")
    review_summary = detail.get("reviewSummary")

    profile = GBPProfile(
        place_id=detail.get("id"),
        name=_localized_text(detail.get("displayName")),
        address=detail.get("formattedAddress"),
        phone=detail.get("internationalPhoneNumber") or detail.get("nationalPhoneNumber"),
        website=detail.get("websiteUri"),
        google_maps_url=detail.get("googleMapsUri"),
        primary_category=primary_category,
        primary_category_display=_localized_text(detail.get("primaryTypeDisplayName")),
        categories=types,
        rating=detail.get("rating"),
        total_reviews=detail.get("userRatingCount"),
        review_summary=_localized_text(review_summary) if isinstance(review_summary, dict) else review_summary,
        reviews=reviews,
        hours=_format_opening_hours(opening_hours) or _format_opening_hours(current_opening_hours),
        open_now=None,  # not exposed by the new API; parse from currentOpeningHours if needed
        editorial_summary=_localized_text(editorial),
        generative_summary=_localized_text(generative),
        photo_count=len(photos),
        photo_references=photo_refs[:10],  # cap — full list is in raw
        business_status=detail.get("businessStatus"),
        raw=detail,
        source=source,
    )
    return profile


def lookup_via_places_api(
    query: str, api_key: str, region: Optional[str] = None
) -> list[GBPProfile]:
    """Search + fetch details. Returns one profile per candidate match."""
    candidates = textsearch(query, api_key, region=region)
    profiles: list[GBPProfile] = []
    for i, c in enumerate(candidates):
        # New API uses `id`; legacy used `place_id`. Accept both.
        place_id = c.get("id") or c.get("place_id")
        if not place_id:
            continue
        # Be polite to the API — it's billed per call.
        if i > 0:
            time.sleep(0.2)
        detail = place_details(place_id, api_key)
        profiles.append(build_profile_from_details(detail))
    return profiles


def search_candidates(
    query: str, api_key: str, region: Optional[str] = None
) -> list[dict]:
    """Lightweight search: returns the raw candidate dicts (no Details call).

    Used by the interactive picker so we can list candidates without
    paying for a Details call on each one until the user picks.
    """
    return textsearch(query, api_key, region=region)


# ---------------------------------------------------------------------------
# Scraping fallback (Playwright) — used when no API key, or for fields the
# Places API doesn't expose (e.g. full Q&A, every photo, all reviews).
# ---------------------------------------------------------------------------


def _scrape_with_playwright(query: str, headless: bool = True) -> list[GBPProfile]:
    """Best-effort scraping via a real browser.

    NOTE: Scraping Google Search / Maps violates Google's ToS and will get
    blocked quickly without residential proxies and fingerprint randomization.
    Use this only as a last resort for personal testing.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "Playwright is not installed. Run: pip install playwright && "
            "python -m playwright install chromium"
        ) from e

    # Embed the query into a Google search URL that targets the Knowledge Panel
    # / business profile side-block, which is where Google surfaces GBP info
    # for branded queries.
    search_url = (
        "https://www.google.com/search?hl=en&q="
        + urllib.parse.quote_plus(query)
        + "&ibp=gwp;0;7"
    )

    profiles: list[GBPProfile] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

        # Try to coax the consent screen out of the way.
        try:
            page.click("text=Accept all", timeout=3000)
        except Exception:
            pass

        page.wait_for_timeout(2000)

        # Pull whatever text is in the side panel / knowledge panel.
        panel = page.query_selector("[data-attrid='kc:/local:side panel']") or page
        text = panel.inner_text(timeout=5000) if panel else ""

        # Heuristic extraction — Google's DOM is unstable, so we lean on text.
        profile = GBPProfile(
            name=query,
            address=_first_match(
                text,
                r"Address\s*\n([^\n]+)",
            ),
            phone=_first_match(text, r"(\+?\d[\d\s().-]{7,})"),
            website=_first_match(text, r"Website\s*\n([^\n]+)"),
            rating=_safe_float(_first_match(text, r"(\d\.\d)\s*★")),
            total_reviews=_safe_int(
                re.search(r"(\d[\d,]*)\s*(?:reviews?|Google reviews?)", text, re.I).group(1)
                if re.search(r"(\d[\d,]*)\s*(?:reviews?|Google reviews?)", text, re.I)
                else None
            ),
            hours=_extract_section(text, "Hours"),
            source="scrape",
            raw={"panel_text": text, "url": search_url},
        )
        profiles.append(profile)

        context.close()
        browser.close()

    return profiles


def _first_match(text: str, pattern: str) -> Optional[str]:
    m = re.search(pattern, text)
    return m.group(1).strip() if m else None


def _safe_float(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _safe_int(s: Optional[str]) -> Optional[int]:
    if not s:
        return None
    try:
        return int(s.replace(",", ""))
    except ValueError:
        return None


def _extract_section(text: str, header: str) -> list[str]:
    """Pull the lines under a 'Header\nline1\nline2' block."""
    lines = text.splitlines()
    out: list[str] = []
    capture = False
    for line in lines:
        s = line.strip()
        if capture:
            if not s:
                break
            out.append(s)
            if len(out) >= 12:
                break
        elif s.lower().startswith(header.lower()):
            capture = True
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_profile(p: GBPProfile) -> None:
    bar = "─" * 60
    print(f"\n{bar}")
    print(f"  {p.name}")
    print(bar)
    print(f"  Address     : {p.address or '-'}")
    print(f"  Phone       : {p.phone or '-'}")
    print(f"  Website     : {p.website or '-'}")
    print(f"  Maps URL    : {p.google_maps_url or '-'}")
    if p.primary_category_display or p.primary_category:
        print(
            f"  Category    : {p.primary_category_display or p.primary_category}"
            + (f"  ({', '.join(p.categories[:5])})" if p.categories else "")
        )
    if p.rating is not None:
        print(
            f"  Rating      : {p.rating} ★  ({p.total_reviews or 0} reviews)"
        )
    if p.business_status:
        print(f"  Status      : {p.business_status}")
    if p.editorial_summary:
        print(f"  Summary     : {p.editorial_summary}")
    if p.review_summary:
        print(f"  AI summary  : {p.review_summary}")
    if p.hours:
        print("  Hours       :")
        for line in p.hours[:8]:
            print(f"      {line}")
    if p.reviews:
        print(f"  Top reviews ({len(p.reviews)} returned):")
        for r in p.reviews[:3]:
            author = r.get("author") or "Anonymous"
            rating = r.get("rating")
            body = (r.get("text") or "").strip().replace("\n", " ")
            if len(body) > 200:
                body = body[:197] + "..."
            print(f"      {author} ({rating}★): {body}")
    if p.photo_count is not None:
        print(f"  Photos      : {p.photo_count} available")
    print(f"  Source      : {p.source}")
    print(bar)


def _print_summary(p: GBPProfile) -> None:
    """Compact one-screen summary — used after the user picks a business."""
    cat = p.primary_category_display or p.primary_category or "-"
    rating = (
        f"{p.rating}★ ({p.total_reviews or 0} reviews)"
        if p.rating is not None
        else "-"
    )
    summary = p.editorial_summary or p.generative_summary or "-"
    if len(summary) > 220:
        summary = summary[:217] + "..."

    print()
    print(f"  ✓ Selected: {p.name}")
    print(f"    Category    : {cat}")
    print(f"    Address     : {p.address or '-'}")
    print(f"    Phone       : {p.phone or '-'}")
    print(f"    Website     : {p.website or '-'}")
    print(f"    Rating      : {rating}")
    print(f"    Photos      : {p.photo_count if p.photo_count is not None else '-'}")
    print(f"    Status      : {p.business_status or '-'}")
    print(f"    Summary     : {summary}")
    print(f"    Place ID    : {p.place_id}")


def _candidate_label(c: dict) -> str:
    """Render a candidate dict as a one-line menu entry."""
    name = (c.get("displayName") or {}).get("text", "?")
    addr = c.get("formattedAddress") or ""
    types = c.get("types") or []
    primary = _localized_text(c.get("primaryTypeDisplayName")) or (
        (c.get("primaryType") or types[0]) if types else ""
    )
    rating = c.get("rating")
    reviews = c.get("userRatingCount")

    line = f"{name}"
    if primary:
        line += f"  ({primary})"
    if addr:
        # Last segment of the address — usually the city
        short = addr.split(",")[-2].strip() if "," in addr else addr
        line += f"  — {short}"
    if rating is not None:
        line += f"  [{rating}★ · {reviews or 0} reviews]"
    return line


def _pick_candidate_interactive(
    candidates: list[dict], query: str
) -> Optional[int]:
    """Show a numbered menu and return the chosen index, or None to skip.

    Single-candidate fast path: auto-pick without prompting.
    Empty list: return None.
    """
    if not candidates:
        return None
    if len(candidates) == 1:
        print("  (only 1 match — auto-selected)")
        return 0

    print(f"  Found {len(candidates)} candidates for '{query}':")
    for i, c in enumerate(candidates, start=1):
        print(f"    {i}) {_candidate_label(c)}")
    print("    s) Skip this query")

    while True:
        try:
            raw = input("    Pick one (1-%d) or 's': " % len(candidates)).strip().lower()
        except EOFError:
            return None
        if raw in {"s", "skip", "q", "quit"}:
            return None
        if raw.isdigit():
            n = int(raw)
            if 1 <= n <= len(candidates):
                return n - 1
        print(f"    ! Please enter a number between 1 and {len(candidates)}, or 's'.")


def _write_json(profiles: list[GBPProfile], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump([asdict(p) for p in profiles], f, indent=2, ensure_ascii=False)


def _write_csv(profiles: list[GBPProfile], path: str) -> None:
    flat_fields = [
        "place_id",
        "name",
        "address",
        "phone",
        "website",
        "google_maps_url",
        "primary_category",
        "primary_category_display",
        "rating",
        "total_reviews",
        "business_status",
        "photo_count",
        "source",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=flat_fields)
        w.writeheader()
        for p in profiles:
            row = {k: getattr(p, k) for k in flat_fields}
            row["categories"] = "; ".join(p.categories)
            w.writerow(row)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Look up Google Business Profile data for a query."
    )
    parser.add_argument("query", nargs="?", help="Business name / search query")
    parser.add_argument("--file", help="File with one query per line")
    parser.add_argument(
        "--out-dir",
        metavar="DIR",
        default=".",
        help="Directory to write per-query JSON files into (default: current)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Skip the automatic per-query JSON save",
    )
    parser.add_argument(
        "--csv", metavar="PATH", help="Write a flattened CSV summary of all picks to PATH"
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Print the full detailed profile (default: compact summary)",
    )
    parser.add_argument(
        "--score",
        action="store_true",
        help="Print the SEO completeness score + prioritized gap list "
        "after each pick (uses seo_scorer.py).",
    )
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help="Save a dated snapshot for each pick (uses seo_snapshots.py).",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="After saving a snapshot, print the week-over-week diff "
        "(requires --snapshot; only meaningful after a second run).",
    )
    parser.add_argument(
        "--suggest",
        action="store_true",
        help="Use GitHub Models to suggest an improved description, "
        "missing services, and review themes (uses seo_suggest.py).",
    )
    parser.add_argument(
        "--scrape",
        action="store_true",
        help="Force the Playwright scraping path even if an API key exists",
    )
    parser.add_argument(
        "--region", help="Bias results to a region code (e.g. 'in', 'uk')"
    )

    args = parser.parse_args(argv)

    queries: list[str] = []
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            queries = [line.strip() for line in f if line.strip()]
    elif args.query:
        queries = [args.query]
    else:
        parser.print_help()
        return 2

    api_key = os.environ.get("GOOGLE_PLACES_API_KEY")
    use_api = bool(api_key) and not args.scrape

    out_dir = Path(args.out_dir)
    if not args.no_save:
        out_dir.mkdir(parents=True, exist_ok=True)

    all_profiles: list[GBPProfile] = []
    for q in queries:
        print(f"\n>>> Looking up: {q}")

        # Step 1: search only (no Details calls yet)
        try:
            if use_api:
                if not api_key:
                    print(
                        "  ! GOOGLE_PLACES_API_KEY is not set in the environment.",
                        file=sys.stderr,
                    )
                    candidates = []
                else:
                    candidates = search_candidates(q, api_key, region=args.region)
            else:
                # Scraping fallback returns full profiles directly
                scrape_profiles = _scrape_with_playwright(q)
                if scrape_profiles:
                    all_profiles.extend(scrape_profiles)
                    if not args.no_save:
                        path = out_dir / f"{_safe_filename(q)}.json"
                        _write_json(scrape_profiles, str(path))
                        print(f"  → Saved {path}")
                continue
        except PlacesAPIError as e:
            print(f"  ! Places API error: {e}", file=sys.stderr)
            candidates = []
        except requests.RequestException as e:
            print(f"  ! Network error: {e}", file=sys.stderr)
            candidates = []

        if not candidates:
            print("  (no results)")
            continue

        # Step 2: user picks one
        chosen_idx = _pick_candidate_interactive(candidates, q)
        if chosen_idx is None:
            print("  (skipped)")
            continue

        chosen = candidates[chosen_idx]
        place_id = chosen.get("id") or chosen.get("place_id")
        if not place_id:
            print("  ! Selected candidate has no place_id; skipping.")
            continue

        # Step 3: fetch full details for the chosen one
        try:
            detail = place_details(place_id, api_key)
            profile = build_profile_from_details(detail)
        except PlacesAPIError as e:
            print(f"  ! Places API error fetching details: {e}", file=sys.stderr)
            continue
        except requests.RequestException as e:
            print(f"  ! Network error fetching details: {e}", file=sys.stderr)
            continue

        # Step 4: print compact summary (or full) + auto-save JSON
        if args.full:
            _print_profile(profile)
        else:
            _print_summary(profile)

        all_profiles.append(profile)
        if not args.no_save:
            path = out_dir / f"{_safe_filename(q)}_{place_id[:8]}.json"
            _write_json([profile], str(path))
            print(f"  → Saved {path}")

        if args.score:
            try:
                from seo_scorer import score_profile
                report = score_profile(profile)
                print(report.summary())
            except Exception as e:
                print(f"  ! Scorer error: {e}", file=sys.stderr)

        if args.snapshot:
            try:
                from seo_snapshots import save_snapshot, latest_two, diff_snapshots
                snap_path = save_snapshot(profile)
                print(f"  → Snapshotted {snap_path.name}")
                if args.diff:
                    prev, curr = latest_two(place_id)
                    if prev and curr and prev != curr:
                        print()
                        print(diff_snapshots(prev, curr))
                    else:
                        print("  (no previous snapshot to diff against)")
            except Exception as e:
                print(f"  ! Snapshot error: {e}", file=sys.stderr)

        if args.suggest:
            try:
                from seo_suggest import suggest_for_profile
                suggest_for_profile(profile)
            except Exception as e:
                print(f"  ! Suggest error: {e}", file=sys.stderr)

    if args.csv and all_profiles:
        _write_csv(all_profiles, args.csv)
        print(f"\nWrote CSV summary of {len(all_profiles)} profiles to {args.csv}")

    return 0


def _safe_filename(s: str) -> str:
    """Make a string safe to use as a filename."""
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("._-")
    return s or "query"


if __name__ == "__main__":
    raise SystemExit(main())