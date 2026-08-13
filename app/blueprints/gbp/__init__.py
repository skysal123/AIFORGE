"""GBP Report & SEO blueprint.

Reuses the project's existing SEO_analyser.py and gbp_lookup.py modules
*live* by default:

* Search and Place Details come from the Google Places API (v1) when
  ``GOOGLE_PLACES_API_KEY`` is set in the environment / .env file.
* The SEO/GBP analysis is produced by Gemini when ``GEMINI_API_KEY`` is set.

If a key is missing or a live call fails, the route handlers render an
explicit error message. The local ``sample_json.json`` is reserved as a
dev/offline fallback only — it is not used as a transparent shadow of
the live data.
"""
from pathlib import Path

try:
    from dotenv import load_dotenv

    # Project root sits three parents above this file:
    #   app/blueprints/gbp/__init__.py
    #   parents[0] -> app/blueprints/gbp
    #   parents[1] -> app/blueprints
    #   parents[2] -> app
    #   parents[3] -> <project root>  (= C:\AIForge Technologies)
    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
except ImportError:
    pass  # python-dotenv not installed; rely on actual env vars

from flask import Blueprint

gbp_bp = Blueprint("gbp", __name__, url_prefix="/gbp-report")

from . import routes  # noqa: E402,F401
